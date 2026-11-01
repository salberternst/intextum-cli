from pathlib import Path

import pytest

from intextum_cli.groups import GroupsError, discover_groups


def touch(root: Path, *names: str) -> None:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)


def as_dict(groups):
    return {g.name: (g.relative_files, g.document_class) for g in groups}


def test_subfolders_and_loose_files(tmp_path):
    touch(
        tmp_path,
        "order-1/letter.pdf",
        "order-1/attachments/positions.xlsx",
        "order-2/letter.pdf",
        "single.pdf",
        ".hidden/x.pdf",
        "order-2/.DS_Store",
        "order-2/~$lock.docx",
    )
    assert as_dict(discover_groups(tmp_path)) == {
        "order-1": (["order-1/attachments/positions.xlsx", "order-1/letter.pdf"], None),
        "order-2": (["order-2/letter.pdf"], None),
        "single.pdf": (["single.pdf"], None),
    }


def test_groups_yaml_combines_files_and_sets_class(tmp_path):
    touch(
        tmp_path, "letter-7.pdf", "table-7.xlsx", "scans/a.png", "scans/b.png", "x.pdf"
    )
    (tmp_path / "groups.yaml").write_text(
        "groups:\n"
        "  - name: case-7\n"
        "    class: Invoice\n"
        "    files: ['*-7.*']\n"
        "  - name: scans\n"
        "    files: [scans]\n"
    )
    assert as_dict(discover_groups(tmp_path)) == {
        "case-7": (["letter-7.pdf", "table-7.xlsx"], "Invoice"),
        "scans": (["scans/a.png", "scans/b.png"], None),
        "x.pdf": (["x.pdf"], None),
    }


def test_groups_yaml_can_take_files_out_of_a_subfolder(tmp_path):
    touch(tmp_path, "inbox/a.pdf", "inbox/b.pdf")
    (tmp_path / "groups.yaml").write_text(
        "groups:\n  - name: only-a\n    files: [inbox/a.pdf]\n"
    )
    assert as_dict(discover_groups(tmp_path)) == {
        "only-a": (["inbox/a.pdf"], None),
        "inbox": (["inbox/b.pdf"], None),
    }


@pytest.mark.parametrize(
    "yaml_text, message",
    [
        ("groups:\n  - name: g\n    files: [missing.pdf]\n", "matches no files"),
        (
            "groups:\n  - name: g1\n    files: [a.pdf]\n  - name: g2\n    files: [a.pdf]\n",
            "is in both",
        ),
        ("groups:\n  - name: folder\n    files: [a.pdf]\n", "clashes"),
        ("groups: nope\n", "top-level 'groups:' list"),
        ("groups:\n  - files: [a.pdf]\n", "needs a 'name'"),
    ],
)
def test_groups_yaml_errors(tmp_path, yaml_text, message):
    touch(tmp_path, "a.pdf", "folder/b.pdf")
    (tmp_path / "groups.yaml").write_text(yaml_text)
    with pytest.raises(GroupsError, match=message):
        discover_groups(tmp_path)


def test_output_folder_inside_input_is_excluded(tmp_path):
    touch(tmp_path, "a.pdf", "results/a.json")
    groups = discover_groups(tmp_path, exclude=[tmp_path / "results"])
    assert [g.name for g in groups] == ["a.pdf"]


def test_absolute_pattern_is_reported(tmp_path):
    touch(tmp_path, "a.pdf")
    (tmp_path / "groups.yaml").write_text(
        f"groups:\n  - name: g\n    files: ['{tmp_path}/a.pdf']\n"
    )
    with pytest.raises(GroupsError, match="invalid pattern|matches no files"):
        discover_groups(tmp_path)


def test_group_by_file_and_unsupported_files(tmp_path):
    touch(
        tmp_path,
        "customer-a/vertrag.pdf",
        "customer-a/anlage.xlsx",
        "customer-a/karte.shp",
        "customer-a/Archiv/alt.doc",
        "customer-b/brief.docx",
        "loose.pdf",
        "notes.h4g",
    )
    (tmp_path / "groups.yaml").write_text(
        "groups:\n  - name: customer-b-set\n    files: [customer-b]\n"
    )
    unsupported = []
    groups = discover_groups(tmp_path, group_by="file", unsupported=unsupported)
    assert as_dict(groups) == {
        "customer-b-set": (["customer-b/brief.docx"], None),
        "loose.pdf": (["loose.pdf"], None),
        "customer-a/Archiv/alt.doc": (["customer-a/Archiv/alt.doc"], None),
        "customer-a/anlage.xlsx": (["customer-a/anlage.xlsx"], None),
        "customer-a/vertrag.pdf": (["customer-a/vertrag.pdf"], None),
    }
    assert sorted(p.name for p in unsupported) == ["karte.shp", "notes.h4g"]

    folder_groups = discover_groups(tmp_path)
    assert as_dict(folder_groups)["customer-a"][0] == [
        "customer-a/Archiv/alt.doc", "customer-a/anlage.xlsx", "customer-a/vertrag.pdf"
    ]  # fmt: skip


def test_exclude_patterns_drop_files_everywhere(tmp_path):
    touch(
        tmp_path,
        "acme/Acme_Contract_Harbor.doc",
        "acme/Acme_DRAFT_07.doc",
        "acme/Archive/old.doc",
        "acme/items_draft.xlsx",
        "acme/items_final.xlsx",
        "acme/map.shp",
    )
    excluded, unsupported = [], []
    groups = discover_groups(
        tmp_path,
        group_by="file",
        exclude_patterns=["draft", r"^acme/archive/"],
        excluded_files=excluded,
        unsupported=unsupported,
    )
    assert [g.name for g in groups] == [
        "acme/Acme_Contract_Harbor.doc",
        "acme/items_final.xlsx",
    ]
    assert sorted(p.name for p in excluded) == [
        "Acme_DRAFT_07.doc", "items_draft.xlsx", "old.doc"
    ]  # fmt: skip
    assert [p.name for p in unsupported] == ["map.shp"]


def test_invalid_exclude_pattern(tmp_path):
    touch(tmp_path, "a.pdf")
    with pytest.raises(GroupsError, match="invalid exclude pattern"):
        discover_groups(tmp_path, exclude_patterns=["(unclosed"])
