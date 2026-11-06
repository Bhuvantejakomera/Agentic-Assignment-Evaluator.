import json
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from backend.app.config import SUBMISSIONS_DIR
from backend.app.database import db_session
from backend.app.models.rubric import RubricResponse, CriterionModel
from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel
from backend.app.models.evaluation import (
    EvaluationResultResponse,
    CriterionEvaluationResult,
    CodeTestExecutionResult,
    EvaluationAdjustRequest,
    BatchApproveRequest
)
from googleapiclient.discovery import build
from backend.app.agents.submission_agent import SubmissionAgent
from backend.app.agents.evaluator_agent import EvaluationAgent
from backend.app.services.classroom_service import ClassroomService
from backend.app.services.document_extractor import DocumentExtractor
from backend.app.services.google_oauth_service import GoogleOAuthService
from backend.app.services.evaluation_engine import EvaluationEngine
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/api/classrooms/{course_id}/assignments/{assignment_id}", tags=["Evaluation"])

@router.post("/evaluate")
def start_evaluation(course_id: str, assignment_id: str):
    """
    Evaluates all student submissions for the specified course and assignment.
    Requires an approved rubric.
    """
    now_str = datetime.now().isoformat()
    with db_session() as conn:
        # Check assignment exists
        assign = conn.execute(
            "SELECT * FROM assignments WHERE course_id = ? AND id = ?",
            (course_id, assignment_id)
        ).fetchone()
        if not assign:
            raise HTTPException(status_code=404, detail="Assignment not found.")

        # Check approved rubric
        rub_row = conn.execute(
            "SELECT * FROM rubrics WHERE course_id = ? AND assignment_id = ? AND status = 'APPROVED' ORDER BY version DESC LIMIT 1",
            (course_id, assignment_id)
        ).fetchone()

        if not rub_row:
            # Check if draft rubric exists
            draft_rub = conn.execute(
                "SELECT * FROM rubrics WHERE course_id = ? AND assignment_id = ? ORDER BY version DESC LIMIT 1",
                (course_id, assignment_id)
            ).fetchone()
            if draft_rub:
                raise HTTPException(status_code=400, detail="Rubric has not been approved yet. Please review and approve the rubric before starting evaluation.")
            else:
                raise HTTPException(status_code=400, detail="No rubric configured for this assignment. Please prepare a rubric first.")

        guidance = rub_row["custom_guidance"] if "custom_guidance" in rub_row.keys() else None
        rubric = RubricResponse(
            id=rub_row["id"],
            course_id=rub_row["course_id"],
            assignment_id=rub_row["assignment_id"],
            version=rub_row["version"],
            status=rub_row["status"],
            criteria=[CriterionModel(**c) for c in json.loads(rub_row["criteria_json"])],
            total_max_marks=rub_row["total_max_marks"],
            late_penalty_percent=rub_row["late_penalty_percent"],
            custom_guidance=guidance,
            created_at=rub_row["created_at"],
            approved_at=rub_row["approved_at"]
        )

        # Retrieve enrolled students and their submissions
        sub_rows = conn.execute(
            """
            SELECT s.id as sub_id, s.student_id, st.name as student_name, s.is_late, s.state,
                   s.attachments_json, s.extracted_content_json, s.submission_flags_json
            FROM course_enrollments ce
            JOIN students st ON ce.student_id = st.id
            LEFT JOIN submissions s ON s.course_id = ce.course_id AND s.assignment_id = ? AND s.student_id = ce.student_id
            WHERE ce.course_id = ?
            ORDER BY st.name ASC
            """,
            (assignment_id, course_id)
        ).fetchall()

        if not sub_rows:
            raise HTTPException(status_code=400, detail="No enrolled students or submissions found for this course.")

        # Initialize Drive service for authorized secure downloads if authenticated
        creds = GoogleOAuthService.get_credentials(ClassroomService.DEFAULT_FACULTY_ID)
        drive_service = build("drive", "v3", credentials=creds) if creds else None

        # Create evaluation run
        run_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO evaluation_runs (id, course_id, assignment_id, rubric_id, started_at, status, total_evaluated)
            VALUES (?, ?, ?, ?, ?, 'RUNNING', 0)
            """,
            (run_id, course_id, assignment_id, rubric.id, now_str)
        )

    # Perform evaluation loop outside the database transaction to prevent locking
    evaluated_list = []
    for row in sub_rows:
        sid = row["student_id"]
        sname = row["student_name"]
        sub_id = row["sub_id"] or f"sub-missing-{sid}"
        is_late = bool(row["is_late"]) if row["is_late"] is not None else False
        state = row["state"] or "MISSING"
        
        existing_sub_flags = []
        if row["submission_flags_json"]:
            try:
                existing_sub_flags = json.loads(row["submission_flags_json"])
            except Exception:
                pass

        attachments = []
        if row["attachments_json"]:
            try:
                att_data = json.loads(row["attachments_json"])
                attachments = [SubmissionAttachment(**a) for a in att_data]
            except Exception:
                pass

        if not attachments:
            state = "MISSING"
            if "MISSING" not in existing_sub_flags:
                existing_sub_flags.append("MISSING")

        extracted = ExtractedContentModel()
        if row["extracted_content_json"]:
            try:
                ext_data = json.loads(row["extracted_content_json"])
                extracted = ExtractedContentModel(**ext_data)
            except Exception:
                pass

        # SubmissionAgent securely downloads and extracts files if not already cached
        triage_flags = []
        if not extracted.text_content and attachments:
            extracted, triage_flags = SubmissionAgent.prepare_and_extract_submission(
                course_id=course_id,
                assignment_id=assignment_id,
                student_id=sid,
                attachments=attachments,
                drive_service=drive_service
            )

        all_flags = list(set(triage_flags + existing_sub_flags))

        eval_res = EvaluationEngine.evaluate_submission(
            run_id=run_id,
            course_id=course_id,
            assignment_id=assignment_id,
            student_id=sid,
            student_name=sname,
            submission_id=sub_id,
            state=state,
            is_late=is_late,
            attachments=attachments,
            extracted_content=extracted,
            rubric=rubric,
            assignment_title=assign["title"],
            assignment_description=assign["description"] or "",
            existing_flags=all_flags
        )

        evaluated_list.append(eval_res)

    # Save evaluation results and update statuses in a single atomic transaction
    completed_time = datetime.now().isoformat()
    stats = {
        "total_evaluated": len(evaluated_list),
        "average_score": round(sum(e.final_score for e in evaluated_list) / len(evaluated_list), 1) if evaluated_list else 0.0,
        "late_count": sum(1 for e in evaluated_list if "LATE" in e.flags),
        "wrong_submission_count": sum(1 for e in evaluated_list if "WRONG_PDF" in e.flags),
        "incomplete_count": sum(1 for e in evaluated_list if "INCOMPLETE" in e.flags),
        "missing_count": sum(1 for e in evaluated_list if "MISSING" in e.flags)
    }

    with db_session() as conn:
        for eval_res in evaluated_list:
            code_exec_json = eval_res.code_execution_results.model_dump_json() if eval_res.code_execution_results else None
            conn.execute(
                """
                INSERT OR REPLACE INTO evaluation_results (
                    id, run_id, course_id, assignment_id, student_id, submission_id,
                    raw_score, late_penalty, final_score, faculty_adjusted_score,
                    faculty_approved, faculty_remarks, criteria_breakdown_json,
                    code_execution_results_json, flags_json, overall_feedback, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eval_res.id, run_id, course_id, assignment_id, eval_res.student_id, eval_res.submission_id if hasattr(eval_res, 'submission_id') else f"sub-{eval_res.student_id}",
                    eval_res.raw_score, eval_res.late_penalty, eval_res.final_score,
                    None, 0, eval_res.faculty_remarks,
                    json.dumps([c.model_dump() for c in eval_res.criteria_breakdown]),
                    code_exec_json, json.dumps(eval_res.flags),
                    eval_res.overall_feedback, eval_res.evaluated_at
                )
            )

        conn.execute(
            """
            UPDATE evaluation_runs 
            SET completed_at = ?, status = 'COMPLETED', total_evaluated = ?, summary_stats_json = ?
            WHERE id = ?
            """,
            (completed_time, len(evaluated_list), json.dumps(stats), run_id)
        )

        conn.execute(
            "UPDATE assignments SET status = 'EVALUATED' WHERE id = ?",
            (assignment_id,)
        )

    AuditService.log_event("EVALUATION_COMPLETED", course_id=course_id, assignment_id=assignment_id, details=stats)

    # Automatically update the marks for this assignment in the classroom's Excel sheet
    _sync_assignment_to_excel(course_id, assignment_id)

    return {
        "run_id": run_id,
        "status": "COMPLETED",
        "stats": stats,
        "message": f"Successfully evaluated {len(evaluated_list)} student submissions. Marks have been automatically updated in the classroom Excel sheet."
    }

