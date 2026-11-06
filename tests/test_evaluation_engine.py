import pytest
from backend.app.models.rubric import RubricResponse, CriterionModel
from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel
from backend.app.services.evaluation_engine import EvaluationEngine

@pytest.fixture
def sample_rubric():
    criteria = [
        CriterionModel(id="c1", name="Algorithm", description="Step-by-step logic", max_marks=30.0, evaluation_type="algorithm"),
        CriterionModel(id="c2", name="Flowchart", description="Visual logic diagram", max_marks=20.0, evaluation_type="diagram_flowchart"),
        CriterionModel(id="c3", name="Code Implementation", description="C program code", max_marks=50.0, evaluation_type="code_execution")
    ]
    return RubricResponse(
        id="rub-test-1",
        course_id="crs-1",
        assignment_id="assign-1",
        version=1,
        status="APPROVED",
        criteria=criteria,
        total_max_marks=100.0,
        late_penalty_percent=20.0,
        created_at="2026-11-03T10:00:00"
    )

def test_full_correct_submission(sample_rubric):
    text = (
        "Algorithm:\nStep 1: Start\nStep 2: Read N\nStep 3: Print result\n"
        "Flowchart structure: Oval start -> Rectangle input -> Diamond branch -> Oval stop\n"
        "C Program code attached."
    )
    code = [{"language": "c", "code": "#include <stdio.h>\nint main() { printf(\"Test\"); return 0; }"}]
    extracted = ExtractedContentModel(text_content=text, code_snippets=code, word_count=len(text.split()))

    res = EvaluationEngine.evaluate_submission(
        run_id="run-1",
        course_id="crs-1",
        assignment_id="assign-1",
        student_id="AP101",
        student_name="Test Student",
        submission_id="sub-1",
        state="TURNED_IN",
        is_late=False,
        attachments=[SubmissionAttachment(filename="lab.c", file_type="C", file_path="/tmp/lab.c", is_readable=True)],
        extracted_content=extracted,
        rubric=sample_rubric,
        assignment_title="Lab 1 - Prime Numbers",
        assignment_description="Algorithm, Flowchart and C program"
    )

    assert res.final_score >= 90.0
    assert not res.flags

def test_partial_submission_missing_flowchart(sample_rubric):
    text = "Algorithm:\nStep 1: Start\nStep 2: Read N\nStep 3: Print result"
    code = [{"language": "c", "code": "#include <stdio.h>\nint main() { return 0; }"}]
    extracted = ExtractedContentModel(text_content=text, code_snippets=code, word_count=len(text.split()))

    res = EvaluationEngine.evaluate_submission(
        run_id="run-1",
        course_id="crs-1",
        assignment_id="assign-1",
        student_id="AP102",
        student_name="Partial Student",
        submission_id="sub-2",
        state="TURNED_IN",
        is_late=False,
        attachments=[SubmissionAttachment(filename="code.c", file_type="C", file_path="/tmp/code.c", is_readable=True)],
        extracted_content=extracted,
        rubric=sample_rubric,
        assignment_title="Lab 1 - Prime Numbers",
        assignment_description="Algorithm, Flowchart and C program"
    )

    # Flowchart criterion should be 0, total around 70-80
    fc_crit = next(c for c in res.criteria_breakdown if c.criterion_id == "c2")
    assert fc_crit.awarded_marks == 0.0
    assert "INCOMPLETE" in res.flags

def test_wrong_submission_detection(sample_rubric):
    text = "Title: Determination of Planck's Constant using Photoelectric Effect. Physics experiment."
    extracted = ExtractedContentModel(text_content=text, code_snippets=[], word_count=len(text.split()))

    res = EvaluationEngine.evaluate_submission(
        run_id="run-1",
        course_id="crs-1",
        assignment_id="assign-1",
        student_id="AP103",
        student_name="Wrong PDF Student",
        submission_id="sub-3",
        state="TURNED_IN",
        is_late=False,
        attachments=[SubmissionAttachment(filename="physics.pdf", file_type="PDF", file_path="/tmp/p.pdf", is_readable=True)],
        extracted_content=extracted,
        rubric=sample_rubric,
        assignment_title="Lab 1 - Prime Numbers",
        assignment_description="Algorithm, Flowchart and C program in C"
    )

    assert res.final_score == 0.0
    assert "WRONG_PDF" in res.flags
    assert "wrong pdf" in res.faculty_remarks.lower()

