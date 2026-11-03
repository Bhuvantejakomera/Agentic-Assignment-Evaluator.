import os
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple
from pypdf import PdfReader
from docx import Document
from bs4 import BeautifulSoup
from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel

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
        ".txt": "TXT"
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
                if extracted:
                    text_content.append(extracted.strip())
                else:
                    warnings.append(f"Page {idx+1} contained no extractable text (may be an image or scanned).")
            
            full_text = "\n\n".join(text_content).strip()
            if not full_text:
                warnings.append("PDF contains no selectable text.")
            return full_text, warnings
        except Exception as e:
            warnings.append(f"PDF extraction error: {str(e)}")
            return "", warnings

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

            full_text = "\n\n".join(paragraphs).strip()
            if not full_text:
                warnings.append("DOCX contains no text.")
            return full_text, warnings
        except Exception as e:
            warnings.append(f"DOCX extraction error: {str(e)}")
            return "", warnings

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
    def extract_code_blocks_from_text(cls, text: str) -> List[Dict[str, str]]:
        """Finds inline code snippets enclosed in backticks or standard markers in text documents."""
        snippets = []
        
        # Match ```lang ... ```
        pattern = r"```([a-zA-Z0-9_\+\-]+)?\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        for lang, code in matches:
            lang_clean = lang.lower().strip() if lang else "c"
            snippets.append({"language": lang_clean, "code": code.strip()})

        # Match C/C++ style #include blocks if no markdown blocks
        if not snippets:
            c_pattern = r"(#include\s+<[^>]+>.*?(?:return\s+0;|return;|exit\(0\);)?\s*\})"
            c_matches = re.findall(c_pattern, text, re.DOTALL)
            for c_code in c_matches:
                snippets.append({"language": "c", "code": c_code.strip()})

        # Match Python style def/class blocks
        if not snippets:
            py_pattern = r"((?:def\s+\w+\(.*\):|class\s+\w+.*?:).*)"
            py_matches = re.findall(py_pattern, text, re.DOTALL)
            for py_code in py_matches:
                if len(py_code.strip()) > 30:
                    snippets.append({"language": "py", "code": py_code.strip()})

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
            elif file_type == "DOCX":
                text, warnings = cls.extract_from_docx(path)
            elif file_type == "HTML":
                text, warnings = cls.extract_from_html(path)
            elif file_type in ("C", "CPP", "PY"):
                text, code_snippets, warnings = cls.extract_from_source_code(path, file_type)
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
