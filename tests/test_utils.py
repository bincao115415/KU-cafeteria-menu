from datetime import date

from freezegun import freeze_time

from src.utils import get_current_monday_kst, normalize_dish_name


def test_normalize_strips_whitespace():
    assert normalize_dish_name("  된장찌개  ") == "된장찌개"


def test_normalize_collapses_inner_whitespace():
    assert normalize_dish_name("된장\t찌개\n") == "된장 찌개"


def test_normalize_unifies_middle_dot():
    assert normalize_dish_name("파스타・스테이크") == "파스타·스테이크"


def test_normalize_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        normalize_dish_name("   ")


@freeze_time("2026-04-22 05:00:00", tz_offset=0)
def test_get_current_monday_kst_midweek():
    assert get_current_monday_kst() == date(2026, 4, 20)


@freeze_time("2026-04-20 01:30:00", tz_offset=0)
def test_get_current_monday_kst_on_monday_morning():
    assert get_current_monday_kst() == date(2026, 4, 20)


@freeze_time("2026-04-19 14:00:00", tz_offset=0)
def test_get_current_monday_kst_sunday_returns_previous_monday():
    assert get_current_monday_kst() == date(2026, 4, 13)
