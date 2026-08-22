"""
Local variable-provenance tracking.

Given a single function's (or the module top level's) AST, this builds a
mapping from variable name -> the constructor call that produced it, so a
rule can ask "is this actually a pysam.AlignmentFile?" instead of "does
this object have a method named .fetch()?"

This is intentionally NOT type inference: no cross-function tracing, no
return-type analysis of user-defined functions, no aliasing through
containers. Three things establish a variable's type, all of them
explicit rather than guessed:

  1. Direct assignment from a known constructor call: `x = pysam.
     AlignmentFile(...)`.
  2. A `with`/`async with` binding from a known constructor call:
     `with pysam.AlignmentFile(...) as x:` — this is just as explicit as
     assignment, it's the idiomatic way to open a pysam file at all.
  3. An explicit parameter type annotation naming a known type:
     `def f(x: pysam.AlignmentFile):`. This is the author's own stated
     claim about the parameter's type, not an inference from its name or
     how it's used — deliberately excluded is any attempt to guess a
     parameter's type from its name (`bam`) or call-site usage
     (`x.fetch(...)` therefore `x` is pysam-like), since that is exactly
     the kind of pattern-matching-as-a-proxy-for-type that produced the
     false positives this module exists to fix.

Reassignment within one scope is tracked chronologically — a later
assignment overrides an earlier one (including an annotation) for any use
after that point. If a variable's origin isn't one of the three patterns
above — most commonly, an unannotated bare function parameter — its type
is reported as unknown (`None`) rather than guessed.
"""

import ast

# (resolved module name, attribute name) -> type tag, for calls of the
# shape `module.func(...)` or `alias.func(...)` where the alias is
# resolved back to its real module first.
MODULE_QUALIFIED_CONSTRUCTORS = {
    ("pysam", "AlignmentFile"): "pysam.AlignmentFile",
    ("pandas", "read_csv"): "pandas.DataFrame",
    ("pandas", "read_table"): "pandas.DataFrame",
    ("pandas", "read_excel"): "pandas.DataFrame",
    ("pandas", "DataFrame"): "pandas.DataFrame",
    # Format-revealing constructors used by LOC001 as a stronger-than-name
    # signal for which coordinate convention a variable came from.
    ("pysam", "VariantFile"): "pysam.VariantFile",  # VCF/BCF — 1-based
    ("pybedtools", "BedTool"): "pybedtools.BedTool",  # BED — 0-based
}

# Method-name-only constructors: any call `<anything>.merge(...)` is
# treated as producing a DataFrame, regardless of what the receiver is —
# this also naturally covers chained merges (`df2 = df1.merge(...)`)
# without needing to separately confirm df1's own type.
ATTRIBUTE_ONLY_CONSTRUCTORS = {
    "merge": "pandas.DataFrame",
}

# (resolved module name, type name) -> type tag, for a parameter annotation
# of the shape `x: module.Type` or `x: alias.Type`. Deliberately a separate,
# smaller table than MODULE_QUALIFIED_CONSTRUCTORS: a constructor and its
# return type usually share a name (`pysam.AlignmentFile(...)` returns a
# `pysam.AlignmentFile`), but not always (`pd.read_csv(...)` returns a
# `pandas.DataFrame`, and nobody annotates a parameter `x: pd.read_csv`).
MODULE_QUALIFIED_TYPES = {
    ("pysam", "AlignmentFile"): "pysam.AlignmentFile",
    ("pandas", "DataFrame"): "pandas.DataFrame",
    ("pysam", "VariantFile"): "pysam.VariantFile",
    ("pybedtools", "BedTool"): "pybedtools.BedTool",
}

# Bare type names recognized in an annotation with no module qualifier,
# e.g. `def f(x: AlignmentFile)` after `from pysam import AlignmentFile` —
# the same bare-name convention PYS001 already accepts for the constructor
# call itself.
BARE_TYPE_NAMES = {
    "AlignmentFile": "pysam.AlignmentFile",
    "DataFrame": "pandas.DataFrame",
    "VariantFile": "pysam.VariantFile",
    "BedTool": "pybedtools.BedTool",
}


def resolve_import_aliases(tree: ast.AST) -> dict:
    """Map local bound names to their real module path, e.g.
    {"ps": "pysam", "pd": "pandas", "pandas": "pandas"} for
    `import pysam as ps` / `import pandas as pd` / `import pandas`."""
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                aliases[local] = alias.name
    return aliases


