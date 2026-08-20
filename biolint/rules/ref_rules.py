"""
Reference genome build rules.

Mixing hg19/GRCh37 and hg38/GRCh38 resources in the same analysis is one of
the most common — and most silent — sources of wrong results in genomics.
Coordinates from one build simply don't mean the same thing in the other,
and nothing crashes when you mix them; you just get confidently wrong
answers. AI coding assistants have no way to know which build a given file
path or URL is supposed to be, so they happily combine them if the prompt
doesn't explicitly say otherwise.
"""

import re
import ast
from . import Finding

HG19_PATTERN = re.compile(r"hg19|grch37", re.IGNORECASE)
HG38_PATTERN = re.compile(r"hg38|grch38", re.IGNORECASE)


def check(tree: ast.AST, source_lines: list) -> list:
    # REF001: a file-level heuristic — if string constants (paths, URLs,
    # filenames) referencing both hg19/GRCh37 and hg38/GRCh38 appear in the
    # same file, that's very likely two different reference builds being
    # used together, whether intentionally (a liftover step, which is fine)
    # or accidentally (which silently corrupts every coordinate downstream).
    hg19_hits = []
    hg38_hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if HG19_PATTERN.search(node.value):
                hg19_hits.append((node.value, node.lineno, node.col_offset))
            if HG38_PATTERN.search(node.value):
                hg38_hits.append((node.value, node.lineno, node.col_offset))

    if hg19_hits and hg38_hits:
        example_19, line19, col19 = hg19_hits[0]
        example_38, line38, _ = hg38_hits[0]
        return [
            Finding(
                line=line19,
                col=col19,
                rule_id="REF001",
                message=(
                    f"Found an hg19/GRCh37 reference ('{example_19}', line "
                    f"{line19}) and an hg38/GRCh38 reference ('{example_38}', "
                    f"line {line38}) in the same file. If this isn't a "
                    "deliberate liftover step, coordinates from these two "
                    "builds are not interchangeable — combining them "
                    "silently produces wrong positions with no error."
                ),
            )
        ]
    return []
