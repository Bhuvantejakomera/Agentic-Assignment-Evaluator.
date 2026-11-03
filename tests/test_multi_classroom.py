import pytest
from backend.app.database import init_db, db_session
from backend.app.services.classroom_service import ClassroomService

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    ClassroomService.seed_initial_classrooms_if_empty()

def test_classroom_discovery_returns_four_courses():
    courses = ClassroomService.get_all_courses(ClassroomService.DEFAULT_FACULTY_ID)
    assert len(courses) >= 4
    course_names = [c.name for c in courses]
    assert "Programming in C" in course_names
    assert "Data Structures" in course_names
    assert "Python Programming" in course_names
    assert "Artificial Intelligence" in course_names

def test_classroom_scoped_assignments():
    courses = ClassroomService.get_all_courses(ClassroomService.DEFAULT_FACULTY_ID)
    c1 = next(c for c in courses if c.name == "Programming in C")
    c2 = next(c for c in courses if c.name == "Data Structures")

    c1_assignments = ClassroomService.get_assignments_for_course(c1.id)
    c2_assignments = ClassroomService.get_assignments_for_course(c2.id)

    # Scoped: c1 must have Lab assignments, c2 has DS assignments
    assert len(c1_assignments) >= 4
    assert any("Lab 1" in a.title for a in c1_assignments)

    assert len(c2_assignments) >= 2
    assert any("Assignment 2" in a.title for a in c2_assignments)

    # Verify no cross-mixing of assignment IDs
    c1_ids = {a.id for a in c1_assignments}
    c2_ids = {a.id for a in c2_assignments}
    assert c1_ids.isdisjoint(c2_ids)

def test_switching_classrooms_preserves_independent_state():
    courses = ClassroomService.get_all_courses(ClassroomService.DEFAULT_FACULTY_ID)
    c1 = next(c for c in courses if c.name == "Programming in C")
    c2 = next(c for c in courses if c.name == "Data Structures")

    # Inspect c1 enrollments
    with db_session() as conn:
        c1_count = conn.execute("SELECT COUNT(*) as c FROM course_enrollments WHERE course_id = ?", (c1.id,)).fetchone()["c"]
        c2_count = conn.execute("SELECT COUNT(*) as c FROM course_enrollments WHERE course_id = ?", (c2.id,)).fetchone()["c"]

    assert c1_count == 66
    assert c2_count == 60
