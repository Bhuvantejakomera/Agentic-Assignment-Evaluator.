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
