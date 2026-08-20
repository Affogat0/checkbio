"""
Genomic table (pandas) rules.

Genomic data loaded into pandas DataFrames is routinely merged/joined on a
single "position" column, which silently produces wrong results whenever
two different chromosomes happen to share a coordinate (extremely common —
every chromosome has a "position 100000"). A pandas merge has no domain
knowledge that a genomic position is only meaningful alongside a
chromosome; it will happily join on position alone and produce output that
looks entirely plausible.
"""

import ast
from . import Finding

# Column-name fragments that indicate a genomic position, on their own.
POSITION_HINTS = {"pos", "position", "start", "end", "coord", "coordinate"}

# Column-name fragments that indicate the chromosome is accounted for.
CHROM_HINTS = {"chrom", "chr", "contig", "seqname", "seqid"}


def _string_values(node) -> list:
    """Extract string constant values from a merge key argument, which may
    be a single string or a list/tuple of strings."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [
            elt.value for elt in node.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        ]
    return []


def _has_hint(values: list, hints: set) -> bool:
    return any(any(h in v.lower() for h in hints) for v in values)


class _Visitor(ast.NodeVisitor):
    def __init__(self):
        self.findings: list[Finding] = []

    def visit_Call(self, node: ast.Call):
        # TAB001: df.merge(other, on=<position-only key>) — flags merges
        # keyed on a position-like column with no accompanying
        # chromosome-like column, on any of on=/left_on=/right_on=.
        func = node.func
        is_merge_call = isinstance(func, ast.Attribute) and func.attr == "merge"

        if is_merge_call:
            key_values = []
            for kw in node.keywords:
                if kw.arg in {"on", "left_on", "right_on"}:
                    key_values.extend(_string_values(kw.value))

            if key_values:
                has_position = _has_hint(key_values, POSITION_HINTS)
                has_chrom = _has_hint(key_values, CHROM_HINTS)
                if has_position and not has_chrom:
                    self.findings.append(
                        Finding(
                            line=node.lineno,
                            col=node.col_offset,
                            rule_id="TAB001",
                            message=(
                                f"Merge key(s) {key_values} include a "
                                "genomic position column but no chromosome "
                                "column. Every chromosome shares the same "
                                "range of position values, so a merge on "
                                "position alone will silently join "
                                "unrelated records from different "
                                "chromosomes. Include chrom/chromosome in "
                                "the merge key."
                            ),
                        )
                    )

        self.generic_visit(node)


def check(tree: ast.AST, source_lines: list) -> list:
    visitor = _Visitor()
    visitor.visit(tree)
    return visitor.findings