def _sync_assignment_to_excel(course_id: str, assignment_id: str):
    """Synchronizes the evaluations for an assignment directly into the classroom Excel workbook."""
    try:
        from backend.app.services.excel_service import ExcelService
        course = ClassroomService.get_course_by_id(course_id)
        if not course:
            return
        assignments = ClassroomService.get_assignments_for_course(course_id)
        assign = next((a for a in assignments if a.id == assignment_id), None)
        if not assign:
            return
        evaluations = get_evaluations(course_id, assignment_id)
        if not evaluations:
            return

        wb_path = Path(course.excel_workbook_path) if course.excel_workbook_path else ExcelService.get_classroom_workbook_path(course.id, course.name, course.section)
        columns = ExcelService.inspect_workbook_columns(wb_path) if wb_path.exists() else []
        target_col = ExcelService.map_assignment_to_column(assign.title, columns) or ExcelService.get_short_column_header(assign.title)

        run_id = evaluations[0].run_id if evaluations else "run1"
        ExcelService.update_consolidated_workbook(
            master_workbook_path=wb_path,
            course_name=course.name,
            assignment_title=assign.title,
            target_column_name=target_col,
            evaluation_results=evaluations,
            run_id=run_id
        )
    except Exception as exc:
        import logging
        logging.error(f"Error auto-syncing Excel workbook for {course_id} / {assignment_id}: {exc}")