def test_late_submission_penalty(sample_rubric):
    text = (
        "Algorithm:\nStep 1: Start\nStep 2: Read N\n"
        "Flowchart structure: Oval start -> Rectangle -> Oval stop\n"
    )
    code = [{"language": "c", "code": "#include <stdio.h>\nint main() { return 0; }"}]
    extracted = ExtractedContentModel(text_content=text, code_snippets=code, word_count=len(text.split()))

    res = EvaluationEngine.evaluate_submission(
        run_id="run-1",
        course_id="crs-1",
        assignment_id="assign-1",
        student_id="AP104",
        student_name="Late Student",
        submission_id="sub-4",
        state="TURNED_IN",
        is_late=True,
        attachments=[SubmissionAttachment(filename="code.c", file_type="C", file_path="/tmp/code.c", is_readable=True)],
        extracted_content=extracted,
        rubric=sample_rubric,
        assignment_title="Lab 1 - Prime Numbers",
        assignment_description="Algorithm, Flowchart and C program"
    )

    assert "LATE" in res.flags
    assert res.late_penalty > 0
    assert "Late" in res.faculty_remarks

@pytest.mark.anyio
async def test_rubric_generation_with_custom_guidance():
    from backend.app.services.llm_engine import LocalLLMEngine
    guidance = "The student is expected to submit a PDF or word file or code files that shows that he/she has executed the arithmetic operation and converting the decimal to binary"
    criteria = await LocalLLMEngine.generate_rubric_from_assignment(
        assignment_title="Lab - Arithmetic & Conversion",
        assignment_description="Complete programming lab tasks",
        max_points=100.0,
        custom_guidance=guidance
    )

    crit_dict = {c.name: c.max_marks for c in criteria}
    # Verify exact criteria formulated from faculty instructions
    assert "Arithmetic Operations Logic & Implementation" in crit_dict
    assert crit_dict["Arithmetic Operations Logic & Implementation"] == 30.0
    assert "Decimal to Binary Conversion Logic" in crit_dict
    assert crit_dict["Decimal to Binary Conversion Logic"] == 30.0
    assert "Visual Execution & Output Proof" in crit_dict
    assert crit_dict["Visual Execution & Output Proof"] == 20.0
    assert "Code Quality & Compliance" in crit_dict
    assert crit_dict["Code Quality & Compliance"] == 20.0
    assert sum(c.max_marks for c in criteria) == 100.0

@pytest.mark.anyio
async def test_rubric_generation_without_guidance_generates_default():
    from backend.app.services.llm_engine import LocalLLMEngine
    # When faculty does NOT provide custom guidance, only then generate default academic criteria
    criteria = await LocalLLMEngine.generate_rubric_from_assignment(
        assignment_title="Lab 1 - Prime Numbers",
        assignment_description="Algorithm, Flowchart and C program in Linux",
        max_points=100.0,
        custom_guidance=None
    )

    crit_names = [c.name for c in criteria]
    # Default criteria should include algorithm, flowchart, program implementation
    assert any("Algorithm" in name for name in crit_names)
    assert any("Flowchart" in name for name in crit_names)
    assert any("Program Implementation" in name for name in crit_names)
    assert sum(c.max_marks for c in criteria) == 100.0

def test_evaluation_with_custom_faculty_expectations_and_screenshots():
    # Rubric created with custom faculty expectations
    guidance = "The student is expected to submit a PDF or word file or code files that shows that he/she has executed the arithmetic operation and converting the decimal to binary"
    criteria = [
        CriterionModel(id="c1", name="Arithmetic Operations", description="Arithmetic calculations", max_marks=40.0, evaluation_type="code_execution"),
        CriterionModel(id="c2", name="Decimal to Binary Conversion", description="Binary conversion logic", max_marks=40.0, evaluation_type="code_execution"),
        CriterionModel(id="c3", name="Visual Output Proof", description="Execution screenshots", max_marks=20.0, evaluation_type="compliance")
    ]
    rubric = RubricResponse(
        id="rub-custom-1",
        course_id="crs-1",
        assignment_id="assign-custom-1",
        version=1,
        status="APPROVED",
        criteria=criteria,
        total_max_marks=100.0,
        late_penalty_percent=20.0,
        custom_guidance=guidance,
        created_at="2026-11-06T10:00:00"
    )

    # Student submission with IDE screenshot code and terminal output
    screenshot_code = [
        {
            "language": "c",
            "code": "#include <stdio.h>\nint main() {\n  int a = 10, b = 5;\n  int sum = a + b;\n  int n = 13, rem, binary = 0;\n  while (n > 0) { rem = n % 2; n = n / 2; }\n  return 0;\n}",
            "filename": "ide_screenshot.png",
            "source": "screenshot_ocr",
            "has_terminal_output": True
        }
    ]
    extracted = ExtractedContentModel(
        text_content="Lab Exercise: Arithmetic & Binary Conversion\nHeading 1: C Program and Output",
        code_snippets=screenshot_code,
        diagram_flowchart_descriptions=["Visual terminal output: Sum = 15, Binary = 1101"],
        word_count=12
    )

    res = EvaluationEngine.evaluate_submission(
        run_id="run-custom",
        course_id="crs-1",
        assignment_id="assign-custom-1",
        student_id="AP999",
        student_name="Screenshot Student",
        submission_id="sub-custom-1",
        state="TURNED_IN",
        is_late=False,
        attachments=[SubmissionAttachment(filename="report.pdf", file_type="PDF", file_path="/tmp/report.pdf", is_readable=True)],
        extracted_content=extracted,
        rubric=rubric,
        assignment_title="Lab 2 - Computing Arithmetic",
        assignment_description="Perform calculations and conversions"
    )

    # Should succeed without false WRONG_PDF flag and award high marks
    assert "WRONG_PDF" not in res.flags
    assert res.final_score >= 80.0

