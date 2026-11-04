import pytest
import tempfile
from pathlib import Path
from backend.app.config import SUBMISSIONS_DIR, DEFAULT_EXCEL_TEMPLATE
from backend.app.agents.security import SecureDriveHandler, DriveSecurityError
from backend.app.agents.classroom_agent import ClassroomAgent
from backend.app.agents.submission_agent import SubmissionAgent
from backend.app.agents.evaluator_agent import EvaluationAgent
from backend.app.models.rubric import RubricResponse, CriterionModel
from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel

def test_drive_security_path_traversal_prevention():
    # Attempt directory traversal attacks
    bad_filenames = [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\cmd.exe",
        "/absolute/path/file.pdf",
        "sub/folder/../../evil.pdf"
    ]
    for bad_fn in bad_filenames:
        if "cmd.exe" in bad_fn:
            with pytest.raises(DriveSecurityError):
                SecureDriveHandler.sanitize_filename(bad_fn)
        else:
            clean = SecureDriveHandler.sanitize_filename(bad_fn)
            assert "/" not in clean
            assert "\\" not in clean
            assert ".." not in clean

def test_drive_security_blocked_extensions():
    dangerous_files = ["malicious.exe", "script.sh", "run.bat", "payload.so", "inject.dylib"]
    for danger in dangerous_files:
        with pytest.raises(DriveSecurityError):
            SecureDriveHandler.sanitize_filename(danger)

def test_secure_destination_path_sandboxed():
    dest = SecureDriveHandler.get_secure_destination_path(
        course_id="crs-101",
        assignment_id="asg-202",
        student_id="AP26110010495",
        filename="report.pdf"
    )
    # Must be strictly inside SUBMISSIONS_DIR
    assert dest.is_relative_to(SUBMISSIONS_DIR.resolve())
    assert dest.name == "report.pdf"

def test_classroom_agent_identity_parsing():
    raw = "Sayanthkumar D | AP26110010495"
    name, roll = ClassroomAgent.parse_student_identity(raw, "116539029070819105982")
    assert name == "Sayanthkumar D"
    assert roll == "AP26110010495"

    # Fallback when no delimiter exists
    raw_fallback = "John Doe"
    name2, roll2 = ClassroomAgent.parse_student_identity(raw_fallback, "123456789")
    assert name2 == "John Doe"
    assert roll2 == "123456789"

def test_submission_agent_prepare_and_triage():
    # Empty attachments -> flagged as MISSING
    extracted, flags = SubmissionAgent.prepare_and_extract_submission(
        course_id="crs-test",
        assignment_id="asg-test",
        student_id="AP26110010495",
        attachments=[]
    )
    assert "MISSING" in flags
    assert extracted.text_content == ""

def test_evaluation_agent_grades_submission():
    rubric = RubricResponse(
        id="rub-test",
        course_id="c1",
        assignment_id="a1",
        version=1,
        status="APPROVED",
        total_max_marks=100.0,
        late_penalty_percent=20.0,
        criteria=[
            CriterionModel(id="c1", name="Algorithm & Concept", max_marks=50.0, description="Explain concept and steps", component_type="algorithm"),
            CriterionModel(id="c2", name="C Implementation", max_marks=50.0, description="C code implementation", component_type="programming")
        ],
        created_at="2026-11-03T10:00:00"
    )

    extracted = ExtractedContentModel(
        text_content="Concept of Circular Queue: Overcomes linear queue limitation using modulo arithmetic. Step 1: Enqueue: (rear + 1) % SIZE. Step 2: Dequeue: (front + 1) % SIZE.",
        code_snippets=[{"language": "c", "code": "#include <stdio.h>\nint main() { printf(\"Queue ready\\n\"); return 0; }"}]
    )

    res = EvaluationAgent.evaluate_submission(
        run_id="run-test",
        course_id="c1",
        assignment_id="a1",
        student_id="AP26110010495",
        student_name="Sayanthkumar D",
        submission_id="sub-101",
        state="TURNED_IN",
        is_late=False,
        attachments=[SubmissionAttachment(filename="code.c", file_type="C", is_readable=True)],
        extracted_content=extracted,
        rubric=rubric
    )

    assert res.student_id == "AP26110010495"
    assert res.student_name == "Sayanthkumar D"
    assert res.final_score > 0
    assert len(res.criteria_breakdown) == 2

def test_file_safety_validation():
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b"%PDF-1.4 test content")
        f.flush()
        is_safe, err = SecureDriveHandler.validate_file_safety(Path(f.name))
        assert is_safe is True
        assert err is None

    # Blocked extension should fail safety validation
    with tempfile.NamedTemporaryFile(suffix=".part") as f:
        f.write(b"part content")
        f.flush()
        is_safe, err = SecureDriveHandler.validate_file_safety(Path(f.name))
        assert is_safe is False
        assert "disallowed" in err.lower()