@router.get("/evaluations", response_model=List[EvaluationResultResponse])
def get_evaluations(course_id: str, assignment_id: str):
    """Retrieves all student evaluation results for the course and assignment."""
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT e.*, st.name as student_name, s.attachments_json
            FROM evaluation_results e
            JOIN students st ON e.student_id = st.id
            LEFT JOIN submissions s ON s.course_id = e.course_id AND s.assignment_id = e.assignment_id AND s.student_id = e.student_id
            WHERE e.course_id = ? AND e.assignment_id = ?
            ORDER BY st.name ASC
            """,
            (course_id, assignment_id)
        ).fetchall()

        results = []
        for r in rows:
            crit_breakdown = [CriterionEvaluationResult(**c) for c in json.loads(r["criteria_breakdown_json"])]
            code_res = CodeTestExecutionResult(**json.loads(r["code_execution_results_json"])) if r["code_execution_results_json"] else None
            flags = json.loads(r["flags_json"]) if r["flags_json"] else []

            att_list = []
            if "attachments_json" in r.keys() and r["attachments_json"]:
                try:
                    raw_atts = json.loads(r["attachments_json"])
                    for a in raw_atts:
                        link = a.get("link")
                        if not link and a.get("file_id"):
                            link = f"https://drive.google.com/file/d/{a['file_id']}/view?usp=drivesdk"
                        att_list.append({
                            "filename": a.get("filename", "submission"),
                            "file_type": a.get("file_type", "UNKNOWN"),
                            "file_id": a.get("file_id"),
                            "link": link
                        })
                except Exception:
                    pass

            results.append(EvaluationResultResponse(
                id=r["id"],
                run_id=r["run_id"],
                course_id=r["course_id"],
                assignment_id=r["assignment_id"],
                student_id=r["student_id"],
                student_name=r["student_name"],
                raw_score=r["raw_score"],
                late_penalty=r["late_penalty"],
                final_score=r["final_score"],
                faculty_adjusted_score=r["faculty_adjusted_score"],
                faculty_approved=bool(r["faculty_approved"]),
                faculty_remarks=r["faculty_remarks"],
                criteria_breakdown=crit_breakdown,
                code_execution_results=code_res,
                flags=flags,
                attachments=att_list,
                overall_feedback=r["overall_feedback"],
                evaluated_at=r["evaluated_at"],
                approved_at=r["approved_at"]
            ))
        return results

@router.get("/evaluations/{student_id}", response_model=EvaluationResultResponse)
def get_student_evaluation(course_id: str, assignment_id: str, student_id: str):
    with db_session() as conn:
        r = conn.execute(
            """
            SELECT e.*, st.name as student_name, s.attachments_json
            FROM evaluation_results e
            JOIN students st ON e.student_id = st.id
            LEFT JOIN submissions s ON s.course_id = e.course_id AND s.assignment_id = e.assignment_id AND s.student_id = e.student_id
            WHERE e.course_id = ? AND e.assignment_id = ? AND e.student_id = ?
            """,
            (course_id, assignment_id, student_id)
        ).fetchone()

        if not r:
            raise HTTPException(status_code=404, detail="Student evaluation record not found.")

        crit_breakdown = [CriterionEvaluationResult(**c) for c in json.loads(r["criteria_breakdown_json"])]
        code_res = CodeTestExecutionResult(**json.loads(r["code_execution_results_json"])) if r["code_execution_results_json"] else None
        flags = json.loads(r["flags_json"]) if r["flags_json"] else []

        att_list = []
        if "attachments_json" in r.keys() and r["attachments_json"]:
            try:
                raw_atts = json.loads(r["attachments_json"])
                for a in raw_atts:
                    link = a.get("link")
                    if not link and a.get("file_id"):
                        link = f"https://drive.google.com/file/d/{a['file_id']}/view?usp=drivesdk"
                    att_list.append({
                        "filename": a.get("filename", "submission"),
                        "file_type": a.get("file_type", "UNKNOWN"),
                        "file_id": a.get("file_id"),
                        "link": link
                    })
            except Exception:
                pass

        return EvaluationResultResponse(
            id=r["id"],
            run_id=r["run_id"],
            course_id=r["course_id"],
            assignment_id=r["assignment_id"],
            student_id=r["student_id"],
            student_name=r["student_name"],
            raw_score=r["raw_score"],
            late_penalty=r["late_penalty"],
            final_score=r["final_score"],
            faculty_adjusted_score=r["faculty_adjusted_score"],
            faculty_approved=bool(r["faculty_approved"]),
            faculty_remarks=r["faculty_remarks"],
            criteria_breakdown=crit_breakdown,
            code_execution_results=code_res,
            flags=flags,
            attachments=att_list,
            overall_feedback=r["overall_feedback"],
            evaluated_at=r["evaluated_at"],
            approved_at=r["approved_at"]
        )

@router.get("/submissions/{student_id}/work")
def open_student_work_redirect(course_id: str, assignment_id: str, student_id: str):
    """Direct redirect to student's work in Google Drive or returns attachment info."""
    from fastapi.responses import RedirectResponse
    with db_session() as conn:
        r = conn.execute(
            """
            SELECT attachments_json FROM submissions
            WHERE course_id = ? AND assignment_id = ? AND student_id = ?
            """,
            (course_id, assignment_id, student_id)
        ).fetchone()

        if not r or not r["attachments_json"]:
            raise HTTPException(status_code=404, detail="No submission record found for student.")

        atts = json.loads(r["attachments_json"])
        if not atts:
            raise HTTPException(status_code=404, detail="Student has not submitted any attachments.")

        first_att = atts[0]
        link = first_att.get("link")
        if not link and first_att.get("file_id"):
            link = f"https://drive.google.com/file/d/{first_att['file_id']}/view?usp=drivesdk"

        if link:
            return RedirectResponse(url=link)
        raise HTTPException(status_code=404, detail="No valid file link found for submission.")

