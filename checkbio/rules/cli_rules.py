"""
External bioinformatics command-line tool rules.

Bioinformatics Python code is routinely a thin wrapper around command-line
tools (samtools, bcftools, bedtools, bwa, ...) invoked via subprocess. AI
generated pipelines very often chain these calls assuming every command
succeeds, then immediately consume the output file — if the tool actually
failed (missing input, bad flags, disk full), the next step reads a
missing, empty, or stale file and fails somewhere far away from the real
cause, or worse, silently produces wrong output.
"""

import ast
from . import Finding

KNOWN_BIO_TOOLS = {
    "samtools", "bcftools", "bedtools", "bwa", "bwa-mem2", "bowtie2",
    "star", "hisat2", "salmon", "kallisto", "minimap2", "gatk",
    "picard", "vcftools", "tabix", "bgzip", "blastn", "blastp", "blastx",
    "plink", "plink2", "seqkit", "fastqc", "multiqc", "cutadapt",
    "trimmomatic", "freebayes",
}


def _first_string_from_command_list(node) -> str | None:
    """Given the first positional arg to subprocess.run/call, extract the
    command name if it's a list/tuple of string constants (the normal,
    safe way to call subprocess)."""
    if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
        first = node.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            # command may be a full path, e.g. "/usr/bin/samtools"
            return first.value.rsplit("/", 1)[-1]
    return None


class _Visitor(ast.NodeVisitor):
    def __init__(self):
        self.findings: list[Finding] = []

    def visit_Call(self, node: ast.Call):
        func = node.func

        is_subprocess_call = (
            isinstance(func, ast.Attribute)
            and func.attr in {"run", "call"}
            and isinstance(func.value, ast.Name)
            and func.value.id in {"subprocess", "sp"}
        ) or (isinstance(func, ast.Name) and func.id in {"run", "call"})

        if is_subprocess_call and node.args:
            tool_name = _first_string_from_command_list(node.args[0])
            if tool_name in KNOWN_BIO_TOOLS:
                has_check_true = any(
                    kw.arg == "check"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                    for kw in node.keywords
                )
                # subprocess.call() has no `check` parameter at all — its
                # return code must always be inspected manually, so it's
                # flagged unconditionally. subprocess.run() is only
                # flagged if check=True is missing.
                is_call_variant = isinstance(func, ast.Attribute) and func.attr == "call" \
                    or (isinstance(func, ast.Name) and func.id == "call")

                if is_call_variant or not has_check_true:
                    self.findings.append(
                        Finding(
                            line=node.lineno,
                            col=node.col_offset,
                            rule_id="CLI001",
                            message=(
                                f"Call to '{tool_name}' via subprocess "
                                "does not verify the command succeeded "
                                "(no check=True, and no return-code check "
                                "visible). If this command fails, the "
                                "failure is silent and any downstream step "
                                "consuming its output will operate on "
                                "missing, empty, or stale data."
                            ),
                            severity="warning",
                        )
                    )

        self.generic_visit(node)


def check(tree: ast.AST, source_lines: list) -> list:
    visitor = _Visitor()
    visitor.visit(tree)
    return visitor.findings
