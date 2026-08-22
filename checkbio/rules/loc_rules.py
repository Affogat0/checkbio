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

LOC001 supplements the name-hint heuristic with the provenance tracker
(checkbio.provenance): if a variable can be traced back to a
pysam.VariantFile (VCF/BCF) or pybedtools.BedTool (BED) constructor call in
its local scope, that's treated as a stronger, confirmed signal than a
name merely containing "vcf" or "bed". The name-hint heuristic is kept as
a fallback, not replaced — in real code, the coordinate value being
compared is usually extracted from a parser object one or more steps after
construction (e.g. via a for-loop or attribute access), which a local,
assignment-only provenance tracker can't see. Provenance mainly adds
confidence when it *can* resolve something; hints still do most of the
work.
"""

import re
import ast
from . import Finding, ONE_BASED_HINTS, name_hints
from ..provenance import build_parent_map, build_provenance, enclosing_scope

# Provenance type tags (from checkbio.provenance) that confirm a variable's
# coordinate convention more strongly than a name-hint match.
PROVENANCE_ZERO_BASED_TAGS = {"pybedtools.BedTool"}
PROVENANCE_ONE_BASED_TAGS = {"pysam.VariantFile"}

# Variable-name fragments that suggest a 0-based coordinate source.
ZERO_BASED_HINTS = {"bed", "pybed", "zero_based", "0based"}

# Chromosome naming convention patterns (LOC003).
_CHR_NUM = r"(?:[1-9]|1[0-9]|2[0-2])"
PREFIXED_CHROM = re.compile(rf"^chr(?:{_CHR_NUM}|X|Y|M|MT)$")
BARE_CHROM = re.compile(rf"^(?:{_CHR_NUM}|X|Y|MT)$")


def _collect_names(node: ast.AST) -> list:
    """Return all ast.Name nodes under `node`."""
    return [n for n in ast.walk(node) if isinstance(n, ast.Name)]


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

    def visit_Compare(self, node: ast.Compare):
        # LOC001: comparing/combining a 0-based-named variable directly
        # against a 1-based-named variable with no visible +/-1 adjustment
        # anywhere in the comparison expression. A confirmed provenance tag
        # (traced to a VCF/BED-reading constructor) counts the same as a
        # name-hint match, just with higher confidence.
        names = _collect_names(node)
        provenance = self._provenance_for(node)
        has_zero = any(
            name_hints(n.id, ZERO_BASED_HINTS)
            or provenance.type_of(n.id, node.lineno) in PROVENANCE_ZERO_BASED_TAGS
            for n in names
        )
        has_one = any(
            name_hints(n.id, ONE_BASED_HINTS)
            or provenance.type_of(n.id, node.lineno) in PROVENANCE_ONE_BASED_TAGS
            for n in names
        )
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
    parents = build_parent_map(tree)
    visitor = _Visitor(tree, parents)
    visitor.visit(tree)
    return visitor.findings + _check_chromosome_naming(tree)
