import tempfile
from pathlib import Path
from backend.app.services.document_extractor import DocumentExtractor

def test_extract_from_source_code_c():
    with tempfile.TemporaryDirectory() as tmpdir:
        c_file = Path(tmpdir) / "test.c"
        code = '#include <stdio.h>\nint main() { printf("Hello World"); return 0; }'
        c_file.write_text(code)

        text, snippets, warnings = DocumentExtractor.extract_from_source_code(c_file, "C")
        assert "Hello World" in text
        assert len(snippets) == 1
        assert snippets[0]["language"] == "c"
        assert not warnings

def test_extract_from_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        html_file = Path(tmpdir) / "submission.html"
        html_content = "<html><head><title>Lab</title></head><body><h1>Algorithm</h1><p>Step 1: Start</p></body></html>"
        html_file.write_text(html_content)

        text, warnings = DocumentExtractor.extract_from_html(html_file)
        assert "Algorithm" in text
        assert "Step 1: Start" in text
        assert not warnings

def test_process_multiple_attachments():
    with tempfile.TemporaryDirectory() as tmpdir:
        p1 = Path(tmpdir) / "notes.txt"
        p1.write_text("Lab 1 theoretical notes on loops and conditionals.")

        p2 = Path(tmpdir) / "program.py"
        p2.write_text("def check_prime(n):\n    return n > 1\n")

        attachments_meta, extracted = DocumentExtractor.process_attachments([str(p1), str(p2)])
        assert len(attachments_meta) == 2
        assert all(a.is_readable for a in attachments_meta)
        assert "theoretical notes" in extracted.text_content
        assert len(extracted.code_snippets) >= 1

