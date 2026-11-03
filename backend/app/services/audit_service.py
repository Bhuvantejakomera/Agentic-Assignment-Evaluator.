import uuid
import json
from datetime import datetime
from typing import Optional, Dict, Any
from backend.app.database import db_session

class AuditService:
    """Maintains immutable audit records of all grading actions and approvals."""

    @classmethod
    def log_event(
        cls,
        action: str,
        faculty_id: Optional[str] = None,
        course_id: Optional[str] = None,
        assignment_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        log_id = str(uuid.uuid4())
        now_str = datetime.now().isoformat()
        details_str = json.dumps(details or {}, ensure_ascii=False)

        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (id, timestamp, faculty_id, course_id, assignment_id, action, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (log_id, now_str, faculty_id, course_id, assignment_id, action, details_str)
            )
        return log_id

