import ast
from pathlib import Path

from .rules import loc_rules, bio_rules, pys_rules, ref_rules, tab_rules, cli_rules

RULE_MODULES = [loc_rules, bio_rules, pys_rules, ref_rules, tab_rules, cli_rules]


def check_source(source: str, filename: str = "<string>") -> list:
    """Run every rule module against a source string. Returns a sorted
    list of Finding objects (by line number)."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        from .rules import Finding
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
    """Run every rule module against a file on disk."""
    source = Path(path).read_text()
    return check_source(source, filename=path)