def _call_type_tag(call: ast.Call, module_aliases: dict):
    func = call.func
    if not isinstance(func, ast.Attribute):
        return None
    if isinstance(func.value, ast.Name):
        receiver_module = module_aliases.get(func.value.id, func.value.id)
        tag = MODULE_QUALIFIED_CONSTRUCTORS.get((receiver_module, func.attr))
        if tag is not None:
            return tag
    return ATTRIBUTE_ONLY_CONSTRUCTORS.get(func.attr)


def _annotation_type_tag(annotation, module_aliases: dict):
    """The type tag named by a parameter annotation, or None if it's
    missing, unrecognized, or not a simple name/attribute (or a quoted
    forward reference to one)."""
    if annotation is None:
        return None
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            annotation = ast.parse(annotation.value, mode="eval").body
        except SyntaxError:
            return None
    if isinstance(annotation, ast.Attribute) and isinstance(annotation.value, ast.Name):
        receiver_module = module_aliases.get(annotation.value.id, annotation.value.id)
        return MODULE_QUALIFIED_TYPES.get((receiver_module, annotation.attr))
    if isinstance(annotation, ast.Name):
        return BARE_TYPE_NAMES.get(annotation.id)
    return None


def _iter_local_nodes(scope_node: ast.AST):
    """Yield every descendant of `scope_node`, without crossing into a
    nested function/lambda's body — provenance is intentionally local to
    one enclosing function (or module top level), never cross-function."""
    stack = list(ast.iter_child_nodes(scope_node))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))


class Provenance:
    """The result of tracking one function/module scope: for each variable
    name, the sequence of (line, type_tag) it was assigned across that
    scope, in source order."""

    def __init__(self, types_by_line: dict):
        self._types_by_line = types_by_line

    def type_of(self, name: str, at_line: int):
        """The type tag of `name` as of `at_line` — i.e. from the most
        recent assignment at or before that line — or None if `name` was
        never assigned in this scope (e.g. it's a bare parameter) or its
        most recent assignment wasn't a recognized constructor call.
        Later reassignments after `at_line` are ignored."""
        entries = self._types_by_line.get(name)
        if not entries:
            return None
        result = None
        for line, tag in entries:
            if line <= at_line:
                result = tag
            else:
                break
        return result


def build_provenance(scope_node: ast.AST, module_tree: ast.AST) -> Provenance:
    """Build a Provenance map for a single function (or module) scope.

    `scope_node` is the FunctionDef/AsyncFunctionDef/Module node whose body
    is being analyzed. `module_tree` is the whole file's AST, used only to
    resolve import aliases (imports are almost always at module level, not
    repeated inside every function).
    """
    aliases = resolve_import_aliases(module_tree)
    types_by_line: dict = {}

    # Parameter annotations seed the very start of the scope (the `def`
    # line itself, which is <= every statement in the body) so they apply
    # from the first use unless a later reassignment overrides them.
    if isinstance(scope_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for arg in (
            scope_node.args.posonlyargs
            + scope_node.args.args
            + scope_node.args.kwonlyargs
        ):
            tag = _annotation_type_tag(arg.annotation, aliases)
            if tag is not None:
                types_by_line.setdefault(arg.arg, []).append((scope_node.lineno, tag))

    # Bindings from plain assignment (`x = call(...)`) and from `with`/
    # `async with` (`with call(...) as x:`) — the latter is just as
    # explicit as assignment, and is the idiomatic way to open a pysam
    # file, so it's tracked the same way, ordered by the same rule: later
    # binding wins for anything after it.
    bindings = []  # (line, col, name, value_node_or_None)
    for node in _iter_local_nodes(scope_node):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            bindings.append((node.lineno, node.col_offset, node.targets[0].id, node.value))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if isinstance(item.optional_vars, ast.Name):
                    bindings.append(
                        (node.lineno, node.col_offset, item.optional_vars.id, item.context_expr)
                    )
    bindings.sort(key=lambda b: (b[0], b[1]))

    for line, _col, name, value in bindings:
        tag = _call_type_tag(value, aliases) if isinstance(value, ast.Call) else None
        types_by_line.setdefault(name, []).append((line, tag))

    return Provenance(types_by_line)


def build_parent_map(tree: ast.AST) -> dict:
    """Map each node to its parent, for enclosing_scope() below."""
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def enclosing_scope(node: ast.AST, parents: dict, module_tree: ast.AST) -> ast.AST:
    """The nearest enclosing FunctionDef/AsyncFunctionDef of `node`, or
    `module_tree` if `node` is at module top level."""
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
        cur = parents.get(cur)
    return module_tree
