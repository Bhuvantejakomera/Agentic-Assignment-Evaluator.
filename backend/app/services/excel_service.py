import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from backend.app.config import REPORTS_DIR, WORKBOOKS_DIR, BASE_DIR, DEFAULT_EXCEL_TEMPLATE
from backend.app.models.evaluation import EvaluationResultResponse

class ExcelService:
    """Manages dedicated consolidated marks workbooks for each classroom,
    supporting assignment-wise columns, assignment-wise detailed sheets,
    and strict course data isolation."""

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
    def get_classroom_workbook_path(cls, course_id: str, course_name: str, section: str) -> Path:
        """Returns the dedicated workbook path for a specific classroom."""
        name_slug = cls.sanitize_slug(course_name)
        sec_slug = cls.sanitize_slug(section)
        return WORKBOOKS_DIR / f"{name_slug}_{sec_slug}_marks_record.xlsx"

    @classmethod
    def ensure_classroom_workbook(
        cls,
        course_id: str,
        course_name: str,
        section: str,
        students: List[Dict[str, str]],
        assignment_titles: List[str],
        seed_from_template: Optional[Path] = None,
        force_refresh: bool = False
    ) -> Path:
        """
        Creates or initializes the dedicated workbook for a classroom.
        Populated with students enrolled in this specific course.
        """
        wb_path = cls.get_classroom_workbook_path(course_id, course_name, section)
        if wb_path.exists() and not force_refresh:
            return wb_path

        # Load existing marks from seed template if available
        existing_marks = {}
        if seed_from_template and seed_from_template.exists():
            try:
                wb_tpl = openpyxl.load_workbook(str(seed_from_template), data_only=True)
                ws_tpl = wb_tpl["Consolidated Marks"] if "Consolidated Marks" in wb_tpl.sheetnames else (wb_tpl["Lab Marks"] if "Lab Marks" in wb_tpl.sheetnames else wb_tpl.active)
                tpl_headers = [str(ws_tpl.cell(1, c).value).strip() if ws_tpl.cell(1, c).value else "" for c in range(1, ws_tpl.max_column + 1)]
                for r in range(2, ws_tpl.max_row + 1):
                    sid = str(ws_tpl.cell(r, 1).value).strip() if ws_tpl.cell(r, 1).value else None
                    if sid:
                        existing_marks[sid] = {}
                        for c, h in enumerate(tpl_headers, 1):
                            val = ws_tpl.cell(r, c).value
                            if val is not None and h:
                                existing_marks[sid][h.lower()] = val
            except Exception as e:
                print(f"Warning loading seed template: {e}")

        # Create new dedicated workbook for this classroom
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Consolidated Marks"

        # Natural sort assignment titles (e.g. Lab-1, Lab-2, ..., Lab-9)
        def get_sort_key(title: str):
            m = re.search(r'(lab|assignment|proj|quiz)[\s_-]*(\d+)', str(title), re.IGNORECASE)
            if m:
                cat_priority = {"lab": 1, "assignment": 2, "proj": 3, "quiz": 4}.get(m.group(1).lower(), 5)
                return (cat_priority, int(m.group(2)), str(title).lower())
            return (99, 999, str(title).lower())

        sorted_assignment_titles = sorted(assignment_titles, key=get_sort_key)

        # Headers
        headers = ["Student ID", "Name"]
        for a_title in sorted_assignment_titles:
            short_title = cls.get_short_column_header(a_title)
            if short_title not in headers:
                headers.append(short_title)
        if "Remarks" not in headers:
            headers.append("Remarks")

        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(1, col_idx, h)
            cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Sort students alphabetically by name for a clean, professional roster
        sorted_students = sorted(students, key=lambda s: s.get("name", "").lower())

        # Populate student roster strictly for this course with clean records
        for r_idx, s in enumerate(sorted_students, 2):
            sid = s["id"]
            ws.cell(r_idx, 1, sid)
            ws.cell(r_idx, 2, s["name"])

        # Auto-adjust column widths
        from openpyxl.utils import get_column_letter
        for col_idx in range(1, len(headers) + 1):
            col_letter = get_column_letter(col_idx)
            if col_idx == 1:
                ws.column_dimensions[col_letter].width = 18
            elif col_idx == 2:
                ws.column_dimensions[col_letter].width = 25
            else:
                ws.column_dimensions[col_letter].width = 14

        wb.save(str(wb_path))
        return wb_path

    @classmethod
    def get_short_column_header(cls, assignment_title: str) -> str:
        """Derives short column name e.g. 'Lab 1 – Algorithms' -> 'Lab-1'."""
        m = re.search(r'(lab|assignment|proj|quiz)[\s_-]*(\d+)', assignment_title, re.IGNORECASE)
        if m:
            prefix = m.group(1).capitalize()
            num = m.group(2)
            return f"{prefix}-{num}"
        return assignment_title[:15].strip()

    @classmethod
    def inspect_workbook_columns(cls, workbook_path: Path) -> List[str]:
        """Reads header row from the Consolidated Marks sheet of the workbook."""
        if not workbook_path.exists():
            return []
        wb = openpyxl.load_workbook(str(workbook_path), data_only=True)
        ws = wb["Consolidated Marks"] if "Consolidated Marks" in wb.sheetnames else wb.active
        headers = []
        for col in range(1, ws.max_column + 1):
            val = ws.cell(1, col).value
            if val is not None:
                headers.append(str(val).strip())
        return headers

    @classmethod
    def inspect_workbook_sheets(cls, workbook_path: Path) -> List[str]:
        """Returns sheet names in the classroom workbook."""
        if not workbook_path.exists():
            return []
        wb = openpyxl.load_workbook(str(workbook_path), data_only=True)
        return wb.sheetnames

    @classmethod
    def map_assignment_to_column(
        cls,
        assignment_title: str,
        available_headers: List[str]
    ) -> Optional[str]:
        """Intelligently detects column name from assignment title (e.g. 'Lab 3' -> 'Lab-3')."""
        short_header = cls.get_short_column_header(assignment_title).lower()
        for h in available_headers:
            if h.lower() == short_header or h.lower() == assignment_title.lower():
                return h

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
        Updates the target column in the classroom workbook, synchronizes remarks,
        adds/updates an assignment-wise detailed sheet, preserves all other marks,
        and saves both the live workbook and versioned reports.
        """
        reports_dir = cls.get_classroom_reports_dir(course_name, assignment_title)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 1. Load or initialize classroom workbook
        if master_workbook_path.exists():
            wb = openpyxl.load_workbook(str(master_workbook_path))
        else:
            wb = openpyxl.Workbook()

        # Find consolidated sheet
        ws_name = "Consolidated Marks" if "Consolidated Marks" in wb.sheetnames else ("Lab Marks" if "Lab Marks" in wb.sheetnames else wb.sheetnames[0])
        ws = wb[ws_name]

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
                # Add student to this classroom's workbook if not present
                row_idx = ws.max_row + 1
                ws.cell(row_idx, 1, res.student_id)
                ws.cell(row_idx, 2, res.student_name)
                student_row_map[sid_clean] = row_idx

            effective_score = res.faculty_adjusted_score if res.faculty_adjusted_score is not None else res.final_score
            
            target_cell = ws.cell(row_idx, target_col_idx)
            # Explicitly set 0.0 for missing or unreadable/wrong submissions
            if "MISSING" in res.flags or res.faculty_remarks == "Missing":
                target_cell.value = 0.0
            elif "WRONG_PDF" in res.flags or "UNREADABLE" in res.flags:
                target_cell.value = 0.0
            else:
                target_cell.value = round(effective_score, 1)

            # Update remarks
            curr_remarks = ws.cell(row_idx, remarks_col_idx).value or ""
            new_remark = res.faculty_remarks
            if new_remark:
                if str(new_remark).lower() not in str(curr_remarks).lower():
                    combined = f"{curr_remarks}, {new_remark}".strip(", ") if curr_remarks else new_remark
                    ws.cell(row_idx, remarks_col_idx, combined)

        # Style header row of consolidated sheet
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        for c in range(1, ws.max_column + 1):
            cell = ws.cell(1, c)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # 5. Add or Update Assignment-Wise Detailed Sheet inside the classroom workbook!
        clean_assign_sheet_title = cls.get_short_column_header(assignment_title) + " Details"
        if clean_assign_sheet_title in wb.sheetnames:
            detail_sheet = wb[clean_assign_sheet_title]
            detail_sheet.delete_rows(1, detail_sheet.max_row + 1)
        else:
            detail_sheet = wb.create_sheet(title=clean_assign_sheet_title)

        cls._populate_detailed_sheet(detail_sheet, evaluation_results)

        # 6. Save the classroom master workbook
        wb.save(str(master_workbook_path))

        # 7. Also save versioned copy in reports/
        versioned_wb_path = reports_dir / f"Consolidated_Marks_v{run_id[:8]}_{timestamp_str}.xlsx"
        wb.save(str(versioned_wb_path))

        # 8. Standalone detailed assignment evaluation report
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
    def _populate_detailed_sheet(
        cls,
        ws,
        evaluation_results: List[EvaluationResultResponse]
    ):
        """Populates an assignment-specific detailed sheet with criterion breakdowns."""
        headers = [
            "Student ID", "Student Name", "Raw Score", "Late Penalty", 
            "Final Score", "Faculty Override", "Status", "Remarks", "Criteria Breakdown", "Evidence Snippet"
        ]
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(1, col_idx, h)
            cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="244061", end_color="244061", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")

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

            crit_summaries = [f"{c.criterion_name}: {c.awarded_marks}/{c.max_marks} [{c.status}]" for c in res.criteria_breakdown]
            evidences = [f"[{c.criterion_name}] {c.evidence}" for c in res.criteria_breakdown if c.evidence]

            ws.cell(row_idx, 9, "\n".join(crit_summaries))
            ws.cell(row_idx, 10, "\n".join(evidences[:2]))

        # Column widths
        ws.column_dimensions['A'].width = 16
        ws.column_dimensions['B'].width = 24
        ws.column_dimensions['C'].width = 12
        ws.column_dimensions['D'].width = 12
        ws.column_dimensions['E'].width = 12
        ws.column_dimensions['F'].width = 16
        ws.column_dimensions['G'].width = 18
        ws.column_dimensions['H'].width = 24
        ws.column_dimensions['I'].width = 40
        ws.column_dimensions['J'].width = 45

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
        cls._populate_detailed_sheet(ws, evaluation_results)

        detail_file = reports_dir / f"Assignment_Evaluation_Detail_{timestamp_str}.xlsx"
        wb.save(str(detail_file))
        return detail_file
