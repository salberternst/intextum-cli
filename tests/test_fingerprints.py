from pathlib import Path

import pytest

from intextum_cli import fingerprints
from intextum_cli.groups import Group
from intextum_cli.processing import Options
from intextum_cli.schema import DocumentClass


@pytest.mark.parametrize(
    "module, invalidates",
    [
        ("conversion_readers", True),
        ("conversion_recovery", True),
        ("conversion_tables", True),
        ("document_model", True),
        ("extraction_prompt", True),
        ("external_fields", True),
        ("group_processing", True),
        ("processing", True),
        ("schema", True),
        ("llm_types", True),
        ("llm_endpoints", True),
        ("review_sidebar", False),
        ("review_batch", False),
    ],
)
def test_code_changes_invalidate_only_processing_results(
    tmp_path, monkeypatch, module, invalidates
):
    path = tmp_path / "invoice.txt"
    path.write_text("Invoice with readable source text")
    group = Group("invoice", tmp_path, [path])
    options = Options(classes=[DocumentClass(name="Invoice")], model="test")
    read_bytes = Path.read_bytes

    def changed_code(path):
        content = read_bytes(path)
        return (
            content + b"\n# changed processing behavior"
            if path.name == f"{module}.py"
            else content
        )

    fingerprints._code_digest.cache_clear()
    try:
        previous = fingerprints.fingerprint(group, options)
        monkeypatch.setattr(Path, "read_bytes", changed_code)
        fingerprints._code_digest.cache_clear()
        assert (fingerprints.fingerprint(group, options) != previous) is invalidates
    finally:
        fingerprints._code_digest.cache_clear()


@pytest.mark.parametrize(
    "settings",
    [
        {"ocr_engine": "tesseract"},
        {"ocr_languages": ["deu"]},
        {"table_mode": "docling"},
        {"detect_marks": True},
    ],
)
def test_ocr_settings_invalidate_extraction(tmp_path, settings):
    path = tmp_path / "register.txt"
    path.write_text("Readable register text")
    group = Group("register", tmp_path, [path])
    initial = Options(classes=[], model="test")
    changed = Options(classes=[], model="test", **settings)
    assert fingerprints.fingerprint(group, initial) != fingerprints.fingerprint(
        group, changed
    )