def test_ocr_preprocessing_dark_mode(tmp_path):
    from PIL import Image, ImageDraw
    from backend.app.services.ocr_service import OCRService

    # Create dark image (VS Code dark theme style)
    dark_img = Image.new("RGB", (300, 100), color=(25, 25, 25))
    d = ImageDraw.Draw(dark_img)
    d.text((10, 10), "int main() { return 0; }", fill=(230, 230, 230))
    p = tmp_path / "dark_ide.png"
    dark_img.save(str(p))

    processed_path, is_temp = OCRService.preprocess_image_for_ocr(p)
    assert is_temp is True
    assert processed_path.exists()

@pytest.mark.anyio
async def test_rubric_generation_with_arbitrary_domain_dijkstra():
    from backend.app.services.llm_engine import LocalLLMEngine
    guidance = "Students must implement Dijkstra algorithm for shortest path in C and display the adjacency matrix with execution output screenshot"
    criteria = await LocalLLMEngine.generate_rubric_from_assignment(
        assignment_title="Lab - Graph Algorithms",
        assignment_description="Shortest path computations in C",
        max_points=100.0,
        custom_guidance=guidance
    )

    crit_dict = {c.name: c.max_marks for c in criteria}
    # Dynamically derived criteria from arbitrary domain
    assert "Dijkstra Algorithm For Shortest Path In C" in crit_dict
    assert crit_dict["Dijkstra Algorithm For Shortest Path In C"] == 40.0
    assert "Adjacency Matrix Logic & Implementation" in crit_dict
    assert crit_dict["Adjacency Matrix Logic & Implementation"] == 40.0
    assert "Visual Execution & Output Proof" in crit_dict
    assert crit_dict["Visual Execution & Output Proof"] == 20.0
    assert sum(c.max_marks for c in criteria) == 100.0

@pytest.mark.anyio
async def test_rubric_generation_with_arbitrary_domain_bank_struct():
    from backend.app.services.llm_engine import LocalLLMEngine
    guidance = "Implement bank account management with struct, deposit, withdraw, balance check, and transaction history in text file"
    criteria = await LocalLLMEngine.generate_rubric_from_assignment(
        assignment_title="Lab - File Handling & Structs",
        assignment_description="Build persistent banking operations",
        max_points=100.0,
        custom_guidance=guidance
    )

    crit_dict = {c.name: c.max_marks for c in criteria}
    assert "Bank Account Management With Struct" in crit_dict
    assert "Deposit Logic & Implementation" in crit_dict
    assert "Withdraw Logic & Implementation" in crit_dict
    assert "Balance Check Logic & Implementation" in crit_dict
    assert "Transaction History In Text File Logic & Implementation" in crit_dict
    assert sum(c.max_marks for c in criteria) == 100.0

@pytest.mark.anyio
async def test_rubric_generation_with_arbitrary_domain_cpu_scheduling():
    from backend.app.services.llm_engine import LocalLLMEngine
    guidance = "The assignment requires students to write a C program for CPU scheduling using FCFS and Round Robin algorithms, and show gantt charts and average waiting time in screenshot"
    criteria = await LocalLLMEngine.generate_rubric_from_assignment(
        assignment_title="Lab - Operating Systems Scheduling",
        assignment_description="Implement and compare scheduling algorithms",
        max_points=100.0,
        custom_guidance=guidance
    )

    crit_dict = {c.name: c.max_marks for c in criteria}
    assert "CPU Scheduling Using FCFS Logic & Implementation" in crit_dict
    assert "Round Robin Algorithms" in crit_dict
    assert "Show Gantt Charts" in crit_dict
    assert "Average Waiting Time Logic & Implementation" in crit_dict
    assert "Visual Execution & Output Proof" in crit_dict
    assert sum(c.max_marks for c in criteria) == 100.0

