from biolint.checker import check_source


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


def test_genomic_slice_flagged():
    src = "result = sequence[start:end]\n"
    findings = check_source(src)
    assert "LOC002" in rule_ids(findings)


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


# --- PYS: pysam rules ---

def test_valid_pysam_mode_not_flagged():
    src = 'import pysam\npysam.AlignmentFile("x.bam", "rb")\n'
    findings = check_source(src)
    assert "PYS001" not in rule_ids(findings)


def test_invalid_pysam_mode_flagged():
    src = 'import pysam\npysam.AlignmentFile("x.bam", "read")\n'
    findings = check_source(src)
    assert "PYS001" in rule_ids(findings)


def test_fetch_call_flagged():
    src = 'bam.fetch("chr1", 0, 100)\n'
    findings = check_source(src)
    assert "PYS002" in rule_ids(findings)


def test_fetch_one_based_arg_flagged():
    src = "bam.fetch(chrom, vcf_pos, end)\n"
    findings = check_source(src)
    assert "PYS003" in rule_ids(findings)


def test_fetch_one_based_arg_with_offset_not_flagged():
    src = "bam.fetch(chrom, vcf_pos - 1, end)\n"
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
    src = 'result = df1.merge(df2, on="position")\n'
    findings = check_source(src)
    assert "TAB001" in rule_ids(findings)


def test_merge_on_chrom_and_position_not_flagged():
    src = 'result = df1.merge(df2, on=["chrom", "position"])\n'
    findings = check_source(src)
    assert "TAB001" not in rule_ids(findings)


# --- CLI: subprocess bioinformatics tool rules ---

def test_subprocess_run_unchecked_flagged():
    src = 'subprocess.run(["samtools", "sort", bam_path])\n'
    findings = check_source(src)
    assert "CLI001" in rule_ids(findings)


def test_subprocess_run_with_check_true_not_flagged():
    src = 'subprocess.run(["samtools", "sort", bam_path], check=True)\n'
    findings = check_source(src)
    assert "CLI001" not in rule_ids(findings)


def test_subprocess_call_bio_tool_flagged():
    src = 'subprocess.call(["bcftools", "view", vcf_path])\n'
    findings = check_source(src)
    assert "CLI001" in rule_ids(findings)


def test_subprocess_non_bio_tool_not_flagged():
    src = 'subprocess.run(["ls", "-la"])\n'
    findings = check_source(src)
    assert "CLI001" not in rule_ids(findings)


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