@router.post("/evaluations/{student_id}/adjust", response_model=EvaluationResultResponse)
def adjust_student_evaluation(course_id: str, assignment_id: str, student_id: str, req: EvaluationAdjustRequest):
    """Allows faculty to adjust marks, add remarks, and approve or unapprove a student grade."""
    now_str = datetime.now().isoformat()
    with db_session() as conn:
        r = conn.execute(
            "SELECT * FROM evaluation_results WHERE course_id = ? AND assignment_id = ? AND student_id = ?",
            (course_id, assignment_id, student_id)
        ).fetchone()

        if not r:
            raise HTTPException(status_code=404, detail="Evaluation result not found.")

        # Update criteria if provided
        updated_criteria_json = r["criteria_breakdown_json"]
        if req.criteria_adjustments:
            curr_criteria = json.loads(updated_criteria_json)
            adj_map = {a["criterion_id"]: a for a in req.criteria_adjustments}
            for c in curr_criteria:
                if c["criterion_id"] in adj_map:
                    c["awarded_marks"] = adj_map[c["criterion_id"]]["awarded_marks"]
                    if "status" in adj_map[c["criterion_id"]]:
                        c["status"] = adj_map[c["criterion_id"]]["status"]
            updated_criteria_json = json.dumps(curr_criteria)

        approved_time = now_str if req.faculty_approved else None

        conn.execute(
            """
            UPDATE evaluation_results
            SET faculty_adjusted_score = ?,
                faculty_remarks = ?,
                faculty_approved = ?,
                criteria_breakdown_json = ?,
                approved_at = ?
            WHERE course_id = ? AND assignment_id = ? AND student_id = ?
            """,
            (
                req.faculty_adjusted_score,
                req.faculty_remarks,
                1 if req.faculty_approved else 0,
                updated_criteria_json,
                approved_time,
                course_id,
                assignment_id,
                student_id
            )
        )

    AuditService.log_event(
        "EVALUATION_ADJUSTED",
        course_id=course_id,
        assignment_id=assignment_id,
        details={
            "student_id": student_id,
            "faculty_adjusted_score": req.faculty_adjusted_score,
            "faculty_remarks": req.faculty_remarks,
            "approved": req.faculty_approved
        }
    )

    # Sync updated grade to Excel workbook
    _sync_assignment_to_excel(course_id, assignment_id)

    return get_student_evaluation(course_id, assignment_id, student_id)

