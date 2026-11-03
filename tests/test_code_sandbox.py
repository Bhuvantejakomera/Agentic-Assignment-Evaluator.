from backend.app.services.code_sandbox import CodeSandbox

def test_c_code_compilation_and_execution_success():
    c_code = """
    #include <stdio.h>
    int main() {
        int a, b;
        if (scanf("%d %d", &a, &b) == 2) {
            printf("%d\\n", a + b);
        }
        return 0;
    }
    """
    test_cases = [
        {"input": "10 25", "expected_output": "35"},
        {"input": "7 8", "expected_output": "15"}
    ]
    result = CodeSandbox.evaluate_c_or_cpp(c_code, language="c", test_cases=test_cases)
    assert result.compilation_success is True
    assert result.tests_passed == 2
    assert result.tests_total == 2

def test_c_code_compilation_failure():
    broken_code = """
    #include <stdio.h>
    int main() {
        syntax error line here
        return 0;
    }
    """
    result = CodeSandbox.evaluate_c_or_cpp(broken_code, language="c")
    assert result.compilation_success is False
    assert result.compilation_error is not None
    assert result.tests_passed == 0

def test_c_code_timeout_protection():
    infinite_loop = """
    #include <stdio.h>
    int main() {
        while(1) { }
        return 0;
    }
    """
    result = CodeSandbox.evaluate_c_or_cpp(infinite_loop, language="c", test_cases=[{"input": "", "expected_output": "done"}])
    assert result.compilation_success is True
    assert result.tests_passed == 0
    assert "timed out" in result.test_details[0]["stderr"].lower()

def test_python_code_execution():
    py_code = """
import sys
data = sys.stdin.read().split()
if data:
    nums = [int(x) for x in data]
    print(sum(nums))
"""
    test_cases = [{"input": "4 5 6", "expected_output": "15"}]
    result = CodeSandbox.evaluate_python(py_code, test_cases=test_cases)
    assert result.compilation_success is True
    assert result.tests_passed == 1
