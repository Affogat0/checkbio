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


# Variable-name fragments that suggest a 1-based coordinate source
# (VCF/GFF/SAM/GTF) — shared by loc_rules (LOC001) and pys_rules (PYS003),
# which both need to recognize the same naming convention. Previously
# defined identically in both files; kept in one place so a change (e.g.
# fixing a substring collision) only has to be made once.
ONE_BASED_HINTS = {"vcf", "gff", "gtf", "sam", "one_based", "1based"}


def name_hints(name: str, hints: set) -> bool:
    """True if `name` (case-insensitively) contains any of `hints` as a
    substring. This is a blunt, intentionally simple heuristic — see the
    README's Known Limitations for the false-positive/false-negative
    trade-offs that come with it (e.g. "sam" also matches "sample")."""
    lowered = name.lower()
    return any(h in lowered for h in hints)