@router.post("/batch-approve")
def batch_approve(course_id: str, assignment_id: str, req: BatchApproveRequest):
    """Batch approves all or specified student evaluations."""
    now_str = datetime.now().isoformat()
    with db_session() as conn:
        if req.student_ids:
            placeholders = ",".join("?" for _ in req.student_ids)
            params = [now_str, course_id, assignment_id] + req.student_ids
            conn.execute(
                f"""
                UPDATE evaluation_results
                SET faculty_approved = 1, approved_at = ?
                WHERE course_id = ? AND assignment_id = ? AND student_id IN ({placeholders})
                """,
                params
            )
            count = len(req.student_ids)
        else:
            res = conn.execute(
                """
                UPDATE evaluation_results
                SET faculty_approved = 1, approved_at = ?
                WHERE course_id = ? AND assignment_id = ?
                """,
                (now_str, course_id, assignment_id)
            )
            count = res.rowcount

        # Check if all approved
        unapproved = conn.execute(
            "SELECT COUNT(*) as c FROM evaluation_results WHERE course_id = ? AND assignment_id = ? AND faculty_approved = 0",
            (course_id, assignment_id)
        ).fetchone()["c"]

        if unapproved == 0:
            conn.execute("UPDATE assignments SET status = 'APPROVED' WHERE id = ?", (assignment_id,))

    AuditService.log_event("BATCH_APPROVED", course_id=course_id, assignment_id=assignment_id, details={"approved_count": count})

    # Sync approved status to Excel workbook
    _sync_assignment_to_excel(course_id, assignment_id)

    return {"approved_count": count, "all_approved": unapproved == 0}

