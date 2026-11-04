import os
import re
import tempfile
import subprocess
from pathlib import Path
from typing import Union, List, Dict, Any, Optional, Tuple

class OCRService:
    """
    High-performance OCR service utilizing native macOS Vision framework
    via compiled binary, with fallback to pytesseract/CLI.
    Extracts text, code structures, and terminal execution outputs from screenshots.
    """

    _BINARY_PATH = Path(__file__).parent.parent / "bin" / "mac_ocr"

    @classmethod
    def is_available(cls) -> bool:
        if cls._BINARY_PATH.exists() and os.access(str(cls._BINARY_PATH), os.X_OK):
            return True
        # Check fallback
        import shutil
        return shutil.which("tesseract") is not None

    @classmethod
    def extract_text_from_image(cls, image_input: Union[str, Path, bytes]) -> str:
        """
        Extracts raw text from an image file path or raw image bytes.
        """
        temp_file = None
        try:
            if isinstance(image_input, (str, Path)):
                image_path = Path(image_input)
                if not image_path.exists():
                    return ""
                target_path = str(image_path)
            elif isinstance(image_input, bytes):
                if len(image_input) < 100:
                    return ""
                # Write to temp file
                suffix = ".png"
                if image_input[:3] == b"\xff\xd8\xff":
                    suffix = ".jpg"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                    f.write(image_input)
                    temp_file = f.name
                target_path = temp_file
            else:
                return ""

            # 1. Native macOS Vision OCR binary
            if cls._BINARY_PATH.exists() and os.access(str(cls._BINARY_PATH), os.X_OK):
                try:
                    res = subprocess.run(
                        [str(cls._BINARY_PATH), target_path],
                        capture_output=True,
                        text=True,
                        timeout=15.0
                    )
                    if res.returncode == 0 and res.stdout:
                        return cls.clean_ocr_text(res.stdout)
                except Exception:
                    pass

            # 2. Fallback to tesseract if installed
            import shutil
            if shutil.which("tesseract"):
                try:
                    res = subprocess.run(
                        ["tesseract", target_path, "stdout"],
                        capture_output=True,
                        text=True,
                        timeout=20.0
                    )
                    if res.returncode == 0 and res.stdout:
                        return cls.clean_ocr_text(res.stdout)
                except Exception:
                    pass

            return ""
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass

    @classmethod
    def clean_ocr_text(cls, raw: str) -> str:
        """Cleans common OCR misrecognitions and normalizes characters."""
        if not raw:
            return ""

        text = raw
        # Normalize curved quotes and backticks
        text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
        
        # Common C library header OCR artifacts
        text = re.sub(r'#\s*include\s*[‹<]\s*stdio\.h[s>]?', '#include <stdio.h>', text, flags=re.IGNORECASE)
        text = re.sub(r'#\s*include\s*[‹<]\s*stdlib\.h[s>]?', '#include <stdlib.h>', text, flags=re.IGNORECASE)
        text = re.sub(r'#\s*include\s*[‹<]\s*math\.h[s>]?', '#include <math.h>', text, flags=re.IGNORECASE)
        text = re.sub(r'#\s*include\s*[‹<]\s*string\.h[s>]?', '#include <string.h>', text, flags=re.IGNORECASE)
        
        # Common C syntax replacements
        text = re.sub(r'\bint\s+main\s*\(\s*\)\s*\(', 'int main() {', text)
        text = re.sub(r'\bvoid\s+main\s*\(\s*\)\s*\(', 'void main() {', text)

        return text

    @classmethod
    def extract_code_and_output_from_ocr(cls, ocr_text: str, filename: str = "") -> Tuple[List[Dict[str, str]], List[str]]:
        """
        Analyzes OCR text to detect code snippets and terminal/program output.
        Returns (code_snippets, output_lines).
        """
        snippets = []
        output_lines = []

        if not ocr_text or len(ocr_text.strip()) < 15:
            return snippets, output_lines

        lines = ocr_text.splitlines()

        # 1. Detect code patterns
        code_markers = [
            r"#include", r"\bint\s+main\b", r"\bvoid\s+main\b", r"\bprintf\s*\(",
            r"\bscanf\s*\(", r"\bwhile\s*\(", r"\bfor\s*\(", r"\bif\s*\(",
            r"\breturn\s+0\s*;", r"\breturn\s+1\s*;", r"\bint\s+[a-zA-Z0-9_,\s]+;",
            r"\bdef\s+[a-zA-Z0-9_]+\s*\(", r"\bimport\s+[a-zA-Z0-9_]+"
        ]

        has_code_indicators = any(re.search(pat, ocr_text, re.IGNORECASE) for pat in code_markers)

        # 2. Detect terminal output patterns
        output_markers = [
            r"\benter\s+two\s+integers\b", r"\benter\s+an\s+integer\b", r"\benter\s+a\s+number\b",
            r"\bresults?\b", r"\bgcd\s+of\b", r"\blcm\s+of\b", r"\bis\s+a\s+palindrome\b",
            r"\bis\s+not\s+a\s+palindrome\b", r"\bnumber\s+of\s+digits\b", r"\bcount\s*=\b",
            r"\boutput\s*:\b", r"\bterminal\b", r"\buser@\b", r"\$\s+\./", r"\bgcc\b"
        ]

        for line in lines:
            if any(re.search(pat, line, re.IGNORECASE) for pat in output_markers):
                output_lines.append(line.strip())

        if has_code_indicators:
            # Clean IDE line numbers from code lines (e.g. " 1\n# include" or "17  while...")
            cleaned_code_lines = []
            for line in lines:
                # If line is just a standalone line number (e.g. "1", "2"), skip it
                if re.match(r'^\s*\d+\s*$', line):
                    continue
                # Strip leading line number (e.g. "17 while(y != 0) {" -> "while(y != 0) {")
                cleaned_line = re.sub(r'^\s*\d+\s+', '', line)
                cleaned_code_lines.append(cleaned_line)

            cleaned_code = "\n".join(cleaned_code_lines).strip()
            
            # Determine language
            lang = "c"
            if "def " in cleaned_code or "import " in cleaned_code:
                lang = "python"
            elif "cout <<" in cleaned_code or "cin >>" in cleaned_code or "std::" in cleaned_code:
                lang = "cpp"

            snippets.append({
                "language": lang,
                "code": cleaned_code,
                "filename": filename or "screenshot_code",
                "source": "screenshot_ocr",
                "has_terminal_output": len(output_lines) > 0
            })

        return snippets, output_lines
