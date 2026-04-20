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


def test_render_contains_korean_and_chinese_names():
    html, subject, text = render_email(_make_bundle())
    assert "된장찌개" in html
    assert "大酱汤" in html
    assert "Soybean Paste Stew" in html
    assert "[高大食堂]" in subject
    assert "1" in subject
    assert "大酱汤" in text


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
