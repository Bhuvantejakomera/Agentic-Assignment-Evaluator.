import pytest
from backend.app.services.collusion_detector import CollusionDetector
from backend.app.models.evaluation import EvaluationResultResponse

def test_clean_code():
    raw_code = """
    // Single line comment
    /* Multi
       line comment */
    1: #include <stdio.h>
    2: int main() {
    3:     int a = 10; // inline comment
    4:     return 0;
    5: }
    """
    cleaned = CollusionDetector.clean_code(raw_code)
    assert "//" not in cleaned
    assert "/*" not in cleaned
    assert "main()" in cleaned
    assert "int a = 10;" in cleaned
    assert "1:" not in cleaned
    assert "2:" not in cleaned

def test_extract_terminal_prompts():
    text = "Compilation output:\nshantanu@SHANTANUs-MacBook-Air lab3 % gcc code.c -o out\nuser@localhost output"
    prompts = CollusionDetector.extract_terminal_prompts(text)
    assert "shantanu@SHANTANUs-MacBook-Air" in prompts
    assert "user@localhost" not in prompts  # Generic filtered out

def test_are_submissions_duplicate_attachment_match():
    item_a = {"att_hashes": {"abc123hash", "def456hash"}}
    item_b = {"att_hashes": {"xyz789hash", "abc123hash"}}
    is_dup, reason = CollusionDetector.are_submissions_duplicate(item_a, item_b)
    assert is_dup is True
    assert "cryptographic" in reason

def test_are_submissions_duplicate_code_match():
    code = "int sum = 0; for(int i=0; i<n; i++) sum += i; printf(\"%d\", sum);"
    hash_code = "sample_code_hash_123"
    item_a = {"code_hash": hash_code, "code_clean": code}
    item_b = {"code_hash": hash_code, "code_clean": code}
    is_dup, reason = CollusionDetector.are_submissions_duplicate(item_a, item_b)
    assert is_dup is True
    assert "logic match" in reason

def test_are_submissions_duplicate_terminal_fingerprint():
    item_a = {"prompts": {"adityakumar@Adityas-MacBook-Air"}}
    item_b = {"prompts": {"adityakumar@Adityas-MacBook-Air"}}
    is_dup, reason = CollusionDetector.are_submissions_duplicate(item_a, item_b)
    assert is_dup is True
    assert "Adityas-MacBook-Air" in reason

def test_independent_submissions_not_duplicate():
    item_a = {
        "att_hashes": {"hash_aaa"},
        "code_hash": "hash_code_aaa",
        "code_clean": "int a = 1; printf(\"%d\", a);",
        "prompts": {"alice@macbook"}
    }
    item_b = {
        "att_hashes": {"hash_bbb"},
        "code_hash": "hash_code_bbb",
        "code_clean": "float x = 2.5; return x * 2.0;",
        "prompts": {"bob@fedora"}
    }
    is_dup, _ = CollusionDetector.are_submissions_duplicate(item_a, item_b)
    assert is_dup is False

def test_chronological_penalty_first_submitter_retains_marks_copies_penalized_20():
    # Setup mock evaluated list
    eval_a = EvaluationResultResponse(
        id="eval-1",
        run_id="run-1",
        course_id="c1",
        assignment_id="a1",
        student_id="S001",
        student_name="Student Early",
        raw_score=90.0,
        late_penalty=0.0,
        final_score=90.0,
        faculty_adjusted_score=None,
        faculty_approved=False,
        faculty_remarks=None,
        criteria_breakdown=[],
        code_execution_results=None,
        flags=[],
        attachments=[],
        overall_feedback="Good",
        evaluated_at="2026-10-07T12:00:00Z"
    )
    eval_b = EvaluationResultResponse(
        id="eval-2",
        run_id="run-1",
        course_id="c1",
        assignment_id="a1",
        student_id="S002",
        student_name="Student Copied One",
        raw_score=90.0,
        late_penalty=0.0,
        final_score=90.0,
        faculty_adjusted_score=None,
        faculty_approved=False,
        faculty_remarks=None,
        criteria_breakdown=[],
        code_execution_results=None,
        flags=[],
        attachments=[],
        overall_feedback="Good",
        evaluated_at="2026-10-07T14:00:00Z"
    )
    eval_c = EvaluationResultResponse(
        id="eval-3",
        run_id="run-1",
        course_id="c1",
        assignment_id="a1",
        student_id="S003",
        student_name="Student Copied Two",
        raw_score=15.0,
        late_penalty=0.0,
        final_score=15.0,
        faculty_adjusted_score=None,
        faculty_approved=False,
        faculty_remarks=None,
        criteria_breakdown=[],
        code_execution_results=None,
        flags=[],
        attachments=[],
        overall_feedback="Partial",
        evaluated_at="2026-10-08T09:00:00Z"
    )

    import json
    shared_code = "int x = 100; int y = 200; printf(\"%d\", x + y); " * 10
    ext_payload = json.dumps({"code_snippets": [{"code": shared_code}]})
    submissions_records = [
        {
            "student_id": "S001",
            "student_name": "Student Early",
            "submission_time": "2026-10-07T10:00:00Z",
            "extracted_content_json": ext_payload
        },
        {
            "student_id": "S002",
            "student_name": "Student Copied One",
            "submission_time": "2026-10-07T14:00:00Z",
            "extracted_content_json": ext_payload
        },
        {
            "student_id": "S003",
            "student_name": "Student Copied Two",
            "submission_time": "2026-10-08T09:00:00Z",
            "extracted_content_json": ext_payload
        }
    ]

    evaluated_list, clusters = CollusionDetector.process_collusion(
        [eval_a, eval_b, eval_c], submissions_records, penalty_amount=20.0
    )

    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["original_author"]["student_id"] == "S001"
    assert len(cluster["copied_students"]) == 2

    # S001 (Earliest submitter) -> 0 deduction, marked ORIGINAL_SUBMISSION
    assert eval_a.final_score == 90.0
    assert "ORIGINAL_SUBMISSION" in eval_a.flags
    assert "DUPLICATE" not in eval_a.flags
    assert "Original author" in eval_a.faculty_remarks

    # S002 (Submitted later) -> -20 deduction, marked DUPLICATE
    assert eval_b.final_score == 70.0
    assert "DUPLICATE" in eval_b.flags
    assert "ORIGINAL_SUBMISSION" not in eval_b.flags
    assert "Copied from Student Early" in eval_b.faculty_remarks
    assert "penalty applied: -20" in eval_b.faculty_remarks

    # S003 (Submitted next day, initial score 15.0) -> capped at 0.0 minimum
    assert eval_c.final_score == 0.0
    assert "DUPLICATE" in eval_c.flags
    assert "Copied from Student Early" in eval_c.faculty_remarks
