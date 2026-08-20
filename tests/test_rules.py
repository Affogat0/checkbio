from biolint.checker import check_source


def rule_ids(findings):
    return {f.rule_id for f in findings}


def test_bio_alphabet_import_flagged():
    src = "from Bio.Alphabet import generic_dna\n"
    findings = check_source(src)
    assert "BL010" in rule_ids(findings)


def test_valid_seqio_format_not_flagged():
    src = 'from Bio import SeqIO\nSeqIO.parse("x.fq", "fastq")\n'
    findings = check_source(src)
    assert "BL011" not in rule_ids(findings)


def test_hallucinated_seqio_format_flagged():
    src = 'from Bio import SeqIO\nSeqIO.parse("x.fq", "fastq-generic")\n'
    findings = check_source(src)
    assert "BL011" in rule_ids(findings)


def test_valid_pysam_mode_not_flagged():
    src = 'import pysam\npysam.AlignmentFile("x.bam", "rb")\n'
    findings = check_source(src)
    assert "BL020" not in rule_ids(findings)


def test_invalid_pysam_mode_flagged():
    src = 'import pysam\npysam.AlignmentFile("x.bam", "read")\n'
    findings = check_source(src)
    assert "BL020" in rule_ids(findings)


def test_fetch_call_flagged():
    src = 'bam.fetch("chr1", 0, 100)\n'
    findings = check_source(src)
    assert "BL021" in rule_ids(findings)


def test_bed_vcf_coordinate_mismatch_flagged():
    src = "if bed_start == vcf_pos:\n    pass\n"
    findings = check_source(src)
    assert "BL001" in rule_ids(findings)


def test_bed_vcf_with_offset_not_flagged():
    src = "if bed_start + 1 == vcf_pos:\n    pass\n"
    findings = check_source(src)
    assert "BL001" not in rule_ids(findings)


def test_genomic_slice_flagged():
    src = "result = sequence[start:end]\n"
    findings = check_source(src)
    assert "BL002" in rule_ids(findings)


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
    assert findings[0].rule_id == "BL000"
