# Faculty-Controlled Intelligent Assignment Evaluation and Grade Management System Using Local Large Language Models

A local-first, AI-assisted assignment evaluation and grade management platform optimized for Apple Silicon (MacBook Air M5 with 24 GB unified memory). The system provides multi-classroom course discovery, automated document extraction, isolated code compilation and testing, hybrid rubric preparation, criterion-level partial marking, versioned Excel report consolidation, and human-in-the-loop faculty grade approval and Google Classroom publishing.

---

## 1. System Architecture

```
                                  [ Authenticated Faculty ]
                                             |
                   +-------------------------+-------------------------+
                   |                                                   |
       [ Web Frontend Dashboard ]                                 [ REST APIs ]
   - My Classrooms Selection                               - Scoped Course Routes
   - Assignment Workspace                                  - Rubric Configuration
   - Rubric Builder & Approval                             - Batch Evaluation Engine
   - Student Review & Adjust Drawer                        - Excel Exporter
   - Google Publishing Lock                                - Audit & Publishing Logs
                   |                                                   |
                   +-------------------------+-------------------------+
                                             |
                  +--------------------------+--------------------------+
                  |                          |                          |
       [ Document Processing ]     [ Code Sandbox ]           [ Local LLM Engine ]
    - PDF Extraction (pypdf)    - Apple Clang (C/C++)      - Ollama (llama3.2 / qwen)
    - DOCX (python-docx)        - Python 3 Subprocess      - Local OpenAI Endpoint
    - HTML (BeautifulSoup4)     - Isolated Temp Dir        - Deterministic NLP Heuristic
    - C, CPP, Python Sources    - Timeout (3.0s Limit)       Analyzer Fallback
                  |                          |                          |
                  +--------------------------+--------------------------+
                                             |
                              +--------------+--------------+
                              |                             |
                 [ Relational Database (SQLite) ]    [ Excel Consolidation ]
                - Faculty, Courses, Enrollments     - Master: Lab_Marks_Record.xlsx
                - Scoped Assignments & Submissions  - Auto Column Mapping (Lab-1, Lab-2..)
                - Rubrics (DRAFT -> APPROVED)       - Preserves Existing Marks
                - Evaluation Runs & Breakdowns      - Remarks: "Late", "Wrong PDF"
                - Audit Trail & Publish Logs        - Versioned Reports in reports/
```

---

## 2. Core Functional Workflow

1. **Faculty Authentication**:
   - Authenticate faculty context (`Prof. Bhuvan Teja`, `chandragajjela2003@gmail.com`).
   - Integrates with Google Classroom OAuth 2.0 and local simulation mode.

## 2. Dedicated Consolidated Marks Workbook Per Classroom & Shared Faculty Dashboard

To ensure institutional scalability without mixing students, assignments, or marks between courses:
1. **Isolated Classroom Workbooks (`workbooks/`)**:
   - Each classroom is allocated its own distinct consolidated marks workbook:
     - `workbooks/programming_in_c_cse_a_marks_record.xlsx` (66 students)
     - `workbooks/data_structures_cse_b_marks_record.xlsx` (60 students)
     - `workbooks/python_programming_aiml_a_marks_record.xlsx` (55 students)
     - `workbooks/artificial_intelligence_aiml_b_marks_record.xlsx` (50 students)
   - **Sheet 1 ("Consolidated Marks")**: Contains student roster strictly enrolled in that course, with dynamic assignment columns (`Lab-1`, `Lab-2`, `Assignment-1`...) and cumulative Remarks (`Late`, `Uploaded the wrong PDF`, `Incomplete`).
   - **Assignment-Wise Detailed Sheets**: Whenever an assignment is evaluated, a dedicated tab (e.g. `Lab-1 Details`, `Assignment-2 Details`) is automatically created/updated inside that classroom's workbook with complete criterion-level breakdowns, raw marks, penalties, final scores, and evidence quotes.
   - **Zero Cross-Course Contamination**: No student from Course A ever enters Course B's workbook, eliminating accidental data mixing.

