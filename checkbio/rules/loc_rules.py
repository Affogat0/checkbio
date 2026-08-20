"""
Coordinate system rules.

The single most common silent bug in bioinformatics code: mixing 0-based
(BED, Python slicing) and 1-based (VCF, GFF, SAM) coordinate systems
without an explicit +1/-1 conversion. AI coding assistants get this wrong
constantly because Python itself is 0-indexed, so a plausible-looking
translation of "get the base at genomic position X" is very often off by
one.

Detection here is intentionally heuristic (name-based), not a full data-flow
analysis, that would require real type/format tracking. The goal is to
catch the common, recognizable patterns, not every possible bug.
"""

import re
import ast
from . import Finding

# Variable-name fragments that suggest a 0-based coordinate source.
ZERO_BASED_HINTS = {"bed", "pybed", "zero_based", "0based"}

# Variable-name fragments that suggest a 1-based coordinate source.
ONE_BASED_HINTS = {"vcf", "gff", "gtf", "sam", "one_based", "1based"}

# Chromosome naming convention patterns (LOC003).
_CHR_NUM = r"(?:[1-9]|1[0-9]|2[0-2])"
PREFIXED_CHROM = re.compile(rf"^chr(?:{_CHR_NUM}|X|Y|M|MT)$")
BARE_CHROM = re.compile(rf"^(?:{_CHR_NUM}|X|Y|MT)$")


def _name_hints(name: str, hints: set) -> bool:
    lowered = name.lower()
    return any(h in lowered for h in hints)


def _collect_names(node: ast.AST) -> list:
    """Return all ast.Name nodes under `node`."""
    return [n for n in ast.walk(node) if isinstance(n, ast.Name)]


class _Visitor(ast.NodeVisitor):
    def __init__(self):
        self.findings: list[Finding] = []

    def visit_Compare(self, node: ast.Compare):
        # LOC001: comparing/combining a 0-based-named variable directly
        # against a 1-based-named variable with no visible +/-1 adjustment
        # anywhere in the comparison expression.
        names = _collect_names(node)
        has_zero = any(_name_hints(n.id, ZERO_BASED_HINTS) for n in names)
        has_one = any(_name_hints(n.id, ONE_BASED_HINTS) for n in names)
        has_offset = any(
            isinstance(sub, ast.BinOp) and isinstance(sub.op, (ast.Add, ast.Sub))
            for sub in ast.walk(node)
        )
        if has_zero and has_one and not has_offset:
            self.findings.append(
                Finding(
                    line=node.lineno,
                    col=node.col_offset,
                    rule_id="LOC001",
                    message=(
                        "Comparing a 0-based coordinate (BED-style) directly "
                        "against a 1-based coordinate (VCF/GFF/SAM-style) "
                        "with no visible +1/-1 adjustment. Verify the "
                        "coordinate systems actually match before comparing."
                    ),
                )
            )
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript):
        # LOC002: slicing a sequence using a variable that looks like a
        # genomic "start"/"end" position, with no nearby comment
        # indicating which coordinate convention is being used.
        slice_node = node.slice
        if isinstance(slice_node, ast.Slice):
            lower_name = getattr(slice_node.lower, "id", None) if isinstance(
                slice_node.lower, ast.Name
            ) else None
            upper_name = getattr(slice_node.upper, "id", None) if isinstance(
                slice_node.upper, ast.Name
            ) else None
            candidates = [n for n in (lower_name, upper_name) if n]
            flagged = [
                n for n in candidates
                if "start" in n.lower() or "end" in n.lower() or "pos" in n.lower()
            ]
            if flagged:
                self.findings.append(
                    Finding(
                        line=node.lineno,
                        col=node.col_offset,
                        rule_id="LOC002",
                        message=(
                            f"Slicing with genomic-position-like variable(s) "
                            f"{flagged} — confirm whether this position is "
                            "0-based or 1-based before using it as a Python "
                            "slice index. Off-by-one here is the most common "
                            "silent bug in genomics code."
                        ),
                        severity="warning",
                    )
                )
        self.generic_visit(node)


def _check_chromosome_naming(tree: ast.AST) -> list:
    # LOC003: a file that uses both "chr1"-style and "1"-style chromosome
    # names is very likely about to fail a join/comparison between two
    # data sources with different naming conventions (e.g. UCSC "chr1" vs
    # Ensembl "1", or "chrM" vs "MT"). This is a file-level heuristic —
    # exact line numbers for both forms are reported so a human can trace
    # where each convention is coming from.
    prefixed_hits = []
    bare_hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if PREFIXED_CHROM.fullmatch(node.value):
                prefixed_hits.append((node.value, node.lineno, node.col_offset))
            elif BARE_CHROM.fullmatch(node.value):
                bare_hits.append((node.value, node.lineno, node.col_offset))

    if prefixed_hits and bare_hits:
        example_prefixed, pline, pcol = prefixed_hits[0]
        example_bare, bline, bcol = bare_hits[0]
        return [
            Finding(
                line=pline,
                col=pcol,
                rule_id="LOC003",
                message=(
                    f"Found chromosome name '{example_prefixed}' (line "
                    f"{pline}) and '{example_bare}' (line {bline}) in the "
                    "same file — these use different chromosome naming "
                    "conventions (chr-prefixed vs. bare, or chrM vs. MT). "
                    "Comparing/joining data across these without "
                    "normalizing first will silently drop or mismatch "
                    "every record on the affected chromosome."
                ),
            )
        ]
    return []


def check(tree: ast.AST, source_lines: list) -> list:
    visitor = _Visitor()
    visitor.visit(tree)
    return visitor.findings + _check_chromosome_naming(tree)
