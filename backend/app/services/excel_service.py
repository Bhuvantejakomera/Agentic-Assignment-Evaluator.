import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from backend.app.config import REPORTS_DIR, BASE_DIR
from backend.app.models.evaluation import EvaluationResultResponse

class ExcelService:
    """Manages classroom-specific Excel workbooks, column mapping, 
    preserving existing marks, and generating detailed versioned evaluation reports."""

    @classmethod
    def sanitize_slug(cls, name: str) -> str:
        s = re.sub(r'[^\w\s-]', '', name).strip().lower()
        return re.sub(r'[-\s]+', '_', s)

    @classmethod
    def get_classroom_reports_dir(cls, course_name: str, assignment_title: str) -> Path:
        course_slug = cls.sanitize_slug(course_name)
        assign_slug = cls.sanitize_slug(assignment_title)
        out_dir = REPORTS_DIR / course_slug / assign_slug
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    @classmethod
    def inspect_workbook_columns(cls, workbook_path: Path) -> List[str]:
        """Reads header row from active sheet of the workbook."""
        if not workbook_path.exists():
            return []
        wb = openpyxl.load_workbook(str(workbook_path), data_only=True)
        ws = wb.active
        headers = []
        for col in range(1, ws.max_column + 1):
            val = ws.cell(1, col).value
            if val is not None:
                headers.append(str(val).strip())
        return headers

    @classmethod
    def map_assignment_to_column(
        cls,
        assignment_title: str,
        available_headers: List[str]
    ) -> Optional[str]:
        """Intelligently detects column name from assignment title (e.g. 'Lab 3' -> 'Lab-3')."""
        assign_clean = re.sub(r'[^a-zA-Z0-9]', '', assignment_title).lower()
        for h in available_headers:
            h_clean = re.sub(r'[^a-zA-Z0-9]', '', h).lower()
            if h_clean in assign_clean or assign_clean in h_clean:
                return h
        return None

    @classmethod
    def update_consolidated_workbook(
        cls,
        master_workbook_path: Path,
        course_name: str,
        assignment_title: str,
        target_column_name: str,
        evaluation_results: List[EvaluationResultResponse],
        run_id: str
    ) -> Tuple[Path, Path]:
        """
        Updates the target column in the master marks workbook, updates remarks,
        preserves all other marks, and outputs both a versioned copy and an assignment detail workbook.
        """
        reports_dir = cls.get_classroom_reports_dir(course_name, assignment_title)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 1. Load or create workbook
        if master_workbook_path.exists():
            wb = openpyxl.load_workbook(str(master_workbook_path))
            ws = wb.active
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Lab Marks"
            # Default headers
            headers = ["Student ID", "Name", "Lab-1", "Lab-2", "Lab-3", "Lab-4", "Lab-5", "Remarks"]
            for col_idx, h in enumerate(headers, 1):
                ws.cell(1, col_idx, h)

        # 2. Map existing headers to column indices
        header_to_col: Dict[str, int] = {}
        for c in range(1, ws.max_column + 1):
            val = ws.cell(1, c).value
            if val is not None:
                header_to_col[str(val).strip()] = c

        # Find or add target column
        target_col_idx = header_to_col.get(target_column_name)
        remarks_col_idx = header_to_col.get("Remarks")

        if not target_col_idx:
            # If Remarks column exists, insert new column before Remarks
            if remarks_col_idx:
                target_col_idx = remarks_col_idx
                ws.insert_cols(target_col_idx)
                ws.cell(1, target_col_idx, target_column_name)
                # Recalculate remarks_col_idx
                remarks_col_idx += 1
            else:
                target_col_idx = ws.max_column + 1
                ws.cell(1, target_col_idx, target_column_name)

        if not remarks_col_idx:
            remarks_col_idx = ws.max_column + 1
            ws.cell(1, remarks_col_idx, "Remarks")

        # 3. Build lookup of student rows by student_id and name
        student_row_map: Dict[str, int] = {}
        for r in range(2, ws.max_row + 1):
            sid = ws.cell(r, 1).value
            name = ws.cell(r, 2).value
            if sid:
                student_row_map[str(sid).strip().upper()] = r
            if name:
                student_row_map[str(name).strip().lower()] = r

        # 4. Update marks and remarks for each evaluated student
        for res in evaluation_results:
            sid_clean = res.student_id.strip().upper()
            name_clean = res.student_name.strip().lower()

            row_idx = student_row_map.get(sid_clean) or student_row_map.get(name_clean)
            if not row_idx:
                # Add student to workbook if not present
                row_idx = ws.max_row + 1
                ws.cell(row_idx, 1, res.student_id)
                ws.cell(row_idx, 2, res.student_name)
                student_row_map[sid_clean] = row_idx

            # Determine score to write (faculty adjusted takes precedence)
            effective_score = res.faculty_adjusted_score if res.faculty_adjusted_score is not None else res.final_score
            
            # If wrong PDF or unreadable, don't award marks
            if "WRONG_PDF" in res.flags or "UNREADABLE" in res.flags or "MISSING" in res.flags:
                ws.cell(row_idx, target_col_idx, None)
            else:
                ws.cell(row_idx, target_col_idx, round(effective_score, 1))

            # Update remarks
            curr_remarks = ws.cell(row_idx, remarks_col_idx).value or ""
            new_remark = res.faculty_remarks
            if new_remark:
                if str(new_remark).lower() not in str(curr_remarks).lower():
                    combined = f"{curr_remarks}, {new_remark}".strip(", ") if curr_remarks else new_remark
                    ws.cell(row_idx, remarks_col_idx, combined)

        # Style header row nicely
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        for c in range(1, ws.max_column + 1):
            cell = ws.cell(1, c)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Save versioned consolidated master workbook
        versioned_wb_path = reports_dir / f"Consolidated_Marks_v{run_id[:8]}_{timestamp_str}.xlsx"
        wb.save(str(versioned_wb_path))

        # Also update the main workbook in place if it is the local master
        try:
            wb.save(str(master_workbook_path))
        except Exception:
            pass

        # 5. Generate detailed assignment-level evaluation report
        detail_path = cls.generate_detailed_assignment_report(
            course_name=course_name,
            assignment_title=assignment_title,
            evaluation_results=evaluation_results,
            run_id=run_id,
            reports_dir=reports_dir,
            timestamp_str=timestamp_str
        )

        return versioned_wb_path, detail_path

    @classmethod
    def generate_detailed_assignment_report(
        cls,
        course_name: str,
        assignment_title: str,
        evaluation_results: List[EvaluationResultResponse],
        run_id: str,
        reports_dir: Path,
        timestamp_str: str
    ) -> Path:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Detailed Evaluation"

        # Headers
        headers = [
            "Student ID", "Student Name", "Raw Score", "Late Penalty", 
            "Final Score", "Faculty Override", "Status", "Remarks", "Criteria Details", "Evidence Snippet"
        ]
        for col_idx, h in enumerate(headers, 1):
            ws.cell(1, col_idx, h)

        for row_idx, res in enumerate(evaluation_results, 2):
            ws.cell(row_idx, 1, res.student_id)
            ws.cell(row_idx, 2, res.student_name)
            ws.cell(row_idx, 3, res.raw_score)
            ws.cell(row_idx, 4, res.late_penalty)
            ws.cell(row_idx, 5, res.final_score)
            ws.cell(row_idx, 6, res.faculty_adjusted_score if res.faculty_adjusted_score is not None else "-")
            
            status_desc = "Approved" if res.faculty_approved else "Draft"
            if res.flags:
                status_desc += f" ({', '.join(res.flags)})"
            ws.cell(row_idx, 7, status_desc)
            ws.cell(row_idx, 8, res.faculty_remarks or "")

            # Criteria details summary
            crit_summaries = []
            evidences = []
            for c in res.criteria_breakdown:
                crit_summaries.append(f"{c.criterion_name}: {c.awarded_marks}/{c.max_marks} [{c.status}]")
                if c.evidence:
                    evidences.append(f"[{c.criterion_name}] {c.evidence}")

            ws.cell(row_idx, 9, "\n".join(crit_summaries))
            ws.cell(row_idx, 10, "\n".join(evidences[:2]))

        # Styling
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="244061", end_color="244061", fill_type="solid")
        for c in range(1, len(headers) + 1):
            cell = ws.cell(1, c)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        detail_file = reports_dir / f"Assignment_Evaluation_Detail_{timestamp_str}.xlsx"
        wb.save(str(detail_file))
        return detail_file
