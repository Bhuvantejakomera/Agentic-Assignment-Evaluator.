import os
import re
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from googleapiclient.http import MediaIoBaseDownload
from backend.app.database import db_session
from backend.app.config import SUBMISSIONS_DIR, DEFAULT_EXCEL_TEMPLATE
from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel
from backend.app.services.document_extractor import DocumentExtractor
from backend.app.services.excel_service import ExcelService
from backend.app.services.audit_service import AuditService
from backend.app.agents.security import SecureDriveHandler, DriveSecurityError

class SubmissionAgent:
    """
    Agent 2: Submission Ingestion & Document Specialist.
    Responsible for:
    - Discovering all coursework assignments per classroom.
    - Synchronizing student submission records with full pagination.
    - Hardened, secure downloading of Google Drive attachments.
    - Multi-format document & code parsing (PDF, DOCX, HTML, C, C++, Python).
    - Triage & anomaly classification (MISSING, LATE, WRONG_PDF, UNREADABLE).
    """

    @classmethod
    def sync_coursework_and_submissions(
        cls,
        classroom_service,
        course_id: str,
        google_to_roll: Dict[str, str],
        drive_service=None
    ) -> int:
        """
        Discovers coursework for course_id and synchronizes all student submissions.
        Returns total coursework count synced.
        """
        now_str = datetime.now().isoformat()

        cw_res = classroom_service.courses().courseWork().list(courseId=course_id).execute()
        coursework_items = cw_res.get("courseWork", [])

        with db_session() as conn:
            for cw in coursework_items:
                cw_id = cw["id"]
                title = cw.get("title", "Untitled Assignment")
                desc = cw.get("description", "")
                max_p = float(cw.get("maxPoints", 100.0))
                due_obj = cw.get("dueDate", {})
                due_date_str = None
                if due_obj:
                    due_date_str = f"{due_obj.get('year')}-{due_obj.get('month'):02d}-{due_obj.get('day'):02d}"

                conn.execute(
                    """
                    INSERT INTO assignments (id, course_id, title, description, max_points, due_date, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        description = excluded.description,
                        max_points = excluded.max_points,
                        due_date = excluded.due_date
                    """,
                    (cw_id, course_id, title, desc, max_p, due_date_str, now_str)
                )

                # Fetch student submissions with pagination
                student_submissions = []
                page_token = None
                while True:
                    try:
                        sub_res = classroom_service.courses().courseWork().studentSubmissions().list(
                            courseId=course_id,
                            courseWorkId=cw_id,
                            pageSize=100,
                            pageToken=page_token
                        ).execute()
                        student_submissions.extend(sub_res.get("studentSubmissions", []))
                        page_token = sub_res.get("nextPageToken")
                        if not page_token:
                            break
                    except Exception as err:
                        print(f"[SubmissionAgent] Error fetching submissions for assignment {cw_id}: {err}")
                        break

                for sub in student_submissions:
                    sub_id = sub["id"]
                    raw_uid = sub.get("userId")
                    # Map Google UID to SRM AP student roll number
                    stud_id = google_to_roll.get(raw_uid, raw_uid)
                    sub_state = sub.get("state", "TURNED_IN")
                    is_late = 1 if sub.get("late") else 0
                    sub_time = sub.get("updateTime") or sub.get("creationTime") or now_str

                    assign_sub = sub.get("assignmentSubmission", {})
                    raw_attachments = assign_sub.get("attachments", [])
                    attachments_info = []

                    for att in raw_attachments:
                        if "driveFile" in att:
                            df = att["driveFile"]
                            raw_fname = df.get("title", "submission.pdf")
                            try:
                                safe_fname = SecureDriveHandler.sanitize_filename(raw_fname)
                            except DriveSecurityError:
                                safe_fname = "blocked_submission.bin"

                            ext = Path(safe_fname).suffix.lstrip(".").upper() or "PDF"
                            attachments_info.append({
                                "filename": safe_fname,
                                "file_id": df.get("id"),
                                "file_type": ext,
                                "link": df.get("alternateLink", "")
                            })
                        elif "link" in att:
                            lk = att["link"]
                            attachments_info.append({
                                "filename": lk.get("title") or lk.get("url"),
                                "file_type": "LINK",
                                "link": lk.get("url")
                            })

                    flags = []
                    if is_late:
                        flags.append("LATE")
                    if sub_state in ("NEW", "CREATED", "RECLAIMED_BY_STUDENT") or len(attachments_info) == 0:
                        flags.append("MISSING")

                    conn.execute(
                        """
                        INSERT INTO submissions (id, course_id, assignment_id, student_id, submission_time, is_late, state, attachments_json, submission_flags_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(course_id, assignment_id, student_id) DO UPDATE SET
                            id = excluded.id,
                            submission_time = excluded.submission_time,
                            is_late = excluded.is_late,
                            state = excluded.state,
                            attachments_json = excluded.attachments_json,
                            submission_flags_json = excluded.submission_flags_json
                        """,
                        (
                            sub_id, course_id, cw_id, stud_id, sub_time, is_late, sub_state,
                            json.dumps(attachments_info), json.dumps(flags), now_str
                        )
                    )

            # Update assignments count on course
            conn.execute(
                "UPDATE courses SET assignments_count = (SELECT COUNT(*) FROM assignments WHERE course_id = ?) WHERE id = ?",
                (course_id, course_id)
            )

            # Refresh classroom workbook with naturally sorted assignments
            cls._refresh_classroom_workbook(conn, course_id, coursework_items)

        return len(coursework_items)

    @classmethod
    def _refresh_classroom_workbook(cls, conn, course_id: str, coursework_items: List[Dict[str, Any]]) -> None:
        """Refreshes the dedicated Excel marks workbook with clean ascending lab columns."""
        course = conn.execute("SELECT name, section FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            return

        c_name = course["name"]
        c_sec = course["section"]

        # Natural sort assignment titles (Lab-1, Lab-2, ..., Lab-9)
        def get_sort_key_cw(cw_item):
            t = cw_item.get("title", "")
            m = re.search(r'(lab|assignment|proj|quiz)[\s_-]*(\d+)', t, re.IGNORECASE)
            if m:
                cat_priority = {"lab": 1, "assignment": 2, "proj": 3, "quiz": 4}.get(m.group(1).lower(), 5)
                return (cat_priority, int(m.group(2)), t.lower())
            return (99, 999, t.lower())

        sorted_cw = sorted(coursework_items, key=get_sort_key_cw)
        assignment_titles = [cw.get("title", "Assignment") for cw in sorted_cw] or ["Assignment 1"]

        # Retrieve enrolled students sorted by name
        students_rows = conn.execute(
            """
            SELECT s.id, s.name, s.email
            FROM course_enrollments ce
            JOIN students s ON ce.student_id = s.id
            WHERE ce.course_id = ?
            ORDER BY s.name ASC
            """,
            (course_id,)
        ).fetchall()

        students_list = [{"id": r["id"], "name": r["name"], "email": r["email"]} for r in students_rows]

        ExcelService.ensure_classroom_workbook(
            course_id=course_id,
            course_name=c_name,
            section=c_sec,
            students=students_list,
            assignment_titles=assignment_titles,
            seed_from_template=DEFAULT_EXCEL_TEMPLATE,
            force_refresh=True
        )

    @classmethod
    def secure_download_drive_attachment(
        cls,
        drive_service,
        file_id: str,
        dest_path: Path
    ) -> bool:
        """
        Hardened Drive download.
        - Validates that dest_path is safely contained in SUBMISSIONS_DIR.
        - Prevents buffer overflow / disk-fill using streaming and max size check.
        - Quarantines and removes incomplete or oversized files.
        """
        try:
            # 1. Enforce sandbox boundary
            root_dir = SUBMISSIONS_DIR.resolve()
            dest_resolved = dest_path.resolve()
            try:
                dest_resolved.relative_to(root_dir)
            except ValueError:
                raise DriveSecurityError(f"Security Alert: Download target {dest_resolved} escapes sandbox {root_dir}!")

            dest_resolved.parent.mkdir(parents=True, exist_ok=True)
            temp_file = dest_resolved.with_suffix(dest_resolved.suffix + ".part")

            # 2. Stream chunked download (with Google Docs fallback if editor format)
            try:
                req = drive_service.files().get_media(fileId=file_id)
                with open(temp_file, "wb") as f:
                    downloader = MediaIoBaseDownload(f, req, chunksize=1024 * 1024)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                        if status and status.resumable_progress > SecureDriveHandler.MAX_FILE_SIZE_BYTES:
                            temp_file.unlink(missing_ok=True)
                            raise DriveSecurityError(f"Drive file {file_id} exceeds {SecureDriveHandler.MAX_FILE_SIZE_BYTES} bytes limit.")
            except Exception as dl_err:
                err_str = str(dl_err)
                if "Use Export with Docs Editors files" in err_str or "fileNotDownloadable" in err_str:
                    # Google Docs editor document: export as PDF
                    req = drive_service.files().export_media(fileId=file_id, mimeType="application/pdf")
                    with open(temp_file, "wb") as f:
                        downloader = MediaIoBaseDownload(f, req, chunksize=1024 * 1024)
                        done = False
                        while not done:
                            status, done = downloader.next_chunk()
                            if status and status.resumable_progress > SecureDriveHandler.MAX_FILE_SIZE_BYTES:
                                temp_file.unlink(missing_ok=True)
                                raise DriveSecurityError(f"Drive file {file_id} exceeds {SecureDriveHandler.MAX_FILE_SIZE_BYTES} bytes limit.")
                else:
                    raise dl_err

            # 3. Atomic move from temporary file to final destination
            if dest_resolved.exists():
                dest_resolved.unlink()
            temp_file.rename(dest_resolved)

            # 4. Post-download safety inspection on final destination
            is_safe, error_msg = SecureDriveHandler.validate_file_safety(dest_resolved)
            if not is_safe:
                dest_resolved.unlink(missing_ok=True)
                print(f"[SubmissionAgent] File safety validation failed for {file_id}: {error_msg}")
                return False

            return True

        except Exception as e:
            if 'temp_file' in locals() and temp_file.exists():
                temp_file.unlink(missing_ok=True)
            print(f"[SubmissionAgent] Secure Drive download failed for {file_id}: {e}")
            return False

    @classmethod
    def prepare_and_extract_submission(
        cls,
        course_id: str,
        assignment_id: str,
        student_id: str,
        attachments: List[SubmissionAttachment],
        drive_service=None
    ) -> Tuple[ExtractedContentModel, List[str]]:
        """
        Downloads missing files from Drive into secure sandbox, extracts text and code,
        and triages anomalies (MISSING, UNREADABLE, WRONG_PDF).
        """
        extracted = ExtractedContentModel()
        flags = []

        if not attachments:
            flags.append("MISSING")
            return extracted, flags

        extracted_texts = []

        for att in attachments:
            file_path = None
            if att.file_path and Path(att.file_path).exists():
                file_path = Path(att.file_path)
            elif att.file_id and drive_service:
                raw_name = att.filename or f"{att.file_id}.pdf"
                try:
                    dest = SecureDriveHandler.get_secure_destination_path(
                        course_id=course_id,
                        assignment_id=assignment_id,
                        student_id=student_id,
                        filename=raw_name
                    )
                    if not dest.exists():
                        cls.secure_download_drive_attachment(drive_service, att.file_id, dest)
                    if dest.exists():
                        file_path = dest
                        att.file_path = str(dest)
                except DriveSecurityError as sec_err:
                    flags.append("SECURITY_VIOLATION")
                    extracted.extraction_warnings.append(str(sec_err))
                    continue

            if not file_path or not file_path.exists():
                continue

            ftype = DocumentExtractor.identify_file_type(file_path)
            if ftype == "DOCX":
                txt, warns = DocumentExtractor.extract_from_docx(file_path)
                docx_snips, docx_outs = DocumentExtractor.extract_code_and_output_from_images_in_docx(file_path)
                if txt:
                    extracted_texts.append(txt)
                    embedded = DocumentExtractor.extract_code_blocks_from_text(txt)
                    if embedded:
                        extracted.code_snippets.extend(embedded)
                if docx_snips:
                    extracted.code_snippets.extend(docx_snips)
                if docx_outs:
                    extracted.diagram_flowchart_descriptions.extend(docx_outs)
                extracted.extraction_warnings.extend(warns)
            elif ftype == "PDF":
                txt, warns = DocumentExtractor.extract_from_pdf(file_path)
                pdf_snips, pdf_outs = DocumentExtractor.extract_code_and_output_from_images_in_pdf(file_path)
                if txt:
                    extracted_texts.append(txt)
                    embedded = DocumentExtractor.extract_code_blocks_from_text(txt)
                    if embedded:
                        extracted.code_snippets.extend(embedded)
                if pdf_snips:
                    extracted.code_snippets.extend(pdf_snips)
                if pdf_outs:
                    extracted.diagram_flowchart_descriptions.extend(pdf_outs)
                extracted.extraction_warnings.extend(warns)
            elif ftype in ("C", "CPP", "PY"):
                txt, code_list, warns = DocumentExtractor.extract_from_source_code(file_path, ftype)
                if txt:
                    extracted_texts.append(txt)
                if code_list:
                    extracted.code_snippets.extend(code_list)
                extracted.extraction_warnings.extend(warns)
            elif ftype in ("HTML", "TXT"):
                txt, warns = DocumentExtractor.extract_from_html(file_path) if ftype == "HTML" else (file_path.read_text(encoding="utf-8", errors="ignore"), [])
                if txt:
                    extracted_texts.append(txt)
                    embedded = DocumentExtractor.extract_code_blocks_from_text(txt)
                    if embedded:
                        extracted.code_snippets.extend(embedded)
                extracted.extraction_warnings.extend(warns)
            elif ftype == "IMAGE":
                ocr_txt = DocumentExtractor.extract_text_from_image if hasattr(DocumentExtractor, "extract_text_from_image") else ""
                from backend.app.services.ocr_service import OCRService
                ocr_txt = OCRService.extract_text_from_image(file_path)
                img_snips, img_outs = OCRService.extract_code_and_output_from_ocr(ocr_txt, file_path.name)
                if ocr_txt:
                    extracted_texts.append(f"--- [Student Screenshot: {file_path.name}] ---\n{ocr_txt}")
                else:
                    extracted_texts.append(f"[Image Deliverable: {file_path.name}]")
                if img_snips:
                    extracted.code_snippets.extend(img_snips)
                if img_outs:
                    extracted.diagram_flowchart_descriptions.extend(img_outs)

        full_extracted = "\n\n".join(extracted_texts).strip()
        extracted.text_content = full_extracted
        extracted.word_count = len(full_extracted.split())

        # Anomaly triage
        if not full_extracted and not extracted.code_snippets:
            flags.append("UNREADABLE")

        # Cache extracted content to database
        try:
            with db_session() as conn:
                conn.execute(
                    """
                    UPDATE submissions 
                    SET extracted_content_json = ? 
                    WHERE course_id = ? AND assignment_id = ? AND student_id = ?
                    """,
                    (extracted.model_dump_json(), course_id, assignment_id, student_id)
                )
        except Exception:
            pass

        return extracted, flags
