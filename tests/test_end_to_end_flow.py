import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import init_db
from backend.app.services.classroom_service import ClassroomService

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_all():
    init_db()
    ClassroomService.seed_initial_classrooms_if_empty()

def test_complete_multi_classroom_end_to_end_scenario():
    """
    Complete end-to-end multi-classroom evaluation scenario:
    1. Faculty authenticates and discovers 4 classrooms.
    2. Faculty selects Classroom A (Programming in C - CSE-A).
    3. Faculty selects Lab 1 – Algorithms & Flowcharts.
    4. Faculty verifies and approves rubric for Lab 1.
    5. Faculty initiates automated evaluation of all submissions (66 students).
    6. Faculty reviews results (evaluations, wrong PDF detections, late penalties).
    7. Faculty generates and exports consolidated Excel report for Classroom A.
    8. Faculty switches to Classroom B (Data Structures - CSE-B).
    9. Faculty selects Assignment 2 (Stack & Queue Implementations).
    10. Faculty approves a distinct rubric for Assignment 2 and evaluates submissions.
    11. Faculty exports a separate report for Classroom B.
    12. State verification: Both evaluation histories remain completely intact in DB.
    13. Faculty returns to Classroom A, views Lab 1 evaluations without reprocessing.
    14. Faculty authorizes publishing for Lab 1 after verification.
    15. Grades are successfully published.
    """

    # --- Phase 1: Authentication & Classroom Discovery ---
    auth_res = client.get("/api/auth/faculty")
    assert auth_res.status_code == 200
    faculty_data = auth_res.json()
    assert faculty_data["name"] == "Prof. Bhuvan Teja"

    classrooms_res = client.get("/api/classrooms")
    assert classrooms_res.status_code == 200
    classrooms = classrooms_res.json()["courses"]
    assert len(classrooms) >= 4

    course_a = next(c for c in classrooms if c["name"] == "Programming in C")
    course_b = next(c for c in classrooms if c["name"] == "Data Structures")
    assert course_a["section"] == "CSE-A"
    assert course_b["section"] == "CSE-B"
    assert course_a["excel_workbook_path"] != course_b["excel_workbook_path"], "Classrooms must use separate workbooks!"

    # Shared faculty dashboard stats
    dash_res = client.get("/api/classrooms/dashboard/stats")
    assert dash_res.status_code == 200
    assert dash_res.json()["total_classrooms"] == 4

    # --- Phase 2: Select Classroom A, Inspect Lab 1 ---
    assign_a_res = client.get(f"/api/classrooms/{course_a['id']}/assignments")
    assert assign_a_res.status_code == 200
    assignments_a = assign_a_res.json()
    lab1 = next(a for a in assignments_a if "Lab 1" in a["title"])

    # --- Phase 3: Rubric Generation & Faculty Approval for Lab 1 ---
    gen_rubric_res = client.post(
        f"/api/classrooms/{course_a['id']}/assignments/{lab1['id']}/rubric/generate",
        json={"course_id": course_a["id"], "assignment_id": lab1["id"]}
    )
    assert gen_rubric_res.status_code == 200
    criteria_a = gen_rubric_res.json()
    assert len(criteria_a) >= 3

    # Save rubric
    save_rubric_res = client.post(
        f"/api/classrooms/{course_a['id']}/assignments/{lab1['id']}/rubric/save",
        json={
            "course_id": course_a["id"],
            "assignment_id": lab1["id"],
            "criteria": criteria_a,
            "total_max_marks": 100.0,
            "late_penalty_percent": 20.0
        }
    )
    assert save_rubric_res.status_code == 200
    assert save_rubric_res.json()["status"] == "DRAFT"

    # Approve rubric (faculty authority)
    approve_rub_res = client.post(f"/api/classrooms/{course_a['id']}/assignments/{lab1['id']}/rubric/approve")
    assert approve_rub_res.status_code == 200
    assert approve_rub_res.json()["status"] == "APPROVED"

    # --- Phase 4: Execute Evaluation for Classroom A, Lab 1 ---
    eval_a_res = client.post(f"/api/classrooms/{course_a['id']}/assignments/{lab1['id']}/evaluate")
    assert eval_a_res.status_code == 200
    eval_a_data = eval_a_res.json()
    assert eval_a_data["status"] == "COMPLETED"
    assert eval_a_data["stats"]["total_evaluated"] == 66
    assert eval_a_data["stats"]["wrong_submission_count"] >= 3
    assert eval_a_data["stats"]["late_count"] >= 2

    # --- Phase 5: Faculty Review & Grade Approval ---
    get_evals_a = client.get(f"/api/classrooms/{course_a['id']}/assignments/{lab1['id']}/evaluations")
    assert get_evals_a.status_code == 200
    evals_list_a = get_evals_a.json()
    assert len(evals_list_a) == 66

    # Verify wrong submission detection on Adityaraj A
    adityaraj = next(e for e in evals_list_a if e["student_id"] == "AP26110010541")
    assert "WRONG_PDF" in adityaraj["flags"]
    assert "wrong pdf" in adityaraj["faculty_remarks"].lower()

    # Batch approve all evaluated students
    batch_app_res = client.post(
        f"/api/classrooms/{course_a['id']}/assignments/{lab1['id']}/batch-approve",
        json={"course_id": course_a["id"], "assignment_id": lab1["id"]}
    )
    assert batch_app_res.status_code == 200
    assert batch_app_res.json()["approved_count"] == 66

    # --- Phase 6: Export Excel Report for Classroom A ---
    export_a_res = client.post(
        f"/api/classrooms/{course_a['id']}/assignments/{lab1['id']}/excel/export?target_column_name=Lab-1"
    )
    assert export_a_res.status_code == 200
    assert export_a_res.json()["status"] == "success"
    assert export_a_res.json()["total_records_updated"] == 66

    # Verify Classroom A workbook has assignment-wise sheet "Lab-1 Details"
    wb_a_info = client.get(f"/api/classrooms/{course_a['id']}/workbook/info").json()
    assert any("Lab-1" in s for s in wb_a_info["sheets"])

    # --- Phase 7: Switch to Classroom B (Data Structures), Assignment 2 ---
    assign_b_res = client.get(f"/api/classrooms/{course_b['id']}/assignments")
    assert assign_b_res.status_code == 200
    assignments_b = assign_b_res.json()
    assign2_b = next(a for a in assignments_b if "Assignment 2" in a["title"])

    # Generate and approve rubric for Assignment 2
    gen_rubric_b = client.post(
        f"/api/classrooms/{course_b['id']}/assignments/{assign2_b['id']}/rubric/generate",
        json={"course_id": course_b["id"], "assignment_id": assign2_b["id"]}
    )
    criteria_b = gen_rubric_b.json()
    client.post(
        f"/api/classrooms/{course_b['id']}/assignments/{assign2_b['id']}/rubric/save",
        json={
            "course_id": course_b["id"],
            "assignment_id": assign2_b["id"],
            "criteria": criteria_b,
            "total_max_marks": 100.0,
            "late_penalty_percent": 15.0
        }
    )
    client.post(f"/api/classrooms/{course_b['id']}/assignments/{assign2_b['id']}/rubric/approve")

    # Evaluate Assignment 2 in Classroom B
    eval_b_res = client.post(f"/api/classrooms/{course_b['id']}/assignments/{assign2_b['id']}/evaluate")
    assert eval_b_res.status_code == 200
    assert eval_b_res.json()["stats"]["total_evaluated"] == 60

    # Batch approve and export Excel for Classroom B
    client.post(
        f"/api/classrooms/{course_b['id']}/assignments/{assign2_b['id']}/batch-approve",
        json={"course_id": course_b["id"], "assignment_id": assign2_b["id"]}
    )
    export_b_res = client.post(
        f"/api/classrooms/{course_b['id']}/assignments/{assign2_b['id']}/excel/export?target_column_name=Assignment-2"
    )
    assert export_b_res.status_code == 200

    # Verify Classroom B workbook has Assignment-2 Details and does NOT mix with Lab-1
    wb_b_info = client.get(f"/api/classrooms/{course_b['id']}/workbook/info").json()
    assert any("Assignment-2" in s for s in wb_b_info["sheets"])
    assert not any("Lab-1" in s for s in wb_b_info["sheets"]), "Classroom B must not contain Classroom A sheets!"

    # --- Phase 8: Return to Classroom A & Verify History Intact Without Reprocessing ---
    # Retrieve evaluations for Classroom A, Lab 1
    reload_evals_a = client.get(f"/api/classrooms/{course_a['id']}/assignments/{lab1['id']}/evaluations")
    assert reload_evals_a.status_code == 200
    reloaded_data = reload_evals_a.json()
    assert len(reloaded_data) == 66
    # All 66 must still be approved
    assert all(e["faculty_approved"] for e in reloaded_data)

    # --- Phase 9: Publishing Verification & Authorization ---
    # Without faculty confirmation -> Must fail with 400
    unauth_pub = client.post(
        f"/api/classrooms/{course_a['id']}/assignments/{lab1['id']}/publish",
        json={"course_id": course_a["id"], "assignment_id": lab1["id"], "faculty_confirmation": False}
    )
    assert unauth_pub.status_code == 400

    # With faculty confirmation -> Succeeds!
    auth_pub = client.post(
        f"/api/classrooms/{course_a['id']}/assignments/{lab1['id']}/publish",
        json={"course_id": course_a["id"], "assignment_id": lab1["id"], "faculty_confirmation": True, "return_submissions": True}
    )
    assert auth_pub.status_code == 200
    pub_data = auth_pub.json()
    assert pub_data["success"] is True
    assert pub_data["total_published"] == 66

    # Verify assignment status in DB is PUBLISHED
    check_assign = client.get(f"/api/classrooms/{course_a['id']}/assignments/{lab1['id']}")
    assert check_assign.json()["status"] == "PUBLISHED"
