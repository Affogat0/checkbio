"""
Example file containing the kinds of mistakes AI coding assistants commonly
introduce in bioinformatics scripts. Run `biolint examples/bad_example.py`
to see biolint catch these.
"""

from Bio import SeqIO
import pysam

# BL010: Bio.Alphabet was removed in Biopython 1.78
from Bio.Alphabet import generic_dna


def load_reads(fastq_path):
    # BL011: hallucinated format string, should be "fastq" or "fastq-sanger"
    records = SeqIO.parse(fastq_path, "fastq-generic")
    return list(records)


def open_bam(bam_path):
    # BL020: invalid pysam mode string
    return pysam.AlignmentFile(bam_path, "read")


def get_coverage(bam_path, chrom, start, end):
    bam = pysam.AlignmentFile(bam_path, "rb")
    # BL021: fetching without confirming an index exists
    return bam.fetch(chrom, start, end)


def compare_bed_to_vcf(bed_start, vcf_pos):
    # BL001: comparing 0-based BED coordinate directly to 1-based VCF
    # coordinate with no offset adjustment
    if bed_start == vcf_pos:
        return True
    return False


def get_base(sequence, start, end):
    # BL002: slicing with genomic start/end without confirming coordinate
    # convention
    return sequence[start:end]
