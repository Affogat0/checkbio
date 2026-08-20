"""A clean file that should trigger zero biolint findings."""

from Bio import SeqIO
import pysam
import os


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
