import re
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from backend.app.database import db_session
from backend.app.config import DEFAULT_EXCEL_TEMPLATE
from backend.app.services.excel_service import ExcelService
from backend.app.services.audit_service import AuditService

class ClassroomAgent:
    """
    Agent 1: Classroom Information & Roster Specialist.
    Responsible for:
    - Discovering courses where the authenticated faculty has teacher access.
    - Paginating the complete student roster (ensuring 100% student coverage without page limits).
    - Parsing institutional student roll numbers (e.g. 'Sayanthkumar D | AP26110010495' -> AP26110010495).
    - Maintaining Google User ID -> Student Roll No mappings.
    - Managing database enrollment state and dedicated classroom Excel workbooks.
    """

    @classmethod
    def parse_student_identity(cls, raw_name: str, google_uid: str) -> Tuple[str, str]:
        """
        Parses full student name from Classroom.
        Institutional format: 'Student Name | RollNumber'
        Returns (clean_name, clean_roll_number).
        """
        raw = (raw_name or "").strip()
        if "|" in raw:
            parts = raw.split("|", 1)
            name = parts[0].strip()
            roll = parts[1].strip()
            if name and roll:
                return name, roll

        # Fallback if no pipe delimiter
        return raw or f"Student {google_uid[:6]}", google_uid

    @classmethod
    def sync_courses_and_roster(
        cls,
        classroom_service,
        faculty_id: str
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, str]]]:
        """
        Connects to Google Classroom API, retrieves courses, paginates rosters,
        and saves clean records to the database.
        Returns:
            (courses_list, course_to_student_map)
        """
        now_str = datetime.now().isoformat()

        # 1. Fetch courses
        courses_res = classroom_service.courses().list(teacherId="me").execute()
        courses_list = courses_res.get("courses", [])

        # Maintain mapping: course_id -> {google_uid: student_roll_no}
        course_student_mappings: Dict[str, Dict[str, str]] = {}

        with db_session() as conn:
            # Purge mock/demo courses when real Google account is syncing
            conn.execute("DELETE FROM courses WHERE id IN ('course-c-101', 'course-ds-201', 'course-py-301', 'course-ai-401')")

            real_course_ids = [c["id"] for c in courses_list]
            if real_course_ids:
                placeholders = ",".join("?" for _ in real_course_ids)
                conn.execute(f"DELETE FROM courses WHERE id NOT IN ({placeholders})", real_course_ids)
            else:
                conn.execute("DELETE FROM courses")

            for c in courses_list:
                course_id = c["id"]
                course_name = c.get("name", "Unnamed Course")
                section = c.get("section", "General")
                description = c.get("descriptionHeading") or c.get("description", "")
                room = c.get("room", "")
                status = "ACTIVE" if c.get("courseState") == "ACTIVE" else "ARCHIVED"

                wb_path = ExcelService.get_classroom_workbook_path(course_id, course_name, section)

                conn.execute(
                    """
                    INSERT INTO courses (id, faculty_id, name, section, description, room, status, excel_workbook_path, last_sync_time, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        section = excluded.section,
                        description = excluded.description,
                        status = excluded.status,
                        last_sync_time = excluded.last_sync_time
                    """,
                    (course_id, faculty_id, course_name, section, description, room, status, str(wb_path), now_str, now_str)
                )

                # 2. Paginate student roster
                all_student_items = []
                page_token = None
                while True:
                    try:
                        s_res = classroom_service.courses().students().list(
                            courseId=course_id,
                            pageSize=100,
                            pageToken=page_token
                        ).execute()
                        items = s_res.get("students", [])
                        all_student_items.extend(items)
                        page_token = s_res.get("nextPageToken")
                        if not page_token:
                            break
                    except Exception as err:
                        print(f"[ClassroomAgent] Error paginating students for {course_id}: {err}")
                        break

                # Clear old enrollments for clean state
                conn.execute("DELETE FROM course_enrollments WHERE course_id = ?", (course_id,))

                google_to_roll: Dict[str, str] = {}
                roster_for_workbook = []

                for s in all_student_items:
                    google_uid = s.get("userId")
                    user_p = s.get("profile", {})
                    raw_name = user_p.get("name", {}).get("fullName") or f"Student {google_uid[:6]}"
                    email = user_p.get("emailAddress", "")

                    clean_name, roll_no = cls.parse_student_identity(raw_name, google_uid)
                    google_to_roll[google_uid] = roll_no

                    roster_for_workbook.append({
                        "id": roll_no,
                        "name": clean_name,
                        "email": email,
                        "google_user_id": google_uid
                    })

                    conn.execute(
                        """
                        INSERT INTO students (id, name, email, google_user_id)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            name = excluded.name,
                            email = excluded.email,
                            google_user_id = excluded.google_user_id
                        """,
                        (roll_no, clean_name, email, google_uid)
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO course_enrollments (course_id, student_id, enrolled_at) VALUES (?, ?, ?)",
                        (course_id, roll_no, now_str)
                    )

                # Remove legacy numeric IDs if any remain unlinked
                conn.execute(
                    "DELETE FROM students WHERE id GLOB '[0-9][0-9][0-9]*' AND length(id) > 15 AND id NOT IN (SELECT student_id FROM course_enrollments)"
                )

                # Update enrolled count
                conn.execute(
                    "UPDATE courses SET enrolled_count = ? WHERE id = ?",
                    (len(roster_for_workbook), course_id)
                )

                course_student_mappings[course_id] = google_to_roll

        AuditService.log_event(
            "CLASSROOM_AGENT_SYNC_COMPLETE",
            faculty_id=faculty_id,
            details={"courses_count": len(courses_list)}
        )

        return courses_list, course_student_mappings

