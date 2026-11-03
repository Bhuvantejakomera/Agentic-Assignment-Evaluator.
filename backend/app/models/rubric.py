from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class CriterionModel(BaseModel):
    id: str
    name: str
    description: str
    max_marks: float
    weight: float = 1.0
    evaluation_type: str = "descriptive"  # descriptive, code_execution, diagram_flowchart, algorithm, compliance
    partial_marking_allowed: bool = True
    penalty_rules: Optional[str] = None

class RubricBase(BaseModel):
    course_id: str
    assignment_id: str
    criteria: List[CriterionModel]
    total_max_marks: float
    late_penalty_percent: float = 20.0

class RubricCreate(RubricBase):
    pass

class RubricResponse(RubricBase):
    id: str
    version: int
    status: str  # DRAFT, APPROVED
    created_at: str
    approved_at: Optional[str] = None

class RubricGenerateRequest(BaseModel):
    course_id: str
    assignment_id: str
    custom_guidance: Optional[str] = None
