import pytest

from pixel_bangkok.heights import derive_height, parse_height_m, parse_levels


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12", 12.0),
        ("12.5 m", 12.5),
        ("7,5m", 7.5),
        ("40 ft", 12.192),
        ("30'", 9.144),
        ("tall", None),
        ("0", None),
        ("-3", None),
        (None, None),
    ],
)
def test_parse_height(raw, expected):
    assert parse_height_m(raw) == (pytest.approx(expected) if expected else None)


def test_parse_levels():
    assert parse_levels("3") == 3
    assert parse_levels("2.5") == 2.5
    assert parse_levels("many") is None


def test_source_height_wins_over_levels():
    derived = derive_height("20", "2", 3.0, 6.0)
    assert (derived.render_height_m, derived.provenance) == (20.0, "source")


def test_levels_are_marked_estimated():
    derived = derive_height(None, "4", 3.5, 6.0)
    assert (derived.render_height_m, derived.provenance) == (14.0, "estimated")
    assert "assumed" in derived.note


def test_missing_data_is_unknown_not_estimated():
    derived = derive_height("tall", None, 3.0, 6.0)
    assert (derived.render_height_m, derived.provenance) == (6.0, "unknown")


def test_manual_override_is_marked_manual():
    derived = derive_height("20", "2", 3.0, 6.0, {"height_m": 76, "note": "curated"})
    assert (derived.render_height_m, derived.provenance, derived.note) == (
        76.0,
        "manual",
        "curated",
    )
