from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class SubmissionAttachment(BaseModel):
    filename: str
    file_type: str  # PDF, DOCX, HTML, C, CPP, PY, UNKNOWN
    file_path: Optional[str] = None
    file_id: Optional[str] = None
    link: Optional[str] = None
    file_size_bytes: int = 0
    is_readable: bool = True
    error_message: Optional[str] = None

class ExtractedContentModel(BaseModel):
    text_content: str = ""
    code_snippets: List[Dict[str, Any]] = Field(default_factory=list)  # [{"language": "c", "code": "...", ...}]
    diagram_flowchart_descriptions: List[str] = Field(default_factory=list)
    word_count: int = 0
    extraction_warnings: List[str] = Field(default_factory=list)

class SubmissionResponse(BaseModel):
    id: str
    course_id: str
    assignment_id: str
    student_id: str
    student_name: str
    submission_time: Optional[str] = None
    is_late: bool = False
    state: str = "TURNED_IN"
    attachments: List[SubmissionAttachment] = Field(default_factory=list)
    submission_flags: List[str] = Field(default_factory=list)

