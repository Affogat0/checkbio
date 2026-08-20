"""
pysam-specific rules.

pysam's AlignmentFile mode strings are easy for an AI model to hallucinate
a plausible-but-invalid variant of (e.g. "rw", "bam", "read"), and code that
calls .fetch()/.pileup() on a BAM/CRAM file without an index in place fails
at runtime in a way that's often confusing to a newcomer debugging AI
generated code.
"""

import ast
from . import Finding

# Real valid pysam.AlignmentFile mode strings.
VALID_MODES = {
    "r", "rb", "rc", "ru", "w", "wb", "wc", "wu", "wb0", "wbu", "a", "ab",
}


class _Visitor(ast.NodeVisitor):
    def __init__(self):
        self.findings: list[Finding] = []
        self._fetch_seen_without_index_guard = False

    def visit_Call(self, node: ast.Call):
        func = node.func

        # BL020: pysam.AlignmentFile(path, mode) with an invalid mode string.
        is_alignment_file_call = (
            isinstance(func, ast.Attribute)
            and func.attr == "AlignmentFile"
            and isinstance(func.value, ast.Name)
            and func.value.id == "pysam"
        ) or (isinstance(func, ast.Name) and func.id == "AlignmentFile")

        if is_alignment_file_call:
            mode_node = None
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode_node = node.args[1]
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode_node = kw.value
            if mode_node is not None and isinstance(mode_node.value, str):
                mode = mode_node.value
                if mode not in VALID_MODES:
                    self.findings.append(
                        Finding(
                            line=node.lineno,
                            col=node.col_offset,
                            rule_id="BL020",
                            message=(
                                f"'{mode}' is not a valid pysam.AlignmentFile "
                                "mode string. Valid modes: "
                                f"{sorted(VALID_MODES)}. This will raise a "
                                "ValueError at runtime — check for a "
                                "hallucinated mode flag."
                            ),
                            severity="error",
                        )
                    )

        # BL021: .fetch() or .pileup() called with no nearby try/except or
        # index-existence check. Heuristic only — flags every call, since
        # detecting a "nearby" guard reliably needs real data-flow analysis.
        # Kept intentionally simple for v0.1: a human reviews the flag.
        if isinstance(func, ast.Attribute) and func.attr in {"fetch", "pileup"}:
            self.findings.append(
                Finding(
                    line=node.lineno,
                    col=node.col_offset,
                    rule_id="BL021",
                    message=(
                        f"'.{func.attr}()' requires an index file "
                        "(.bai/.csi/.crai) to exist alongside the BAM/CRAM "
                        "file. Confirm the index exists (or is being "
                        "created) before this call — this is a common "
                        "silent failure point in AI-generated pysam code."
                    ),
                    severity="warning",
                )
            )

        self.generic_visit(node)


def check(tree: ast.AST, source_lines: list) -> list:
    visitor = _Visitor()
    visitor.visit(tree)
    return visitor.findings
