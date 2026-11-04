import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import init_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_all():
    init_db()

def test_complete_classroom_end_to_end_scenario():
    """
    End-to-end evaluation scenario using real faculty identity and course data:
    1. Faculty authenticates (Bhuvan Teja K | AP25122040016 / bhuvan_k@srmap.edu.in).
    2. Faculty retrieves classrooms (CSE 101 - FUNDAMENTALS OF COMPUTING AND PROGRAMMING IN C).
    3. Faculty selects Lab-1.
    4. Faculty verifies and approves rubric for Lab-1.
    5. Faculty initiates automated evaluation of all submissions (67 students).
    6. Faculty reviews results (evaluations, triage flags, remarks).
    7. Faculty batch-approves evaluations.
    8. Faculty exports consolidated Excel report.
    9. Faculty authorizes publishing with confirmation guardrail.
    """

    # --- Phase 1: Authentication & Classroom Discovery ---
    auth_res = client.get("/api/auth/faculty")
    assert auth_res.status_code == 200
    faculty_data = auth_res.json()
    assert faculty_data["email"] == "bhuvan_k@srmap.edu.in"
    assert "Bhuvan Teja" in faculty_data["name"]

    classrooms_res = client.get("/api/classrooms")
    assert classrooms_res.status_code == 200
    classrooms = classrooms_res.json()["courses"]
    assert len(classrooms) >= 1

    course = next(c for c in classrooms if "CSE 101" in c["name"])
    assert course["excel_workbook_path"] is not None

    # Shared faculty dashboard stats
    dash_res = client.get("/api/classrooms/dashboard/stats")
    assert dash_res.status_code == 200
    assert dash_res.json()["total_students"] >= 67

    # --- Phase 2: Inspect Assignments & Select Lab-1 ---
    assign_res = client.get(f"/api/classrooms/{course['id']}/assignments")
    assert assign_res.status_code == 200
    assignments = assign_res.json()
    assert len(assignments) >= 5
    lab1 = next(a for a in assignments if "Lab-1" in a["title"] or "Lab 1" in a["title"])

    # --- Phase 3: Rubric Generation & Faculty Approval for Lab-1 ---
    gen_rubric_res = client.post(
        f"/api/classrooms/{course['id']}/assignments/{lab1['id']}/rubric/generate",
        json={"course_id": course["id"], "assignment_id": lab1["id"]}
    )
    assert gen_rubric_res.status_code == 200
    criteria = gen_rubric_res.json()
    assert len(criteria) >= 2

    # Save rubric
    save_rubric_res = client.post(
        f"/api/classrooms/{course['id']}/assignments/{lab1['id']}/rubric/save",
        json={
            "course_id": course["id"],
            "assignment_id": lab1["id"],
            "criteria": criteria,
            "total_max_marks": 100.0,
            "late_penalty_percent": 20.0
        }
    )
    assert save_rubric_res.status_code == 200
    assert save_rubric_res.json()["status"] == "DRAFT"

    # Approve rubric (faculty authority)
    approve_rub_res = client.post(f"/api/classrooms/{course['id']}/assignments/{lab1['id']}/rubric/approve")
    assert approve_rub_res.status_code == 200
    assert approve_rub_res.json()["status"] == "APPROVED"

    # --- Phase 4: Execute Evaluation for Lab-1 ---
    eval_res = client.post(f"/api/classrooms/{course['id']}/assignments/{lab1['id']}/evaluate")
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["status"] == "COMPLETED"
    assert eval_data["stats"]["total_evaluated"] == 67

    # --- Phase 5: Faculty Review & Grade Approval ---
    get_evals = client.get(f"/api/classrooms/{course['id']}/assignments/{lab1['id']}/evaluations")
    assert get_evals.status_code == 200
    evals_list = get_evals.json()
    assert len(evals_list) == 67

    # Batch approve all evaluated students
    batch_app_res = client.post(
        f"/api/classrooms/{course['id']}/assignments/{lab1['id']}/batch-approve",
        json={"course_id": course["id"], "assignment_id": lab1["id"]}
    )
    assert batch_app_res.status_code == 200
    assert batch_app_res.json()["approved_count"] == 67

    # --- Phase 6: Export Excel Report ---
    export_res = client.post(
        f"/api/classrooms/{course['id']}/assignments/{lab1['id']}/excel/export?target_column_name=Lab-1"
    )
    assert export_res.status_code == 200
    assert export_res.json()["status"] == "success"
    assert export_res.json()["total_records_updated"] == 67

    # --- Phase 7: History Intact Without Reprocessing ---
    reload_evals = client.get(f"/api/classrooms/{course['id']}/assignments/{lab1['id']}/evaluations")
    assert reload_evals.status_code == 200
    reloaded_data = reload_evals.json()
    assert len(reloaded_data) == 67
    assert all(e["faculty_approved"] for e in reloaded_data)

    # --- Phase 8: Publishing Verification & Authorization ---
    # Without faculty confirmation -> Must fail with 400
    unauth_pub = client.post(
        f"/api/classrooms/{course['id']}/assignments/{lab1['id']}/publish",
        json={"course_id": course["id"], "assignment_id": lab1["id"], "faculty_confirmation": False}
    )
    assert unauth_pub.status_code == 400

    # With faculty confirmation -> Succeeds!
    auth_pub = client.post(
        f"/api/classrooms/{course['id']}/assignments/{lab1['id']}/publish",
        json={"course_id": course["id"], "assignment_id": lab1["id"], "faculty_confirmation": True, "return_submissions": True}
    )
    assert auth_pub.status_code == 200
    pub_data = auth_pub.json()
    assert pub_data["success"] is True
    assert pub_data["total_published"] == 67

    # Verify assignment status in DB is PUBLISHED
    check_assign = client.get(f"/api/classrooms/{course['id']}/assignments/{lab1['id']}")
    assert check_assign.json()["status"] == "PUBLISHED"
