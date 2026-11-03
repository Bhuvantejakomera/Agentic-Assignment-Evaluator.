from fastapi import APIRouter, HTTPException
from typing import List
from backend.app.database import db_session
from backend.app.models.assignment import AssignmentResponse, AssignmentDetailResponse
from backend.app.services.classroom_service import ClassroomService

router = APIRouter(prefix="/api/classrooms/{course_id}/assignments", tags=["Assignments"])

@router.get("", response_model=List[AssignmentResponse])
def list_assignments(course_id: str):
    """Retrieves assignments strictly scoped to course_id."""
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Course '{course_id}' not found.")
    
    return ClassroomService.get_assignments_for_course(course_id)

@router.get("/{assignment_id}", response_model=AssignmentDetailResponse)
def get_assignment_detail(course_id: str, assignment_id: str):
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Course '{course_id}' not found.")

    assignments = ClassroomService.get_assignments_for_course(course_id)
    matching = next((a for a in assignments if a.id == assignment_id), None)
    if not matching:
        raise HTTPException(status_code=404, detail=f"Assignment '{assignment_id}' not found in course '{course_id}'.")

    return AssignmentDetailResponse(
        **matching.model_dump(),
        course_name=course.name,
        course_section=course.section
    )

