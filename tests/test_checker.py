from checkbio.checker import check_file
from checkbio.cli import main


def test_missing_file_reported_gracefully(tmp_path):
    missing = tmp_path / "does_not_exist.py"
    findings = check_file(str(missing))
    assert len(findings) == 1
    assert findings[0].rule_id == "REP000"
    assert findings[0].severity == "error"


def test_undecodable_file_reported_gracefully(tmp_path):
    bad = tmp_path / "bad_encoding.py"
    bad.write_bytes(b"\xff\xfe\x00# not valid utf-8\n")
    findings = check_file(str(bad))
    assert len(findings) == 1
    assert findings[0].rule_id == "REP000"


def test_directory_passed_as_file_reported_gracefully(tmp_path):
    findings = check_file(str(tmp_path))
    assert len(findings) == 1
    assert findings[0].rule_id == "REP000"


def test_one_bad_file_does_not_abort_the_whole_cli_run(tmp_path, capsys):
    good = tmp_path / "good.py"
    good.write_text('from Bio.Alphabet import generic_dna\n')
    missing = tmp_path / "missing.py"

    exit_code = main([str(good), str(missing)])

    out = capsys.readouterr().out
    assert "BIO001" in out  # the readable file was still checked
    assert "missing.py" in out  # the unreadable file was reported, not swallowed
    assert exit_code == 1
