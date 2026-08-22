# checkbio

A static analysis linter that catches **bioinformatics-specific mistakes**
in Python code — especially the kind AI coding assistants (Claude, Codex,
ChatGPT, Copilot, etc.) tend to silently introduce.

It does **not** try to be a general-purpose linter. Use `flake8`/`pylint`/
`ruff` for that. `checkbio` only checks for domain-specific correctness
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
to be wrong. `checkbio` exists to catch the specific patterns that keep
showing up.

## Install

```bash
pip install checkbio
```

### From source

```bash
git clone https://github.com/Affogat0/checkbio.git
cd checkbio
pip install -e .
```

## Usage

```bash
checkbio script.py
checkbio pipeline/*.py
```

Example output:

```
examples/bad_example.py
  12:0  [BIO001] 'Bio.Alphabet' was removed in Biopython 1.78 (2020)...
  15:11 [REF001] Found an hg19/GRCh37 reference and an hg38/GRCh38 reference in the same file...
  19:13 [LOC003] Found chromosome name 'chr1' and 'MT' in the same file...
  25:14 [BIO002] 'fastq-generic' is not a recognized Bio.SeqIO format string...
  31:11 [PYS001] 'read' is not a valid pysam.AlignmentFile mode string...
  37:11 [PYS003] '.fetch()' called with argument(s) ['vcf_pos'] that look 1-based...
  43:7  [LOC001] Comparing a 0-based coordinate directly against a 1-based coordinate...
  52:11 [TAB001] Merge key(s) ['position'] include a genomic position column but no chromosome column...

checkbio: 3 error(s), 5 warning(s)
```

### As a pre-commit hook

Add to your `.pre-commit-config.yaml` (note: the `v0.1.0`/`v0.2.0` tags in this repo's history predate the project's rename from `biolint` and point at a different package — use `v0.3.0` or later):

'''
repos:
  - repo: https://github.com/Affogat0/checkbio
    rev: v0.3.0
    hooks:
      - id: checkbio
'''

## Rule families

Rules are grouped into families by ID prefix, following the same pattern
as tools like ESLint/Ruff. This will grow well past the current rule set — the prefix
tells you at a glance what domain a warning belongs to without needing to
memorize individual rule numbers.

| Prefix | Family | Status |
|--------|--------|--------|
| `LOC` | Genomic coordinates | implemented |
| `REF` | Reference genome builds | implemented |
| `BIO` | Biopython-specific | implemented |
| `PYS` | pysam-specific | implemented |
| `TAB` | Genomic tables (pandas) | implemented |
| `REP` | Reproducibility / robustness (e.g. unparseable file) | implemented |
| `FMT` | General file format mismatches | planned |
| `VCF` | Variant (VCF) processing | planned |
| `SEQ` | Sequence handling (translation frames, ambiguous bases) | planned |
| `SAM` | SAM/BAM/CRAM-specific (beyond pysam wrapper calls) | planned |
| `ID` | Biological identifiers (Ensembl versions, gene symbols) | planned |
| `NET` | NCBI / remote API etiquette | planned |
| `AI` | Suspicious AI-generated-code patterns (cross-cutting) | planned |

## Rules (v0.3)

| ID | Severity | What it catches |
|----|----------|------------------|
| LOC001 | warning | Comparing a 0-based (BED-style) coordinate directly against a 1-based (VCF/GFF/SAM-style) coordinate with no visible offset |
| LOC003 | warning | A file uses both chr-prefixed and bare chromosome names (or `chrM`/`MT`) — a common silent join/comparison failure |
| REF001 | warning | A file references both hg19/GRCh37 and hg38/GRCh38 resources — coordinates from the two builds aren't interchangeable |
| BIO001 | error | Import of `Bio.Alphabet`, removed in Biopython 1.78 |
| BIO002 | error | `SeqIO`/`AlignIO` call with a format string that isn't a real Biopython format |
| PYS001 | error | `pysam.AlignmentFile()` opened with an invalid mode string |
| PYS003 | warning | `.fetch()`/`.pileup()` called with a start/end argument that looks 1-based, with no visible `-1` conversion — pysam expects 0-based, half-open coordinates |
| TAB001 | warning | `DataFrame.merge()` keyed on a genomic position column with no accompanying chromosome column |
| REP000 | error | The file itself couldn't be parsed (syntax error) |

**Known limitations (v0.3):**
- **LOC003** and **REF001** are file-level heuristics based on string
  literals — they won't catch mismatches that only appear via runtime
  values (e.g. a chromosome name read from a config file at runtime),
  and a deliberate liftover step will trigger a (correct, but
  not-actually-a-bug) flag.
- **TAB001** only inspects string literal merge keys — it won't catch
  keys built dynamically (e.g. a list constructed in a variable before
  being passed to `on=`).
- **PYS003**, **TAB001**, and (partially) **LOC001** now require a local
  variable-provenance tracker to confirm what an object actually is
  (a `pysam.AlignmentFile`, a pandas `DataFrame`) before firing, instead
  of matching on a method name alone. Tracking is scoped to one function
  (or module top level) and recognizes three explicit patterns: direct
  `variable = call(...)` assignment, a `with call(...) as variable:`
  binding, and an explicit parameter type annotation
  (`def f(bam: pysam.AlignmentFile)`). It does **not** follow for-loop
  targets (`for record in vcf_file:`) or a value across a function-call
  boundary, and it deliberately never infers a type from a parameter's
  *name* or how it's used in the body — only an explicit annotation
  counts. In practice this means an unannotated parameter (`def f(bam)`,
  with no type hint) is reported as "unknown," and those three rules stay
  silent on it rather than guessing. This trades real false negatives for
  eliminating the false positives found in the v0.1 audit — see the
  rules' own docstrings in `checkbio/rules/` and `checkbio/provenance.py`
  for the reasoning.
- **LOC001**'s and **PYS003**'s fallback (when provenance can't resolve
  anything) is still plain substring matching on variable/argument names
  against a fixed hint list (`vcf`, `gff`, `sam`, `bed`, ...). This means
  two known, accepted trade-offs: (1) it will miss a real bug between
  two generically-named coordinates (`start`/`position`) that don't
  happen to reference a format in their name, and (2) it can
  false-positive on an unrelated variable whose name merely contains a
  hint as a substring — `sample_start` matches the `sam` hint, for
  example. This was flagged in review and deliberately not "fixed" by
  making the matching smarter (e.g. whole-word matching breaks the
  intentional `pybed`-inside-`pybedtools` partial match some of these
  hints rely on); it's left as a known, name-heuristic limitation rather
  than a hidden one.

## Roadmap

- `VCF` family: multi-allelic assumptions, genotype/INFO field presence,
  variant normalization before comparison
- `SEQ` family: translation frame mistakes, ambiguous base (IUPAC)
  assumptions, sequence-type confusion (protein vs. nucleotide)
- `ID` family: Ensembl ID version suffix mismatches, gene symbol vs.
  stable ID joins, species mismatches
- `NET` family: NCBI/Entrez rate limiting, missing email/API key,
  retry/backoff on remote calls
- File-extension vs. parser-library mismatch detection (e.g. calling a
  FASTA parser on a `.vcf` path)
- GitHub Action for CI-time checking on pull requests
- VS Code extension for real-time inline flagging

## Contributing

This project exists to catch real, recurring mistakes — if you've hit a
bioinformatics-specific bug that an AI coding assistant introduced (or that
you've seen a colleague hit), please open an issue describing it. Concrete
before/after code examples are the most useful thing you can contribute.

## License

MIT
