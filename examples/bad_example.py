"""
Example file containing the kinds of mistakes AI coding assistants commonly
introduce in bioinformatics scripts. Run `checkbio examples/bad_example.py`
to see checkbio catch these.
"""

from Bio import SeqIO
import pysam
import pandas as pd

# BIO001: Bio.Alphabet was removed in Biopython 1.78
from Bio.Alphabet import generic_dna

# REF001: mixing hg19 and hg38 reference paths in the same file
REF_HG19 = "/data/reference/hg19/genome.fa"
REF_HG38 = "/data/reference/hg38/genome.fa"

# LOC003: chromosome naming mismatch (chr-prefixed vs. bare, MT vs chrM)
UCSC_CHROM = "chr1"
ENSEMBL_MT = "MT"


def load_reads(fastq_path):
    # BIO002: hallucinated format string, should be "fastq" or "fastq-sanger"
    records = SeqIO.parse(fastq_path, "fastq-generic")
    return list(records)


def open_bam(bam_path):
    # PYS001: invalid pysam mode string
    return pysam.AlignmentFile(bam_path, "read")


def get_coverage_from_vcf_pos(bam_path, chrom, vcf_pos, end):
    bam = pysam.AlignmentFile(bam_path, "rb")
    # PYS003: vcf_pos is 1-based, fetch() needs 0-based — missing -1
    return bam.fetch(chrom, vcf_pos, end)


def compare_bed_to_vcf(bed_start, vcf_pos):
    # LOC001: comparing 0-based BED coordinate directly to 1-based VCF
    # coordinate with no offset adjustment
    if bed_start == vcf_pos:
        return True
    return False


def merge_variant_tables(variants_path, annotations_path):
    df1 = pd.read_csv(variants_path)
    df2 = pd.read_csv(annotations_path)
    # TAB001: merging genomic tables on position only, no chromosome column
    return df1.merge(df2, on="position")
