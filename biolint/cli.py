"""
Command-line entry point.

Usage:
    biolint script.py
    biolint script1.py script2.py
    biolint mypipeline/*.py
"""

import argparse
import sys

from .checker import check_file


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="biolint",
        description=(
            "Static analysis for bioinformatics-specific mistakes in "
            "Python code — especially the kind AI coding assistants "
            "silently introduce (coordinate bugs, hallucinated "
            "Biopython/pysam API calls, format mismatches)."
        ),
    )
    parser.add_argument("files", nargs="+", help="Python file(s) to check")
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit with a non-zero status even if only warnings (no "
        "errors) were found. Useful for pre-commit/CI enforcement.",
    )
    args = parser.parse_args(argv)

    total_errors = 0
    total_warnings = 0

    for filepath in args.files:
        findings = check_file(filepath)
        if not findings:
            continue
        print(f"\n{filepath}")
        for f in findings:
            print(f"  {f}")
            if f.severity == "error":
                total_errors += 1
            else:
                total_warnings += 1

    if total_errors or total_warnings:
        print(
            f"\nbiolint: {total_errors} error(s), {total_warnings} warning(s)"
        )
    else:
        print("biolint: no issues found")

    if total_errors > 0:
        return 1
    if total_warnings > 0 and args.fail_on_warning:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
