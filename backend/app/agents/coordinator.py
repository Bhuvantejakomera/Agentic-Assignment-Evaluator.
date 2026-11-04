from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from backend.app.agents.classroom_agent import ClassroomAgent
from backend.app.agents.submission_agent import SubmissionAgent
from backend.app.agents.evaluator_agent import EvaluationAgent
from backend.app.agents.security import SecureDriveHandler
from backend.app.services.audit_service import AuditService

class AgentCoordinator:
    """
    Coordinator / Orchestrator for the 3-Agent Architecture:
    1. ClassroomAgent: Course discovery, student roster pagination, roll-no extraction.
    2. SubmissionAgent: Coursework sync, secure Google Drive downloads, document extraction.
    3. EvaluationAgent: Local LLM rubric evaluation, C/Python sandbox testing, Excel reports.
    """

    @classmethod
    def sync_live_classroom_ecosystem(
        cls,
        classroom_service,
        drive_service,
        faculty_id: str
    ) -> Dict[str, Any]:
        """
        Executes coordinated full-sync across ClassroomAgent and SubmissionAgent:
        Step 1: ClassroomAgent syncs courses, paginates all students, parses roll numbers.
        Step 2: SubmissionAgent syncs coursework, paginates submissions, securely prepares attachments.
        """
        # Step 1: Run ClassroomAgent
        courses_list, course_student_mappings = ClassroomAgent.sync_courses_and_roster(
            classroom_service=classroom_service,
            faculty_id=faculty_id
        )

        total_assignments_synced = 0
        total_students_synced = sum(len(mapping) for mapping in course_student_mappings.values())

        # Step 2: Run SubmissionAgent for each course
        for c in courses_list:
            c_id = c["id"]
            google_to_roll = course_student_mappings.get(c_id, {})
            cw_count = SubmissionAgent.sync_coursework_and_submissions(
                classroom_service=classroom_service,
                course_id=c_id,
                google_to_roll=google_to_roll,
                drive_service=drive_service
            )
            total_assignments_synced += cw_count

        AuditService.log_event(
            "COORDINATOR_FULL_SYNC_SUCCESS",
            faculty_id=faculty_id,
            details={
                "courses_count": len(courses_list),
                "assignments_count": total_assignments_synced,
                "students_count": total_students_synced
            }
        )

        return {
            "status": "success",
            "courses_synced": len(courses_list),
            "assignments_synced": total_assignments_synced,
            "students_synced": total_students_synced,
            "message": f"Successfully synchronized {len(courses_list)} courses, {total_assignments_synced} assignments, and {total_students_synced} students with full security validation."
        }

    @classmethod
    def run_assignment_evaluation(
        cls,
        course_id: str,
        assignment_id: str,
        rubric,
        sub_rows: list,
        drive_service=None
    ) -> Tuple[str, list, Path, Path]:
        """
        Coordinates submission extraction (SubmissionAgent) and grading (EvaluationAgent).
        """
        import uuid
        run_id = str(uuid.uuid4())
        evaluated_results = []

        for row in sub_rows:
            sid = row["student_id"]
            sname = row["student_name"]
            sub_id = row["sub_id"] or f"sub-missing-{sid}"
            is_late = bool(row["is_late"]) if row["is_late"] is not None else False
            state = row["state"] or "MISSING"

            # Parse attachments
            import json
            from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel
            attachments = []
            if row["attachments_json"]:
                try:
                    att_data = json.loads(row["attachments_json"])
                    attachments = [SubmissionAttachment(**a) for a in att_data]
                except Exception:
                    pass

            # SubmissionAgent: Securely download and extract
            extracted, triage_flags = SubmissionAgent.prepare_and_extract_submission(
                course_id=course_id,
                assignment_id=assignment_id,
                student_id=sid,
                attachments=attachments,
                drive_service=drive_service
            )

            # EvaluationAgent: Run local LLM and Code Sandbox evaluation
            res = EvaluationAgent.evaluate_submission(
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
                existing_flags=triage_flags
            )
            evaluated_results.append(res)

        # Consolidate and update classroom Excel marks workbook
        versioned_wb, detail_wb = EvaluationAgent.evaluate_course_assignment(
            course_id=course_id,
            assignment_id=assignment_id,
            rubric=rubric,
            evaluated_results=evaluated_results,
            run_id=run_id
        )

        return run_id, evaluated_results, versioned_wb, detail_wb

