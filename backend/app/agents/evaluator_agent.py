import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from backend.app.database import db_session
from backend.app.models.rubric import RubricResponse
from backend.app.models.evaluation import EvaluationResultResponse
from backend.app.services.evaluation_engine import EvaluationEngine
from backend.app.services.excel_service import ExcelService
from backend.app.services.audit_service import AuditService

class EvaluationAgent:
    """
    Agent 3: Local LLM Correction & Code Sandbox Specialist.
    Responsible for:
    - Multi-criteria rubric matching against student submissions.
    - Local LLM inference for descriptive/theoretical questions without cloud leakage.
    - Isolated compilation and sandboxed testing for C/C++/Python code.
    - Partial marks computation and criterion-level constructive feedback.
    - Consolidated marks synchronization in the classroom's dedicated Excel workbook.
    """

    @classmethod
    def evaluate_submission(
        cls,
        run_id: str,
        course_id: str,
        assignment_id: str,
        student_id: str,
        student_name: str,
        submission_id: str,
        state: str,
        is_late: bool,
        attachments: list,
        extracted_content,
        rubric: RubricResponse,
        existing_flags: Optional[List[str]] = None
    ) -> EvaluationResultResponse:
        """Evaluates a single student submission against the rubric."""
        return EvaluationEngine.evaluate_submission(
            run_id=run_id,
            course_id=course_id,
            assignment_id=assignment_id,
            student_id=student_id,
            student_name=student_name,
            submission_id=submission_id,
            state=state,
            is_late=is_late,
            attachments=attachments,
            extracted_content=extracted_content,
            rubric=rubric,
            existing_flags=existing_flags
        )

    @classmethod
    def evaluate_course_assignment(
        cls,
        course_id: str,
        assignment_id: str,
        rubric: RubricResponse,
        evaluated_results: List[EvaluationResultResponse],
        run_id: str
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Consolidates evaluation results into the database and the classroom's Excel workbook.
        Preserves existing marks in other columns.
        Returns (versioned_workbook_path, detailed_report_path).
        """
        now_str = datetime.now().isoformat()

        with db_session() as conn:
            course = conn.execute("SELECT name, excel_workbook_path FROM courses WHERE id = ?", (course_id,)).fetchone()
            assign = conn.execute("SELECT title FROM assignments WHERE id = ?", (assignment_id,)).fetchone()

            if not course or not assign:
                raise ValueError(f"Course {course_id} or Assignment {assignment_id} not found in database.")

            course_name = course["name"]
            assign_title = assign["title"]
            wb_path = Path(course["excel_workbook_path"]) if course["excel_workbook_path"] else ExcelService.get_classroom_workbook_path(course_id, course_name, "General")

            # 1. Save all evaluation results to DB
            for res in evaluated_results:
                conn.execute(
                    """
                    INSERT INTO evaluation_results (
                        id, run_id, course_id, assignment_id, student_id,
                        raw_score, late_penalty, final_score, faculty_adjusted_score,
                        faculty_approved, faculty_remarks, criteria_breakdown_json,
                        flags_json, overall_feedback, evaluated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, student_id) DO UPDATE SET
                        final_score = excluded.final_score,
                        faculty_adjusted_score = excluded.faculty_adjusted_score,
                        faculty_approved = excluded.faculty_approved,
                        faculty_remarks = excluded.faculty_remarks,
                        criteria_breakdown_json = excluded.criteria_breakdown_json,
                        flags_json = excluded.flags_json,
                        overall_feedback = excluded.overall_feedback,
                        evaluated_at = excluded.evaluated_at
                    """,
                    (
                        res.id, run_id, course_id, assignment_id, res.student_id,
                        res.raw_score, res.late_penalty, res.final_score, res.faculty_adjusted_score,
                        1 if res.faculty_approved else 0, res.faculty_remarks,
                        json.dumps([c.model_dump() for c in res.criteria_breakdown]),
                        json.dumps(res.flags), res.overall_feedback, now_str
                    )
                )

            # 2. Update evaluation run status
            conn.execute(
                """
                UPDATE evaluation_runs
                SET status = 'COMPLETED', completed_at = ?, total_evaluated = ?
                WHERE id = ?
                """,
                (now_str, len(evaluated_results), run_id)
            )

            # 3. Update assignment status
            conn.execute("UPDATE assignments SET status = 'EVALUATED' WHERE id = ?", (assignment_id,))

        # 4. Map target column and update Excel workbook
        available_headers = ExcelService.inspect_workbook_columns(wb_path)
        target_col = ExcelService.map_assignment_to_column(assign_title, available_headers)
        if not target_col:
            target_col = ExcelService.get_short_column_header(assign_title)

        versioned_wb, detail_wb = ExcelService.update_consolidated_workbook(
            master_workbook_path=wb_path,
            course_name=course_name,
            assignment_title=assign_title,
            target_column_name=target_col,
            evaluation_results=evaluated_results,
            run_id=run_id
        )

        AuditService.log_event(
            "EVALUATION_AGENT_COMPLETED",
            course_id=course_id,
            assignment_id=assignment_id,
            details={
                "run_id": run_id,
                "evaluated_count": len(evaluated_results),
                "workbook": str(wb_path),
                "target_column": target_col
            }
        )

        return versioned_wb, detail_wb

