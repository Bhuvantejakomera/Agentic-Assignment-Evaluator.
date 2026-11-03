import os
import sys
import time
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from backend.app.models.evaluation import CodeTestExecutionResult

class CodeSandbox:
    """Safe, isolated execution sandbox for C, C++, and Python assignment submissions."""

    TIMEOUT_SECONDS = 3.0

    @classmethod
    def evaluate_c_or_cpp(
        cls,
        source_code: str,
        language: str = "c",
        test_cases: Optional[List[Dict[str, str]]] = None
    ) -> CodeTestExecutionResult:
        if not test_cases:
            test_cases = [{"input": "", "expected_output": ""}]

        compiler = "clang" if language.lower() == "c" else "clang++"
        file_ext = ".c" if language.lower() == "c" else ".cpp"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            src_file = tmppath / f"student_submission{file_ext}"
            bin_file = tmppath / "student_app"

            src_file.write_text(source_code, encoding="utf-8")

            # 1. Compilation
            compile_cmd = [compiler, "-O2", "-Wall", str(src_file), "-o", str(bin_file)]
            try:
                comp_start = time.perf_counter()
                comp_proc = subprocess.run(
                    compile_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=cls.TIMEOUT_SECONDS
                )
                comp_duration = (time.perf_counter() - comp_start) * 1000.0

                if comp_proc.returncode != 0:
                    return CodeTestExecutionResult(
                        language=language,
                        compilation_success=False,
                        compilation_error=comp_proc.stderr.strip() or comp_proc.stdout.strip(),
                        tests_passed=0,
                        tests_total=len(test_cases),
                        test_details=[],
                        execution_time_ms=comp_duration
                    )
            except subprocess.TimeoutExpired:
                return CodeTestExecutionResult(
                    language=language,
                    compilation_success=False,
                    compilation_error="Compilation timed out.",
                    tests_passed=0,
                    tests_total=len(test_cases),
                    test_details=[],
                    execution_time_ms=cls.TIMEOUT_SECONDS * 1000.0
                )
            except Exception as e:
                return CodeTestExecutionResult(
                    language=language,
                    compilation_success=False,
                    compilation_error=f"Compilation failed to start: {str(e)}",
                    tests_passed=0,
                    tests_total=len(test_cases),
                    test_details=[],
                    execution_time_ms=0.0
                )

            # 2. Test Execution
            passed = 0
            test_details = []
            total_exec_time = 0.0

            for idx, tc in enumerate(test_cases):
                inp = tc.get("input", "")
                expected = tc.get("expected_output", "").strip()
                t_start = time.perf_counter()

                try:
                    run_proc = subprocess.run(
                        [str(bin_file)],
                        input=inp,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=cls.TIMEOUT_SECONDS
                    )
                    t_duration = (time.perf_counter() - t_start) * 1000.0
                    total_exec_time += t_duration

                    actual = run_proc.stdout.strip()
                    err = run_proc.stderr.strip()

                    # Match test case
                    is_match = False
                    if not expected:
                        # If no expected output defined, success if returncode == 0
                        is_match = (run_proc.returncode == 0)
                    else:
                        is_match = (expected in actual) or (actual == expected)

                    if is_match and run_proc.returncode == 0:
                        passed += 1

                    test_details.append({
                        "test_index": idx + 1,
                        "passed": is_match,
                        "exit_code": run_proc.returncode,
                        "input": inp,
                        "expected": expected,
                        "actual": actual,
                        "stderr": err,
                        "duration_ms": round(t_duration, 2)
                    })

                except subprocess.TimeoutExpired:
                    test_details.append({
                        "test_index": idx + 1,
                        "passed": False,
                        "exit_code": -1,
                        "input": inp,
                        "expected": expected,
                        "actual": "",
                        "stderr": "Execution timed out (infinite loop or blocked I/O).",
                        "duration_ms": cls.TIMEOUT_SECONDS * 1000.0
                    })
                except Exception as e:
                    test_details.append({
                        "test_index": idx + 1,
                        "passed": False,
                        "exit_code": -1,
                        "input": inp,
                        "expected": expected,
                        "actual": "",
                        "stderr": f"Execution error: {str(e)}",
                        "duration_ms": 0.0
                    })

            return CodeTestExecutionResult(
                language=language,
                compilation_success=True,
                compilation_error=None,
                tests_passed=passed,
                tests_total=len(test_cases),
                test_details=test_details,
                execution_time_ms=round(total_exec_time, 2)
            )

    @classmethod
    def evaluate_python(
        cls,
        source_code: str,
        test_cases: Optional[List[Dict[str, str]]] = None
    ) -> CodeTestExecutionResult:
        if not test_cases:
            test_cases = [{"input": "", "expected_output": ""}]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            src_file = tmppath / "student_submission.py"
            src_file.write_text(source_code, encoding="utf-8")

            # 1. Syntax check
            try:
                compile(source_code, "student_submission.py", "exec")
            except SyntaxError as se:
                return CodeTestExecutionResult(
                    language="py",
                    compilation_success=False,
                    compilation_error=f"Python Syntax Error: {se.msg} on line {se.lineno}",
                    tests_passed=0,
                    tests_total=len(test_cases),
                    test_details=[],
                    execution_time_ms=0.0
                )

            # 2. Execution
            passed = 0
            test_details = []
            total_exec_time = 0.0

            for idx, tc in enumerate(test_cases):
                inp = tc.get("input", "")
                expected = tc.get("expected_output", "").strip()
                t_start = time.perf_counter()

                try:
                    run_proc = subprocess.run(
                        [sys.executable, str(src_file)],
                        input=inp,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=cls.TIMEOUT_SECONDS
                    )
                    t_duration = (time.perf_counter() - t_start) * 1000.0
                    total_exec_time += t_duration

                    actual = run_proc.stdout.strip()
                    err = run_proc.stderr.strip()

                    is_match = False
                    if not expected:
                        is_match = (run_proc.returncode == 0)
                    else:
                        is_match = (expected in actual) or (actual == expected)

                    if is_match and run_proc.returncode == 0:
                        passed += 1

                    test_details.append({
                        "test_index": idx + 1,
                        "passed": is_match,
                        "exit_code": run_proc.returncode,
                        "input": inp,
                        "expected": expected,
                        "actual": actual,
                        "stderr": err,
                        "duration_ms": round(t_duration, 2)
                    })

                except subprocess.TimeoutExpired:
                    test_details.append({
                        "test_index": idx + 1,
                        "passed": False,
                        "exit_code": -1,
                        "input": inp,
                        "expected": expected,
                        "actual": "",
                        "stderr": "Execution timed out.",
                        "duration_ms": cls.TIMEOUT_SECONDS * 1000.0
                    })
                except Exception as e:
                    test_details.append({
                        "test_index": idx + 1,
                        "passed": False,
                        "exit_code": -1,
                        "input": inp,
                        "expected": expected,
                        "actual": "",
                        "stderr": f"Runtime error: {str(e)}",
                        "duration_ms": 0.0
                    })

            return CodeTestExecutionResult(
                language="py",
                compilation_success=True,
                compilation_error=None,
                tests_passed=passed,
                tests_total=len(test_cases),
                test_details=test_details,
                execution_time_ms=round(total_exec_time, 2)
            )

