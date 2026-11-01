import os

import pytest

from intextum_cli import dedupe
from intextum_cli.dedupe import find_duplicates

WORK_ORDER = (
    "Service order No. {number}. For Acme Ltd and {customer} the following "
    "order is scheduled. Acme assembles the equipment at the depot {place}, "
    "units {units}, with a total mass of {mass} kg. The order starts on {start} "
    "and ends on {end}. The order total is {price} euros, payable after delivery by 15.12. "
    "The equipment must be inspected twice a year, repairs are to be reported "
    "within three days and spare parts may only be supplied by the manufacturer."
)
BASE = dict(number="01/2026", customer="Globex Inc", place="SampleDepot", units="12/3 and 120",
            mass="3,4", start="01.10.2027", end="30.09.2037", price="289,00")  # fmt: skip


def write(root, name, text, mtime=None):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


def texts_of(*paths):
    return {path: path.read_text(encoding="utf-8") for path in paths}


def test_signed_copy_wins_over_draft_and_archive_copy(tmp_path):
    text = WORK_ORDER.format(**BASE)
    draft = write(tmp_path, "globex/Draft_Order.docx.txt", text, mtime=2_000)
    signed = write(
        tmp_path,
        "globex/Order_Globex_signed.pdf.txt",
        text + "\nSignature",
        mtime=1_000,
    )
    archived = write(
        tmp_path,
        "globex/Archive/Order_Globex_signed.pdf.txt",
        text + "\nSignature",
        mtime=3_000,
    )
    duplicates = find_duplicates(tmp_path, texts_of(draft, signed, archived))
    assert set(duplicates) == {draft, archived}
    assert (
        duplicates[draft].primary == signed and duplicates[draft].reason == "same text"
    )
    assert (
        duplicates[archived].primary == signed
        and duplicates[archived].reason == "identical file"
    )


def test_template_orders_with_different_numbers_stay_separate(tmp_path):
    first = write(tmp_path, "globex/SC_01_SampleDepot.txt", WORK_ORDER.format(**BASE))
    other = {**BASE, "number": "02/2026", "place": "ExampleDepot", "units": "7/1", "mass": "1,2",
             "start": "01.01.2028", "price": "102,00"}  # fmt: skip
    second = write(
        tmp_path, "globex/SC_02_ExampleDepot.txt", WORK_ORDER.format(**other)
    )
    assert find_duplicates(tmp_path, texts_of(first, second)) == {}


@pytest.mark.parametrize(
    "change",
    [
        {"price": "999,00"},
        {"number": "02/2026"},
        {"start": "01.10.2028"},
        {"price": "-289,00"},
    ],
    ids=["amount", "reference", "date", "negative-amount"],
)
def test_one_changed_number_among_many_keeps_orders_separate(tmp_path, change):
    # Enough shared numbers made the old 90% numeric overlap accept a changed fee.
    suffix = " The example order reference number is 43210."
    first = write(tmp_path, "order.txt", WORK_ORDER.format(**BASE) + suffix)
    second = write(
        tmp_path, "order_revised.txt", WORK_ORDER.format(**{**BASE, **change}) + suffix
    )
    assert find_duplicates(tmp_path, texts_of(first, second)) == {}


@pytest.mark.parametrize("amount", ["999,00", "289,00"])
def test_added_numbers_including_repeated_values_keep_orders_separate(tmp_path, amount):
    text = WORK_ORDER.format(**BASE)
    first = write(tmp_path, "order.txt", text)
    second = write(
        tmp_path, "order_revised.txt", text + f" Additional charge: {amount} euros."
    )
    assert find_duplicates(tmp_path, texts_of(first, second)) == {}


def test_swapped_numbers_keep_orders_separate(tmp_path):
    text = WORK_ORDER.format(**BASE)
    first = write(tmp_path, "order.txt", text + " Delivery: 10 units in 20 days.")
    second = write(
        tmp_path, "order_revised.txt", text + " Delivery: 20 units in 10 days."
    )
    assert find_duplicates(tmp_path, texts_of(first, second)) == {}


def test_only_compares_within_the_same_top_level_folder(tmp_path):
    text = WORK_ORDER.format(**BASE)
    a = write(tmp_path, "globex/order.txt", text)
    b = write(tmp_path, "initech/order.txt", text)
    assert find_duplicates(tmp_path, texts_of(a, b)) == {}


def test_short_texts_only_match_when_identical(tmp_path):
    a = write(tmp_path, "globex/photo_1.txt", "Photo SampleDepot", mtime=1_000)
    b = write(tmp_path, "globex/photo_2.txt", "Photo SampleDepot", mtime=2_000)
    c = write(tmp_path, "globex/photo_3.txt", "Photo ExampleDepot")
    duplicates = find_duplicates(tmp_path, texts_of(a, b, c))
    assert list(duplicates) == [a] and duplicates[a].primary == b


def test_extended_version_is_not_a_copy_of_the_older_one(tmp_path):
    older = WORK_ORDER.format(**BASE)
    extension = (
        " In addition, the testing units in the workshop, the packaging along the "
        "assembly line and the tools at the workbench are included in the inspection, "
        "whereby the tools may only be serviced after the end of the production run and "
        "worn inserts in the testing units are to be replaced, so that the output quality "
        "stays within limits; the maintenance work is to be agreed with the customer."
    )
    old = write(tmp_path, "globex/2021/equipment.txt", older)
    new = write(tmp_path, "globex/2023/equipment_new.txt", older + extension)
    # Rejected by the symmetric overlap, not by the length check.
    assert len(older) / len(older + extension) >= dedupe.MIN_LENGTH_RATIO
    assert find_duplicates(tmp_path, texts_of(old, new)) == {}