def test_evaluation_with_arbitrary_domain_dijkstra_submission():
    guidance = "Students must implement Dijkstra algorithm for shortest path in C and display the adjacency matrix with execution output screenshot"
    criteria = [
        CriterionModel(id="c1", name="Dijkstra Algorithm For Shortest Path In C", description="Shortest path implementation", max_marks=40.0, evaluation_type="algorithm"),
        CriterionModel(id="c2", name="Adjacency Matrix Logic & Implementation", description="Matrix display logic", max_marks=40.0, evaluation_type="code_execution"),
        CriterionModel(id="c3", name="Visual Execution & Output Proof", description="Execution screenshots", max_marks=20.0, evaluation_type="compliance")
    ]
    rubric = RubricResponse(
        id="rub-dijkstra-1",
        course_id="crs-1",
        assignment_id="assign-dijkstra-1",
        version=1,
        status="APPROVED",
        criteria=criteria,
        total_max_marks=100.0,
        late_penalty_percent=20.0,
        custom_guidance=guidance,
        created_at="2026-11-06T10:00:00"
    )

    dijkstra_c_code = """
#include <stdio.h>
#define INF 9999
int dijkstra(int graph[10][10], int n, int start) {
    int distance[10], visited[10];
    for (int i=0; i<n; i++) { distance[i] = graph[start][i]; visited[i]=0; }
    visited[start] = 1;
    for (int count=1; count<n-1; count++) {
        int min = INF, next = 0;
        for (int i=0; i<n; i++) {
            if (distance[i] < min && !visited[i]) { min = distance[i]; next = i; }
        }
        visited[next] = 1;
        for (int i=0; i<n; i++) {
            if (!visited[i] && min + graph[next][i] < distance[i]) {
                distance[i] = min + graph[next][i];
            }
        }
    }
    printf("Adjacency matrix loaded. Shortest path computed.\\n");
    return 0;
}
"""
    screenshot_snippets = [
        {
            "language": "c",
            "code": dijkstra_c_code,
            "filename": "dijkstra_ide_screenshot.png",
            "source": "screenshot_ocr",
            "has_terminal_output": True
        }
    ]
    extracted = ExtractedContentModel(
        text_content="Lab Exercise: Graph Shortest Path using Dijkstra Algorithm\nStep 1: Read adjacency matrix\nStep 2: Initialize distance\nStep 3: Update shortest distances",
        code_snippets=screenshot_snippets,
        diagram_flowchart_descriptions=["Visual terminal output: Shortest path from node 0 to 4 = 12"],
        word_count=25
    )

    res = EvaluationEngine.evaluate_submission(
        run_id="run-dijkstra",
        course_id="crs-1",
        assignment_id="assign-dijkstra-1",
        student_id="AP505",
        student_name="Graph Student",
        submission_id="sub-dijkstra-1",
        state="TURNED_IN",
        is_late=False,
        attachments=[SubmissionAttachment(filename="dijkstra_report.pdf", file_type="PDF", file_path="/tmp/dijkstra.pdf", is_readable=True)],
        extracted_content=extracted,
        rubric=rubric,
        assignment_title="Lab 6 - Dijkstra Graph Shortest Path",
        assignment_description="Implement graph algorithms in C"
    )

    assert "WRONG_PDF" not in res.flags
    assert res.final_score >= 90.0
    # Verify that faculty guidance is cited in the remarks or explanations
    assert any("dijkstra" in c.explanation.lower() for c in res.criteria_breakdown)

