import os
import re
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import openpyxl
from backend.app.config import (
    BASE_DIR,
    DEFAULT_EXCEL_TEMPLATE,
    SUBMISSIONS_DIR,
    SAMPLE_DATA_DIR,
    WORKBOOKS_DIR
)
from backend.app.database import db_session
from backend.app.models.course import CourseResponse
from backend.app.models.assignment import AssignmentResponse
from backend.app.models.submission import SubmissionResponse, SubmissionAttachment, ExtractedContentModel
from backend.app.services.document_extractor import DocumentExtractor
from backend.app.services.audit_service import AuditService
from backend.app.services.excel_service import ExcelService

class ClassroomService:
    """Handles course discovery, assignment retrieval, student rosters, 
    and submission ingestion across real Google Classrooms."""

    DEFAULT_FACULTY_ID = "fac-1001"
    DEFAULT_FACULTY_NAME = "Bhuvan Teja K | AP25122040016"
    DEFAULT_FACULTY_EMAIL = "bhuvan_k@srmap.edu.in"

    @classmethod
    def seed_initial_classrooms_if_empty(cls) -> None:
        """Ensures the faculty record exists in DB without injecting any fake mock courses."""
        with db_session() as conn:
            fac = conn.execute("SELECT id FROM faculty WHERE id = ?", (cls.DEFAULT_FACULTY_ID,)).fetchone()
            if not fac:
                now_str = datetime.now().isoformat()
                conn.execute(
                    """
                    INSERT INTO faculty (id, email, name, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (cls.DEFAULT_FACULTY_ID, cls.DEFAULT_FACULTY_EMAIL, cls.DEFAULT_FACULTY_NAME, now_str)
                )

    @classmethod
    def get_all_courses(cls, faculty_id: str) -> List[CourseResponse]:
        """Returns all courses accessible by the authenticated faculty."""
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT id, faculty_id, name, section, description, room, status,
                       enrolled_count, assignments_count, excel_workbook_path, last_sync_time, created_at
                FROM courses
                WHERE faculty_id = ?
                ORDER BY name ASC
                """,
                (faculty_id,)
            ).fetchall()

            return [
                CourseResponse(
                    id=r["id"],
                    faculty_id=r["faculty_id"],
                    name=r["name"],
                    section=r["section"],
                    description=r["description"],
                    room=r["room"],
                    status=r["status"],
                    enrolled_count=r["enrolled_count"],
                    assignments_count=r["assignments_count"],
                    excel_workbook_path=r["excel_workbook_path"],
                    last_sync_time=r["last_sync_time"],
                    created_at=r["created_at"]
                )
                for r in rows
            ]

    @classmethod
    def get_course_by_id(cls, course_id: str) -> Optional[CourseResponse]:
        with db_session() as conn:
            r = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
            if not r:
                return None
            return CourseResponse(
                id=r["id"],
                faculty_id=r["faculty_id"],
                name=r["name"],
                section=r["section"],
                description=r["description"],
                room=r["room"],
                status=r["status"],
                enrolled_count=r["enrolled_count"],
                assignments_count=r["assignments_count"],
                excel_workbook_path=r["excel_workbook_path"],
                last_sync_time=r["last_sync_time"],
                created_at=r["created_at"]
            )

    @classmethod
    def get_assignments_for_course(cls, course_id: str) -> List[AssignmentResponse]:
        """Strictly scoped: returns only assignments belonging to the specified course_id."""
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT a.*, 
                       (SELECT COUNT(*) FROM submissions s WHERE s.course_id = a.course_id AND s.assignment_id = a.id) as total_sub,
                       (SELECT COUNT(*) FROM evaluation_results e WHERE e.course_id = a.course_id AND e.assignment_id = a.id) as eval_sub,
                       (SELECT COUNT(*) FROM evaluation_results e WHERE e.course_id = a.course_id AND e.assignment_id = a.id AND e.faculty_approved = 1) as app_sub,
                       (SELECT id FROM rubrics r WHERE r.course_id = a.course_id AND r.assignment_id = a.id ORDER BY version DESC LIMIT 1) as rub_id
                FROM assignments a
                WHERE a.course_id = ?
                ORDER BY a.created_at ASC
                """,
                (course_id,)
            ).fetchall()

            assignments = []
            for r in rows:
                rub_id = r["rub_id"]
                assignments.append(AssignmentResponse(
                    id=r["id"],
                    course_id=r["course_id"],
                    title=r["title"],
                    description=r["description"],
                    max_points=r["max_points"],
                    due_date=r["due_date"],
                    materials=json.loads(r["materials_json"]) if r["materials_json"] else None,
                    submission_types=json.loads(r["submission_types_json"]) if r["submission_types_json"] else ["PDF", "DOCX", "C", "CPP", "PY"],
                    status=r["status"],
                    created_at=r["created_at"],
                    total_submissions=r["total_sub"],
                    evaluated_submissions=r["eval_sub"],
                    approved_submissions=r["app_sub"],
                    has_rubric=bool(rub_id),
                    rubric_id=rub_id
                ))

            # Natural sort assignments (Lab-1, Lab-2, ..., Lab-9)
            def get_sort_key_title(assign: AssignmentResponse):
                m = re.search(r'(lab|assignment|proj|quiz)[\s_-]*(\d+)', assign.title, re.IGNORECASE)
                if m:
                    cat_priority = {"lab": 1, "assignment": 2, "proj": 3, "quiz": 4}.get(m.group(1).lower(), 5)
                    return (cat_priority, int(m.group(2)), assign.title.lower())
                return (99, 999, assign.title.lower())

            assignments.sort(key=get_sort_key_title)
            return assignments

    @classmethod
    def get_faculty_dashboard_stats(cls, faculty_id: str) -> Dict[str, Any]:
        """Calculates global aggregated metrics across all classrooms for the shared faculty dashboard."""
        with db_session() as conn:
            courses = conn.execute(
                "SELECT id, name, section, enrolled_count, assignments_count, excel_workbook_path, status FROM courses WHERE faculty_id = ?",
                (faculty_id,)
            ).fetchall()

            total_courses = len(courses)
            total_students = sum(c["enrolled_count"] or 0 for c in courses)
            total_assignments = sum(c["assignments_count"] or 0 for c in courses)

            # Global evaluation counts
            eval_stats = conn.execute(
                """
                SELECT 
                    COUNT(*) as total_evaluated,
                    SUM(CASE WHEN faculty_approved = 1 THEN 1 ELSE 0 END) as total_approved
                FROM evaluation_results
                """
            ).fetchone()

            total_published = conn.execute("SELECT COUNT(*) as c FROM publish_logs WHERE faculty_id = ?", (faculty_id,)).fetchone()["c"]

            course_summaries = []
            for c in courses:
                cid = c["id"]
                c_eval = conn.execute(
                    """
                    SELECT 
                        COUNT(*) as evaluated,
                        SUM(CASE WHEN faculty_approved = 1 THEN 1 ELSE 0 END) as approved
                    FROM evaluation_results
                    WHERE course_id = ?
                    """,
                    (cid,)
                ).fetchone()

                wb_path = c["excel_workbook_path"]
                wb_exists = bool(wb_path and Path(wb_path).exists())

                course_summaries.append({
                    "course_id": cid,
                    "name": c["name"],
                    "section": c["section"],
                    "status": c["status"],
                    "enrolled_count": c["enrolled_count"],
                    "assignments_count": c["assignments_count"],
                    "evaluated_count": c_eval["evaluated"] if c_eval else 0,
                    "approved_count": c_eval["approved"] if (c_eval and c_eval["approved"]) else 0,
                    "workbook_path": wb_path,
                    "workbook_exists": wb_exists
                })

            return {
                "faculty_id": faculty_id,
                "total_classrooms": total_courses,
                "total_students": total_students,
                "total_assignments": total_assignments,
                "total_evaluated": eval_stats["total_evaluated"] if eval_stats else 0,
                "total_approved": eval_stats["total_approved"] if (eval_stats and eval_stats["total_approved"]) else 0,
                "total_published": total_published,
                "classrooms": course_summaries
            }
