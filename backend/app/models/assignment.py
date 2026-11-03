from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class AssignmentBase(BaseModel):
    id: str
    course_id: str
    title: str
    description: Optional[str] = None
    max_points: float = 100.0
    due_date: Optional[str] = None
    materials: Optional[List[Dict[str, Any]]] = None
    submission_types: Optional[List[str]] = Field(default_factory=lambda: ["PDF", "DOCX", "C", "CPP", "PY"])
    status: str = "DRAFT"

class AssignmentCreate(AssignmentBase):
    pass

class AssignmentResponse(AssignmentBase):
    created_at: str
    total_submissions: int = 0
    evaluated_submissions: int = 0
    approved_submissions: int = 0
    has_rubric: bool = False
    rubric_id: Optional[str] = None

class AssignmentDetailResponse(AssignmentResponse):
    course_name: str
    course_section: str

