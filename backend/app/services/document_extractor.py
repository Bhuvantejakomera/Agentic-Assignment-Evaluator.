import os
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from pypdf import PdfReader
from docx import Document
from bs4 import BeautifulSoup
from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel
from backend.app.services.ocr_service import OCRService

class DocumentExtractor:
    """Specialized document and source code extractor for PDF, DOCX, HTML, C, C++, and Python."""

    SUPPORTED_EXTENSIONS = {
        ".pdf": "PDF",
        ".docx": "DOCX",
        ".doc": "DOCX",
        ".html": "HTML",
        ".htm": "HTML",
        ".c": "C",
        ".cpp": "CPP",
        ".cc": "CPP",
        ".h": "C",
        ".hpp": "CPP",
        ".py": "PY",
        ".txt": "TXT",
        ".jpg": "IMAGE",
        ".jpeg": "IMAGE",
        ".png": "IMAGE",
        ".webp": "IMAGE",
        ".bmp": "IMAGE"
    }

    @classmethod
    def identify_file_type(cls, file_path: Path) -> str:
        ext = file_path.suffix.lower()
        return cls.SUPPORTED_EXTENSIONS.get(ext, "UNKNOWN")

    @classmethod
    def extract_from_pdf(cls, file_path: Path) -> Tuple[str, List[str]]:
        text_content = []
        warnings = []
        try:
            reader = PdfReader(str(file_path))
            if len(reader.pages) == 0:
                warnings.append("PDF has 0 pages (empty file).")
                return "", warnings

            for idx, page in enumerate(reader.pages):
                extracted = page.extract_text()
                if extracted and extracted.strip():
                    text_content.append(extracted.strip())
                
                # Check for embedded screenshots / images on page
                try:
                    for img_idx, img in enumerate(page.images):
                        ocr_text = OCRService.extract_text_from_image(img.data)
                        if ocr_text and ocr_text.strip():
                            text_content.append(f"--- [Page {idx+1} Screenshot / Code Image] ---\n{ocr_text.strip()}")
                except Exception as img_err:
                    warnings.append(f"Image OCR on page {idx+1} skipped: {str(img_err)}")

            full_text = "\n\n".join(text_content).strip()
            if not full_text:
                warnings.append("PDF contains no selectable or OCR extractable text.")
            return full_text, warnings
        except Exception as e:
            warnings.append(f"PDF extraction error: {str(e)}")
            return "", warnings

    @classmethod
    def extract_code_and_output_from_images_in_pdf(cls, file_path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
        """Extracts code blocks and terminal outputs from screenshots embedded in PDF."""
        all_snippets = []
        all_outputs = []
        try:
            reader = PdfReader(str(file_path))
            for idx, page in enumerate(reader.pages):
                for img_idx, img in enumerate(page.images):
                    ocr_text = OCRService.extract_text_from_image(img.data)
                    if ocr_text:
                        snips, outs = OCRService.extract_code_and_output_from_ocr(
                            ocr_text, filename=f"{file_path.name}_page_{idx+1}_img_{img_idx+1}"
                        )
                        all_snippets.extend(snips)
                        all_outputs.extend(outs)
        except Exception:
            pass
        return all_snippets, all_outputs

    @classmethod
    def extract_from_docx(cls, file_path: Path) -> Tuple[str, List[str]]:
        warnings = []
        try:
            doc = Document(str(file_path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            
            # Also extract text from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_text:
                        paragraphs.append(" | ".join(row_text))

            # Extract embedded images / screenshots via OCR
            try:
                for rel_id, rel in doc.part.rels.items():
                    if "image" in rel.target_ref:
                        img_blob = rel.target_part.blob
                        ocr_text = OCRService.extract_text_from_image(img_blob)
                        if ocr_text and ocr_text.strip():
                            paragraphs.append(f"--- [DOCX Screenshot: {os.path.basename(rel.target_ref)}] ---\n{ocr_text.strip()}")
            except Exception as img_err:
                warnings.append(f"DOCX image OCR skipped: {str(img_err)}")

            full_text = "\n\n".join(paragraphs).strip()
            if not full_text:
                warnings.append("DOCX contains no text or readable images.")
            return full_text, warnings
        except Exception as e:
            warnings.append(f"DOCX extraction error: {str(e)}")
            return "", warnings

    @classmethod
    def extract_code_and_output_from_images_in_docx(cls, file_path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
        """Extracts code blocks and terminal outputs from screenshots embedded in DOCX."""
        all_snippets = []
        all_outputs = []
        try:
            doc = Document(str(file_path))
            for rel_id, rel in doc.part.rels.items():
                if "image" in rel.target_ref:
                    img_blob = rel.target_part.blob
                    ocr_text = OCRService.extract_text_from_image(img_blob)
                    if ocr_text:
                        snips, outs = OCRService.extract_code_and_output_from_ocr(
                            ocr_text, filename=f"{file_path.name}_{os.path.basename(rel.target_ref)}"
                        )
                        all_snippets.extend(snips)
                        all_outputs.extend(outs)
        except Exception:
            pass
        return all_snippets, all_outputs

    @classmethod
    def extract_from_html(cls, file_path: Path) -> Tuple[str, List[str]]:
        warnings = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
            
            # Remove scripts and styles
            for script in soup(["script", "style"]):
                script.decompose()

            text = soup.get_text(separator="\n").strip()
            cleaned_text = re.sub(r'\n+', '\n', text)
            if not cleaned_text:
                warnings.append("HTML contains no visible text.")
            return cleaned_text, warnings
        except Exception as e:
            warnings.append(f"HTML extraction error: {str(e)}")
            return "", warnings

    @classmethod
    def extract_from_source_code(cls, file_path: Path, lang: str) -> Tuple[str, List[Dict[str, str]], List[str]]:
        warnings = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                code_text = f.read()

            snippet = {"language": lang.lower(), "code": code_text, "filename": file_path.name}
            return code_text, [snippet], warnings
        except Exception as e:
            warnings.append(f"Source code reading error: {str(e)}")
            return "", [], warnings

    @classmethod
    def extract_c_code_blocks(cls, text: str) -> List[Dict[str, str]]:
        """Extracts complete C/C++ programs from plain or extracted document text using balanced brace analysis."""
        snippets = []
        lines = text.splitlines()
        in_code = False
        current_block = []
        brace_depth = 0
        has_seen_main = False
        has_seen_brace = False

        for line in lines:
            stripped = line.strip()

            # Boundary delimiter: next question, document break, or separate section
            if in_code and (re.match(r'^[b-z]\)\s+', stripped, re.IGNORECASE) or 
                            re.match(r'^(?:question|experiment|lab|task)\s*[\d:]+', stripped, re.IGNORECASE) or
                            stripped.lower().startswith('--- document:')):
                if current_block:
                    code_str = "\n".join(current_block).strip()
                    if len(code_str) > 30 and ("{" in code_str or "#include" in code_str):
                        snippets.append({"language": "c", "code": code_str, "source": "document_text"})
                in_code = False
                current_block = []
                brace_depth = 0
                has_seen_main = False
                has_seen_brace = False

            if not in_code:
                if stripped.startswith('#include') or re.search(r'\b(int|void)\s+main\s*\(', stripped):
                    in_code = True
                    current_block = [line]
                    brace_depth = line.count('{') - line.count('}')
                    has_seen_brace = '{' in line
                    has_seen_main = bool(re.search(r'\b(int|void)\s+main\s*\(', stripped))
            else:
                # Terminal output delimiter
                if stripped.lower() in ("output", "output:", "output :-", "visual output", "terminal output", "result", "sample output"):
                    if current_block:
                        code_str = "\n".join(current_block).strip()
                        if len(code_str) > 30:
                            snippets.append({"language": "c", "code": code_str, "source": "document_text"})
                    in_code = False
                    current_block = []
                    brace_depth = 0
                    has_seen_main = False
                    has_seen_brace = False
                    continue

                current_block.append(line)
                brace_depth += line.count('{') - line.count('}')
                if '{' in line:
                    has_seen_brace = True
                if re.search(r'\b(int|void)\s+main\s*\(', stripped):
                    has_seen_main = True

                # If main() was found and braces are balanced back to 0
                if has_seen_main and has_seen_brace and brace_depth <= 0:
                    code_str = "\n".join(current_block).strip()
                    if len(code_str) > 30:
                        snippets.append({"language": "c", "code": code_str, "source": "document_text"})
                    in_code = False
                    current_block = []
                    brace_depth = 0
                    has_seen_main = False
                    has_seen_brace = False

        if current_block:
            code_str = "\n".join(current_block).strip()
            if len(code_str) > 30 and ("{" in code_str or "#include" in code_str):
                snippets.append({"language": "c", "code": code_str, "source": "document_text"})

        return snippets

    @classmethod
    def extract_code_blocks_from_text(cls, text: str) -> List[Dict[str, str]]:
        """Finds inline code snippets enclosed in backticks or standard markers in text documents."""
        snippets = []
        
        # 1. Match ```lang ... ```
        pattern = r"```([a-zA-Z0-9_\+\-]+)?\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        for lang, code in matches:
            lang_clean = lang.lower().strip() if lang else "c"
            snippets.append({"language": lang_clean, "code": code.strip(), "source": "markdown_code_block"})

        # 2. Match C/C++ complete programs using balanced brace parser
        if not snippets:
            c_snippets = cls.extract_c_code_blocks(text)
            if c_snippets:
                snippets.extend(c_snippets)

        # 3. Match Python style def/class blocks
        if not snippets:
            py_pattern = r"((?:def\s+\w+\(.*\):|class\s+\w+.*?:).*)"
            py_matches = re.findall(py_pattern, text, re.DOTALL)
            for py_code in py_matches:
                if len(py_code.strip()) > 30:
                    snippets.append({"language": "py", "code": py_code.strip(), "source": "python_block"})

        return snippets

    @classmethod
    def process_attachments(cls, file_paths: List[str]) -> Tuple[List[SubmissionAttachment], ExtractedContentModel]:
        """Processes multiple attachments per student and normalizes them."""
        attachments_meta = []
        all_texts = []
        all_code_snippets = []
        all_warnings = []
        diagram_flowcharts = []

        for p_str in file_paths:
            path = Path(p_str)
            if not path.exists():
                attachments_meta.append(SubmissionAttachment(
                    filename=path.name,
                    file_type="UNKNOWN",
                    file_path=str(path),
                    is_readable=False,
                    error_message="File does not exist on disk."
                ))
                all_warnings.append(f"File {path.name} not found.")
                continue

            file_type = cls.identify_file_type(path)
            size = path.stat().st_size
            text = ""
            warnings = []
            code_snippets = []

            if file_type == "PDF":
                text, warnings = cls.extract_from_pdf(path)
                pdf_snips, pdf_outs = cls.extract_code_and_output_from_images_in_pdf(path)
                code_snippets.extend(pdf_snips)
                for out_line in pdf_outs:
                    diagram_flowcharts.append(f"Visual terminal output in {path.name}: {out_line}")
            elif file_type == "DOCX":
                text, warnings = cls.extract_from_docx(path)
                docx_snips, docx_outs = cls.extract_code_and_output_from_images_in_docx(path)
                code_snippets.extend(docx_snips)
                for out_line in docx_outs:
                    diagram_flowcharts.append(f"Visual terminal output in {path.name}: {out_line}")
            elif file_type == "HTML":
                text, warnings = cls.extract_from_html(path)
            elif file_type in ("C", "CPP", "PY"):
                text, code_snippets, warnings = cls.extract_from_source_code(path, file_type)
            elif file_type == "IMAGE":
                ocr_text = OCRService.extract_text_from_image(path)
                img_snips, img_outs = OCRService.extract_code_and_output_from_ocr(ocr_text, filename=path.name)
                code_snippets.extend(img_snips)
                if ocr_text:
                    text = f"--- [Student Screenshot: {path.name}] ---\n{ocr_text}"
                else:
                    text = f"[Image Deliverable: {path.name} - Student submitted image/photo of lab output or diagram]"
                for out_line in img_outs:
                    diagram_flowcharts.append(f"Terminal output in {path.name}: {out_line}")
                if not img_outs:
                    diagram_flowcharts.append(f"Image deliverable: {path.name}")
            else:
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                except Exception as e:
                    warnings.append(f"Unsupported file type reading error: {str(e)}")

            # Extract any embedded code from PDFs or Word documents
            if file_type in ("PDF", "DOCX", "HTML", "TXT"):
                embedded = cls.extract_code_blocks_from_text(text)
                code_snippets.extend(embedded)

            # Check for flowchart / diagram keywords in text
            flowchart_keywords = ["flowchart", "flow chart", "diagram", "step 1: start", "step 2:", "pseudo code", "pseudocode"]
            for kw in flowchart_keywords:
                if kw in text.lower():
                    diagram_flowcharts.append(f"Detected {kw} section in {path.name}")
                    break

            is_readable = len(text.strip()) > 0 or len(code_snippets) > 0
            attachments_meta.append(SubmissionAttachment(
                filename=path.name,
                file_type=file_type,
                file_path=str(path),
                file_size_bytes=size,
                is_readable=is_readable,
                error_message="; ".join(warnings) if warnings else None
            ))

            if text:
                all_texts.append(f"--- Document: {path.name} ({file_type}) ---\n{text}")
            all_code_snippets.extend(code_snippets)
            all_warnings.extend(warnings)

        combined_text = "\n\n".join(all_texts)
        words = len(combined_text.split())

        extracted_model = ExtractedContentModel(
            text_content=combined_text,
            code_snippets=all_code_snippets,
            diagram_flowchart_descriptions=diagram_flowcharts,
            word_count=words,
            extraction_warnings=all_warnings
        )

        return attachments_meta, extracted_model

