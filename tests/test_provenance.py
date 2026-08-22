import ast

from checkbio.provenance import build_provenance, build_parent_map, enclosing_scope


def _function_and_module(src: str):
    """Parse `src`, which must contain exactly one top-level function, and
    return (function_def_node, module_node)."""
    tree = ast.parse(src)
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    return func, tree


def _call_line(src: str, marker: str) -> int:
    """Line number of the (first) line containing `marker`."""
    for i, line in enumerate(src.splitlines(), start=1):
        if marker in line:
            return i
    raise ValueError(f"marker {marker!r} not found")


# --- simple construction ---

def test_pysam_alignment_file_tracked():
    src = (
        "import pysam\n"
        "def f(path):\n"
        '    bam = pysam.AlignmentFile(path, "rb")\n'
        "    return bam.fetch()\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "bam.fetch()")
    assert prov.type_of("bam", at_line) == "pysam.AlignmentFile"


def test_pandas_read_csv_tracked():
    src = (
        "import pandas as pd\n"
        "def f(path):\n"
        "    df = pd.read_csv(path)\n"
        "    return df.merge(df)\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "df.merge(df)")
    assert prov.type_of("df", at_line) == "pandas.DataFrame"


def test_merge_result_tracked_as_dataframe():
    src = (
        "def f(df1, df2):\n"
        '    merged = df1.merge(df2, on="chrom")\n'
        "    return merged.head()\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "merged.head()")
    assert prov.type_of("merged", at_line) == "pandas.DataFrame"


# --- with...as bindings ---

def test_with_as_binding_tracked():
    src = (
        "import pysam\n"
        "def f(path):\n"
        '    with pysam.AlignmentFile(path, "rb") as bam:\n'
        "        return bam.fetch()\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "bam.fetch()")
    assert prov.type_of("bam", at_line) == "pysam.AlignmentFile"


def test_with_as_binding_survives_after_the_with_block():
    # Python doesn't block-scope `with`, so the binding is still visible
    # (and still typed) for the rest of the function after it exits.
    src = (
        "import pysam\n"
        "def f(path):\n"
        '    with pysam.AlignmentFile(path, "rb") as bam:\n'
        "        pass\n"
        "    return bam.fetch()\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "return bam.fetch()")
    assert prov.type_of("bam", at_line) == "pysam.AlignmentFile"


def test_with_as_reassignment_after_block_overrides():
    src = (
        "import pysam\n"
        "def f(path):\n"
        '    with pysam.AlignmentFile(path, "rb") as bam:\n'
        "        pass\n"
        "    bam = None\n"
        "    return bam\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "return bam")
    assert prov.type_of("bam", at_line) is None


def test_with_as_unrecognized_call_is_unknown():
    src = (
        "def f(path):\n"
        "    with open(path) as fh:\n"
        "        return fh.read()\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "fh.read()")
    assert prov.type_of("fh", at_line) is None


# --- parameter type annotations ---

def test_annotated_parameter_tracked():
    src = (
        "import pysam\n"
        "def f(bam: pysam.AlignmentFile, chrom):\n"
        "    return bam.fetch(chrom)\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "bam.fetch(chrom)")
    assert prov.type_of("bam", at_line) == "pysam.AlignmentFile"


def test_annotated_parameter_with_aliased_import_tracked():
    src = (
        "import pysam as ps\n"
        "def f(bam: ps.AlignmentFile):\n"
        "    return bam.fetch()\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "bam.fetch()")
    assert prov.type_of("bam", at_line) == "pysam.AlignmentFile"


def test_annotated_parameter_bare_name_tracked():
    # from pysam import AlignmentFile; def f(bam: AlignmentFile): ...
    src = (
        "from pysam import AlignmentFile\n"
        "def f(bam: AlignmentFile):\n"
        "    return bam.fetch()\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "bam.fetch()")
    assert prov.type_of("bam", at_line) == "pysam.AlignmentFile"


def test_annotated_parameter_forward_ref_string_tracked():
    src = (
        "import pysam\n"
        'def f(bam: "pysam.AlignmentFile"):\n'
        "    return bam.fetch()\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "bam.fetch()")
    assert prov.type_of("bam", at_line) == "pysam.AlignmentFile"


def test_unannotated_parameter_still_unknown():
    src = "def f(bam):\n    return bam.fetch()\n"
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "bam.fetch()")
    assert prov.type_of("bam", at_line) is None


def test_annotated_parameter_reassignment_overrides():
    src = (
        "import pysam\n"
        "def f(bam: pysam.AlignmentFile):\n"
        "    bam = None\n"
        "    return bam\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "return bam")
    assert prov.type_of("bam", at_line) is None


def test_unrecognized_type_annotation_is_unknown():
    src = "def f(bam: SomeUnrelatedType):\n    return bam.fetch()\n"
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "bam.fetch()")
    assert prov.type_of("bam", at_line) is None


# --- aliased imports ---

def test_aliased_pysam_import_tracked():
    src = (
        "import pysam as ps\n"
        "def f(path):\n"
        '    bam = ps.AlignmentFile(path, "rb")\n'
        "    return bam.fetch()\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "bam.fetch()")
    assert prov.type_of("bam", at_line) == "pysam.AlignmentFile"


def test_aliased_pandas_import_tracked():
    src = (
        "import pandas as pd\n"
        "def f(path):\n"
        "    table = pd.read_csv(path)\n"
        "    return table\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "return table")
    assert prov.type_of("table", at_line) == "pandas.DataFrame"


# --- reassignment ---

def test_reassignment_later_type_wins_after_that_point():
    src = (
        "import pysam\n"
        "import pandas as pd\n"
        "def f(bam_path, csv_path):\n"
        '    x = pysam.AlignmentFile(bam_path, "rb")\n'
        "    before = x\n"
        "    x = pd.read_csv(csv_path)\n"
        "    after = x\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    before_line = _call_line(src, "before = x")
    after_line = _call_line(src, "after = x")
    assert prov.type_of("x", before_line) == "pysam.AlignmentFile"
    assert prov.type_of("x", after_line) == "pandas.DataFrame"


# --- unknown, don't guess ---

def test_function_parameter_is_unknown():
    src = (
        "def f(bam):\n"
        "    return bam.fetch()\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "bam.fetch()")
    assert prov.type_of("bam", at_line) is None


def test_assignment_from_unrecognized_call_is_unknown():
    src = (
        "def f():\n"
        "    conn = some_unrelated_library.connect()\n"
        "    return conn.fetch()\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    at_line = _call_line(src, "conn.fetch()")
    assert prov.type_of("conn", at_line) is None


def test_never_assigned_name_is_unknown():
    src = (
        "def f():\n"
        "    return 1\n"
    )
    func, module = _function_and_module(src)
    prov = build_provenance(func, module)
    assert prov.type_of("nonexistent", 2) is None


# --- scope boundary ---

def test_does_not_cross_into_nested_function():
    src = (
        "import pysam\n"
        "def outer():\n"
        "    def inner():\n"
        '        bam = pysam.AlignmentFile("x.bam", "rb")\n'
        "        return bam\n"
        "    return inner().fetch()\n"
    )
    tree = ast.parse(src)
    outer = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    prov = build_provenance(outer, tree)
    # "bam" was assigned inside the nested function, not in outer's own
    # scope — outer's provenance map must not see it.
    assert prov.type_of("bam", 6) is None


# --- module-level scope + parent-map integration ---

def test_module_level_assignment_tracked():
    src = (
        "import pysam\n"
        'bam = pysam.AlignmentFile("x.bam", "rb")\n'
        "reads = bam.fetch()\n"
    )
    tree = ast.parse(src)
    prov = build_provenance(tree, tree)
    at_line = _call_line(src, "reads = bam.fetch()")
    assert prov.type_of("bam", at_line) == "pysam.AlignmentFile"


def test_enclosing_scope_resolves_function_and_module():
    src = (
        "import pysam\n"
        "def f():\n"
        '    bam = pysam.AlignmentFile("x.bam", "rb")\n'
        "    return bam.fetch()\n"
    )
    tree = ast.parse(src)
    parents = build_parent_map(tree)
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    fetch_call = next(
        n for n in ast.walk(func)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "fetch"
    )
    assert enclosing_scope(fetch_call, parents, tree) is func
    assert enclosing_scope(func, parents, tree) is tree
