from checkbio.checker import check_source


def rule_ids(findings):
    return {f.rule_id for f in findings}


# --- LOC: coordinate rules ---

def test_bed_vcf_coordinate_mismatch_flagged():
    src = "if bed_start == vcf_pos:\n    pass\n"
    findings = check_source(src)
    assert "LOC001" in rule_ids(findings)


def test_bed_vcf_with_offset_not_flagged():
    src = "if bed_start + 1 == vcf_pos:\n    pass\n"
    findings = check_source(src)
    assert "LOC001" not in rule_ids(findings)


def test_loc001_provenance_confirms_when_names_carry_no_hint():
    # Neither variable name contains a hint substring ("vcf"/"bed"/etc) —
    # this can only fire via the provenance tracker confirming their
    # constructors (pybedtools.BedTool / pysam.VariantFile).
    src = (
        "import pysam\n"
        "import pybedtools\n"
        "def f(bed_path, vcf_path):\n"
        "    left_reader = pybedtools.BedTool(bed_path)\n"
        "    right_reader = pysam.VariantFile(vcf_path)\n"
        "    if left_reader == right_reader:\n"
        "        pass\n"
    )
    findings = check_source(src)
    assert "LOC001" in rule_ids(findings)


def test_chromosome_naming_mismatch_flagged():
    src = 'a = "chr1"\nb = "MT"\n'
    findings = check_source(src)
    assert "LOC003" in rule_ids(findings)


def test_chromosome_naming_consistent_not_flagged():
    src = 'a = "chr1"\nb = "chrM"\n'
    findings = check_source(src)
    assert "LOC003" not in rule_ids(findings)


# --- BIO: Biopython rules ---

def test_bio_alphabet_import_flagged():
    src = "from Bio.Alphabet import generic_dna\n"
    findings = check_source(src)
    assert "BIO001" in rule_ids(findings)


def test_valid_seqio_format_not_flagged():
    src = 'from Bio import SeqIO\nSeqIO.parse("x.fq", "fastq")\n'
    findings = check_source(src)
    assert "BIO002" not in rule_ids(findings)


def test_hallucinated_seqio_format_flagged():
    src = 'from Bio import SeqIO\nSeqIO.parse("x.fq", "fastq-generic")\n'
    findings = check_source(src)
    assert "BIO002" in rule_ids(findings)


def test_seqio_write_handle_not_mistaken_for_format():
    src = 'from Bio import SeqIO\nSeqIO.write(records, "aligned_output.fasta", "fasta")\n'
    findings = check_source(src)
    assert "BIO002" not in rule_ids(findings)


def test_seqio_write_hallucinated_format_flagged():
    src = 'from Bio import SeqIO\nSeqIO.write(records, "out.fq", "fastq-generic")\n'
    findings = check_source(src)
    assert "BIO002" in rule_ids(findings)


def test_alignio_convert_checks_both_formats():
    src = (
        'from Bio import AlignIO\n'
        'AlignIO.convert("in.aln", "clustal", "out.phy", "phylip-generic")\n'
    )
    findings = check_source(src)
    assert "BIO002" in rule_ids(findings)


def test_alignio_convert_valid_formats_not_flagged():
    src = (
        'from Bio import AlignIO\n'
        'AlignIO.convert("in.aln", "clustal", "out.phy", "phylip-relaxed")\n'
    )
    findings = check_source(src)
    assert "BIO002" not in rule_ids(findings)


def test_alignio_phylip_relaxed_not_flagged():
    src = 'from Bio import AlignIO\nAlignIO.parse("aln.phy", "phylip-relaxed")\n'
    findings = check_source(src)
    assert "BIO002" not in rule_ids(findings)


def test_seqio_pdb_seqres_not_flagged():
    src = 'from Bio import SeqIO\nSeqIO.parse("structure.pdb", "pdb-seqres")\n'
    findings = check_source(src)
    assert "BIO002" not in rule_ids(findings)


# --- PYS: pysam rules ---

def test_valid_pysam_mode_not_flagged():
    src = 'import pysam\npysam.AlignmentFile("x.bam", "rb")\n'
    findings = check_source(src)
    assert "PYS001" not in rule_ids(findings)


def test_invalid_pysam_mode_flagged():
    src = 'import pysam\npysam.AlignmentFile("x.bam", "read")\n'
    findings = check_source(src)
    assert "PYS001" in rule_ids(findings)


def test_fetch_one_based_arg_flagged():
    src = (
        "import pysam\n"
        "def f(bam_path, chrom, vcf_pos, end):\n"
        '    bam = pysam.AlignmentFile(bam_path, "rb")\n'
        "    bam.fetch(chrom, vcf_pos, end)\n"
    )
    findings = check_source(src)
    assert "PYS003" in rule_ids(findings)


def test_fetch_one_based_arg_with_offset_not_flagged():
    src = (
        "import pysam\n"
        "def f(bam_path, chrom, vcf_pos, end):\n"
        '    bam = pysam.AlignmentFile(bam_path, "rb")\n'
        "    bam.fetch(chrom, vcf_pos - 1, end)\n"
    )
    findings = check_source(src)
    assert "PYS003" not in rule_ids(findings)


