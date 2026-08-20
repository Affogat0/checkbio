"""
Biopython-specific rules.

AI coding assistants are frequently trained on a mix of old and new
Biopython documentation/examples, and Biopython has made several breaking
changes over the years (most notably removing Bio.Alphabet in 1.78+). The
result: models confidently generate code against an API that no longer
exists, or pass a format string to SeqIO that isn't real.
"""

import ast
from . import Finding

# Bio.Alphabet was removed in Biopython 1.78 (2020). Still shows up
# constantly in AI-generated code trained on older examples/tutorials.
REMOVED_MODULES = {"Bio.Alphabet"}

# Real, valid SeqIO/AlignIO format strings (non-exhaustive but covers the
# common ones). Anything not in this set is flagged for a human to check,
# since it may be a hallucinated or misspelled format name.
VALID_SEQIO_FORMATS = {
    "fasta", "fasta-2line", "fastq", "fastq-sanger", "fastq-solexa",
    "fastq-illumina", "genbank", "gb", "embl", "imgt", "phd", "sff",
    "sff-trim", "qual", "tab", "clustal", "nexus", "phylip", "stockholm",
    "swiss", "uniprot-xml", "seqxml", "abi", "abi-trim", "ig", "pir",
}


class _Visitor(ast.NodeVisitor):
    def __init__(self):
        self.findings: list[Finding] = []

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        if module in REMOVED_MODULES:
            self.findings.append(
                Finding(
                    line=node.lineno,
                    col=node.col_offset,
                    rule_id="BL010",
                    message=(
                        f"'{module}' was removed in Biopython 1.78 (2020). "
                        "This import will fail on any current Biopython "
                        "install. This is a very common AI-generated-code "
                        "hallucination from older training examples."
                    ),
                    severity="error",
                )
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # BL011: SeqIO.parse()/SeqIO.read() called with a format string
        # that isn't a real Biopython format.
        func = node.func
        is_seqio_call = (
            isinstance(func, ast.Attribute)
            and func.attr in {"parse", "read", "write", "convert"}
            and isinstance(func.value, ast.Name)
            and func.value.id in {"SeqIO", "AlignIO"}
        )
        if is_seqio_call:
            # format is usually the 2nd positional arg, or a "format=" kwarg
            fmt_node = None
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                fmt_node = node.args[1]
            for kw in node.keywords:
                if kw.arg == "format" and isinstance(kw.value, ast.Constant):
                    fmt_node = kw.value
            if fmt_node is not None and isinstance(fmt_node.value, str):
                fmt = fmt_node.value.lower()
                if fmt not in VALID_SEQIO_FORMATS:
                    self.findings.append(
                        Finding(
                            line=node.lineno,
                            col=node.col_offset,
                            rule_id="BL011",
                            message=(
                                f"'{fmt}' is not a recognized Bio.SeqIO/"
                                "AlignIO format string. Check for a typo or "
                                "a hallucinated format name — this will "
                                "raise a ValueError at runtime."
                            ),
                            severity="error",
                        )
                    )
        self.generic_visit(node)


def check(tree: ast.AST, source_lines: list) -> list:
    visitor = _Visitor()
    visitor.visit(tree)
    return visitor.findings
