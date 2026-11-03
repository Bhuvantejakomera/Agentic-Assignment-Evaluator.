from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime
from backend.app.database import db_session
from backend.app.models.course import CourseResponse, ClassroomListResponse
from backend.app.services.classroom_service import ClassroomService
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/api/classrooms", tags=["Classrooms"])

@router.get("", response_model=ClassroomListResponse)
def list_classrooms():
    """Retrieves all classrooms associated with the faculty account."""
    ClassroomService.seed_initial_classrooms_if_empty()
    courses = ClassroomService.get_all_courses(ClassroomService.DEFAULT_FACULTY_ID)
    
    with db_session() as conn:
        fac = conn.execute(
            "SELECT name, email FROM faculty WHERE id = ?",
            (ClassroomService.DEFAULT_FACULTY_ID,)
        ).fetchone()

    return ClassroomListResponse(
        faculty_id=ClassroomService.DEFAULT_FACULTY_ID,
        faculty_name=fac["name"] if fac else ClassroomService.DEFAULT_FACULTY_NAME,
        faculty_email=fac["email"] if fac else ClassroomService.DEFAULT_FACULTY_EMAIL,
        courses=courses
    )

@router.get("/{course_id}", response_model=CourseResponse)
def get_classroom_details(course_id: str):
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Classroom with ID '{course_id}' not found.")
    return course

@router.post("/{course_id}/sync")
def sync_classroom(course_id: str):
    """Refreshes synchronization timestamp for the classroom."""
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Classroom with ID '{course_id}' not found.")

    now_str = datetime.now().isoformat()
    with db_session() as conn:
        conn.execute(
            "UPDATE courses SET last_sync_time = ? WHERE id = ?",
            (now_str, course_id)
        )
    AuditService.log_event("CLASSROOM_SYNCED", course_id=course_id)
    return {"status": "synced", "course_id": course_id, "last_sync_time": now_str}
