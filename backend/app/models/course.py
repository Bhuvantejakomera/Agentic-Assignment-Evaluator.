from pydantic import BaseModel, Field
from typing import Optional, List

class CourseBase(BaseModel):
    id: str
    name: str
    section: str
    description: Optional[str] = None
    room: Optional[str] = None
    status: str = "ACTIVE"
    enrolled_count: int = 0
    assignments_count: int = 0
    excel_workbook_path: Optional[str] = None
    last_sync_time: Optional[str] = None

class CourseCreate(CourseBase):
    faculty_id: str

class CourseResponse(CourseBase):
    faculty_id: str
    created_at: str

class ClassroomListResponse(BaseModel):
    faculty_id: str
    faculty_name: str
    faculty_email: str
    courses: List[CourseResponse]

