from datetime import date, datetime

from src.models import (
    DishTranslated,
    TranslatedCafeteriaMenu,
    TranslatedDaySection,
    TranslatedWeeklyBundle,
)
from src.renderer import render_email


def _make_bundle() -> TranslatedWeeklyBundle:
    cm = TranslatedCafeteriaMenu(
        cafeteria_id="songnim",
        cafeteria_name_ko="수당삼양 Faculty House 송림",
        cafeteria_name_zh="修堂三养教员俱乐部 松林",
        cafeteria_name_en="Sudang-Samyang Faculty House Songnim",
        week_start=date(2026, 4, 20),
        days=[
            TranslatedDaySection(
                date=date(2026, 4, 20), weekday="MON",
                categories={"식사": [DishTranslated(
                    name_ko="된장찌개", name_zh="大酱汤", name_en="Soybean Paste Stew",
                    note_zh="韩式豆瓣酱", is_new=True, confidence="high",
                )]},
            ),
            *[TranslatedDaySection(date=date(2026, 4, 20 + i), weekday=w, categories={})
              for i, w in enumerate(["TUE", "WED", "THU", "FRI", "SAT", "SUN"], start=1)],
        ],
        source_url="https://www.korea.ac.kr/ko/503/subview.do",
        fetched_at=datetime(2026, 4, 20, 10, 30),
    )
    return TranslatedWeeklyBundle(
        week_start=date(2026, 4, 20), cafeterias=[cm], new_dish_count=1,
    )


def test_render_contains_chinese_and_english_names():
    html, subject, text = render_email(_make_bundle())
    assert "大酱汤" in html
    assert "Soybean Paste Stew" in html
    assert "[高大食堂]" in subject
    assert "1" in subject
    assert "大酱汤" in text


def test_render_omits_korean():
    html, _, text = render_email(_make_bundle())
    assert "된장찌개" not in html
    assert "수당삼양" not in html
    assert "된장찌개" not in text


def test_render_shows_only_weekdays():
    html, _, _ = render_email(_make_bundle())
    assert "周一 Mon" in html
    assert "周五 Fri" in html
    # Saturday/Sunday columns dropped
    assert "周六" not in html
    assert "周日" not in html
    assert "Sat" not in html
    assert "Sun" not in html


def test_render_uses_new_badge():
    html, _, _ = render_email(_make_bundle())
    assert "★" in html


def test_render_empty_days_show_placeholder():
    html, _, _ = render_email(_make_bundle())
    assert "未更新" in html


def test_render_contains_source_link():
    html, _, _ = render_email(_make_bundle())
    assert "https://www.korea.ac.kr/ko/503/subview.do" in html


def test_render_inlines_css():
    html, _, _ = render_email(_make_bundle())
    assert 'style="' in html


def _bundle_with_categories(categories: dict) -> TranslatedWeeklyBundle:
    cm = TranslatedCafeteriaMenu(
        cafeteria_id="science",
        cafeteria_name_ko="자연계 학생식당",
        cafeteria_name_zh="自然科学校区学生食堂",
        cafeteria_name_en="Science Campus Student Cafeteria",
        week_start=date(2026, 4, 20),
        days=[
            TranslatedDaySection(
                date=date(2026, 4, 20), weekday="MON", categories=categories,
            ),
            *[TranslatedDaySection(date=date(2026, 4, 20 + i), weekday=w, categories={})
              for i, w in enumerate(["TUE", "WED", "THU", "FRI", "SAT", "SUN"], start=1)],
        ],
        source_url="https://www.korea.ac.kr/ko/504/subview.do",
        fetched_at=datetime(2026, 4, 20, 10, 30),
    )
    return TranslatedWeeklyBundle(
        week_start=date(2026, 4, 20), cafeterias=[cm], new_dish_count=0,
    )


def test_render_drops_breakfast_categories():
    dish = DishTranslated(
        name_ko="x", name_zh="稀饭", name_en="Congee",
        note_zh=None, is_new=False, confidence="high",
    )
    bundle = _bundle_with_categories({
        "조식": [dish],
        "중식": [DishTranslated(
            name_ko="x", name_zh="午餐菜", name_en="Lunch Dish",
            note_zh=None, is_new=False, confidence="high",
        )],
    })
    html, _, text = render_email(bundle)
    assert "稀饭" not in html
    assert "稀饭" not in text
    assert "조식" not in html
    assert "午餐菜" in html


def test_render_translates_category_labels():
    dish = DishTranslated(
        name_ko="x", name_zh="饭", name_en="Rice",
        note_zh=None, is_new=False, confidence="high",
    )
    bundle = _bundle_with_categories({"중식": [dish], "석식": [dish]})
    html, _, _ = render_email(bundle)
    assert "午餐 Lunch" in html
    assert "晚餐 Dinner" in html
    # Raw Korean category key should not appear as a header
    assert ">중식<" not in html
    assert ">석식<" not in html