@pytest.mark.anyio
async def test_rubric_generation_with_lettered_list_and_explicit_marks():
    from backend.app.services.llm_engine import LocalLLMEngine
    guidance = """Student is expected to submit a PDF or word that has the screenshot or the code and output for the folowing tasks.
a)Find the sum of individual digits of a positive integer and find the reverse of the given number. (33 marks)
b)Generate the first n terms of Fibonacci sequence.(30 marks)  
c)Generate all the prime numbers between 1 and n, where n is a value supplied by the user.(33 marks)

and 4 marks for heading and code readability."""

    criteria = await LocalLLMEngine.generate_rubric_from_assignment(
        assignment_title="Lab 1 - Loops & Math",
        assignment_description="Exercises on digits, Fibonacci, and primes",
        max_points=100.0,
        custom_guidance=guidance
    )

    crit_dict = {c.name: c.max_marks for c in criteria}
    assert any("Sum of Digits" in k for k in crit_dict)
    assert any("Fibonacci" in k for k in crit_dict)
    assert any("Prime" in k for k in crit_dict)
    assert any("Readability" in k or "Headings" in k for k in crit_dict)
    # Check exact marks
    assert any("Sum of Digits" in k and crit_dict[k] == 33.0 for k in crit_dict)
    assert any("Fibonacci" in k and crit_dict[k] == 30.0 for k in crit_dict)
    assert any("Prime" in k and crit_dict[k] == 33.0 for k in crit_dict)
    assert any(("Readability" in k or "Headings" in k) and crit_dict[k] == 4.0 for k in crit_dict)
    assert sum(c.max_marks for c in criteria) == 100.0

@pytest.mark.anyio
async def test_rubric_generation_with_continuous_prose_and_math_symbols():
    from backend.app.services.llm_engine import LocalLLMEngine
    guidance = """Students are required to submit a single PDF or Word document containing either clear screenshots or the formatted text of their C++ source code alongside verified terminal output screenshots for all three tasks. The assignment is evaluated out of a total of 100 marks: Task A (finding the sum of individual digits of a positive integer and its reverse) carries 33 marks, Task B (generating the first $n$ terms of the Fibonacci sequence) carries 30 marks, and Task C (generating all prime numbers between $1$ and $n$, with $n$ provided by the user) carries 33 marks. The remaining 4 marks are allotted for documentation quality, specifically proper document headings (student details and task titles) and overall code readability, including clean indentation and comments."""

    criteria = await LocalLLMEngine.generate_rubric_from_assignment(
        assignment_title="Lab 1 - Mathematical Algorithms",
        assignment_description="C++ programming lab",
        max_points=100.0,
        custom_guidance=guidance
    )

    crit_dict = {c.name: c.max_marks for c in criteria}
    assert any("Sum of Digits" in k and crit_dict[k] == 33.0 for k in crit_dict)
    assert any("Fibonacci" in k and crit_dict[k] == 30.0 for k in crit_dict)
    assert any("Prime" in k and crit_dict[k] == 33.0 for k in crit_dict)
    assert any(("Readability" in k or "Headings" in k) and crit_dict[k] == 4.0 for k in crit_dict)
    assert sum(c.max_marks for c in criteria) == 100.0

@pytest.mark.anyio
async def test_rubric_generation_with_markdown_bold_bullets():
    from backend.app.services.llm_engine import LocalLLMEngine
    guidance = """* **Submission Format:** A single PDF or Word document containing either the code text or clear source code screenshots, alongside terminal execution output screenshots for each task.
* **Task A (33 Marks):** Find the sum of individual digits of a positive integer and find the reverse of the given number.
* **Task B (30 Marks):** Generate the first $n$ terms of the Fibonacci sequence.
* **Task C (33 Marks):** Generate all prime numbers between $1$ and $n$, where $n$ is supplied by the user.
* **Formatting & Documentation (4 Marks):** Proper document headings (student details, task titles) and code readability (clean indentation and comments).
* **Total Marks:** 100 Marks."""

    criteria = await LocalLLMEngine.generate_rubric_from_assignment(
        assignment_title="Lab 1 - Markdown Style",
        assignment_description="Structured task syllabus",
        max_points=100.0,
        custom_guidance=guidance
    )

    crit_dict = {c.name: c.max_marks for c in criteria}
    assert any("Sum of Digits" in k and crit_dict[k] == 33.0 for k in crit_dict)
    assert any("Fibonacci" in k and crit_dict[k] == 30.0 for k in crit_dict)
    assert any("Prime" in k and crit_dict[k] == 33.0 for k in crit_dict)
    assert any(("Readability" in k or "Headings" in k or "Formatting" in k) and crit_dict[k] == 4.0 for k in crit_dict)
    assert sum(c.max_marks for c in criteria) == 100.0