2. **Shared Faculty Dashboard**:
   - Central control hub for faculty managing multiple courses.
   - Global institutional counters: *Total Active Classrooms*, *Total Enrolled Students*, *Total Coursework Tasks*, *Total Evaluated*, *Faculty Approved*.
   - Direct download links for each classroom's consolidated workbook directly from the dashboard card.
   - Fast one-click classroom workspace switching via header navigation.

3. **Rubric Preparation (Hybrid AI + Faculty Control)**:
   - AI reads assignment instructions and breaks them into explicit measurable criteria:
     - Theoretical Concepts & Descriptive Explanations
     - Step-by-Step Algorithm
     - Flowchart & Visual Logic
     - Program Implementation & Execution Correctness
   - Faculty modifies weights and marks, and explicitly approves the rubric before evaluation starts.

4. **Heterogeneous Document Extraction & Submission Classification**:
   - Supports PDF documents, Word documents (`.docx`), HTML files, and source code files (`.c`, `.cpp`, `.py`).
   - Detects submission irregularities:
     - **Late submissions**: automatically flags and applies approved late penalty percentage.
     - **Wrong submissions / Unrelated documents**: detects off-topic PDFs (e.g. uploaded physics homework for C programming lab) and flags `WRONG_PDF` with 0 marks.
     - **Incomplete submissions**: awards accurate partial marks for completed criteria while zeroing missing criteria.
     - **Unreadable / Missing files**: flags unreadable or empty files.

5. **Isolated Code Compilation & Sandbox Execution**:
   - Uses Apple Clang (`clang -O2 -Wall`) for C and C++ programs.
   - Executes code in isolated temporary directories with 3.0-second timeout enforcement to prevent infinite loops.
   - Evaluates test cases against expected outputs.

6. **Excel Consolidation (Compatible with `Lab_Marks_Record.xlsx`)**:
   - Maps evaluated assignments to target columns (e.g. `Lab-1`, `Lab-2`, `Lab-3` or new columns).
   - Preserves all other student marks and un-evaluated columns without silent overwrites.
   - Records student remarks (`Late`, `Uploaded the wrong PDF`, `Incomplete`).
   - Automatically stores timestamped versioned workbooks in `reports/{course_slug}/{assignment_slug}/`.

7. **Human-in-the-Loop Faculty Dashboard**:
   - Interactive review drawer: inspect criterion breakdowns, evidence citations, and code outputs.
   - Live mark adjustment and override.
   - One-click "Approve All Evaluated" or individual grade approval.

8. **Google Classroom Grade Publishing**:
   - Grade publishing lock: requires explicit faculty confirmation before pushing grades.
   - Option to publish as draft grades or return submissions directly to students.
   - Immutable audit logging of all grading and publishing events.

---

## 3. Directory Structure

```
Automate/
├── backend/
│   └── app/
│       ├── __init__.py
│       ├── config.py                 # Paths, LLM base URL, OAuth settings
│       ├── database.py               # SQLite schema with course isolation constraints
│       ├── models/                   # Pydantic data schemas
│       │   ├── course.py
│       │   ├── assignment.py
│       │   ├── rubric.py
│       │   ├── submission.py
│       │   └── evaluation.py
│       ├── services/
│       │   ├── classroom_service.py  # Multi-classroom discovery & submission ingestion
│       │   ├── document_extractor.py # PDF, DOCX, HTML, C, CPP, Python file extraction
│       │   ├── code_sandbox.py       # Isolated Clang compilation & test runner
│       │   ├── llm_engine.py         # Local LLM client & semantic heuristic fallback
│       │   ├── evaluation_engine.py  # Rubric-based partial marks & irregularity detection
│       │   ├── excel_service.py      # openpyxl workbook mapping matching Lab_Marks_Record.xlsx
│       │   └── audit_service.py      # Immutable audit trail
│       └── api/                      # REST API endpoints
│           ├── auth_routes.py
│           ├── classroom_routes.py
│           ├── assignment_routes.py
│           ├── rubric_routes.py
│           ├── evaluation_routes.py
│           ├── excel_routes.py
│           └── publish_routes.py
├── frontend/                         # Modern Single-Page Desktop Application
│   ├── index.html                    # Responsive desktop UI with Tailwind CSS
│   ├── css/style.css                 # Custom badges, animations, layout
│   └── js/
│       ├── api.js                    # Fetch client for all backend endpoints
│       └── app.js                    # State management, classroom switcher, modals
├── tests/                            # Automated test suite (18 unit and integration tests)
│   ├── test_multi_classroom.py       # Course discovery, isolation, switching
│   ├── test_document_extractor.py    # Multi-format document parsing
│   ├── test_code_sandbox.py          # Clang compilation & execution sandbox
│   ├── test_evaluation_engine.py     # Rubric criteria, partial marking, wrong PDF detection
│   ├── test_excel_service.py         # Lab_Marks_Record.xlsx mapping and remarks
│   └── test_end_to_end_flow.py       # Full Classroom A -> Classroom B -> Return to A -> Publish flow
├── reports/                          # Versioned Excel exports by course and assignment
├── Lab_Marks_Record.xlsx             # Faculty master marks workbook
├── run.py                            # Application launcher script
└── requirements.txt
```

