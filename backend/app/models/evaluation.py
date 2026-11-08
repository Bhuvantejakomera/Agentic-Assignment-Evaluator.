from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class CriterionEvaluationResult(BaseModel):
    criterion_id: str
    criterion_name: str
    max_marks: float
    awarded_marks: float
    status: str  # completed, partial, missing, incorrect
    explanation: str
    evidence: Optional[str] = None
    flags: List[str] = Field(default_factory=list)

class CodeTestExecutionResult(BaseModel):
    language: str
    compilation_success: bool
    compilation_error: Optional[str] = None
    tests_passed: int = 0
    tests_total: int = 0
    test_details: List[Dict[str, Any]] = Field(default_factory=list)
    execution_time_ms: float = 0.0

class EvaluationResultResponse(BaseModel):
    id: str
    run_id: str
    course_id: str
    assignment_id: str
    student_id: str
    student_name: str
    raw_score: float
    late_penalty: float
    duplicate_penalty: float = 0.0
    duplicate_of: Optional[str] = None
    final_score: float
    faculty_adjusted_score: Optional[float] = None
    faculty_approved: bool = False
    faculty_remarks: Optional[str] = None
    criteria_breakdown: List[CriterionEvaluationResult]
    code_execution_results: Optional[CodeTestExecutionResult] = None
    flags: List[str] = Field(default_factory=list)
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    overall_feedback: str
    evaluated_at: str
    approved_at: Optional[str] = None

class EvaluationAdjustRequest(BaseModel):
    faculty_adjusted_score: Optional[float] = None
    faculty_remarks: Optional[str] = None
    faculty_approved: bool = True
    criteria_adjustments: Optional[List[Dict[str, Any]]] = None

class BatchApproveRequest(BaseModel):
    course_id: str
    assignment_id: str
    student_ids: Optional[List[str]] = None  # None means approve all

class PublishRequest(BaseModel):
    course_id: str
    assignment_id: str
    return_submissions: bool = False
    faculty_confirmation: bool = False

class PublishResponse(BaseModel):
    success: bool
    total_published: int
    published_grades: List[Dict[str, Any]]
    message: str
    timestamp: str