@pytest.mark.anyio
async def test_rubric_generation_with_lab_sheet_sections():
    from backend.app.services.llm_engine import LocalLLMEngine
    guidance = """### Lab Instructions & Evaluation Scheme

* **Deliverable:** Upload a single file (**PDF or Word**) containing the source code (pasted text or readable screenshots) paired with terminal output screenshots for each exercise.
* **Task 1 — Digit Sum & Reversal (33 Marks):**
Accept a positive integer, calculate the sum of its individual digits, and print the reversed number.
* **Task 2 — Fibonacci Generator (30 Marks):**
Prompt for $n$ and output the first $n$ numbers in the Fibonacci sequence.
* **Task 3 — Prime Numbers Range (33 Marks):**
Take an upper bound $n$ from the user and display all prime numbers in the interval $[1, n]$.
* **Presentation & Quality (4 Marks):**
Header details (Student Name, Roll Number/ID, Lab Title) plus clean, readable code with proper spacing and indentation.
* **Total Assessment:** 100 Marks"""

    criteria = await LocalLLMEngine.generate_rubric_from_assignment(
        assignment_title="Lab Manual Sheet",
        assignment_description="Structured course manual",
        max_points=100.0,
        custom_guidance=guidance
    )

    crit_dict = {c.name: c.max_marks for c in criteria}
    assert any("Task 1" in k and crit_dict[k] == 33.0 for k in crit_dict)
    assert any("Task 2" in k and crit_dict[k] == 30.0 for k in crit_dict)
    assert any("Task 3" in k and crit_dict[k] == 33.0 for k in crit_dict)
    assert any(("Presentation" in k or "Readability" in k or "Quality" in k) and crit_dict[k] == 4.0 for k in crit_dict)
    assert sum(c.max_marks for c in criteria) == 100.0

@pytest.mark.anyio
async def test_rubric_generation_with_direct_override():
    from backend.app.services.llm_engine import LocalLLMEngine
    guidance = "Refer to the instructions and evaluate only for code readability and formatting structure."
    criteria = await LocalLLMEngine.generate_rubric_from_assignment(
        assignment_title="Code Review",
        assignment_description="Check styling",
        max_points=100.0,
        custom_guidance=guidance
    )

    assert len(criteria) == 1
    assert "Readability" in criteria[0].name or "Compliance" in criteria[0].name
    assert criteria[0].max_marks == 100.0
    assert criteria[0].evaluation_type == "compliance"

def test_pdf_docx_screenshot_not_penalized_by_compilation():
    from backend.app.services.evaluation_engine import EvaluationEngine
    from backend.app.models.rubric import RubricResponse, CriterionModel
    from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel

    # Mock PDF attachment with OCR code containing line numbers
    attachment = SubmissionAttachment(
        filename="LAB-3.pdf",
        file_type="PDF",
        file_path="/tmp/LAB-3.pdf",
        is_readable=True
    )
    
    extracted = ExtractedContentModel(
        text_content="Student submitted Lab 3 with digits sum, fibonacci, and prime numbers.",
        code_snippets=[
            {
                "language": "c",
                "code": "#include <stdio.h>\n2\n3\n4\nint main() { int num, sum=0, rev=0; scanf(\"%d\", &num); while(num>0){ sum += num%10; rev = rev*10 + num%10; num /= 10; } printf(\"%d %d\", sum, rev); return 0; }",
                "source": "screenshot_ocr"
            }
        ],
        diagram_flowchart_descriptions=["Visual terminal output in LAB-3.pdf: Enter a positive integer: 1234 sum=10 rev=4321"],
        word_count=50,
        extraction_warnings=[]
    )

    crit = CriterionModel(
        id="crit_1",
        name="Task A: Sum of Digits & Reversal",
        description="Calculate sum of digits and reverse of positive integer",
        max_marks=33.0,
        evaluation_type="code_execution"
    )

    rubric = RubricResponse(
        id="r_test",
        course_id="c1",
        assignment_id="a1",
        version=1,
        status="APPROVED",
        criteria=[crit],
        total_max_marks=33.0,
        late_penalty_percent=0.0,
        created_at="now"
    )

    result = EvaluationEngine.evaluate_submission(
        submission_id="sub_test",
        run_id="run_test",
        course_id="c1",
        assignment_id="a1",
        student_id="s_test",
        student_name="Test Student",
        state="TURNED_IN",
        rubric=rubric,
        attachments=[attachment],
        extracted_content=extracted,
        is_late=False,
        assignment_title="Lab 3",
        assignment_description="C Programming Lab 3"
    )

    assert result.code_execution_results is None
    assert "INCOMPLETE" not in result.flags
    assert result.raw_score == 33.0
    assert result.criteria_breakdown[0].status == "completed"
    assert "Compilation failed" not in result.criteria_breakdown[0].explanation

