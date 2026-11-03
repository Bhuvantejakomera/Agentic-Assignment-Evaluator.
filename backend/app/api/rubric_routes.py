import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from typing import Optional, List
from backend.app.database import db_session
from backend.app.models.rubric import RubricResponse, RubricCreate, RubricGenerateRequest, CriterionModel
from backend.app.services.classroom_service import ClassroomService
from backend.app.services.llm_engine import LocalLLMEngine
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/api/classrooms/{course_id}/assignments/{assignment_id}/rubric", tags=["Rubric"])

@router.get("", response_model=Optional[RubricResponse])
def get_rubric(course_id: str, assignment_id: str):
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT * FROM rubrics 
            WHERE course_id = ? AND assignment_id = ?
            ORDER BY version DESC LIMIT 1
            """,
            (course_id, assignment_id)
        ).fetchone()

        if not row:
            return None

        criteria_list = [CriterionModel(**c) for c in json.loads(row["criteria_json"])]
        return RubricResponse(
            id=row["id"],
            course_id=row["course_id"],
            assignment_id=row["assignment_id"],
            version=row["version"],
            status=row["status"],
            criteria=criteria_list,
            total_max_marks=row["total_max_marks"],
            late_penalty_percent=row["late_penalty_percent"],
            created_at=row["created_at"],
            approved_at=row["approved_at"]
        )

@router.post("/generate", response_model=List[CriterionModel])
async def generate_rubric(course_id: str, assignment_id: str, req: Optional[RubricGenerateRequest] = None):
    """Uses Local LLM to analyze assignment deliverables and generate proposed rubric criteria."""
    with db_session() as conn:
        assign = conn.execute(
            "SELECT title, description, max_points FROM assignments WHERE course_id = ? AND id = ?",
            (course_id, assignment_id)
        ).fetchone()

    if not assign:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    criteria = await LocalLLMEngine.generate_rubric_from_assignment(
        assignment_title=assign["title"],
        assignment_description=assign["description"] or "",
        max_points=assign["max_points"],
        custom_guidance=req.custom_guidance if req else None
    )

    return criteria

@router.post("/save", response_model=RubricResponse)
def save_rubric(course_id: str, assignment_id: str, rubric_data: RubricCreate):
    """Saves or updates rubric criteria in DRAFT status."""
    now_str = datetime.now().isoformat()
    rubric_id = str(uuid.uuid4())
    criteria_json = json.dumps([c.model_dump() for c in rubric_data.criteria])

    with db_session() as conn:
        # Check current version
        curr = conn.execute(
            "SELECT id, version FROM rubrics WHERE course_id = ? AND assignment_id = ? ORDER BY version DESC LIMIT 1",
            (course_id, assignment_id)
        ).fetchone()

        new_version = (curr["version"] + 1) if curr else 1

        conn.execute(
            """
            INSERT INTO rubrics (id, course_id, assignment_id, version, status, criteria_json, total_max_marks, late_penalty_percent, created_at)
            VALUES (?, ?, ?, ?, 'DRAFT', ?, ?, ?, ?)
            """,
            (rubric_id, course_id, assignment_id, new_version, criteria_json, rubric_data.total_max_marks, rubric_data.late_penalty_percent, now_str)
        )

    AuditService.log_event("RUBRIC_SAVED", course_id=course_id, assignment_id=assignment_id, details={"rubric_id": rubric_id, "version": new_version})

    return RubricResponse(
        id=rubric_id,
        course_id=course_id,
        assignment_id=assignment_id,
        version=new_version,
        status="DRAFT",
        criteria=rubric_data.criteria,
        total_max_marks=rubric_data.total_max_marks,
        late_penalty_percent=rubric_data.late_penalty_percent,
        created_at=now_str
    )

@router.post("/approve", response_model=RubricResponse)
def approve_rubric(course_id: str, assignment_id: str):
    """Faculty explicitly approves the rubric before evaluation can be launched."""
    now_str = datetime.now().isoformat()
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM rubrics WHERE course_id = ? AND assignment_id = ? ORDER BY version DESC LIMIT 1",
            (course_id, assignment_id)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=400, detail="No rubric exists to approve. Please generate or create one first.")

        conn.execute(
            "UPDATE rubrics SET status = 'APPROVED', approved_at = ? WHERE id = ?",
            (now_str, row["id"])
        )

        criteria_list = [CriterionModel(**c) for c in json.loads(row["criteria_json"])]

    AuditService.log_event("RUBRIC_APPROVED", course_id=course_id, assignment_id=assignment_id, details={"rubric_id": row["id"]})

    return RubricResponse(
        id=row["id"],
        course_id=row["course_id"],
        assignment_id=row["assignment_id"],
        version=row["version"],
        status="APPROVED",
        criteria=criteria_list,
        total_max_marks=row["total_max_marks"],
        late_penalty_percent=row["late_penalty_percent"],
        created_at=row["created_at"],
        approved_at=now_str
    )

