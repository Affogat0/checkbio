"""
biolint: a static analysis linter that catches common bioinformatics-specific
mistakes in Python code, especially the kind that AI coding assistants
(Claude, Codex, ChatGPT, etc.) tend to silently introduce.

It does NOT try to be a general-purpose linter (use flake8/pylint for that).
It only checks for domain-specific correctness issues: coordinate system
bugs, hallucinated or deprecated Biopython/pysam API usage, and file format
mismatches.
"""

__version__ = "0.1.0"

from .checker import check_file, check_source  # noqa: F401
