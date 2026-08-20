# biolint

A static analysis linter that catches **bioinformatics-specific mistakes**
in Python code — especially the kind AI coding assistants (Claude, Codex,
ChatGPT, Copilot, etc.) tend to silently introduce.

It does **not** try to be a general-purpose linter. Use `flake8`/`pylint`/
`ruff` for that. `biolint` only checks for domain-specific correctness
issues that a general linter has no way of knowing about: genomic
coordinate bugs, hallucinated or deprecated Biopython/pysam API usage, and
file format mismatches.

## Why

AI coding assistants are very good at producing plausible-looking
bioinformatics code, and just as good at confidently getting
domain-specific details wrong: mixing 0-based and 1-based coordinate
systems, calling a Biopython API that was removed years ago, passing an
invalid mode string to `pysam.AlignmentFile`. These bugs are usually
silent — the code runs, sometimes even produces output, and just happens
to be wrong. `biolint` exists to catch the specific patterns that keep
showing up.

## Install

```bash
pip install biolint
```

(Not yet published to PyPI — for now, install from source: see below.)

### From source

```bash
git clone https://github.com/YOUR_USERNAME/biolint.git
cd biolint
pip install -e .
```

## Usage

```bash
biolint script.py
biolint pipeline/*.py
```

Example output:

```
examples/bad_example.py
  11:0  [BL010] 'Bio.Alphabet' was removed in Biopython 1.78 (2020)...
  16:14 [BL011] 'fastq-generic' is not a recognized Bio.SeqIO format string...
  22:11 [BL020] 'read' is not a valid pysam.AlignmentFile mode string...
  28:11 [BL021] '.fetch()' requires an index file (.bai/.csi/.crai)...
  34:7  [BL001] Comparing a 0-based coordinate directly against a 1-based coordinate...
  42:11 [BL002] Slicing with genomic-position-like variable(s) ['start', 'end']...

biolint: 3 error(s), 3 warning(s)
```

### As a pre-commit hook

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Affogat0/biolint
    rev: v0.1.0
    hooks:
      - id: biolint
```

## Rules (v0.1)

| ID | Category | Severity | What it catches |
|----|----------|----------|------------------|
| BL001 | Coordinates | warning | Comparing a 0-based (BED-style) coordinate directly against a 1-based (VCF/GFF/SAM-style) coordinate with no visible offset |
| BL002 | Coordinates | warning | Slicing a sequence with a genomic start/end-like variable, no nearby indication of coordinate convention |
| BL010 | Biopython | error | Import of `Bio.Alphabet`, removed in Biopython 1.78 |
| BL011 | Biopython | error | `SeqIO`/`AlignIO` call with a format string that isn't a real Biopython format |
| BL020 | pysam | error | `pysam.AlignmentFile()` opened with an invalid mode string |
| BL021 | pysam | warning | `.fetch()`/`.pileup()` call — reminder that this requires an index file to exist |

**Known limitation (v0.1):** BL021 currently flags *every* `.fetch()`/
`.pileup()` call, even ones that are already correctly guarded by an index
check. Real guard-detection needs data-flow analysis, which is on the
roadmap — for now it's a reminder, not a definitive error, and is scored
as a warning rather than an error for that reason.

## Roadmap

- Data-flow-aware BL021 (stop flagging already-guarded `.fetch()` calls)
- File-extension vs. parser-library mismatch detection (e.g. calling a
  FASTA parser on a `.vcf` path)
- Deprecated/renamed function detection across more libraries
  (scikit-bio, pandas idioms common in bioinformatics scripts)
- GitHub Action for CI-time checking on pull requests
- VS Code extension for real-time inline flagging

## Contributing

This project exists to catch real, recurring mistakes — if you've hit a
bioinformatics-specific bug that an AI coding assistant introduced (or that
you've seen a colleague hit), please open an issue describing it. Concrete
before/after code examples are the most useful thing you can contribute.

## License

MIT
