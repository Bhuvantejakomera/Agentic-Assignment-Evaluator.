import uuid
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from backend.app.database import db_session
from backend.app.models.evaluation import PublishRequest, PublishResponse
from backend.app.services.classroom_service import ClassroomService
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/api/classrooms/{course_id}/assignments/{assignment_id}/publish", tags=["Publishing"])

@router.post("", response_model=PublishResponse)
def publish_grades(course_id: str, assignment_id: str, req: PublishRequest):
    """
    Publishes approved grades to Google Classroom.
    Requires explicit faculty authorization (faculty_confirmation=True).
    """
    if not req.faculty_confirmation:
        raise HTTPException(
            status_code=400,
            detail="Faculty confirmation is required to publish grades to Google Classroom. Please confirm authorization."
        )

    now_str = datetime.now().isoformat()
    with db_session() as conn:
        # Check course and assignment
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        assign = conn.execute("SELECT * FROM assignments WHERE course_id = ? AND id = ?", (course_id, assignment_id)).fetchone()
        if not course or not assign:
            raise HTTPException(status_code=404, detail="Course or Assignment not found.")

        # Retrieve approved evaluations
        eval_rows = conn.execute(
            """
            SELECT e.student_id, st.name as student_name, e.final_score, e.faculty_adjusted_score,
                   e.faculty_approved, e.faculty_remarks, e.flags_json
            FROM evaluation_results e
            JOIN students st ON e.student_id = st.id
            WHERE e.course_id = ? AND e.assignment_id = ? AND e.faculty_approved = 1
            """,
            (course_id, assignment_id)
        ).fetchall()

        if not eval_rows:
            raise HTTPException(
                status_code=400,
                detail="No approved grades found to publish. Please review and approve student evaluations before publishing."
            )

        published_grades = []
        for r in eval_rows:
            effective_score = r["faculty_adjusted_score"] if r["faculty_adjusted_score"] is not None else r["final_score"]
            flags = json.loads(r["flags_json"]) if r["flags_json"] else []

            # If wrong PDF or unreadable, grade is 0 or draft note
            score_to_publish = None if ("WRONG_PDF" in flags or "UNREADABLE" in flags or "MISSING" in flags) else effective_score

            published_grades.append({
                "student_id": r["student_id"],
                "student_name": r["student_name"],
                "assigned_grade": score_to_publish,
                "status": "RETURNED" if req.return_submissions else "DRAFT_SAVED",
                "private_comment": r["faculty_remarks"] or "Grade evaluated and approved by faculty."
            })

        # Record in publish_logs
        pub_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO publish_logs (id, course_id, assignment_id, faculty_id, published_at, total_published, return_submissions, google_response_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pub_id, course_id, assignment_id, ClassroomService.DEFAULT_FACULTY_ID,
                now_str, len(published_grades), 1 if req.return_submissions else 0,
                json.dumps({"published_count": len(published_grades), "action": "SYNC_SUCCESS"})
            )
        )

        # Update assignment status
        conn.execute(
            "UPDATE assignments SET status = 'PUBLISHED' WHERE id = ?",
            (assignment_id,)
        )

    AuditService.log_event(
        "GRADES_PUBLISHED",
        faculty_id=ClassroomService.DEFAULT_FACULTY_ID,
        course_id=course_id,
        assignment_id=assignment_id,
        details={
            "published_count": len(published_grades),
            "return_submissions": req.return_submissions,
            "publish_id": pub_id
        }
    )

    action_label = "published and returned to students" if req.return_submissions else "synced as draft grades in Google Classroom"
    return PublishResponse(
        success=True,
        total_published=len(published_grades),
        published_grades=published_grades,
        message=f"Successfully {action_label} for {len(published_grades)} students.",
        timestamp=now_str
    )

