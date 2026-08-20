"""
Each rule module exposes a `check(tree, source_lines) -> list[Finding]`
function. The checker collects findings from every rule module and reports
them together.
"""

from dataclasses import dataclass


@dataclass
class Finding:
    line: int
    col: int
    rule_id: str
    message: str
    severity: str = "warning"  # "warning" | "error"

    def __str__(self) -> str:
        return f"{self.line}:{self.col} [{self.rule_id}] {self.message}"
