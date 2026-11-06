import json
import re
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from backend.app.models.rubric import RubricResponse, CriterionModel
from backend.app.models.submission import SubmissionAttachment, ExtractedContentModel
from backend.app.models.evaluation import (
    CriterionEvaluationResult,
    CodeTestExecutionResult,
    EvaluationResultResponse
)
from backend.app.services.code_sandbox import CodeSandbox
from backend.app.services.llm_engine import LocalLLMEngine

class EvaluationEngine:
    """Core evaluation orchestrator performing rubric-based partial marking,
    code testing, late penalty calculation, and submission irregularity detection."""

    WRONG_SUBMISSION_KEYWORDS = [
        "physics", "chemistry", "photoelectric", "planck", "history essay", "macroeconomics",
        "literature review", "electrical engineering circuits", "sample text placeholder",
        "lorem ipsum", "wrong file", "test upload please ignore"
    ]

    @classmethod
    def detect_wrong_submission(
        cls,
        extracted_text: str,
        assignment_title: str,
        assignment_description: str,
        code_snippets: Optional[List[Dict[str, str]]] = None,
        custom_guidance: Optional[str] = None,
        criteria: Optional[List[CriterionModel]] = None,
        diagram_flowcharts: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """Detects whether student uploaded an unrelated document (e.g. wrong PDF or different lab)."""
        import re
        text_lower = (extracted_text or "").lower()
        if len(text_lower.strip()) == 0 and not code_snippets:
            return False, ""

        # Check explicit unrelated subject triggers
        for kw in cls.WRONG_SUBMISSION_KEYWORDS:
            if kw in text_lower:
                return True, f"Uploaded document appears unrelated: contains '{kw}'"

        # Combine text, code snippets, and diagram/terminal descriptions
        combined_content = text_lower
        if code_snippets:
            for s in code_snippets:
                combined_content += " " + s.get("code", "").lower()
        if diagram_flowcharts:
            for df in diagram_flowcharts:
                combined_content += " " + df.lower()

        # Check against technical criteria if provided
        if criteria:
            from backend.app.services.llm_engine import LocalLLMEngine
            tech_criteria = [
                c for c in criteria
                if c.evaluation_type in ("code_execution", "algorithm", "diagram_flowchart")
                and not any(k in c.name.lower() for k in ("quality", "compliance", "readability", "penalty", "heading"))
                and c.max_marks > 0
            ]
            if len(tech_criteria) >= 2:
                matched_tech_count = 0
                for tc in tech_criteria:
                    task_sigs = LocalLLMEngine.extract_task_signature_keywords(f"{tc.name} {tc.description}")
                    if not task_sigs:
                        task_sigs = LocalLLMEngine.extract_domain_keywords(f"{tc.name} {tc.description}")
                    if not task_sigs:
                        continue
                    if any(r in task_sigs for r in ("reverse", "reversal")):
                        if any(r in combined_content for r in ("reverse", "reversal", "rev")):
                            matched_tech_count += 1
                    elif any(sig in combined_content for sig in task_sigs):
                        matched_tech_count += 1

                content_words = len(combined_content.split())
                if matched_tech_count == 0 and (content_words >= 25 or len(code_snippets or []) >= 1):
                    return True, "Submitted deliverable contains unrelated tasks/problems (found 0 matches for assigned lab criteria)."

        # Check domain relevance against assignment context + faculty expectations
        combined_prompt = f"{assignment_title} {assignment_description} {custom_guidance or ''}".lower()
        context_words = set(re_words for re_words in re.findall(r'[a-zA-Z]{4,}', combined_prompt))
        if len(context_words) > 3:
            overlap = [w for w in context_words if w in combined_content]
            
            # Programming & domain indicators confirming this is a valid computing submission
            programming_indicators = [
                "stdio.h", "main()", "printf", "scanf", "while", "for", "include",
                "return 0", "int ", "void ", "palindrome", "gcd", "lcm", "digit",
                "reverse", "result", "c programming", "arithmetic", "binary", "decimal",
                "operator", "terminal", "screenshot", "output", "calculator", "bits"
            ]
            has_prog = any(pi in combined_content for pi in programming_indicators)

            # If student submitted over 60 words but has zero overlap AND no programming indicators
            if len(combined_content.split()) > 60 and len(overlap) == 0 and not has_prog:
                return True, "Content has no semantic overlap with assignment topic."

        return False, ""

    @staticmethod
    def _extract_missing_output_penalty(guidance: Optional[str]) -> Optional[float]:
        """Infer a numeric per-task penalty for missing output from faculty guidance.

        Faculty may phrase it many ways:
          - "no output do a minus of 5 per task"
          - "if there is no output subtract 5 points"
          - "missing output penalty 5"
          - "output not present – deduct 5"
          - "minus 5 if output is missing"
        Returns a negative float (e.g. -5.0) if detected, otherwise None.
        """
        if not guidance:
            return None
        text = guidance.lower()

        # Quick gate: must mention "output" somewhere
        if "output" not in text:
            return None

        penalty_verbs = r"(?:minus|deduct|subtract|lose|penalty|reduce|take\s+away|cut)"

        # Pattern A: "output" … penalty-verb … number
        pat_a = r"output.*?" + penalty_verbs + r".*?(\d+(?:\.\d+)?)"
        m = re.search(pat_a, text, re.DOTALL)
        if m:
            return -float(m.group(1))

        # Pattern B: penalty-verb … number … "output"
        pat_b = penalty_verbs + r".*?(\d+(?:\.\d+)?).*?output"
        m = re.search(pat_b, text, re.DOTALL)
        if m:
            return -float(m.group(1))

        return None

    @classmethod
    def evaluate_submission(
        cls,
        run_id: str,
        course_id: str,
        assignment_id: str,
        student_id: str,
        student_name: str,
        submission_id: str,
        state: str,
        is_late: bool,
        attachments: List[SubmissionAttachment],
        extracted_content: ExtractedContentModel,
        rubric: RubricResponse,
        assignment_title: str = "",
        assignment_description: str = "",
        test_cases: Optional[List[Dict[str, str]]] = None,
        existing_flags: Optional[List[str]] = None
    ) -> EvaluationResultResponse:
        now_str = datetime.now().isoformat()
        flags = list(existing_flags) if existing_flags else []
        criteria_results: List[CriterionEvaluationResult] = []
        code_exec_result: Optional[CodeTestExecutionResult] = None
        remarks = None

        # 1. Check Missing Submission
        is_missing = (
            state in ("MISSING", "NEW", "CREATED", "RECLAIMED_BY_STUDENT")
            or "MISSING" in flags
            or (not attachments and not extracted_content.text_content.strip())
        )
        if is_missing:
            for crit in rubric.criteria:
                criteria_results.append(CriterionEvaluationResult(
                    criterion_id=crit.id,
                    criterion_name=crit.name,
                    max_marks=crit.max_marks,
                    awarded_marks=0.0,
                    status="missing",
                    explanation="No submission was turned in.",
                    evidence=None,
                    flags=["MISSING"]
                ))
            return EvaluationResultResponse(
                id=str(uuid.uuid4()),
                run_id=run_id,
                course_id=course_id,
                assignment_id=assignment_id,
                student_id=student_id,
                student_name=student_name,
                raw_score=0.0,
                late_penalty=0.0,
                final_score=0.0,
                faculty_approved=False,
                faculty_remarks="Missing",
                criteria_breakdown=criteria_results,
                code_execution_results=None,
                flags=["MISSING"],
                overall_feedback="Submission was not turned in by the student.",
                evaluated_at=now_str
            )

        # 2. Check Unreadable Attachments
        has_readable = any(att.is_readable for att in attachments)
        if not has_readable and attachments:
            for crit in rubric.criteria:
                criteria_results.append(CriterionEvaluationResult(
                    criterion_id=crit.id,
                    criterion_name=crit.name,
                    max_marks=crit.max_marks,
                    awarded_marks=0.0,
                    status="incorrect",
                    explanation="Attached file could not be read or extracted.",
                    evidence=None,
                    flags=["UNREADABLE"]
                ))
            return EvaluationResultResponse(
                id=str(uuid.uuid4()),
                run_id=run_id,
                course_id=course_id,
                assignment_id=assignment_id,
                student_id=student_id,
                student_name=student_name,
                raw_score=0.0,
                late_penalty=0.0,
                final_score=0.0,
                faculty_approved=False,
                faculty_remarks="Unreadable or corrupt file",
                criteria_breakdown=criteria_results,
                code_execution_results=None,
                flags=["UNREADABLE"],
                overall_feedback="Student attached unreadable or corrupt file.",
                evaluated_at=now_str
            )

        # 3. Check Wrong Submission (e.g. Uploaded Wrong PDF or Unrelated Lab)
        is_wrong, wrong_reason = cls.detect_wrong_submission(
            extracted_content.text_content,
            assignment_title,
            assignment_description,
            extracted_content.code_snippets,
            custom_guidance=rubric.custom_guidance,
            criteria=rubric.criteria,
            diagram_flowcharts=extracted_content.diagram_flowchart_descriptions
        )
        if is_wrong:
            flags.append("WRONG_PDF")
            remarks = "Uploaded the wrong PDF"
            for crit in rubric.criteria:
                criteria_results.append(CriterionEvaluationResult(
                    criterion_id=crit.id,
                    criterion_name=crit.name,
                    max_marks=crit.max_marks,
                    awarded_marks=0.0,
                    status="incorrect",
                    explanation=f"Submission rejected: {wrong_reason}",
                    evidence=extracted_content.text_content[:150] if extracted_content.text_content else None,
                    flags=["WRONG_PDF"]
                ))
            return EvaluationResultResponse(
                id=str(uuid.uuid4()),
                run_id=run_id,
                course_id=course_id,
                assignment_id=assignment_id,
                student_id=student_id,
                student_name=student_name,
                raw_score=0.0,
                late_penalty=0.0,
                final_score=0.0,
                faculty_approved=False,
                faculty_remarks=remarks,
                criteria_breakdown=criteria_results,
                code_execution_results=None,
                flags=flags,
                overall_feedback=f"Irregular submission detected: {wrong_reason}. Requires faculty verification.",
                evaluated_at=now_str
            )

        # 4. Detect optional missing-output penalty from faculty guidance
        text_lower = (extracted_content.text_content or "").lower()
        output_txt_indicators = [
            "output:", "output :-", "terminal", "debug console", "problems output",
            "gcc ", "./a.exe", "./a.out", ".exe", "--- results", "ps c:\\", "ps d:\\"
        ]
        has_output_screenshots = (
            bool(extracted_content.diagram_flowchart_descriptions) or
            any(s.get("has_terminal_output") for s in extracted_content.code_snippets if isinstance(s, dict)) or
            any(ind in text_lower for ind in output_txt_indicators)
        )
        missing_output_penalty = cls._extract_missing_output_penalty(rubric.custom_guidance)

        has_direct_code_file = any(att.file_type in ("C", "CPP", "PY") for att in attachments)
        has_screenshot_deliverable = any(att.file_type in ("PDF", "DOCX", "IMAGE") for att in attachments) or \
                                     any(s.get("source") in ("screenshot", "screenshot_ocr") for s in extracted_content.code_snippets)

        if extracted_content.code_snippets:
            primary_snippet = extracted_content.code_snippets[0]
            lang = primary_snippet.get("language", "c")
            code_str = primary_snippet.get("code", "")
            # Only execute in sandbox if student uploaded a direct code file and not a screenshot deliverable
            is_screenshot = primary_snippet.get("source") in ("screenshot", "screenshot_ocr") or has_screenshot_deliverable
            if lang in ("c", "cpp") and has_direct_code_file and not is_screenshot:
                code_exec_result = CodeSandbox.evaluate_c_or_cpp(code_str, lang, test_cases)
            elif lang in ("py", "python") and has_direct_code_file and not is_screenshot:
                code_exec_result = CodeSandbox.evaluate_python(code_str, test_cases)

        # 5. Evaluate Criterion by Criterion
        for crit in rubric.criteria:
            crit_eval = LocalLLMEngine.evaluate_criterion_semantic(
                criterion=crit,
                extracted_text=extracted_content.text_content,
                code_snippets=extracted_content.code_snippets,
                assignment_context=f"{assignment_title}\n{assignment_description}",
                custom_guidance=rubric.custom_guidance,
                diagram_flowcharts=extracted_content.diagram_flowchart_descriptions
            )

            # If this is code execution or technical algorithmic criterion:
            if crit.evaluation_type in ("code_execution", "algorithm"):
                is_screenshot_code = any(s.get("source") in ("screenshot", "screenshot_ocr") for s in extracted_content.code_snippets) or has_screenshot_deliverable
                if code_exec_result and code_exec_result.compilation_success and code_exec_result.tests_total > 0 and crit.evaluation_type == "code_execution":
                    pass_ratio = code_exec_result.tests_passed / code_exec_result.tests_total
                    crit_eval["awarded_marks"] = round(crit.max_marks * pass_ratio, 1)
                    crit_eval["status"] = "completed" if pass_ratio == 1.0 else ("partial" if pass_ratio > 0 else "incorrect")
                    crit_eval["explanation"] = f"Passed {code_exec_result.tests_passed}/{code_exec_result.tests_total} automated test cases."
                elif is_screenshot_code:
                    crit_eval = LocalLLMEngine.evaluate_screenshot_implementation(
                        criterion=crit,
                        code_snippets=extracted_content.code_snippets,
                        diagram_flowcharts=extracted_content.diagram_flowchart_descriptions,
                        assignment_context=f"{assignment_title}\n{assignment_description}",
                        custom_guidance=rubric.custom_guidance,
                        extracted_text=extracted_content.text_content
                    )
                    # Apply missing output penalty if faculty specified it and no output was found
                    task_has_output = crit_eval.get("has_output", False) or has_output_screenshots
                    if missing_output_penalty is not None and not task_has_output:
                        new_score = max(0.0, crit_eval["awarded_marks"] + missing_output_penalty)
                        crit_eval["awarded_marks"] = round(new_score, 1)
                        if crit_eval["awarded_marks"] == crit.max_marks:
                            crit_eval["status"] = "completed"
                        elif crit_eval["awarded_marks"] > 0:
                            crit_eval["status"] = "partial"
                        else:
                            crit_eval["status"] = "incorrect"
                        crit_eval["explanation"] += f" Penalty applied: missing output screenshot ({missing_output_penalty} pts)."
                elif code_exec_result and not code_exec_result.compilation_success and crit.evaluation_type == "code_execution":
                    crit_eval["awarded_marks"] = round(crit.max_marks * 0.2, 1)  # Partial marks for code attempt
                    crit_eval["status"] = "partial"
                    crit_eval["explanation"] = f"Compilation failed: {code_exec_result.compilation_error[:120]}"

            criteria_results.append(CriterionEvaluationResult(
                criterion_id=crit.id,
                criterion_name=crit.name,
                max_marks=crit.max_marks,
                awarded_marks=crit_eval["awarded_marks"],
                status=crit_eval["status"],
                explanation=crit_eval["explanation"],
                evidence=crit_eval.get("evidence"),
                flags=[]
            ))

        # 6. Sum raw score
        raw_score = sum(c.awarded_marks for c in criteria_results)
        raw_score = round(raw_score, 1)

        # 7. Late Penalty
        late_penalty = 0.0
        if is_late:
            flags.append("LATE")
            penalty_pct = rubric.late_penalty_percent / 100.0
            late_penalty = round(raw_score * penalty_pct, 1)
            remarks = "Late" if not remarks else f"{remarks}; Late"

        final_score = max(0.0, round(raw_score - late_penalty, 1))

        # 8. Check Incomplete
        has_missing_crit = any(c.status in ("missing", "partial") for c in criteria_results)
        if has_missing_crit and raw_score < rubric.total_max_marks:
            flags.append("INCOMPLETE")
            if not remarks:
                remarks = "Incomplete"

        # 9. Uncertainty flag for borderline cases
        if 0 < raw_score < (rubric.total_max_marks * 0.5):
            flags.append("UNCERTAIN")

        feedback_summary = (
            f"Evaluated across {len(criteria_results)} criteria. "
            f"Raw Score: {raw_score}/{rubric.total_max_marks}. "
            f"{'Late penalty applied (-' + str(late_penalty) + '). ' if is_late else ''}"
            f"Final Recommended Score: {final_score}."
        )

        return EvaluationResultResponse(
            id=str(uuid.uuid4()),
            run_id=run_id,
            course_id=course_id,
            assignment_id=assignment_id,
            student_id=student_id,
            student_name=student_name,
            raw_score=raw_score,
            late_penalty=late_penalty,
            final_score=final_score,
            faculty_adjusted_score=None,
            faculty_approved=False,
            faculty_remarks=remarks,
            criteria_breakdown=criteria_results,
            code_execution_results=code_exec_result,
            flags=flags,
            overall_feedback=feedback_summary,
            evaluated_at=now_str
        )