@pytest.mark.anyio
async def test_missing_output_penalty_applied_consistently_across_coding_tasks():
    from backend.app.services.evaluation_engine import EvaluationEngine
    from backend.app.services.llm_engine import LocalLLMEngine
    from backend.app.models.rubric import RubricResponse
    from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel

    guidance = """Student is expected to submit a PDF or word that has the screenshots of the code and output for:
a)Find the sum of individual digits of a positive integer and find the reverse of the given number. (33 marks)
b)Generate the first n terms of Fibonacci sequence.(30 marks)  
c)Generate all the prime numbers between 1 and n, where n is a value supplied by the user.(33 marks)

and 4 marks for headings and code readability.
d)If there is no output do a minus of 5 per task"""

    criteria = await LocalLLMEngine.generate_rubric_from_assignment("Lab", "C Lab", 100.0, guidance)
    # Verify all tasks are code_execution
    assert all(c.evaluation_type == "code_execution" for c in criteria if "Task" in c.name)

    rubric = RubricResponse(
        id="r_pen", course_id="c1", assignment_id="a1", version=1, status="APPROVED",
        criteria=criteria, total_max_marks=100.0, late_penalty_percent=0.0, custom_guidance=guidance, created_at="now"
    )

    # 1. Test student WITH output in document text
    ext_with_out = ExtractedContentModel(
        text_content="C Lab Work\nOUTPUT:\nPS D:\\Lab> gcc task.c\n./a.exe\nEnter a positive integer: 20\nResults: 2",
        code_snippets=[
            {
                "language": "c",
                "code": "#include <stdio.h>\n// Task A: reverse number & digits\nint rev=0, rem;\nwhile(n>0){ rem=n%10; rev=rev*10+rem; }\n// Task B: fibonacci\nint t1=0, t2=1;\n// Task C: prime\nfor(int i=2; i<n; i++){}\nint main(){ return 0; }",
                "source": "screenshot_ocr"
            }
        ],
        diagram_flowchart_descriptions=[],
        word_count=50
    )
    att = SubmissionAttachment(filename="doc.docx", file_type="DOCX", file_path="/tmp/doc.docx", is_readable=True)
    res_with_out = EvaluationEngine.evaluate_submission(
        submission_id="s1", run_id="r1", course_id="c1", assignment_id="a1",
        student_id="st1", student_name="Student With Output", state="TURNED_IN",
        is_late=False, attachments=[att], extracted_content=ext_with_out, rubric=rubric,
        assignment_title="Lab", assignment_description="C Lab"
    )
    # Output is present in text => No penalty applied
    assert not any("Penalty applied" in c.explanation for c in res_with_out.criteria_breakdown)

    # 2. Test student WITHOUT any output
    ext_no_out = ExtractedContentModel(
        text_content="Student submitted code only without running it.",
        code_snippets=[
            {
                "language": "c",
                "code": "#include <stdio.h>\n// Task A: reverse number & digits\nint rev=0, rem;\nwhile(n>0){ rem=n%10; rev=rev*10+rem; }\n// Task B: fibonacci\nint t1=0, t2=1;\n// Task C: prime\nfor(int i=2; i<n; i++){}\nint main(){ return 0; }",
                "source": "screenshot_ocr"
            }
        ],
        diagram_flowchart_descriptions=[],
        word_count=20
    )
    res_no_out = EvaluationEngine.evaluate_submission(
        submission_id="s2", run_id="r1", course_id="c1", assignment_id="a1",
        student_id="st2", student_name="Student No Output", state="TURNED_IN",
        is_late=False, attachments=[att], extracted_content=ext_no_out, rubric=rubric,
        assignment_title="Lab", assignment_description="C Lab"
    )
    # Output is absent => Penalty applied across all coding tasks
    coding_crits = [c for c in res_no_out.criteria_breakdown if "Task" in c.criterion_name]
    assert all("Penalty applied" in c.explanation for c in coding_crits)
    assert all(c.awarded_marks <= (c.max_marks - 5.0) for c in coding_crits)


