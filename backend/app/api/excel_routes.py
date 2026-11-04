from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from typing import Optional, List, Dict, Any
from backend.app.config import DEFAULT_EXCEL_TEMPLATE, REPORTS_DIR
from backend.app.database import db_session
from backend.app.services.classroom_service import ClassroomService
from backend.app.services.excel_service import ExcelService
from backend.app.services.audit_service import AuditService
from backend.app.api.evaluation_routes import get_evaluations

router = APIRouter(prefix="/api/classrooms/{course_id}/assignments/{assignment_id}/excel", tags=["Excel Reporting"])

@router.get("/columns")
def get_workbook_columns(course_id: str, assignment_id: str):
    """Inspects the classroom workbook and identifies available and suggested target columns."""
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    assignments = ClassroomService.get_assignments_for_course(course_id)
    assign = next((a for a in assignments if a.id == assignment_id), None)
    if not assign:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    wb_path = Path(course.excel_workbook_path) if course.excel_workbook_path else ExcelService.get_classroom_workbook_path(course.id, course.name, course.section)
    if not wb_path.exists():
        # Ensure workbook exists
        wb_path = ExcelService.get_classroom_workbook_path(course.id, course.name, course.section)

    columns = ExcelService.inspect_workbook_columns(wb_path)
    suggested_col = ExcelService.map_assignment_to_column(assign.title, columns)

    return {
        "workbook_path": str(wb_path),
        "workbook_name": wb_path.name,
        "columns": columns,
        "suggested_column": suggested_col or ExcelService.get_short_column_header(assign.title),
        "is_column_existing": suggested_col is not None
    }

@router.post("/export")
def export_excel(
    course_id: str,
    assignment_id: str,
    target_column_name: Optional[str] = Query(None)
):
    """
    Updates the master classroom workbook, records student grades & remarks,
    generates versioned backups and a detailed assignment evaluation report.
    """
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    assignments = ClassroomService.get_assignments_for_course(course_id)
    assign = next((a for a in assignments if a.id == assignment_id), None)
    if not assign:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    evaluations = get_evaluations(course_id, assignment_id)
    if not evaluations:
        raise HTTPException(status_code=400, detail="No evaluation results found to export. Please run evaluation first.")

    wb_path = Path(course.excel_workbook_path) if course.excel_workbook_path else ExcelService.get_classroom_workbook_path(course.id, course.name, course.section)

    # Determine target column
    if not isinstance(target_column_name, str) or not target_column_name:
        columns = ExcelService.inspect_workbook_columns(wb_path)
        target_column_name = ExcelService.map_assignment_to_column(assign.title, columns) or assign.title

    run_id = evaluations[0].run_id if evaluations else "run1"

    versioned_wb, detail_wb = ExcelService.update_consolidated_workbook(
        master_workbook_path=wb_path,
        course_name=course.name,
        assignment_title=assign.title,
        target_column_name=target_column_name,
        evaluation_results=evaluations,
        run_id=run_id
    )

    try:
        AuditService.log_event(
            "EXCEL_EXPORTED",
            course_id=course_id,
            assignment_id=assignment_id,
            details={
                "target_column": target_column_name,
                "versioned_master": str(versioned_wb),
                "detail_report": str(detail_wb),
                "student_count": len(evaluations)
            }
        )
    except Exception as audit_err:
        print(f"[ExcelExport] Audit log warning: {audit_err}")

    return {
        "status": "success",
        "classroom_workbook_path": str(wb_path),
        "target_column": target_column_name,
        "versioned_master_workbook": str(versioned_wb),
        "detail_report_path": str(detail_wb),
        "total_records_updated": len(evaluations),
        "message": f"Successfully updated column '{target_column_name}' and added detailed evaluation sheet in classroom workbook."
    }

@router.get("/preview")
def preview_excel(course_id: str, assignment_id: str, file_type: str = Query("master")):
    """
    Parses and returns structured spreadsheet data (sheets, headers, rows)
    for interactive in-browser inspection before or after downloading.
    """
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    assignments = ClassroomService.get_assignments_for_course(course_id)
    assign = next((a for a in assignments if a.id == assignment_id), None)
    if not assign:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    reports_dir = ExcelService.get_classroom_reports_dir(course.name, assign.title)
    prefix = "Consolidated_Marks" if file_type == "master" else "Assignment_Evaluation"
    files = sorted(reports_dir.glob(f"{prefix}*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)

    target_file = None
    if files:
        target_file = files[0]
    elif file_type == "master":
        wb_path = Path(course.excel_workbook_path) if course.excel_workbook_path else ExcelService.get_classroom_workbook_path(course.id, course.name, course.section)
        if wb_path.exists():
            target_file = wb_path

    # If file doesn't exist yet, auto-export if evaluation results exist
    if not target_file or not target_file.exists():
        evaluations = get_evaluations(course_id, assignment_id)
        if evaluations:
            try:
                export_excel(course_id, assignment_id)
                files = sorted(reports_dir.glob(f"{prefix}*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
                if files:
                    target_file = files[0]
            except Exception as exp_err:
                print(f"[preview_excel] Auto-export warning: {exp_err}")

    if not target_file or not target_file.exists():
        if file_type == "master" and DEFAULT_EXCEL_TEMPLATE.exists():
            target_file = DEFAULT_EXCEL_TEMPLATE
        else:
            raise HTTPException(status_code=404, detail="No Excel workbook found to preview. Please run evaluation or export first.")

    import openpyxl
    wb = openpyxl.load_workbook(str(target_file), data_only=True)
    sheets_data = []

    for s_name in wb.sheetnames:
        ws = wb[s_name]
        raw_rows = []
        for r in ws.iter_rows(values_only=True):
            if any(cell is not None and str(cell).strip() != "" for cell in r):
                raw_rows.append([str(c) if c is not None else "" for c in r])
        
        if raw_rows:
            headers = raw_rows[0]
            data_rows = raw_rows[1:]
            sheets_data.append({
                "sheet_name": s_name,
                "headers": headers,
                "rows": data_rows,
                "total_rows": len(data_rows),
                "total_cols": len(headers)
            })

    return {
        "status": "success",
        "file_type": file_type,
        "filename": target_file.name,
        "file_path": str(target_file),
        "sheets": sheets_data,
        "active_sheet": sheets_data[0]["sheet_name"] if sheets_data else ""
    }

@router.get("/download")
def download_excel(course_id: str, assignment_id: str, file_type: str = Query("master")):
    """Serves the latest generated Excel file for downloading."""
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    assignments = ClassroomService.get_assignments_for_course(course_id)
    assign = next((a for a in assignments if a.id == assignment_id), None)
    if not assign:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    reports_dir = ExcelService.get_classroom_reports_dir(course.name, assign.title)
    
    # Find newest file matching file_type
    prefix = "Consolidated_Marks" if file_type == "master" else "Assignment_Evaluation"
    files = sorted(reports_dir.glob(f"{prefix}*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        # Fallback to default workbook if master requested
        if file_type == "master" and DEFAULT_EXCEL_TEMPLATE.exists():
            return FileResponse(
                path=str(DEFAULT_EXCEL_TEMPLATE),
                filename=DEFAULT_EXCEL_TEMPLATE.name,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        raise HTTPException(status_code=404, detail="No exported Excel reports found for this assignment.")

    latest_file = files[0]
    return FileResponse(
        path=str(latest_file),
        filename=latest_file.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

