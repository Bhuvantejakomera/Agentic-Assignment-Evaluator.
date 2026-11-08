import hashlib
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional, Set
from backend.app.models.evaluation import EvaluationResultResponse

class CollusionDetector:
    """
    Forensic duplicate and collusion detection across student submissions.
    Identifies identical files, code implementations, OCR terminal fingerprints,
    and orders submissions chronologically:
      - Earliest submitter: Original author (0 penalty)
      - Subsequent submitters: Copied work (-20 points penalty)
    """

    @staticmethod
    def clean_code(code_str: str) -> str:
        """Strips comments, gutter numbers, and whitespace to extract normalized logic tokens."""
        if not code_str:
            return ""
        # Remove single-line and multi-line comments
        code_str = re.sub(r"//.*", "", code_str)
        code_str = re.sub(r"/\*.*?\*/", "", code_str, flags=re.DOTALL)
        code_str = re.sub(r"#.*", "", code_str)
        # Remove standalone gutter line numbers
        lines = [re.sub(r"^\s*\d{1,4}[:\.]?\s*", "", l).strip() for l in code_str.splitlines()]
        code_str = " ".join(l for l in lines if l)
        # Normalize whitespace
        code_str = re.sub(r"\s+", " ", code_str).strip().lower()
        return code_str

    @staticmethod
    def extract_terminal_prompts(text: str) -> Set[str]:
        """Extracts unique machine hostnames/usernames from terminal OCR (e.g. user@hostname)."""
        if not text:
            return set()
        prompts = set(re.findall(r"([a-zA-Z0-9_\-\.]+@[a-zA-Z0-9_\-\.]+)", text))
        # Filter out generic local dev prompts
        generic = {"user@localhost", "root@localhost", "student@localhost"}
        return {p for p in prompts if p.lower() not in generic}

    @classmethod
    def are_submissions_duplicate(cls, item_a: Dict[str, Any], item_b: Dict[str, Any]) -> Tuple[bool, str]:
        """Compares two student submissions across multiple forensic layers."""
        # 1. Attachment File Hash Match (Identical uploaded file)
        if item_a.get("att_hashes") and item_b.get("att_hashes"):
            shared_files = item_a["att_hashes"] & item_b["att_hashes"]
            if shared_files:
                return True, "Identical attachment file upload (100% cryptographic match)"

        # 2. Exact Normalized Code Hash Match
        if item_a.get("code_hash") and item_b.get("code_hash"):
            if item_a["code_hash"] == item_b["code_hash"]:
                return True, "Identical program code implementation (100% logic match)"

        # 3. Exact Substantive Text Deliverable Hash Match
        if item_a.get("full_txt_hash") and item_b.get("full_txt_hash"):
            if item_a["full_txt_hash"] == item_b["full_txt_hash"]:
                return True, "Identical document text and deliverable contents"

        # 4. Shared Specific Machine / Terminal Fingerprint
        shared_prompts = item_a.get("prompts", set()) & item_b.get("prompts", set())
        if shared_prompts:
            return True, f"Shared terminal machine fingerprint ({list(shared_prompts)[0]})"

        # 5. High Code Token Jaccard Similarity (>= 94% with similar length)
        code_a = item_a.get("code_clean", "")
        code_b = item_b.get("code_clean", "")
        if len(code_a) > 200 and len(code_b) > 200:
            tokens_a = set(code_a.split())
            tokens_b = set(code_b.split())
            union = len(tokens_a | tokens_b)
            if union > 0:
                sim = len(tokens_a & tokens_b) / union
                if sim >= 0.94 and abs(len(code_a) - len(code_b)) < 80:
                    return True, f"Near-identical code token similarity ({int(sim * 100)}% match)"

        return False, ""

    @classmethod
    def find_collusion_clusters(cls, submissions_data: List[Dict[str, Any]]) -> List[List[int]]:
        """Builds connected component clusters of duplicate submissions."""
        n = len(submissions_data)
        adj = {i: set() for i in range(n)}

        for i in range(n):
            for j in range(i + 1, n):
                is_dup, _ = cls.are_submissions_duplicate(submissions_data[i], submissions_data[j])
                if is_dup:
                    adj[i].add(j)
                    adj[j].add(i)

        visited = set()
        clusters = []
        for i in range(n):
            if i not in visited:
                comp = []
                q = [i]
                visited.add(i)
                while q:
                    curr = q.pop()
                    comp.append(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            q.append(neighbor)
                if len(comp) > 1:
                    clusters.append(comp)

        return clusters

    @classmethod
    def process_collusion(
        cls,
        evaluated_list: List[Any],
        submissions_records: List[Dict[str, Any]],
        penalty_amount: float = 20.0
    ) -> Tuple[List[Any], List[Dict[str, Any]]]:
        """
        Detects duplicate submissions and applies chronological penalties:
        - Earliest submitter: 0 deduction
        - Subsequent submitters: -20 deduction
        """
        # Map student_id to submission metadata
        sub_meta_map = {}
        for row in submissions_records:
            sid = row.get("student_id")
            if not sid:
                continue

            ext_raw = row.get("extracted_content_json") or "{}"
            if isinstance(ext_raw, str):
                try:
                    ext = json.loads(ext_raw)
                except Exception:
                    ext = {}
            else:
                ext = ext_raw or {}

            att_hashes = set()
            att_raw = row.get("attachments_json") or "[]"
            if isinstance(att_raw, str):
                try:
                    atts = json.loads(att_raw)
                except Exception:
                    atts = []
            else:
                atts = att_raw or []
            if isinstance(atts, list):
                for a in atts:
                    fp = a.get("file_path")
                    if fp:
                        try:
                            with open(fp, "rb") as f:
                                att_hashes.add(hashlib.sha256(f.read()).hexdigest())
                        except Exception:
                            pass

            code_snippets = ext.get("code_snippets") or []
            all_codes = [cls.clean_code(cs.get("code", "")) for cs in code_snippets if len(cs.get("code", "").strip()) > 30]
            combined_code = " ".join(all_codes)
            code_hash = hashlib.sha256(combined_code.encode()).hexdigest() if len(combined_code) > 100 else None

            txt = (ext.get("text_content") or "").lower()
            prompts = cls.extract_terminal_prompts(txt)
            for df in ext.get("diagram_flowchart_descriptions") or []:
                prompts |= cls.extract_terminal_prompts(df)

            txt_clean = re.sub(r"\s+", " ", txt).strip()
            full_txt_hash = hashlib.sha256(txt_clean.encode()).hexdigest() if len(txt_clean) > 300 else None

            sub_time = row.get("submission_time") or row.get("created_at") or "9999-12-31T23:59:59Z"

            sub_meta_map[sid] = {
                "student_id": sid,
                "student_name": row.get("student_name") or row.get("name", "Unknown"),
                "submission_id": row.get("id") or row.get("sub_id", ""),
                "time": sub_time,
                "att_hashes": att_hashes,
                "code_clean": combined_code,
                "code_hash": code_hash,
                "prompts": prompts,
                "full_txt_hash": full_txt_hash,
                "txt_clean": txt_clean
            }

        # Filter items that are in evaluated_list
        eval_by_student = {e.student_id: e for e in evaluated_list}
        eval_subs = [sub_meta_map[sid] for sid in eval_by_student if sid in sub_meta_map]

        clusters = cls.find_collusion_clusters(eval_subs)
        cluster_reports = []

        for cluster_idx, cl in enumerate(clusters, 1):
            cl_items = [eval_subs[i] for i in cl]
            # Sort chronologically by submission time
            cl_items.sort(key=lambda x: x["time"])

            original_item = cl_items[0]
            orig_eval = eval_by_student.get(original_item["student_id"])
            if orig_eval:
                orig_eval.duplicate_cluster_id = cluster_idx
                orig_eval.duplicate_penalty = 0.0
                orig_eval.duplicate_of = None
                orig_eval.flags = list(set(orig_eval.flags + ["ORIGINAL_SUBMISSION"]))
                orig_note = f"Original author in duplicate cluster #{cluster_idx} ({len(cl_items)} students). Submitted earliest at {original_item['time'][:16]}."
                if orig_eval.faculty_remarks:
                    if "Original author" not in orig_eval.faculty_remarks:
                        orig_eval.faculty_remarks += f" | {orig_note}"
                else:
                    orig_eval.faculty_remarks = orig_note

            copies_data = []
            for copied_item in cl_items[1:]:
                cp_eval = eval_by_student.get(copied_item["student_id"])
                if cp_eval:
                    cp_eval.duplicate_cluster_id = cluster_idx
                    cp_eval.duplicate_penalty = penalty_amount
                    cp_eval.duplicate_of = original_item["student_name"]
                    # Apply -20 deduction
                    cp_eval.flags = list(set(cp_eval.flags + ["DUPLICATE"]))
                    # Remove ORIGINAL_SUBMISSION if present
                    if "ORIGINAL_SUBMISSION" in cp_eval.flags:
                        cp_eval.flags.remove("ORIGINAL_SUBMISSION")

                    # Deduct penalty (capped at 0.0 minimum)
                    original_final = cp_eval.final_score
                    new_final = max(0.0, round(original_final - penalty_amount, 1))
                    cp_eval.final_score = new_final

                    # Format human-friendly time difference
                    time_note = f"submitted later at {copied_item['time'][:16]}"
                    remark = f"Duplicate submission (Cluster #{cluster_idx}): Copied from {original_item['student_name']} ({time_note}). Plagiarism penalty applied: -{penalty_amount} pts."
                    if cp_eval.faculty_remarks:
                        if "Duplicate submission" not in cp_eval.faculty_remarks:
                            cp_eval.faculty_remarks = f"{remark} | {cp_eval.faculty_remarks}"
                    else:
                        cp_eval.faculty_remarks = remark

                    copies_data.append({
                        "student_id": copied_item["student_id"],
                        "student_name": copied_item["student_name"],
                        "submission_time": copied_item["time"],
                        "penalty": penalty_amount,
                        "final_score": new_final
                    })

            cluster_reports.append({
                "cluster_id": cluster_idx,
                "original_author": {
                    "student_id": original_item["student_id"],
                    "student_name": original_item["student_name"],
                    "submission_time": original_item["time"],
                    "score": orig_eval.final_score if orig_eval else 0.0
                },
                "total_students": len(cl_items),
                "copied_students": copies_data
            })

        return evaluated_list, cluster_reports
