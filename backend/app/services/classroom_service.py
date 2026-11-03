import os
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
    and submission ingestion across multiple classrooms."""

    DEFAULT_FACULTY_ID = "fac-1001"
    DEFAULT_FACULTY_NAME = "Prof. Bhuvan Teja"
    DEFAULT_FACULTY_EMAIL = "chandragajjela2003@gmail.com"

    @classmethod
    def seed_initial_classrooms_if_empty(cls) -> None:
        """Seeds initial data for multiple classrooms, students from Lab_Marks_Record.xlsx, and assignments."""
        with db_session() as conn:
            # Check if faculty exists
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

            # Read students from Lab_Marks_Record.xlsx
            students = []
            if DEFAULT_EXCEL_TEMPLATE.exists():
                wb = openpyxl.load_workbook(str(DEFAULT_EXCEL_TEMPLATE), data_only=True)
                ws = wb.active
                for r in range(2, ws.max_row + 1):
                    sid = ws.cell(r, 1).value
                    sname = ws.cell(r, 2).value
                    if sid:
                        students.append({
                            "id": str(sid).strip(),
                            "name": str(sname).strip() if sname else f"Student {sid}",
                            "email": f"{str(sid).strip().lower()}@srmap.edu.in"
                        })
            else:
                for i in range(1, 67):
                    sid = f"AP26110010{500+i}"
                    students.append({"id": sid, "name": f"Student {i}", "email": f"{sid.lower()}@srmap.edu.in"})

            # Insert students
            for s in students:
                conn.execute(
                    "INSERT OR IGNORE INTO students (id, name, email) VALUES (?, ?, ?)",
                    (s["id"], s["name"], s["email"])
                )

            # Initialize dedicated workbooks for each classroom
            wb_c1 = ExcelService.ensure_classroom_workbook(
                "course-c-101", "Programming in C", "CSE-A", students,
                ["Lab 1", "Lab 2", "Lab 3", "Lab 4"], seed_from_template=DEFAULT_EXCEL_TEMPLATE
            )
            wb_c2 = ExcelService.ensure_classroom_workbook(
                "course-ds-201", "Data Structures", "CSE-B", students[:60],
                ["Assignment 1", "Assignment 2"]
            )
            wb_c3 = ExcelService.ensure_classroom_workbook(
                "course-py-301", "Python Programming", "AIML-A", students[:55],
                ["Lab 1", "Lab 2"]
            )
            wb_c4 = ExcelService.ensure_classroom_workbook(
                "course-ai-401", "Artificial Intelligence", "AIML-B", students[:50],
                ["Lab 1", "Project"]
            )

            # Check courses count
            course_count = conn.execute("SELECT COUNT(*) as c FROM courses").fetchone()["c"]
            if course_count > 0:
                # Update courses with their dedicated workbooks if needed
                conn.execute("UPDATE courses SET excel_workbook_path = ? WHERE id = 'course-c-101'", (str(wb_c1),))
                conn.execute("UPDATE courses SET excel_workbook_path = ? WHERE id = 'course-ds-201'", (str(wb_c2),))
                conn.execute("UPDATE courses SET excel_workbook_path = ? WHERE id = 'course-py-301'", (str(wb_c3),))
                conn.execute("UPDATE courses SET excel_workbook_path = ? WHERE id = 'course-ai-401'", (str(wb_c4),))
                return

            now_str = datetime.now().isoformat()

            # Course 1: Programming in C (CSE-A)
            c1_id = "course-c-101"
            conn.execute(
                """
                INSERT INTO courses (id, faculty_id, name, section, description, room, status, enrolled_count, assignments_count, excel_workbook_path, last_sync_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (c1_id, cls.DEFAULT_FACULTY_ID, "Programming in C", "CSE-A",
                 "Foundations of C programming, pointers, algorithms, and modular design.", "AL-302", "ACTIVE",
                 len(students), 4, str(wb_c1), now_str, now_str)
            )

            # Course 2: Data Structures (CSE-B)
            c2_id = "course-ds-201"
            conn.execute(
                """
                INSERT INTO courses (id, faculty_id, name, section, description, room, status, enrolled_count, assignments_count, excel_workbook_path, last_sync_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (c2_id, cls.DEFAULT_FACULTY_ID, "Data Structures", "CSE-B",
                 "Linear and non-linear data structures, trees, graphs, stacks, and complexity analysis.", "BL-204", "ACTIVE",
                 60, 2, str(wb_c2), now_str, now_str)
            )

            # Course 3: Python Programming (AIML-A)
            c3_id = "course-py-301"
            conn.execute(
                """
                INSERT INTO courses (id, faculty_id, name, section, description, room, status, enrolled_count, assignments_count, excel_workbook_path, last_sync_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (c3_id, cls.DEFAULT_FACULTY_ID, "Python Programming", "AIML-A",
                 "Advanced Python, data handling, functional programming, and computational thinking.", "CL-101", "ACTIVE",
                 55, 2, str(wb_c3), now_str, now_str)
            )

            # Course 4: Artificial Intelligence (AIML-B)
            c4_id = "course-ai-401"
            conn.execute(
                """
                INSERT INTO courses (id, faculty_id, name, section, description, room, status, enrolled_count, assignments_count, excel_workbook_path, last_sync_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (c4_id, cls.DEFAULT_FACULTY_ID, "Artificial Intelligence", "AIML-B",
                 "Informed search algorithms, heuristic optimization, and knowledge representation.", "DL-405", "ACTIVE",
                 50, 2, str(wb_c4), now_str, now_str)
            )

            # Enroll students into Course 1 (CSE-A)
            for s in students:
                conn.execute(
                    "INSERT OR IGNORE INTO course_enrollments (course_id, student_id, enrolled_at) VALUES (?, ?, ?)",
                    (c1_id, s["id"], now_str)
                )

            # Enroll first 60 students into Course 2 (CSE-B)
            for s in students[:60]:
                conn.execute(
                    "INSERT OR IGNORE INTO course_enrollments (course_id, student_id, enrolled_at) VALUES (?, ?, ?)",
                    (c2_id, s["id"], now_str)
                )

            # Enroll first 55 students into Course 3 (AIML-A)
            for s in students[:55]:
                conn.execute(
                    "INSERT OR IGNORE INTO course_enrollments (course_id, student_id, enrolled_at) VALUES (?, ?, ?)",
                    (c3_id, s["id"], now_str)
                )

            # Enroll first 50 students into Course 4 (AIML-B)
            for s in students[:50]:
                conn.execute(
                    "INSERT OR IGNORE INTO course_enrollments (course_id, student_id, enrolled_at) VALUES (?, ?, ?)",
                    (c4_id, s["id"], now_str)
                )

            # Assignments for Course 1: Programming in C
            due_c1_l1 = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d 23:59:59")
            due_c1_l2 = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d 23:59:59")
            due_c1_l3 = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d 23:59:59")
            due_c1_l4 = (datetime.now() + timedelta(days=6)).strftime("%Y-%m-%d 23:59:59")

            assignments_c1 = [
                ("assign-c-lab1", c1_id, "Lab 1 – Algorithms & Flowcharts",
                 "Write step-by-step algorithms, draw flowcharts, and implement solutions in C for basic numerical operations and prime number checking.", 100.0, due_c1_l1),
                ("assign-c-lab2", c1_id, "Lab 2 – Operators & Expressions",
                 "Implement C programs demonstrating arithmetic, relational, logical, and bitwise operators with formatted output.", 100.0, due_c1_l2),
                ("assign-c-lab3", c1_id, "Lab 3 – Conditional Statements",
                 "Implement nested if-else and switch-case structures in C to solve branching problems.", 100.0, due_c1_l3),
                ("assign-c-lab4", c1_id, "Lab 4 – Loops & Iterations",
                 "Implement while, for, and do-while loops in C for series summation and pattern printing.", 100.0, due_c1_l4),
            ]

            for a_id, crs_id, title, desc, max_p, due in assignments_c1:
                conn.execute(
                    """
                    INSERT INTO assignments (id, course_id, title, description, max_points, due_date, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', ?)
                    """,
                    (a_id, crs_id, title, desc, max_p, due, now_str)
                )

            # Assignments for Course 2: Data Structures
            due_c2_a1 = (datetime.now() - timedelta(days=4)).strftime("%Y-%m-%d 23:59:59")
            due_c2_a2 = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d 23:59:59")
            assignments_c2 = [
                ("assign-ds-1", c2_id, "Assignment 1 – Singly & Doubly Linked Lists",
                 "Explain node structures, write insertion and deletion algorithms, and implement doubly linked lists in C.", 100.0, due_c2_a1),
                ("assign-ds-2", c2_id, "Assignment 2 – Stack & Queue Implementations",
                 "Explain LIFO and FIFO mechanisms, provide visual diagrams, and implement circular queues with underflow/overflow handling.", 100.0, due_c2_a2),
            ]
            for a_id, crs_id, title, desc, max_p, due in assignments_c2:
                conn.execute(
                    """
                    INSERT INTO assignments (id, course_id, title, description, max_points, due_date, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', ?)
                    """,
                    (a_id, crs_id, title, desc, max_p, due, now_str)
                )

            # Assignments for Course 3: Python Programming
            assignments_c3 = [
                ("assign-py-1", c3_id, "Lab 1 – Python Data Structures & Comprehensions",
                 "Demonstrate list comprehensions, dictionary transformations, and file I/O operations in Python.", 100.0, due_c2_a1),
                ("assign-py-2", c3_id, "Lab 2 – Modular Design & Exceptions",
                 "Build robust custom exception classes and modular mathematical packages.", 100.0, due_c2_a2),
            ]
            for a_id, crs_id, title, desc, max_p, due in assignments_c3:
                conn.execute(
                    """
                    INSERT INTO assignments (id, course_id, title, description, max_points, due_date, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', ?)
                    """,
                    (a_id, crs_id, title, desc, max_p, due, now_str)
                )

            # Assignments for Course 4: Artificial Intelligence
            assignments_c4 = [
                ("assign-ai-1", c4_id, "Lab 1 – Breadth-First & Depth-First Search",
                 "Implement BFS and DFS in Python to solve the 8-puzzle problem and graph pathfinding.", 100.0, due_c2_a1),
                ("assign-ai-2", c4_id, "Project – A* Heuristic Search",
                 "Design Manhattan and Euclidean distance heuristics and evaluate search tree node expansions.", 100.0, due_c2_a2),
            ]
            for a_id, crs_id, title, desc, max_p, due in assignments_c4:
                conn.execute(
                    """
                    INSERT INTO assignments (id, course_id, title, description, max_points, due_date, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', ?)
                    """,
                    (a_id, crs_id, title, desc, max_p, due, now_str)
                )

            # Seed realistic student submissions for Course 1, Lab 1 and Course 2, Assignment 2
            cls._seed_submissions_for_course_c1(conn, students, "assign-c-lab1", c1_id)
            cls._seed_submissions_for_course_c2(conn, students[:60], "assign-ds-2", c2_id)

    @classmethod
    def _seed_submissions_for_course_c1(cls, conn, students, assignment_id: str, course_id: str) -> None:
        """Seeds realistic student submissions for Course 1, Lab 1."""
        now = datetime.now()
        due_time = now - timedelta(days=5)

        # Known irregular students from real Lab Marks Record:
        # AP26110010541: Uploaded the wrong PDF
        # AP26110010531: Late
        # AP26110010526: Wrong PDF
        # AP26110010492: Wrong PDF
        # AP26110010491: Wrong PDF
        # AP26110010493: Incomplete (Shivam Rai)

        wrong_pdf_ids = {"AP26110010541", "AP26110010526", "AP26110010492", "AP26110010491"}
        late_ids = {"AP26110010531", "AP26110010542", "AP26110010514"}
        incomplete_ids = {"AP26110010493", "AP26110010496", "AP26110010502", "AP26110010485", "AP26110010521"}

        for s in students:
            sid = s["id"]
            sub_id = f"sub-{course_id}-{assignment_id}-{sid}"
            is_late = sid in late_ids
            sub_time = (due_time + timedelta(hours=6 if is_late else -4)).isoformat()

            flags = []
            if is_late:
                flags.append("LATE")

            if sid in wrong_pdf_ids:
                flags.append("WRONG_PDF")
                text = (
                    "PHYSICS EXPERIMENT REPORT\n"
                    "Title: Determination of Planck's Constant using Photoelectric Effect.\n"
                    "Apparatus: Vacuum tube, variable DC supply, optical filters, mercury vapor lamp.\n"
                    "Observations and graphs attached."
                )
                code_snippets = []
                attachments = [{"filename": f"{sid}_Physics_Lab.pdf", "file_type": "PDF", "file_path": f"/dummy/{sid}.pdf", "file_size_bytes": 45000, "is_readable": True}]
            elif sid in incomplete_ids:
                flags.append("INCOMPLETE")
                text = (
                    f"Student: {s['name']} ({sid})\n"
                    "Lab 1: Algorithm & C Implementation\n"
                    "Algorithm:\nStep 1: Start.\nStep 2: Read integer N.\nStep 3: If N <= 1 then not prime.\nStep 4: Check divisibility.\nStep 5: Display result.\n"
                    "(Flowchart was not completed due to time constraints).\n"
                    "```c\n#include <stdio.h>\nint main() {\n    int n = 17, is_prime = 1;\n    for(int i = 2; i * i <= n; i++) {\n        if (n % i == 0) { is_prime = 0; break; }\n    }\n    printf(\"%d is %s\\n\", n, is_prime ? \"Prime\" : \"Not Prime\");\n    return 0;\n}\n```"
                )
                code_snippets = [{"language": "c", "code": "#include <stdio.h>\nint main() {\n    int n = 17, is_prime = 1;\n    for(int i = 2; i * i <= n; i++) {\n        if (n % i == 0) { is_prime = 0; break; }\n    }\n    printf(\"%d is %s\\n\", n, is_prime ? \"Prime\" : \"Not Prime\");\n    return 0;\n}"}]
                attachments = [{"filename": f"{sid}_Lab1.pdf", "file_type": "PDF", "file_path": f"/dummy/{sid}.pdf", "file_size_bytes": 52000, "is_readable": True}]
            else:
                # Full submission
                text = (
                    f"Student: {s['name']} ({sid})\n"
                    "Course: Programming in C (CSE-A)\n"
                    "Lab 1: Algorithms, Flowcharts, and Prime Number Determination in C\n\n"
                    "1. Theoretical Concepts & Explanation:\n"
                    "A prime number is a positive integer greater than 1 that has no positive divisors other than 1 and itself.\n"
                    "To optimize primality testing, we only need to test divisors up to sqrt(N).\n\n"
                    "2. Algorithm:\n"
                    "Step 1: Start\n"
                    "Step 2: Read positive integer N from user\n"
                    "Step 3: If N <= 1, print 'Not Prime' and exit\n"
                    "Step 4: Initialize divisor i = 2\n"
                    "Step 5: While i * i <= N:\n"
                    "        If N % i == 0, print 'Not Prime' and exit\n"
                    "        i = i + 1\n"
                    "Step 6: Print 'Prime'\n"
                    "Step 7: Stop\n\n"
                    "3. Flowchart & Visual Diagram:\n"
                    "Flowchart Structure: [Start Oval] -> [Input N Rectangle] -> [Decision Diamond N<=1?] -> [Loop Diamond i*i<=N] -> [Decision N%i==0] -> [Output Prime/Not Prime] -> [Stop Oval]\n\n"
                    "4. C Implementation:\n"
                    "```c\n#include <stdio.h>\n#include <math.h>\nint main() {\n    int n = 29;\n    if (n <= 1) { printf(\"Not Prime\\n\"); return 0; }\n    int flag = 1;\n    for (int i = 2; i * i <= n; i++) {\n        if (n % i == 0) { flag = 0; break; }\n    }\n    if (flag) printf(\"Prime\\n\");\n    else printf(\"Not Prime\\n\");\n    return 0;\n}\n```"
                )
                code_snippets = [{"language": "c", "code": "#include <stdio.h>\nint main() {\n    int n = 29;\n    if (n <= 1) { printf(\"Prime\\n\"); return 0; }\n    int flag = 1;\n    for (int i = 2; i * i <= n; i++) {\n        if (n % i == 0) { flag = 0; break; }\n    }\n    if (flag) printf(\"Prime\\n\");\n    else printf(\"Not Prime\\n\");\n    return 0;\n}"}]
                attachments = [
                    {"filename": f"{sid}_Lab1.pdf", "file_type": "PDF", "file_path": f"/dummy/{sid}.pdf", "file_size_bytes": 62000, "is_readable": True},
                    {"filename": f"{sid}_prime.c", "file_type": "C", "file_path": f"/dummy/{sid}_prime.c", "file_size_bytes": 1200, "is_readable": True}
                ]

            content_json = json.dumps({
                "text_content": text,
                "code_snippets": code_snippets,
                "diagram_flowchart_descriptions": ["Flowchart structure present"] if sid not in incomplete_ids and sid not in wrong_pdf_ids else [],
                "word_count": len(text.split()),
                "extraction_warnings": []
            })

            conn.execute(
                """
                INSERT OR REPLACE INTO submissions (
                    id, course_id, assignment_id, student_id, submission_time,
                    is_late, state, attachments_json, extracted_content_json,
                    submission_flags_json, raw_file_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'TURNED_IN', ?, ?, ?, ?, ?)
                """,
                (
                    sub_id, course_id, assignment_id, sid, sub_time,
                    1 if is_late else 0, json.dumps(attachments), content_json,
                    json.dumps(flags), f"/submissions/{sid}", now.isoformat()
                )
            )

    @classmethod
    def _seed_submissions_for_course_c2(cls, conn, students, assignment_id: str, course_id: str) -> None:
        """Seeds submissions for Course 2 (Data Structures), Assignment 2."""
        now = datetime.now()
        due_time = now - timedelta(days=1)

        for s in students:
            sid = s["id"]
            sub_id = f"sub-{course_id}-{assignment_id}-{sid}"
            is_late = False
            sub_time = (due_time - timedelta(hours=3)).isoformat()

            text = (
                f"Student: {s['name']} ({sid})\n"
                "Data Structures (CSE-B) - Assignment 2: Circular Queue Implementation\n"
                "1. Concept:\n"
                "A circular queue overcomes the memory limitation of a linear queue by connecting the rear back to the front.\n"
                "2. Algorithm:\n"
                "Step 1: Enqueue: If (rear + 1) % SIZE == front -> Overflow.\n"
                "Step 2: Else rear = (rear + 1) % SIZE; queue[rear] = item.\n"
                "Step 3: Dequeue: If front == -1 -> Underflow.\n"
                "Step 4: Else front = (front + 1) % SIZE.\n"
                "3. Diagram:\n"
                "Visual circular array with front and rear pointers moving modulo capacity.\n"
                "```c\n#include <stdio.h>\n#define SIZE 5\nint queue[SIZE], front = -1, rear = -1;\nvoid enqueue(int val) {\n    if ((rear + 1) % SIZE == front) { printf(\"Overflow\\n\"); return; }\n    if (front == -1) front = 0;\n    rear = (rear + 1) % SIZE;\n    queue[rear] = val;\n    printf(\"Enqueued %d\\n\", val);\n}\nint main() {\n    enqueue(10);\n    enqueue(20);\n    printf(\"Queue ready\\n\");\n    return 0;\n}\n```"
            )
            code_snippets = [{"language": "c", "code": "#include <stdio.h>\n#define SIZE 5\nint queue[SIZE], front = -1, rear = -1;\nvoid enqueue(int val) {\n    if ((rear + 1) % SIZE == front) { printf(\"Overflow\\n\"); return; }\n    if (front == -1) front = 0;\n    rear = (rear + 1) % SIZE;\n    queue[rear] = val;\n    printf(\"Enqueued %d\\n\", val);\n}\nint main() {\n    enqueue(10);\n    enqueue(20);\n    printf(\"Queue ready\\n\");\n    return 0;\n}"}]
            attachments = [{"filename": f"{sid}_circular_queue.pdf", "file_type": "PDF", "file_path": f"/dummy/{sid}.pdf", "file_size_bytes": 48000, "is_readable": True}]

            content_json = json.dumps({
                "text_content": text,
                "code_snippets": code_snippets,
                "diagram_flowchart_descriptions": ["Circular buffer diagram"],
                "word_count": len(text.split()),
                "extraction_warnings": []
            })

            conn.execute(
                """
                INSERT OR REPLACE INTO submissions (
                    id, course_id, assignment_id, student_id, submission_time,
                    is_late, state, attachments_json, extracted_content_json,
                    submission_flags_json, raw_file_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'TURNED_IN', ?, ?, ?, ?, ?)
                """,
                (
                    sub_id, course_id, assignment_id, sid, sub_time,
                    0, json.dumps(attachments), content_json,
                    json.dumps([]), f"/submissions/{sid}", now.isoformat()
                )
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

