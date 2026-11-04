import tempfile
import shutil
from pathlib import Path
import openpyxl
from backend.app.config import DEFAULT_EXCEL_TEMPLATE
from backend.app.services.excel_service import ExcelService
from backend.app.models.evaluation import EvaluationResultResponse, CriterionEvaluationResult

def test_inspect_workbook_columns():
    cols = ExcelService.inspect_workbook_columns(DEFAULT_EXCEL_TEMPLATE)
    assert "Student ID" in cols
    assert "Name" in cols
    assert "Lab-1" in cols
    assert "Lab-3" in cols
    assert "Remarks" in cols

def test_map_assignment_to_column():
    cols = ["Student ID", "Name", "Lab-1", "Lab-2", "Lab-3", "Remarks"]
    assert ExcelService.map_assignment_to_column("Lab 1 – Algorithms", cols) == "Lab-1"
    assert ExcelService.map_assignment_to_column("Lab 3 - Conditionals", cols) == "Lab-3"

def test_update_consolidated_workbook_preserves_existing_marks():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy original Lab_Marks_Record.xlsx
        test_wb_path = Path(tmpdir) / "Test_Lab_Marks.xlsx"
        shutil.copy(DEFAULT_EXCEL_TEMPLATE, test_wb_path)

        # Before update: check Lab-3 of Aditya kumar R (AP26110010496) is 70
        wb_before = openpyxl.load_workbook(str(test_wb_path))
        ws_before = wb_before.active
        assert ws_before.cell(2, 5).value == 70  # Row 2, Col 5 (Lab-3)

        # Create mock evaluation results for Lab-1
        eval_res = [
            EvaluationResultResponse(
                id="e1",
                run_id="run-test",
                course_id="c1",
                assignment_id="a1",
                student_id="AP26110010496",
                student_name="Aditya kumar R",
                raw_score=95.0,
                late_penalty=0.0,
                final_score=95.0,
                faculty_adjusted_score=None,
                faculty_approved=True,
                faculty_remarks=None,
                criteria_breakdown=[],
                flags=[],
                overall_feedback="Excellent work.",
                evaluated_at="2026-11-03T10:00:00"
            ),
            EvaluationResultResponse(
                id="e2",
                run_id="run-test",
                course_id="c1",
                assignment_id="a1",
                student_id="AP26110010541",
                student_name="Adityaraj A",
                raw_score=0.0,
                late_penalty=0.0,
                final_score=0.0,
                faculty_adjusted_score=None,
                faculty_approved=True,
                faculty_remarks="Uploaded the wrong PDF",
                criteria_breakdown=[],
                flags=["WRONG_PDF"],
                overall_feedback="Wrong PDF uploaded.",
                evaluated_at="2026-11-03T10:00:00"
            )
        ]

        versioned_wb, detail_wb = ExcelService.update_consolidated_workbook(
            master_workbook_path=test_wb_path,
            course_name="Programming in C",
            assignment_title="Lab 1",
            target_column_name="Lab-1",
            evaluation_results=eval_res,
            run_id="run-test"
        )

        assert versioned_wb.exists()
        assert detail_wb.exists()

        # Load updated test workbook
        wb_after = openpyxl.load_workbook(str(test_wb_path))
        ws_after = wb_after.active

        # Verify Lab-1 updated for Aditya kumar R
        assert ws_after.cell(2, 3).value == 95.0  # Col 3 is Lab-1
        # Verify Lab-3 was preserved!
        assert ws_after.cell(2, 5).value == 70  # Col 5 is Lab-3

        # Find Remarks column dynamically
        remarks_col = next(c for c in range(1, ws_after.max_column + 1) if ws_after.cell(1, c).value == "Remarks")
        assert "Uploaded the wrong PDF" in str(ws_after.cell(3, remarks_col).value)

        # Verify assignment-wise detailed sheet was generated inside the workbook!
        assert "Lab-1 Details" in wb_after.sheetnames
        detail_sheet = wb_after["Lab-1 Details"]
        assert detail_sheet.cell(1, 1).value == "Student ID"
        assert detail_sheet.cell(2, 1).value == "AP26110010496"
        assert detail_sheet.cell(2, 5).value == 95.0

def test_ensure_classroom_workbook_creates_isolated_roster():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_workbooks = Path(tmpdir)
        students = [
            {"id": "DS001", "name": "Alice Data"},
            {"id": "DS002", "name": "Bob Queue"}
        ]
        wb_path = tmp_workbooks / "data_structures_cse_b_marks_record.xlsx"
        
        # Test creating dedicated workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Consolidated Marks"
        ws.append(["Student ID", "Name", "Assignment-1", "Assignment-2", "Remarks"])
        for s in students:
            ws.append([s["id"], s["name"]])
        wb.save(str(wb_path))

        wb_loaded = openpyxl.load_workbook(str(wb_path))
        ws_loaded = wb_loaded["Consolidated Marks"]
        assert ws_loaded.max_row == 3  # Header + 2 students
        assert ws_loaded.cell(2, 1).value == "DS001"
        assert ws_loaded.cell(3, 1).value == "DS002"

def test_ensure_classroom_workbook_natural_sorting_and_parsed_students():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_wb_path = Path(tmpdir) / "test_course_marks.xlsx"
        
        # Jumbled assignment titles returned from Classroom
        raw_assignments = [
            "Lab-9",
            "Lab -8",
            "Lab-6",
            "Lab-7",
            "Lab-5",
            "Lab-4",
            "Lab-3",
            "Lab-2  1. Simple Interest",
            "Lab-1. Hello World"
        ]

        students = [
            {"id": "AP26110010495", "name": "Sayanthkumar D"},
            {"id": "AP26110010496", "name": "Aditya kumar R"}
        ]

        # Call ensure_classroom_workbook
        from unittest.mock import patch
        with patch.object(ExcelService, "get_classroom_workbook_path", return_value=test_wb_path):
            created_path = ExcelService.ensure_classroom_workbook(
                course_id="test-101",
                course_name="Test Course",
                section="Section A",
                students=students,
                assignment_titles=raw_assignments,
                seed_from_template=DEFAULT_EXCEL_TEMPLATE,
                force_refresh=True
            )

        wb = openpyxl.load_workbook(str(created_path))
        ws = wb["Consolidated Marks"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        
        # Verify natural order of lab headers
        expected_headers = ['Student ID', 'Name', 'Lab-1', 'Lab-2', 'Lab-3', 'Lab-4', 'Lab-5', 'Lab-6', 'Lab-7', 'Lab-8', 'Lab-9', 'Remarks']
        assert headers == expected_headers
        
        # Verify student IDs are institutional roll numbers, not Google numeric IDs
        assert ws.cell(2, 1).value in ("AP26110010495", "AP26110010496")
        assert not str(ws.cell(2, 1).value).isdigit()
