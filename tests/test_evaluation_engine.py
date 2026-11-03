import pytest
from backend.app.models.rubric import RubricResponse, CriterionModel
from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel
from backend.app.services.evaluation_engine import EvaluationEngine

@pytest.fixture
def sample_rubric():
    criteria = [
        CriterionModel(id="c1", name="Algorithm", description="Step-by-step logic", max_marks=30.0, evaluation_type="algorithm"),
        CriterionModel(id="c2", name="Flowchart", description="Visual logic diagram", max_marks=20.0, evaluation_type="diagram_flowchart"),
        CriterionModel(id="c3", name="Code Implementation", description="C program code", max_marks=50.0, evaluation_type="code_execution")
    ]
    return RubricResponse(
        id="rub-test-1",
        course_id="crs-1",
        assignment_id="assign-1",
        version=1,
        status="APPROVED",
        criteria=criteria,
        total_max_marks=100.0,
        late_penalty_percent=20.0,
        created_at="2026-11-03T10:00:00"
    )

def test_full_correct_submission(sample_rubric):
    text = (
        "Algorithm:\nStep 1: Start\nStep 2: Read N\nStep 3: Print result\n"
        "Flowchart structure: Oval start -> Rectangle input -> Diamond branch -> Oval stop\n"
        "C Program code attached."
    )
    code = [{"language": "c", "code": "#include <stdio.h>\nint main() { printf(\"Test\"); return 0; }"}]
    extracted = ExtractedContentModel(text_content=text, code_snippets=code, word_count=len(text.split()))

    res = EvaluationEngine.evaluate_submission(
        run_id="run-1",
        course_id="crs-1",
        assignment_id="assign-1",
        student_id="AP101",
        student_name="Test Student",
        submission_id="sub-1",
        state="TURNED_IN",
        is_late=False,
        attachments=[SubmissionAttachment(filename="lab.c", file_type="C", file_path="/tmp/lab.c", is_readable=True)],
        extracted_content=extracted,
        rubric=sample_rubric,
        assignment_title="Lab 1 - Prime Numbers",
        assignment_description="Algorithm, Flowchart and C program"
    )

    assert res.final_score >= 90.0
    assert not res.flags

def test_partial_submission_missing_flowchart(sample_rubric):
    text = "Algorithm:\nStep 1: Start\nStep 2: Read N\nStep 3: Print result"
    code = [{"language": "c", "code": "#include <stdio.h>\nint main() { return 0; }"}]
    extracted = ExtractedContentModel(text_content=text, code_snippets=code, word_count=len(text.split()))

    res = EvaluationEngine.evaluate_submission(
        run_id="run-1",
        course_id="crs-1",
        assignment_id="assign-1",
        student_id="AP102",
        student_name="Partial Student",
        submission_id="sub-2",
        state="TURNED_IN",
        is_late=False,
        attachments=[SubmissionAttachment(filename="code.c", file_type="C", file_path="/tmp/code.c", is_readable=True)],
        extracted_content=extracted,
        rubric=sample_rubric,
        assignment_title="Lab 1 - Prime Numbers",
        assignment_description="Algorithm, Flowchart and C program"
    )

    # Flowchart criterion should be 0, total around 70-80
    fc_crit = next(c for c in res.criteria_breakdown if c.criterion_id == "c2")
    assert fc_crit.awarded_marks == 0.0
    assert "INCOMPLETE" in res.flags

def test_wrong_submission_detection(sample_rubric):
    text = "Title: Determination of Planck's Constant using Photoelectric Effect. Physics experiment."
    extracted = ExtractedContentModel(text_content=text, code_snippets=[], word_count=len(text.split()))

    res = EvaluationEngine.evaluate_submission(
        run_id="run-1",
        course_id="crs-1",
        assignment_id="assign-1",
        student_id="AP103",
        student_name="Wrong PDF Student",
        submission_id="sub-3",
        state="TURNED_IN",
        is_late=False,
        attachments=[SubmissionAttachment(filename="physics.pdf", file_type="PDF", file_path="/tmp/p.pdf", is_readable=True)],
        extracted_content=extracted,
        rubric=sample_rubric,
        assignment_title="Lab 1 - Prime Numbers",
        assignment_description="Algorithm, Flowchart and C program in C"
    )

    assert res.final_score == 0.0
    assert "WRONG_PDF" in res.flags
    assert "wrong pdf" in res.faculty_remarks.lower()

def test_late_submission_penalty(sample_rubric):
    text = (
        "Algorithm:\nStep 1: Start\nStep 2: Read N\n"
        "Flowchart structure: Oval start -> Rectangle -> Oval stop\n"
    )
    code = [{"language": "c", "code": "#include <stdio.h>\nint main() { return 0; }"}]
    extracted = ExtractedContentModel(text_content=text, code_snippets=code, word_count=len(text.split()))

    res = EvaluationEngine.evaluate_submission(
        run_id="run-1",
        course_id="crs-1",
        assignment_id="assign-1",
        student_id="AP104",
        student_name="Late Student",
        submission_id="sub-4",
        state="TURNED_IN",
        is_late=True,
        attachments=[SubmissionAttachment(filename="code.c", file_type="C", file_path="/tmp/code.c", is_readable=True)],
        extracted_content=extracted,
        rubric=sample_rubric,
        assignment_title="Lab 1 - Prime Numbers",
        assignment_description="Algorithm, Flowchart and C program"
    )

    assert "LATE" in res.flags
    assert res.late_penalty > 0
    assert "Late" in res.faculty_remarks
