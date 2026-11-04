import pytest
import re
from backend.app.database import init_db, db_session
from backend.app.services.classroom_service import ClassroomService

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

def test_classroom_discovery():
    courses = ClassroomService.get_all_courses(ClassroomService.DEFAULT_FACULTY_ID)
    assert len(courses) >= 1
    course_names = [c.name for c in courses]
    assert any("CSE 101" in name for name in course_names)

def test_classroom_scoped_assignments():
    courses = ClassroomService.get_all_courses(ClassroomService.DEFAULT_FACULTY_ID)
    c1 = next(c for c in courses if "CSE 101" in c.name)

    c1_assignments = ClassroomService.get_assignments_for_course(c1.id)

    # Scoped: c1 must have the real lab assignments (Lab-1 through Lab-9)
    assert len(c1_assignments) >= 5
    assert any("Lab-1" in a.title or "Lab 1" in a.title for a in c1_assignments)
    assert any("Lab-9" in a.title or "Lab 9" in a.title for a in c1_assignments)

    # Verify all assignments belong strictly to this course ID
    assert all(a.course_id == c1.id for a in c1_assignments)

def test_enrollments_preserved():
    courses = ClassroomService.get_all_courses(ClassroomService.DEFAULT_FACULTY_ID)
    c1 = next(c for c in courses if "CSE 101" in c.name)

    # Inspect c1 enrollments (67 students)
    with db_session() as conn:
        c1_count = conn.execute("SELECT COUNT(*) as c FROM course_enrollments WHERE course_id = ?", (c1.id,)).fetchone()["c"]

    assert c1_count == 67

def test_separate_consolidated_workbook_per_classroom():
    """Verifies that each classroom has a dedicated separate workbook file in workbooks/."""
    courses = ClassroomService.get_all_courses(ClassroomService.DEFAULT_FACULTY_ID)
    workbook_paths = [c.excel_workbook_path for c in courses]

    # Each course must have a non-null distinct workbook path
    assert all(wb is not None for wb in workbook_paths)
    assert len(set(workbook_paths)) == len(courses), "Classrooms must not share workbook files!"

    # Verify filenames correspond to course slugs
    for c in courses:
        slug = re.sub(r'[^a-z0-9]+', '_', c.name.lower()).strip('_')
        assert slug in c.excel_workbook_path.lower()

def test_shared_faculty_dashboard_stats():
    """Verifies aggregated metrics for the faculty dashboard."""
    stats = ClassroomService.get_faculty_dashboard_stats(ClassroomService.DEFAULT_FACULTY_ID)
    assert stats["total_classrooms"] >= 1
    assert stats["total_students"] >= 67
    assert stats["total_assignments"] >= 9
    assert len(stats["classrooms"]) >= 1
