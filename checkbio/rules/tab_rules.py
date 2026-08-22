"""
Genomic table (pandas) rules.

Genomic data loaded into pandas DataFrames is routinely merged/joined on a
single "position" column, which silently produces wrong results whenever
two different chromosomes happen to share a coordinate (extremely common —
every chromosome has a "position 100000"). A pandas merge has no domain
knowledge that a genomic position is only meaningful alongside a
chromosome; it will happily join on position alone and produce output that
looks entirely plausible.

TAB001 only fires once the provenance tracker (checkbio.provenance)
confirms the merge is actually a pandas operation — either `pd.merge(...)`/
`pandas.merge(...)` (resolved through import aliases), or `<name>.merge(...)`
where `<name>`'s local provenance traces back to a DataFrame constructor —
rather than matching on any object that happens to have a `.merge()`
method. If a `.merge()` receiver's origin is untraceable in its local
scope (e.g. it's a function parameter), the rule stays silent rather than
firing with a hedge, the same policy PYS003 uses for the same reason.
"""

import ast
from . import Finding
from ..provenance import (
    build_parent_map,
    build_provenance,
    enclosing_scope,
    resolve_import_aliases,
)

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
    def __init__(self, module_tree: ast.AST, parents: dict, aliases: dict):
        self.findings: list[Finding] = []
        self._module_tree = module_tree
        self._parents = parents
        self._aliases = aliases
        self._provenance_cache: dict = {}

    def _provenance_for(self, node: ast.AST):
        scope = enclosing_scope(node, self._parents, self._module_tree)
        key = id(scope)
        if key not in self._provenance_cache:
            self._provenance_cache[key] = build_provenance(scope, self._module_tree)
        return self._provenance_cache[key]

    def _is_confirmed_dataframe_merge(self, node: ast.Call) -> bool:
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "merge"):
            return False
        receiver = func.value
        if not isinstance(receiver, ast.Name):
            return False
        # Module-level call form: pd.merge(df1, df2, ...) / pandas.merge(...)
        if self._aliases.get(receiver.id, receiver.id) == "pandas":
            return True
        # Method-call form: <name>.merge(...) — confirm <name> is a DataFrame.
        return self._provenance_for(node).type_of(receiver.id, node.lineno) == "pandas.DataFrame"

    def visit_Call(self, node: ast.Call):
        # TAB001: df.merge(other, on=<position-only key>) — flags merges
        # keyed on a position-like column with no accompanying
        # chromosome-like column, on any of on=/left_on=/right_on=.
        if self._is_confirmed_dataframe_merge(node):
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
    parents = build_parent_map(tree)
    aliases = resolve_import_aliases(tree)
    visitor = _Visitor(tree, parents, aliases)
    visitor.visit(tree)
    return visitor.findings