def test_unrelated_lab_categorized_as_wrong_pdf():
    from backend.app.services.evaluation_engine import EvaluationEngine
    from backend.app.models.rubric import RubricResponse, CriterionModel
    from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel

    # Rubric for Lab 3
    criteria = [
        CriterionModel(id="c1", name="Task A: Sum of Digits & Number Reversal Logic", description="Find the sum of individual digits of a positive integer and find the reverse of the given number.", max_marks=33.0, evaluation_type="code_execution"),
        CriterionModel(id="c2", name="Task B: Fibonacci Sequence Generation", description="Generate the first n terms of Fibonacci sequence.", max_marks=30.0, evaluation_type="code_execution"),
        CriterionModel(id="c3", name="Task C: Prime Numbers Range [1, n]", description="Generate all the prime numbers between 1 and n.", max_marks=33.0, evaluation_type="code_execution"),
        CriterionModel(id="c4", name="Document Headings & Code Readability", description="headings and code readability", max_marks=4.0, evaluation_type="compliance")
    ]
    rubric = RubricResponse(
        id="r_lab3", course_id="c1", assignment_id="a1", version=1, status="APPROVED",
        criteria=criteria, total_max_marks=100.0, late_penalty_percent=0.0, created_at="now"
    )

    # Student submitted Lab 4 (Armstrong numbers, Multiplication table, Decimal to binary)
    unrelated_snippets = [
        {
            "language": "c",
            "code": "#include <stdio.h>\nint main() { int num, temp, digits = 0; double sum = 0.0; printf(\"Armstrong check\"); return 0; }",
            "source": "screenshot_ocr"
        },
        {
            "language": "c",
            "code": "#include <stdio.h>\nint main() { int n, limit; printf(\"Multiplication table\"); return 0; }",
            "source": "screenshot_ocr"
        },
        {
            "language": "c",
            "code": "#include <stdio.h>\nint main() { int decimal, binary[32]; printf(\"Binary equivalent\"); return 0; }",
            "source": "screenshot_ocr"
        }
    ]
    extracted = ExtractedContentModel(
        text_content="C Lab Work 4\nArmstrong Number Verification\nMultiplication Table\nDecimal to binary conversion\nTerminal: 153 is an Armstrong number\nBinary equivalent of 67: 1000011",
        code_snippets=unrelated_snippets,
        diagram_flowchart_descriptions=["Terminal output: 153 is an Armstrong number", "Terminal output: Binary equivalent: 1000011"],
        word_count=45
    )
    att = SubmissionAttachment(filename="Lab4_unrelated.pdf", file_type="PDF", file_path="/tmp/Lab4.pdf", is_readable=True)

    result = EvaluationEngine.evaluate_submission(
        submission_id="sub_wrong", run_id="r1", course_id="c1", assignment_id="a1",
        student_id="st_wrong", student_name="Adityaraj A", state="TURNED_IN",
        is_late=False, attachments=[att], extracted_content=extracted, rubric=rubric,
        assignment_title="Lab 3", assignment_description="C Programming Lab 3"
    )

    assert "WRONG_PDF" in result.flags
    assert result.raw_score == 0.0
    assert result.final_score == 0.0
    assert "Uploaded the wrong PDF" in result.faculty_remarks
    assert all(c.awarded_marks == 0.0 for c in result.criteria_breakdown)
    assert all(c.status == "incorrect" for c in result.criteria_breakdown)


def test_cropped_code_screenshot_verified_via_output():
    from backend.app.services.evaluation_engine import EvaluationEngine
    from backend.app.models.rubric import RubricResponse, CriterionModel
    from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel

    crit = CriterionModel(
        id="c1",
        name="Task B: Fibonacci Sequence Generation",
        description="Generate the first n terms of Fibonacci sequence.",
        max_marks=30.0,
        evaluation_type="code_execution"
    )
    rubric = RubricResponse(
        id="r1", course_id="c1", assignment_id="a1", version=1, status="APPROVED",
        criteria=[crit], total_max_marks=30.0, late_penalty_percent=0.0, created_at="now"
    )

    # Student screenshot only has 3 visible lines (cropped in IDE), but terminal output proves full completion
    cropped_code = [
        {
            "language": "c",
            "code": "int main() {\n  int n = 5;\n  // rest of code scrolled off screen in screenshot\n",
            "source": "screenshot_ocr",
            "has_terminal_output": True
        }
    ]
    extracted = ExtractedContentModel(
        text_content="Fibonacci series calculation\nTerminal: gcc fib.c -o fib\nFibonacci Sequence (first 5 terms): 0, 1, 1, 2, 3",
        code_snippets=cropped_code,
        diagram_flowchart_descriptions=["Terminal output: 0, 1, 1, 2, 3"],
        word_count=15
    )
    att = SubmissionAttachment(filename="fib_cropped.pdf", file_type="PDF", file_path="/tmp/fib.pdf", is_readable=True)

    res = EvaluationEngine.evaluate_submission(
        submission_id="s1", run_id="r1", course_id="c1", assignment_id="a1",
        student_id="st1", student_name="Cropped Student", state="TURNED_IN", is_late=False,
        attachments=[att], extracted_content=extracted, rubric=rubric,
        assignment_title="Lab 3", assignment_description="C Lab"
    )

    assert res.raw_score == 30.0
    assert res.criteria_breakdown[0].status == "completed"
    assert "Verified fibonacci implementation" in res.criteria_breakdown[0].explanation
    assert "Visual execution and terminal output confirmed" in res.criteria_breakdown[0].explanation



