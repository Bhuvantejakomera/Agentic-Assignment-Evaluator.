from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from backend.app.database import db_session
from backend.app.services.classroom_service import ClassroomService
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class FacultyProfileResponse(BaseModel):
    id: str
    name: str
    email: str
    is_connected_google: bool

@router.get("/faculty", response_model=FacultyProfileResponse)
def get_current_faculty():
    with db_session() as conn:
        r = conn.execute(
            "SELECT id, name, email, google_access_token FROM faculty WHERE id = ?",
            (ClassroomService.DEFAULT_FACULTY_ID,)
        ).fetchone()

        if not r:
            ClassroomService.seed_initial_classrooms_if_empty()
            r = conn.execute(
                "SELECT id, name, email, google_access_token FROM faculty WHERE id = ?",
                (ClassroomService.DEFAULT_FACULTY_ID,)
            ).fetchone()

        return FacultyProfileResponse(
            id=r["id"],
            name=r["name"],
            email=r["email"],
            is_connected_google=bool(r["google_access_token"])
        )

@router.post("/connect-google")
def connect_google_classroom():
    """Simulates or connects Google OAuth, returns success."""
    with db_session() as conn:
        conn.execute(
            """
            UPDATE faculty 
            SET google_access_token = 'simulated_google_oauth_token_active'
            WHERE id = ?
            """,
            (ClassroomService.DEFAULT_FACULTY_ID,)
        )
    AuditService.log_event("GOOGLE_CLASSROOM_CONNECTED", faculty_id=ClassroomService.DEFAULT_FACULTY_ID)
    return {"status": "connected", "message": "Successfully authenticated with Google Classroom."}