---

## 4. Setup and Installation

### Prerequisites
- macOS on Apple Silicon (M1/M2/M3/M4/M5)
- Python 3.9+ with `venv`
- Apple Command Line Tools (`clang`) for C/C++ compilation

### 1. Activate Environment and Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Automated Verification Tests
Run the comprehensive test suite to verify multi-classroom isolation, document extraction, code sandboxing, Excel consolidation, and end-to-end evaluation:
```bash
source .venv/bin/activate
PYTHONPATH=. pytest -v tests/
```

### 3. Launch the Application Server
```bash
source .venv/bin/activate
python run.py
```
Open your browser and navigate to:
**`http://localhost:8000`**

---

## 5. End-to-End Multi-Classroom Scenario Walkthrough

1. **Access My Classrooms**:
   - The faculty dashboard opens showing four active courses: *Programming in C (CSE-A)*, *Data Structures (CSE-B)*, *Python Programming (AIML-A)*, and *Artificial Intelligence (AIML-B)*.
2. **Open Classroom A & Lab 1**:
   - Click **Open Classroom** on *Programming in C*.
   - Click **Configure & Evaluate** on *Lab 1 – Algorithms & Flowcharts*.
3. **Approve Rubric**:
   - Click **Generate Hybrid Rubric with Local LLM**.
   - Review the 4 proposed criteria (*Theoretical Concepts*, *Algorithm Specification*, *Flowchart Logic*, *Program Implementation*).
   - Click **Approve Rubric**.
4. **Evaluate Submissions**:
   - Click **Start Automated Evaluation**.
   - The system extracts documents, executes C code in the Clang sandbox, checks test cases, identifies wrong PDFs (e.g. student Adityaraj A who uploaded a physics paper), applies late penalties (e.g. Advit Singh), and calculates partial marks.
5. **Review & Batch Approve**:
   - Filter by *Wrong PDF*, *Late*, or *Review / Uncertain*.
   - Click **Inspect & Adjust** on any student to override scores or add custom remarks.
   - Click **Approve All Evaluated**.
6. **Export to Consolidated Excel**:
   - Click **Export Excel Report**.
   - Target column `Lab-1` is auto-selected from `Lab_Marks_Record.xlsx`.
   - Click **Export & Consolidate Excel Workbook**.
   - The master workbook is updated with scores and remarks, and a versioned report is saved to `reports/programming_in_c/lab_1/`.
7. **Switch to Classroom B**:
   - Use the header classroom dropdown to switch to *Data Structures (CSE-B)*.
   - Open *Assignment 2 – Stack & Queue Implementations*, approve its rubric, evaluate its 60 students, and export its separate Excel report.
8. **Switch Back to Classroom A**:
   - Switch back to *Programming in C*.
   - Open *Lab 1*: all 66 student evaluations, approval statuses, and Excel exports remain completely intact without reprocessing!
9. **Publish to Google Classroom**:
   - Click **Publish to Classroom**.
   - Review the summary of approved grades.
   - Check **Return submissions to students** and click **Authorize & Publish Marks to Google Classroom**.

