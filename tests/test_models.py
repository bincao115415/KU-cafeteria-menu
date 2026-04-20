from datetime import date, datetime

import pytest
from pydantic import ValidationError

from src.models import (
    CafeteriaMenu,
    DaySection,
    DishRaw,
    DishTranslated,
    TranslatedCafeteriaMenu,
    TranslatedDaySection,
    TranslatedWeeklyBundle,
    WeeklyBundle,
)


def test_dish_raw_minimal():
    d = DishRaw(name_ko="된장찌개", raw_text="된장찌개")
    assert d.name_ko == "된장찌개"


def test_day_section_weekday_enum():
    with pytest.raises(ValidationError):
        DaySection(date=date(2026, 4, 20), weekday="FOO", categories={})


def test_cafeteria_menu_round_trip():
    m = CafeteriaMenu(
        cafeteria_id="songnim",
        cafeteria_name_ko="수당삼양 Faculty House 송림",
        cafeteria_name_zh="수당삼양教职工之家 松林",
        cafeteria_name_en="Sudang-Samyang Faculty House Songnim",
        week_start=date(2026, 4, 20),
        days=[DaySection(date=date(2026, 4, 20), weekday="MON", categories={})],
        source_url="https://www.korea.ac.kr/ko/503/subview.do",
        fetched_at=datetime(2026, 4, 20, 10, 30),
    )
    dumped = m.model_dump_json()
    restored = CafeteriaMenu.model_validate_json(dumped)
    assert restored == m


def test_dish_translated_defaults():
    d = DishTranslated(name_ko="A", name_zh="甲", name_en="A")
    assert d.is_new is False
    assert d.confidence == "high"
    assert d.note_zh is None


def test_translated_weekly_bundle_defaults():
    b = TranslatedWeeklyBundle(week_start=date(2026, 4, 20), cafeterias=[])
    assert b.new_dish_count == 0
    assert b.global_errors == []


def test_weekly_bundle_has_cafeterias():
    m = CafeteriaMenu(
        cafeteria_id="x", cafeteria_name_ko="x", cafeteria_name_zh="x", cafeteria_name_en="x",
        week_start=date(2026, 4, 20),
        days=[DaySection(date=date(2026, 4, 20), weekday="MON", categories={})],
        source_url="https://x/", fetched_at=datetime(2026, 4, 20, 10, 30),
    )
    wb = WeeklyBundle(week_start=date(2026, 4, 20), cafeterias=[m])
    assert len(wb.cafeterias) == 1


def test_translated_day_section_default_categories_empty_dict():
    tds = TranslatedDaySection(date=date(2026, 4, 20), weekday="MON")
    assert tds.categories == {}


def test_translated_cafeteria_menu_default_errors_empty():
    tcm = TranslatedCafeteriaMenu(
        cafeteria_id="x", cafeteria_name_ko="x", cafeteria_name_zh="x", cafeteria_name_en="x",
        week_start=date(2026, 4, 20), days=[],
        source_url="https://x/", fetched_at=datetime(2026, 4, 20, 10, 30),
    )
    assert tcm.errors == []
