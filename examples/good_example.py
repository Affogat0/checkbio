"""A clean file — should trigger zero checkbio findings other than the
unavoidable PYS002 reminder (fetch() always needs an index; checkbio can't
verify the guard actually runs before the call without real data-flow
analysis, see the README's known limitations)."""

import subprocess
from Bio import SeqIO
import pysam
import os

REF_HG38 = "/data/reference/hg38/genome.fa"
CHROM = "chr1"


def load_reads(fastq_path):
    records = SeqIO.parse(fastq_path, "fastq")
    return list(records)


def open_bam_readonly(bam_path):
    return pysam.AlignmentFile(bam_path, "rb")


def get_coverage(bam_path, chrom, start, end):
    if not os.path.exists(bam_path + ".bai"):
        raise FileNotFoundError("BAM index not found, run samtools index first")
    bam = pysam.AlignmentFile(bam_path, "rb")
    return bam.fetch(chrom, start, end)


def get_coverage_from_vcf_pos(bam_path, chrom, vcf_pos, end):
    bam = pysam.AlignmentFile(bam_path, "rb")
    # correctly converts the 1-based VCF position to 0-based before fetch()
    return bam.fetch(chrom, vcf_pos - 1, end)


def merge_variant_tables(df1, df2):
    return df1.merge(df2, on=["chrom", "position"])


def sort_bam(bam_path):
    subprocess.run(
        ["samtools", "sort", bam_path, "-o", "sorted.bam"], check=True
    )
