import json
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
        assignment_description: str
    ) -> Tuple[bool, str]:
        """Detects whether student uploaded an unrelated document (e.g. wrong PDF)."""
        text_lower = extracted_text.lower()
        if len(text_lower.strip()) == 0:
            return False, ""

        # Check explicit unrelated subject triggers
        for kw in cls.WRONG_SUBMISSION_KEYWORDS:
            if kw in text_lower:
                return True, f"Uploaded document appears unrelated: contains '{kw}'"

        # Check domain relevance against assignment context
        context_words = set(re_words for re_words in (assignment_title + " " + assignment_description).lower().split() if len(re_words) > 3)
        if len(context_words) > 3:
            overlap = [w for w in context_words if w in text_lower]
            # If student submitted over 100 words but has zero overlap with key assignment words
            if len(text_lower.split()) > 60 and len(overlap) == 0:
                # Double check if code snippets exist
                return True, "Content has no semantic overlap with assignment topic."

        return False, ""

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
        assignment_title: str,
        assignment_description: str,
        test_cases: Optional[List[Dict[str, str]]] = None
    ) -> EvaluationResultResponse:
        now_str = datetime.now().isoformat()
        flags = []
        criteria_results: List[CriterionEvaluationResult] = []
        code_exec_result: Optional[CodeTestExecutionResult] = None
        remarks = None

        # 1. Check Missing Submission
        if state == "MISSING" or (not attachments and not extracted_content.text_content.strip()):
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

        # 3. Check Wrong Submission (e.g. Uploaded Wrong PDF)
        is_wrong, wrong_reason = cls.detect_wrong_submission(
            extracted_content.text_content,
            assignment_title,
            assignment_description
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

        # 4. Code Execution if applicable
        if extracted_content.code_snippets:
            primary_snippet = extracted_content.code_snippets[0]
            lang = primary_snippet.get("language", "c")
            code_str = primary_snippet.get("code", "")
            if lang in ("c", "cpp"):
                code_exec_result = CodeSandbox.evaluate_c_or_cpp(code_str, lang, test_cases)
            elif lang in ("py", "python"):
                code_exec_result = CodeSandbox.evaluate_python(code_str, test_cases)

        # 5. Evaluate Criterion by Criterion
        for crit in rubric.criteria:
            crit_eval = LocalLLMEngine.evaluate_criterion_semantic(
                criterion=crit,
                extracted_text=extracted_content.text_content,
                code_snippets=extracted_content.code_snippets,
                assignment_context=f"{assignment_title}\n{assignment_description}"
            )

            # If this is code execution criterion and we have actual execution results:
            if crit.evaluation_type == "code_execution" and code_exec_result:
                if not code_exec_result.compilation_success:
                    crit_eval["awarded_marks"] = round(crit.max_marks * 0.2, 1)  # Partial marks for code attempt
                    crit_eval["status"] = "partial"
                    crit_eval["explanation"] = f"Compilation failed: {code_exec_result.compilation_error[:120]}"
                elif code_exec_result.tests_total > 0:
                    pass_ratio = code_exec_result.tests_passed / code_exec_result.tests_total
                    crit_eval["awarded_marks"] = round(crit.max_marks * pass_ratio, 1)
                    crit_eval["status"] = "completed" if pass_ratio == 1.0 else ("partial" if pass_ratio > 0 else "incorrect")
                    crit_eval["explanation"] = f"Passed {code_exec_result.tests_passed}/{code_exec_result.tests_total} automated test cases."

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
