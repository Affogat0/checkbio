"""
pysam-specific rules.

pysam's AlignmentFile mode strings are easy for an AI model to hallucinate
a plausible-but-invalid variant of (e.g. "rw", "bam", "read"), and fetch()/
pileup() calls are a common site for a silent 0-based/1-based coordinate
mistake carried over from a 1-based source (VCF/GFF/SAM).

PYS003 only fires once the provenance tracker (checkbio.provenance)
confirms the .fetch()/.pileup() receiver is actually a pysam.AlignmentFile,
rather than matching on the method name alone. If the receiver's origin is
untraceable in its local scope, the rule stays silent rather than firing
with a hedge — consistent with how the rest of checkbio treats anything it
can't confirm (e.g. BIO002 skips a non-literal format argument rather than
warning about it).
"""

import ast
from . import Finding, ONE_BASED_HINTS, name_hints
from ..provenance import build_parent_map, build_provenance, enclosing_scope

# Real valid pysam.AlignmentFile mode strings.
VALID_MODES = {
    "r", "rb", "rc", "ru", "w", "wb", "wc", "wu", "wb0", "wbu", "a", "ab",
}


class _Visitor(ast.NodeVisitor):
    def __init__(self, module_tree: ast.AST, parents: dict):
        self.findings: list[Finding] = []
        self._module_tree = module_tree
        self._parents = parents
        self._provenance_cache: dict = {}

    def _provenance_for(self, node: ast.AST):
        scope = enclosing_scope(node, self._parents, self._module_tree)
        key = id(scope)
        if key not in self._provenance_cache:
            self._provenance_cache[key] = build_provenance(scope, self._module_tree)
        return self._provenance_cache[key]

    def visit_Call(self, node: ast.Call):
        func = node.func

        # PYS001: pysam.AlignmentFile(path, mode) with an invalid mode string.
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
                            rule_id="PYS001",
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

        # PYS003: .fetch()/.pileup() called with a start/end argument whose
        # name suggests it came from a 1-based source (VCF/GFF/SAM) with no
        # visible -1 adjustment. pysam's fetch() always expects 0-based,
        # half-open coordinates regardless of the 1-based conventions used
        # in SAM/BAM's own text display or in VCF/GFF — this mismatch is a
        # very common off-by-one specifically at the fetch() call site.
        #
        # Only evaluated once the provenance tracker confirms the receiver
        # is actually a pysam.AlignmentFile — not any object that happens
        # to have a method named .fetch()/.pileup(). If the receiver's
        # origin can't be traced within this scope (e.g. it's a function
        # parameter), the tracker reports "unknown" and this rule doesn't
        # fire — see the module docstring for why unknown means silent,
        # not a hedged warning.
        is_confirmed_alignment_file = (
            isinstance(func, ast.Attribute)
            and func.attr in {"fetch", "pileup"}
            and isinstance(func.value, ast.Name)
            and self._provenance_for(node).type_of(func.value.id, node.lineno)
            == "pysam.AlignmentFile"
        )
        if is_confirmed_alignment_file:
            arg_names = [a.id for a in node.args if isinstance(a, ast.Name)]
            one_based_args = [n for n in arg_names if name_hints(n, ONE_BASED_HINTS)]
            has_offset = any(
                isinstance(a, ast.BinOp) and isinstance(a.op, ast.Sub)
                for a in node.args
            )
            if one_based_args and not has_offset:
                self.findings.append(
                    Finding(
                        line=node.lineno,
                        col=node.col_offset,
                        rule_id="PYS003",
                        message=(
                            f"'.{func.attr}()' called with argument(s) "
                            f"{one_based_args} that look 1-based (VCF/GFF/"
                            "SAM-style), but pysam expects 0-based, "
                            "half-open coordinates. Confirm a -1 conversion "
                            "has been applied to the start position before "
                            "this call."
                        ),
                        severity="warning",
                    )
                )

        self.generic_visit(node)


def check(tree: ast.AST, source_lines: list) -> list:
    parents = build_parent_map(tree)
    visitor = _Visitor(tree, parents)
    visitor.visit(tree)
    return visitor.findings
