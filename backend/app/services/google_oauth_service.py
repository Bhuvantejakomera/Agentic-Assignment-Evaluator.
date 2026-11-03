import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
import google.oauth2.credentials
from backend.app.config import (
    BASE_DIR,
    GOOGLE_CLIENT_SECRETS_FILE,
    GOOGLE_SCOPES,
    DEFAULT_EXCEL_TEMPLATE
)
from backend.app.database import db_session
from backend.app.services.audit_service import AuditService
from backend.app.services.excel_service import ExcelService

CREDENTIALS_FILE = Path(GOOGLE_CLIENT_SECRETS_FILE)

class GoogleOAuthService:
    """Manages real Google OAuth 2.0 flow and live Google Classroom API synchronization."""

    @classmethod
    def get_credentials_path(cls) -> Path:
        return CREDENTIALS_FILE

    @classmethod
    def is_credentials_file_configured(cls) -> bool:
        if not CREDENTIALS_FILE.exists():
            return False
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                data = json.load(f)
                cfg = data.get("web") or data.get("installed", {})
                cid = cfg.get("client_id", "").strip()
                csecret = cfg.get("client_secret", "").strip()
                if not cid or not csecret:
                    return False
                if "YOUR_GOOGLE_CLIENT_ID" in cid or "YOUR_GOOGLE_CLIENT_SECRET" in csecret:
                    return False
                return True
        except Exception:
            return False

    @classmethod
    def get_effective_redirect_uri(cls, requested_redirect_uri: str) -> str:
        """Ensures the redirect URI precisely matches what is registered in credentials.json."""
        if CREDENTIALS_FILE.exists():
            try:
                with open(CREDENTIALS_FILE, "r") as f:
                    data = json.load(f)
                    cfg = data.get("web") or data.get("installed", {})
                    registered = cfg.get("redirect_uris", [])
                    if registered:
                        for reg in registered:
                            if reg.strip() == requested_redirect_uri.strip():
                                return reg.strip()
                        return registered[0].strip()
            except Exception:
                pass
        return requested_redirect_uri

    @classmethod
    def get_client_info(cls) -> Dict[str, Any]:
        configured = cls.is_credentials_file_configured()
        client_id = None
        project_id = None
        redirect_uris = []
        if CREDENTIALS_FILE.exists():
            try:
                with open(CREDENTIALS_FILE, "r") as f:
                    raw = json.load(f)
                    cfg = raw.get("web") or raw.get("installed", {})
                    client_id = cfg.get("client_id")
                    project_id = cfg.get("project_id")
                    redirect_uris = cfg.get("redirect_uris", [])
            except Exception:
                pass
        return {
            "configured": configured,
            "credentials_file": str(CREDENTIALS_FILE),
            "client_id": client_id,
            "project_id": project_id,
            "redirect_uris": redirect_uris
        }

    @classmethod
    def save_client_secrets(cls, secrets_dict: Dict[str, Any]) -> bool:
        """Saves Google OAuth client secrets JSON to disk."""
        if "web" not in secrets_dict and "installed" not in secrets_dict:
            secrets_dict = {"web": secrets_dict}

        # Auto-ensure default redirect_uris if empty
        cfg = secrets_dict.get("web") or secrets_dict.get("installed", {})
        if "redirect_uris" not in cfg or not cfg["redirect_uris"]:
            cfg["redirect_uris"] = [
                "http://localhost:8000/api/auth/google/callback",
                "http://127.0.0.1:8000/api/auth/google/callback"
            ]

        with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
            json.dump(secrets_dict, f, indent=2)
        return True

    @classmethod
    def get_authorization_url(cls, redirect_uri: str) -> str:
        """Generates Google OAuth 2.0 consent URL."""
        if not cls.is_credentials_file_configured():
            raise ValueError(
                "Real Google OAuth client credentials are not configured yet. "
                "Please upload or configure your real credentials.json from Google Cloud Console."
            )

        # Allow HTTP for local development
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

        effective_uri = cls.get_effective_redirect_uri(redirect_uri)

        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            str(CREDENTIALS_FILE),
            scopes=GOOGLE_SCOPES,
            redirect_uri=effective_uri
        )

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent"
        )
        return auth_url

    @classmethod
    def exchange_code_for_tokens(
        cls,
        code: str,
        redirect_uri: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Exchanges code for tokens and fetches user profile."""
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

        effective_uri = cls.get_effective_redirect_uri(redirect_uri)

        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            str(CREDENTIALS_FILE),
            scopes=GOOGLE_SCOPES,
            redirect_uri=effective_uri
        )
        flow.fetch_token(code=code)
        creds = flow.credentials

        # Fetch user info
        oauth2_service = build("oauth2", "v2", credentials=creds)
        user_info = oauth2_service.userinfo().get().execute()

        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
            "expiry": creds.expiry.isoformat() if creds.expiry else None
        }

        return token_data, user_info

    @classmethod
    def save_tokens_for_faculty(
        cls,
        faculty_id: str,
        user_info: Dict[str, Any],
        token_data: Dict[str, Any]
    ) -> None:
        """Saves user profile and access/refresh tokens in database."""
        email = user_info.get("email")
        name = user_info.get("name") or email
        token_str = json.dumps(token_data)

        with db_session() as conn:
            conn.execute(
                """
                UPDATE faculty
                SET email = ?,
                    name = ?,
                    google_access_token = ?,
                    google_refresh_token = ?,
                    token_expiry = ?
                WHERE id = ?
                """,
                (
                    email,
                    name,
                    token_str,
                    token_data.get("refresh_token"),
                    token_data.get("expiry"),
                    faculty_id
                )
            )
        AuditService.log_event("GOOGLE_LOGIN_SUCCESS", faculty_id=faculty_id, details={"email": email, "name": name})

    @classmethod
    def get_credentials(cls, faculty_id: str) -> Optional[google.oauth2.credentials.Credentials]:
        """Loads and refreshes OAuth credentials for the faculty."""
        with db_session() as conn:
            r = conn.execute(
                "SELECT google_access_token FROM faculty WHERE id = ?",
                (faculty_id,)
            ).fetchone()
            if not r or not r["google_access_token"]:
                return None

            try:
                data = json.loads(r["google_access_token"])
                creds = google.oauth2.credentials.Credentials(
                    token=data.get("token"),
                    refresh_token=data.get("refresh_token"),
                    token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
                    client_id=data.get("client_id"),
                    client_secret=data.get("client_secret"),
                    scopes=data.get("scopes")
                )
                return creds
            except Exception:
                return None

    @classmethod
    def sync_live_google_classroom(cls, faculty_id: str) -> Dict[str, Any]:
        """
        Connects to live Google Classroom API using authenticated faculty credentials.
        Fetches real courses, coursework, student rosters, and submissions!
        """
        creds = cls.get_credentials(faculty_id)
        if not creds:
            raise ValueError("No active Google OAuth credentials found. Please sign in with Google first.")

        # Build Classroom client
        service = build("classroom", "v1", credentials=creds)

        # 1. Fetch courses where faculty is a teacher
        courses_res = service.courses().list(teacherId="me").execute()
        courses_list = courses_res.get("courses", [])

        now_str = datetime.now().isoformat()
        total_courses_synced = len(courses_list)
        total_assignments_synced = 0
        total_students_synced = 0

        with db_session() as conn:
            for c in courses_list:
                course_id = c["id"]
                course_name = c.get("name", "Unnamed Course")
                section = c.get("section", "General")
                description = c.get("descriptionHeading") or c.get("description", "")
                room = c.get("room", "")
                status = "ACTIVE" if c.get("courseState") == "ACTIVE" else "ARCHIVED"

                # Dedicated workbook path
                wb_path = ExcelService.get_classroom_workbook_path(course_id, course_name, section)

                # Upsert course
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

                # 2. Fetch Coursework / Assignments
                try:
                    cw_res = service.courses().courseWork().list(courseId=course_id).execute()
                    coursework_items = cw_res.get("courseWork", [])
                    total_assignments_synced += len(coursework_items)

                    for cw in coursework_items:
                        cw_id = cw["id"]
                        title = cw.get("title", "Untitled Assignment")
                        desc = cw.get("description", "")
                        max_p = float(cw.get("maxPoints", 100.0))
                        due_obj = cw.get("dueDate", {})
                        due_date_str = None
                        if due_obj:
                            due_date_str = f"{due_obj.get('year')}-{due_obj.get('month'):02d}-{due_obj.get('day'):02d}"

                        conn.execute(
                            """
                            INSERT INTO assignments (id, course_id, title, description, max_points, due_date, status, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', ?)
                            ON CONFLICT(id) DO UPDATE SET
                                title = excluded.title,
                                description = excluded.description,
                                max_points = excluded.max_points,
                                due_date = excluded.due_date
                            """,
                            (cw_id, course_id, title, desc, max_p, due_date_str, now_str)
                        )
                except Exception:
                    pass

                # 3. Fetch Students Roster
                course_students = []
                try:
                    students_res = service.courses().students().list(courseId=course_id).execute()
                    student_items = students_res.get("students", [])
                    total_students_synced += len(student_items)

                    for s in student_items:
                        user_p = s.get("profile", {})
                        sid = s.get("userId")
                        sname = user_p.get("name", {}).get("fullName") or f"Student {sid[:6]}"
                        semail = user_p.get("emailAddress", "")

                        course_students.append({"id": sid, "name": sname, "email": semail})

                        conn.execute(
                            "INSERT OR IGNORE INTO students (id, name, email) VALUES (?, ?, ?)",
                            (sid, sname, semail)
                        )
                        conn.execute(
                            "INSERT OR IGNORE INTO course_enrollments (course_id, student_id, enrolled_at) VALUES (?, ?, ?)",
                            (course_id, sid, now_str)
                        )

                    # Update enrolled count
                    conn.execute(
                        "UPDATE courses SET enrolled_count = ? WHERE id = ?",
                        (len(student_items), course_id)
                    )
                except Exception:
                    pass

                # Ensure dedicated consolidated workbook exists with these students
                assignment_titles = [cw.get("title", "Assignment") for cw in coursework_items] if 'coursework_items' in locals() else ["Assignment 1"]
                ExcelService.ensure_classroom_workbook(
                    course_id=course_id,
                    course_name=course_name,
                    section=section,
                    students=course_students,
                    assignment_titles=assignment_titles
                )

        AuditService.log_event(
            "GOOGLE_CLASSROOM_SYNC_COMPLETE",
            faculty_id=faculty_id,
            details={
                "courses_count": total_courses_synced,
                "assignments_count": total_assignments_synced,
                "students_count": total_students_synced
            }
        )

        return {
            "status": "success",
            "courses_synced": total_courses_synced,
            "assignments_synced": total_assignments_synced,
            "students_synced": total_students_synced,
            "message": f"Successfully synchronized {total_courses_synced} courses from Google Classroom."
        }

