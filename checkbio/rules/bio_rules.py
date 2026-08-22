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
    # Bio.SeqIO formats
    "fasta", "fasta-2line", "fastq", "fastq-sanger", "fastq-solexa",
    "fastq-illumina", "genbank", "gb", "embl", "imgt", "phd", "sff",
    "sff-trim", "qual", "tab", "clustal", "nexus", "phylip", "stockholm",
    "swiss", "uniprot-xml", "seqxml", "abi", "abi-trim", "ig", "pir",
    "ace", "cif-atom", "cif-seqres", "gck", "nib", "pdb-atom",
    "pdb-seqres", "snapgene", "twobit", "xdna",
    # Bio.AlignIO-only formats (parse()/read() are shared between the two
    # modules, so these need to be recognized too)
    "emboss", "fasta-m10", "maf", "mauve", "msf", "phylip-sequential",
    "phylip-relaxed",
}

# Positions/keywords where each SeqIO/AlignIO function actually expects a
# format string. parse()/read() take (handle, format, ...) — format at
# index 1. write() takes (sequences, handle, format) — format at index 2,
# not 1. convert() takes (in_file, in_format, out_file, out_format) — two
# separate format strings, at index 1 and index 3, under distinct keyword
# names (in_format=/out_format=, not format=).
FORMAT_ARG_POSITIONS = {
    "parse": [1],
    "read": [1],
    "write": [2],
    "convert": [1, 3],
}
FORMAT_KEYWORD_NAMES = {
    "parse": {"format"},
    "read": {"format"},
    "write": {"format"},
    "convert": {"in_format", "out_format"},
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
                    rule_id="BIO001",
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
        # BIO002: SeqIO.parse()/SeqIO.read() called with a format string
        # that isn't a real Biopython format.
        func = node.func
        is_seqio_call = (
            isinstance(func, ast.Attribute)
            and func.attr in {"parse", "read", "write", "convert"}
            and isinstance(func.value, ast.Name)
            and func.value.id in {"SeqIO", "AlignIO"}
        )
        if is_seqio_call:
            # Which argument position(s)/keyword(s) actually hold a format
            # string depends on which function this is — write()/convert()
            # don't put it at the same spot as parse()/read().
            fmt_nodes = []
            for idx in FORMAT_ARG_POSITIONS.get(func.attr, []):
                if len(node.args) > idx and isinstance(node.args[idx], ast.Constant):
                    fmt_nodes.append(node.args[idx])
            kw_names = FORMAT_KEYWORD_NAMES.get(func.attr, {"format"})
            for kw in node.keywords:
                if kw.arg in kw_names and isinstance(kw.value, ast.Constant):
                    fmt_nodes.append(kw.value)

            for fmt_node in fmt_nodes:
                if not isinstance(fmt_node.value, str):
                    continue
                fmt = fmt_node.value.lower()
                if fmt not in VALID_SEQIO_FORMATS:
                    self.findings.append(
                        Finding(
                            line=node.lineno,
                            col=node.col_offset,
                            rule_id="BIO002",
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