def test_fetch_on_unconfirmed_receiver_not_flagged():
    # "bam" is a bare parameter here — never constructed in this scope, so
    # its provenance is unknown. PYS003 now requires a confirmed
    # pysam.AlignmentFile receiver, so this stays silent even though the
    # argument name looks 1-based.
    src = "def f(bam, chrom, vcf_pos, end):\n    bam.fetch(chrom, vcf_pos, end)\n"
    findings = check_source(src)
    assert "PYS003" not in rule_ids(findings)


def test_fetch_on_unrelated_object_not_flagged():
    # Same method name as pysam's fetch(), but constructed from something
    # checkbio doesn't recognize as pysam — exactly the false positive
    # (any object with a .fetch() method) the provenance rewiring targets.
    src = (
        "def f(vcf_pos, chrom, end):\n"
        "    cfg = RemoteConfig()\n"
        "    cfg.fetch(chrom, vcf_pos, end)\n"
    )
    findings = check_source(src)
    assert "PYS003" not in rule_ids(findings)


def test_fetch_via_with_as_flagged():
    # The idiomatic way to open a pysam file — `with ... as bam:` — must
    # be recognized just as reliably as plain assignment.
    src = (
        "import pysam\n"
        "def check_coverage(bam_path, chrom, vcf_pos, end):\n"
        '    with pysam.AlignmentFile(bam_path, "rb") as bam:\n'
        "        return bam.fetch(chrom, vcf_pos, end)\n"
    )
    findings = check_source(src)
    assert "PYS003" in rule_ids(findings)


def test_fetch_on_annotated_parameter_flagged():
    # An explicit type annotation on a parameter is the author's own
    # stated claim about its type — not a guess — so it's honored.
    src = (
        "import pysam\n"
        "def check_coverage(bam: pysam.AlignmentFile, chrom, vcf_pos, end):\n"
        "    return bam.fetch(chrom, vcf_pos, end)\n"
    )
    findings = check_source(src)
    assert "PYS003" in rule_ids(findings)


def test_fetch_on_unannotated_parameter_still_not_flagged():
    # Same shape as the annotated case above, minus the annotation — this
    # is the boundary checkbio intentionally does not cross: no inference
    # from the parameter's name or how it's used in the body.
    src = (
        "def check_coverage(bam, chrom, vcf_pos, end):\n"
        "    return bam.fetch(chrom, vcf_pos, end)\n"
    )
    findings = check_source(src)
    assert "PYS003" not in rule_ids(findings)


# --- REF: reference genome build rules ---

def test_genome_build_mismatch_flagged():
    src = (
        'ref19 = "/data/hg19/genome.fa"\n'
        'ref38 = "/data/hg38/genome.fa"\n'
    )
    findings = check_source(src)
    assert "REF001" in rule_ids(findings)


def test_single_genome_build_not_flagged():
    src = 'ref = "/data/hg38/genome.fa"\nother = "/data/hg38/annotation.gtf"\n'
    findings = check_source(src)
    assert "REF001" not in rule_ids(findings)


# --- TAB: pandas genomic table rules ---

def test_merge_on_position_only_flagged():
    src = (
        "import pandas as pd\n"
        "def f(path1, path2):\n"
        "    df1 = pd.read_csv(path1)\n"
        "    df2 = pd.read_csv(path2)\n"
        '    result = df1.merge(df2, on="position")\n'
    )
    findings = check_source(src)
    assert "TAB001" in rule_ids(findings)


def test_merge_on_chrom_and_position_not_flagged():
    src = (
        "import pandas as pd\n"
        "def f(path1, path2):\n"
        "    df1 = pd.read_csv(path1)\n"
        "    df2 = pd.read_csv(path2)\n"
        '    result = df1.merge(df2, on=["chrom", "position"])\n'
    )
    findings = check_source(src)
    assert "TAB001" not in rule_ids(findings)


def test_module_level_pd_merge_call_flagged():
    # pd.merge(df1, df2, ...) — the module-level function form, not the
    # .merge() method form — should be recognized just as reliably.
    src = (
        "import pandas as pd\n"
        "def f(df1, df2):\n"
        '    return pd.merge(df1, df2, on="position")\n'
    )
    findings = check_source(src)
    assert "TAB001" in rule_ids(findings)


def test_merge_on_unconfirmed_receiver_not_flagged():
    # df1/df2 are bare parameters here, never constructed in this scope —
    # provenance is unknown, so TAB001 stays silent.
    src = 'def f(df1, df2):\n    return df1.merge(df2, on="position")\n'
    findings = check_source(src)
    assert "TAB001" not in rule_ids(findings)


def test_merge_on_unrelated_object_not_flagged():
    # Same method name, but the receiver isn't a pandas DataFrame at all —
    # exactly the false positive (any object with a .merge() method) the
    # provenance rewiring targets.
    src = (
        "def f(other):\n"
        "    builder = ConfigBuilder()\n"
        '    return builder.merge(other, on="position")\n'
    )
    findings = check_source(src)
    assert "TAB001" not in rule_ids(findings)


# --- General ---

def test_clean_file_produces_minimal_findings():
    src = (
        'from Bio import SeqIO\n'
        'SeqIO.parse("x.fq", "fastq")\n'
        'x = [1, 2, 3]\n'
        'y = sum(x)\n'
    )
    findings = check_source(src)
    assert findings == []


def test_syntax_error_reported_gracefully():
    src = "def broken(:\n"
    findings = check_source(src)
    assert len(findings) == 1
    assert findings[0].rule_id == "REP000"
