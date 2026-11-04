from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from typing import List, Dict, Any
from datetime import datetime
from backend.app.database import db_session
from backend.app.models.course import CourseResponse, ClassroomListResponse
from backend.app.services.classroom_service import ClassroomService
from backend.app.services.excel_service import ExcelService
from backend.app.services.audit_service import AuditService
from backend.app.config import DEFAULT_EXCEL_TEMPLATE

router = APIRouter(prefix="/api/classrooms", tags=["Classrooms"])

@router.get("/dashboard/stats")
def get_dashboard_stats():
    """Aggregated global metrics across all classrooms for the shared faculty dashboard."""
    ClassroomService.seed_initial_classrooms_if_empty()
    return ClassroomService.get_faculty_dashboard_stats(ClassroomService.DEFAULT_FACULTY_ID)

@router.get("", response_model=ClassroomListResponse)
def list_classrooms():
    """Retrieves all classrooms associated with the faculty account."""
    ClassroomService.seed_initial_classrooms_if_empty()
    courses = ClassroomService.get_all_courses(ClassroomService.DEFAULT_FACULTY_ID)
    
    with db_session() as conn:
        fac = conn.execute(
            "SELECT name, email FROM faculty WHERE id = ?",
            (ClassroomService.DEFAULT_FACULTY_ID,)
        ).fetchone()

    return ClassroomListResponse(
        faculty_id=ClassroomService.DEFAULT_FACULTY_ID,
        faculty_name=fac["name"] if fac else ClassroomService.DEFAULT_FACULTY_NAME,
        faculty_email=fac["email"] if fac else ClassroomService.DEFAULT_FACULTY_EMAIL,
        courses=courses
    )

@router.get("/{course_id}", response_model=CourseResponse)
def get_classroom_details(course_id: str):
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Classroom with ID '{course_id}' not found.")
    return course

@router.get("/{course_id}/workbook")
def download_classroom_workbook(course_id: str):
    """Directly downloads the dedicated consolidated marks workbook for the classroom."""
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Classroom '{course_id}' not found.")

    if not course.excel_workbook_path or not Path(course.excel_workbook_path).exists():
        raise HTTPException(status_code=404, detail="Consolidated marks workbook not found for this classroom.")

    wb_path = Path(course.excel_workbook_path)
    return FileResponse(
        path=str(wb_path),
        filename=wb_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@router.get("/{course_id}/workbook/info")
def get_classroom_workbook_info(course_id: str):
    """Returns sheets and columns metadata for this classroom's dedicated workbook."""
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Classroom '{course_id}' not found.")

    wb_path = Path(course.excel_workbook_path) if course.excel_workbook_path else None
    if not wb_path or not wb_path.exists():
        return {"exists": False, "sheets": [], "columns": [], "path": None}

    sheets = ExcelService.inspect_workbook_sheets(wb_path)
    columns = ExcelService.inspect_workbook_columns(wb_path)
    return {
        "exists": True,
        "path": str(wb_path),
        "filename": wb_path.name,
        "sheets": sheets,
        "columns": columns
    }

@router.get("/{course_id}/workbook/preview")
def preview_classroom_workbook(course_id: str):
    """
    Parses and returns structured spreadsheet data (sheets, headers, rows)
    for interactive in-browser inspection of the classroom master workbook.
    """
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Classroom '{course_id}' not found.")

    wb_path = Path(course.excel_workbook_path) if course.excel_workbook_path else None
    if not wb_path or not wb_path.exists():
        wb_path = ExcelService.get_classroom_workbook_path(course.id, course.name, course.section)

    if not wb_path or not wb_path.exists():
        if DEFAULT_EXCEL_TEMPLATE.exists():
            wb_path = DEFAULT_EXCEL_TEMPLATE
        else:
            raise HTTPException(status_code=404, detail="Consolidated marks workbook not found for this classroom.")

    import openpyxl
    wb = openpyxl.load_workbook(str(wb_path), data_only=True)
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
        "file_type": "master",
        "course_id": course_id,
        "filename": wb_path.name,
        "file_path": str(wb_path),
        "sheets": sheets_data,
        "active_sheet": sheets_data[0]["sheet_name"] if sheets_data else ""
    }

@router.post("/{course_id}/sync")
def sync_classroom(course_id: str):
    """Refreshes synchronization timestamp for the classroom."""
    course = ClassroomService.get_course_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Classroom with ID '{course_id}' not found.")

    now_str = datetime.now().isoformat()
    with db_session() as conn:
        conn.execute(
            "UPDATE courses SET last_sync_time = ? WHERE id = ?",
            (now_str, course_id)
        )
    AuditService.log_event("CLASSROOM_SYNCED", course_id=course_id)
    return {"status": "synced", "course_id": course_id, "last_sync_time": now_str}

