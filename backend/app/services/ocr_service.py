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
    Includes automated dark-mode inversion, contrast normalization,
    IDE gutter line-number stripping, and terminal output classification.
    """

    _BINARY_PATH = Path(__file__).parent.parent / "bin" / "mac_ocr"

    @classmethod
    def is_available(cls) -> bool:
        if cls._BINARY_PATH.exists() and os.access(str(cls._BINARY_PATH), os.X_OK):
            return True
        import shutil
        return shutil.which("tesseract") is not None

    @classmethod
    def preprocess_image_for_ocr(cls, source_path: Path) -> Tuple[Path, bool]:
        """
        Preprocesses image for maximum OCR accuracy on IDE and terminal screenshots:
        - Detects dark-mode IDE themes (VS Code Dark+, Dev-C++ blue, Linux terminal).
        - If dark, inverts to black text on white background (drastically reduces dropped characters).
        - Enhances contrast and sharpens code text boundaries.
        Returns (preprocessed_path, is_temp).
        """
        try:
            from PIL import Image, ImageOps, ImageStat, ImageEnhance
            img = Image.open(str(source_path))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            gray = ImageOps.grayscale(img)
            stat = ImageStat.Stat(gray)
            avg_luminance = stat.mean[0]

            needs_inversion = avg_luminance < 115  # Dark mode threshold
            if needs_inversion:
                processed = ImageOps.invert(gray)
            else:
                processed = gray

            # Boost contrast for blurry or low-res screenshots
            enhancer = ImageEnhance.Contrast(processed)
            enhanced = enhancer.enhance(1.4)

            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            enhanced.save(tmp.name, format="PNG")
            tmp.close()
            return Path(tmp.name), True
        except Exception:
            return source_path, False

    @classmethod
    def extract_text_from_image(cls, image_input: Union[str, Path, bytes]) -> str:
        """
        Extracts raw text from an image file path or raw image bytes with auto-preprocessing.
        """
        temp_file = None
        processed_temp = None
        try:
            if isinstance(image_input, (str, Path)):
                image_path = Path(image_input)
                if not image_path.exists():
                    return ""
                target_path = image_path
            elif isinstance(image_input, bytes):
                if len(image_input) < 100:
                    return ""
                suffix = ".png"
                if image_input[:3] == b"\xff\xd8\xff":
                    suffix = ".jpg"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                    f.write(image_input)
                    temp_file = f.name
                target_path = Path(temp_file)
            else:
                return ""

            # Apply Apple Silicon / Pillow preprocessing (Dark mode inversion + contrast)
            ocr_target, is_temp = cls.preprocess_image_for_ocr(target_path)
            if is_temp:
                processed_temp = str(ocr_target)

            # 1. Native macOS Vision OCR binary (runs blazingly fast on M-Series Neural Engine)
            if cls._BINARY_PATH.exists() and os.access(str(cls._BINARY_PATH), os.X_OK):
                try:
                    res = subprocess.run(
                        [str(cls._BINARY_PATH), str(ocr_target)],
                        capture_output=True,
                        text=True,
                        timeout=15.0
                    )
                    if res.returncode == 0 and res.stdout:
                        return cls.clean_ocr_text(res.stdout)
                except Exception:
                    pass

            # 2. Fallback to tesseract CLI if installed
            import shutil
            if shutil.which("tesseract"):
                try:
                    res = subprocess.run(
                        ["tesseract", str(ocr_target), "stdout"],
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
            if processed_temp and os.path.exists(processed_temp):
                try:
                    os.unlink(processed_temp)
                except Exception:
                    pass

    @classmethod
    def clean_ocr_text(cls, raw: str) -> str:
        """Cleans common OCR misrecognitions and normalizes code & terminal characters."""
        if not raw:
            return ""

        text = raw
        # Normalize curved quotes and backticks
        text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
        text = text.replace("«", '"').replace("»", '"').replace("`", "'")

        # Common C library header OCR artifacts
        text = re.sub(r'#\s*1nclude', '#include', text, flags=re.IGNORECASE)
        text = re.sub(r'#\s*include\s*[‹<]\s*stdio\.h[s>]?', '#include <stdio.h>', text, flags=re.IGNORECASE)
        text = re.sub(r'#\s*include\s*[‹<]\s*stdlib\.h[s>]?', '#include <stdlib.h>', text, flags=re.IGNORECASE)
        text = re.sub(r'#\s*include\s*[‹<]\s*math\.h[s>]?', '#include <math.h>', text, flags=re.IGNORECASE)
        text = re.sub(r'#\s*include\s*[‹<]\s*string\.h[s>]?', '#include <string.h>', text, flags=re.IGNORECASE)
        text = re.sub(r'#\s*include\s*[‹<]\s*conio\.h[s>]?', '#include <conio.h>', text, flags=re.IGNORECASE)

        # Common syntax repairs from OCR
        text = re.sub(r'\b1nt\s+main\b', 'int main', text)
        text = re.sub(r'\bintmain\s*\(', 'int main(', text)
        text = re.sub(r'\bvoidmain\s*\(', 'void main(', text)
        text = re.sub(r'\bpr1ntf\b', 'printf', text)
        text = re.sub(r'\bsc4nf\b', 'scanf', text)
        text = re.sub(r'\bint\s+main\s*\(\s*\)\s*\(', 'int main() {', text)
        text = re.sub(r'\bvoid\s+main\s*\(\s*\)\s*\(', 'void main() {', text)

        return text

    @classmethod
    def extract_code_and_output_from_ocr(cls, ocr_text: str, filename: str = "") -> Tuple[List[Dict[str, str]], List[str]]:
        """
        Analyzes OCR text to detect code snippets and terminal/program output.
        Distinguishes IDE source code blocks from terminal console output runs.
        Returns (code_snippets, output_lines).
        """
        snippets = []
        output_lines = []

        if not ocr_text or len(ocr_text.strip()) < 10:
            return snippets, output_lines

        lines = ocr_text.splitlines()

        # 1. Detect code patterns
        code_markers = [
            r"#include", r"\bint\s+main\b", r"\bvoid\s+main\b", r"\bprintf\s*\(",
            r"\bscanf\s*\(", r"\bwhile\s*\(", r"\bfor\s*\(", r"\bif\s*\(",
            r"\breturn\s+0\s*;", r"\breturn\s+1\s*;", r"\bint\s+[a-zA-Z0-9_,\s]+;",
            r"\bfloat\s+[a-zA-Z0-9_,\s]+;", r"\bdouble\s+[a-zA-Z0-9_,\s]+;",
            r"\bdef\s+[a-zA-Z0-9_]+\s*\(", r"\bimport\s+[a-zA-Z0-9_]+",
            r"cout\s*<<", r"cin\s*>>"
        ]

        has_code_indicators = any(re.search(pat, ocr_text, re.IGNORECASE) for pat in code_markers)

        # 2. Detect terminal output patterns (including arithmetic, binary, and problem runs)
        output_markers = [
            r"\benter\s+(?:two\s+)?integers?\b", r"\benter\s+(?:an?\s+)?numbers?\b",
            r"\benter\s+the\s+value\b", r"\benter\s+choice\b", r"\binput\s*:\b",
            r"\bresults?\s*[:=]\b", r"\bsum\s*[:=]\b", r"\baddition\s*[:=]\b",
            r"\bdifference\s*[:=]\b", r"\bproduct\s*[:=]\b", r"\bquotient\s*[:=]\b",
            r"\bremainder\s*[:=]\b", r"\bbinary\b", r"\bdecimal\b",
            r"\bgcd\s+of\b", r"\blcm\s+of\b", r"\bis\s+a\s+palindrome\b",
            r"\bis\s+not\s+a\s+palindrome\b", r"\bnumber\s+of\s+digits\b", r"\bcount\s*=\b",
            r"\boutput\s*[:=-]\b", r"\bterminal\b", r"\buser@\b", r"\$\s+\./", r"\bgcc\b",
            r"\bprocess\s+returned\s+0\b", r"\bexecution\s+time\b", r"\bpress\s+any\s+key\b"
        ]

        for line in lines:
            line_str = line.strip()
            if any(re.search(pat, line_str, re.IGNORECASE) for pat in output_markers):
                output_lines.append(line_str)
            # Detect standalone binary number patterns (e.g. "1010", "11001") in output
            elif re.match(r'^(?:[01]{4,32}|[0-9]+\s+[01]{4,32})$', line_str):
                output_lines.append(f"Binary output: {line_str}")

        if has_code_indicators:
            # Clean IDE line numbers from code lines (e.g. " 1\n# include" or "17  while...")
            cleaned_code_lines = []
            for line in lines:
                # If line is just a standalone line number (e.g. "1", "2"), skip it
                if re.match(r'^\s*\d+\s*$', line):
                    continue
                # Strip leading IDE gutter line number (e.g. "17 while(y != 0) {" -> "while(y != 0) {")
                cleaned_line = re.sub(r'^\s*\d{1,4}\s+', '', line)
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
