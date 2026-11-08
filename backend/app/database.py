import sqlite3
import json
from contextlib import contextmanager
from typing import Generator, Any, Dict, List, Optional
from datetime import datetime
from backend.app.config import DATABASE_PATH

def get_db_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with foreign keys enabled, WAL mode, and resilient busy timeouts."""
    conn = sqlite3.connect(str(DATABASE_PATH), timeout=60.0)
    conn.execute("PRAGMA busy_timeout = 60000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_session() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for automatic commit/rollback and connection closing."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db() -> None:
    """Initializes the database schema with multi-classroom isolation constraints."""
    with db_session() as conn:
        cursor = conn.cursor()
        
        # 1. Faculty table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS faculty (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            google_access_token TEXT,
            google_refresh_token TEXT,
            token_expiry TEXT,
            created_at TEXT NOT NULL
        );
        """)

        # 2. Courses table (Multi-classroom support)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id TEXT PRIMARY KEY,
            faculty_id TEXT NOT NULL,
            name TEXT NOT NULL,
            section TEXT NOT NULL,
            description TEXT,
            room TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            enrolled_count INTEGER DEFAULT 0,
            assignments_count INTEGER DEFAULT 0,
            excel_workbook_path TEXT,
            last_sync_time TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (faculty_id) REFERENCES faculty(id) ON DELETE CASCADE
        );
        """)

        # 3. Assignments table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            max_points REAL DEFAULT 100.0,
            due_date TEXT,
            materials_json TEXT,
            submission_types_json TEXT,
            status TEXT NOT NULL DEFAULT 'DRAFT',
            created_at TEXT NOT NULL,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        );
        """)

        # 4. Students table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            google_user_id TEXT
        );
        """)
        try:
            cursor.execute("ALTER TABLE students ADD COLUMN google_user_id TEXT")
        except Exception:
            pass

        # 5. Course Enrollments table (Enables student in multiple courses)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS course_enrollments (
            course_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            enrolled_at TEXT NOT NULL,
            PRIMARY KEY (course_id, student_id),
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        );
        """)

        # 6. Rubrics table (Assignment-specific marking criteria)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rubrics (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            assignment_id TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'DRAFT',
            criteria_json TEXT NOT NULL,
            total_max_marks REAL NOT NULL,
            late_penalty_percent REAL DEFAULT 30.0,
            custom_guidance TEXT,
            created_at TEXT NOT NULL,
            approved_at TEXT,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
            UNIQUE(course_id, assignment_id, version)
        );
        """)
        try:
            cursor.execute("ALTER TABLE rubrics ADD COLUMN custom_guidance TEXT")
        except Exception:
            pass

        # 7. Submissions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            assignment_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            submission_time TEXT,
            is_late INTEGER DEFAULT 0,
            state TEXT NOT NULL DEFAULT 'TURNED_IN',
            attachments_json TEXT,
            extracted_content_json TEXT,
            submission_flags_json TEXT,
            raw_file_path TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            UNIQUE(course_id, assignment_id, student_id)
        );
        """)

        # 8. Evaluation Runs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_runs (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            assignment_id TEXT NOT NULL,
            rubric_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            total_evaluated INTEGER DEFAULT 0,
            summary_stats_json TEXT,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
            FOREIGN KEY (rubric_id) REFERENCES rubrics(id) ON DELETE CASCADE
        );
        """)

        # 9. Evaluation Results table (With partial criteria breakdown & faculty overrides)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_results (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            course_id TEXT NOT NULL,
            assignment_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            submission_id TEXT,
            raw_score REAL NOT NULL,
            late_penalty REAL DEFAULT 0.0,
            final_score REAL NOT NULL,
            faculty_adjusted_score REAL,
            faculty_approved INTEGER DEFAULT 0,
            faculty_remarks TEXT,
            criteria_breakdown_json TEXT NOT NULL,
            code_execution_results_json TEXT,
            flags_json TEXT,
            overall_feedback TEXT,
            evaluated_at TEXT NOT NULL,
            approved_at TEXT,
            duplicate_penalty REAL DEFAULT 0.0,
            duplicate_of TEXT,
            duplicate_cluster_id INTEGER,
            FOREIGN KEY (run_id) REFERENCES evaluation_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            UNIQUE(course_id, assignment_id, student_id)
        );
        """)

        # 10. Audit Logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            faculty_id TEXT,
            course_id TEXT,
            assignment_id TEXT,
            action TEXT NOT NULL,
            details_json TEXT
        );
        """)

        # 11. Publishing Logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS publish_logs (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            assignment_id TEXT NOT NULL,
            faculty_id TEXT NOT NULL,
            published_at TEXT NOT NULL,
            total_published INTEGER NOT NULL,
            return_submissions INTEGER DEFAULT 0,
            google_response_json TEXT,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        );
        """)

        # Migrations for existing databases
        try:
            cursor.execute("ALTER TABLE evaluation_results ADD COLUMN duplicate_penalty REAL DEFAULT 0.0")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE evaluation_results ADD COLUMN duplicate_of TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE evaluation_results ADD COLUMN duplicate_cluster_id INTEGER")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE rubrics ADD COLUMN custom_guidance TEXT")
        except Exception:
            pass

