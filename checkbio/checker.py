import ast
from pathlib import Path

from .rules import Finding, loc_rules, bio_rules, pys_rules, ref_rules, tab_rules

RULE_MODULES = [loc_rules, bio_rules, pys_rules, ref_rules, tab_rules]


def check_source(source: str, filename: str = "<string>") -> list:
    """Run every rule module against a source string. Returns a sorted
    list of Finding objects (by line number)."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [
            Finding(
                line=e.lineno or 0,
                col=e.offset or 0,
                rule_id="REP000",
                message=f"Could not parse file: {e.msg}",
                severity="error",
            )
        ]

    source_lines = source.splitlines()
    findings = []
    for module in RULE_MODULES:
        findings.extend(module.check(tree, source_lines))

    return sorted(findings, key=lambda f: (f.line, f.col))


def check_file(path: str) -> list:
    """Run every rule module against a file on disk.

    A file that can't be read at all (missing, a directory, permission
    denied, not valid text) is reported the same way an unparseable file
    is — one REP000 finding for that file — rather than raising and
    aborting the whole `checkbio` run over every other file passed in.
    """
    try:
        source = Path(path).read_text()
    except (OSError, UnicodeDecodeError) as e:
        return [
            Finding(
                line=0,
                col=0,
                rule_id="REP000",
                message=f"Could not read file: {e}",
                severity="error",
            )
        ]
    return check_source(source, filename=path)
