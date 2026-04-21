from datetime import date, datetime

import httpx
import pytest
import respx

from src.models import (
    DishTranslated,
    TranslatedCafeteriaMenu,
    TranslatedDaySection,
    TranslatedWeeklyBundle,
)
from src.notion_writer import (
    CAFETERIA_SHORT_ZH,
    NotionWriter,
    _render_dishes_text,
    classify_meal,
    group_into_meals,
)


def _bundle_with_dishes(categories: dict[str, list[DishTranslated]]) -> TranslatedWeeklyBundle:
    day = TranslatedDaySection(
        date=date(2026, 4, 20), weekday="MON", categories=categories
    )
    cm = TranslatedCafeteriaMenu(
        cafeteria_id="science",
        cafeteria_name_ko="자연계", cafeteria_name_zh="自然科学", cafeteria_name_en="Science",
        week_start=date(2026, 4, 20),
        days=[day],
        source_url="https://example.com/s",
        fetched_at=datetime(2026, 4, 20, 9, 0),
    )
    return TranslatedWeeklyBundle(week_start=date(2026, 4, 20), cafeterias=[cm])


def test_classify_meal_by_korean_label():
    assert classify_meal("중식B") == "午餐"
    assert classify_meal("석식") == "晚餐"
    assert classify_meal("석식A") == "晚餐"
    assert classify_meal("파스타/스테이크 코스") == "午餐"


def test_group_splits_lunch_and_dinner():
    dishes_lunch = [DishTranslated(name_ko="김치찌개", name_zh="泡菜汤", name_en="Kimchi Stew")]
    dishes_dinner = [DishTranslated(name_ko="불고기", name_zh="烤肉", name_en="Bulgogi")]
    bundle = _bundle_with_dishes({"중식B": dishes_lunch, "석식": dishes_dinner})

    meals = group_into_meals(bundle, lambda cid, ko, en: None)

    assert len(meals) == 2
    meal_by = {m["meal"]: m for m in meals}
    assert meal_by["午餐"]["dish_count"] == 1
    assert meal_by["晚餐"]["dish_count"] == 1
    assert meal_by["午餐"]["categories"][0]["label_ko"] == "중식B"
    assert meal_by["晚餐"]["categories"][0]["label_ko"] == "석식"


def test_group_filters_hidden_breakfast_categories():
    dishes = [DishTranslated(name_ko="토스트", name_zh="吐司", name_en="Toast")]
    bundle = _bundle_with_dishes({"조식": dishes, "천원의아침": dishes, "아침": dishes})
    assert group_into_meals(bundle, lambda *a, **k: None) == []


def test_group_counts_new_dishes():
    dishes = [
        DishTranslated(name_ko="A", name_zh="A", name_en="A", is_new=True),
        DishTranslated(name_ko="B", name_zh="B", name_en="B", is_new=False),
        DishTranslated(name_ko="C", name_zh="C", name_en="C", is_new=True),
    ]
    bundle = _bundle_with_dishes({"중식B": dishes})
    [meal] = group_into_meals(bundle, lambda *a, **k: None)
    assert meal["dish_count"] == 3
    assert meal["new_count"] == 2


def test_group_confidence_is_worst_case():
    dishes = [
        DishTranslated(name_ko="A", name_zh="A", name_en="A", confidence="high"),
        DishTranslated(name_ko="B", name_zh="B", name_en="B", confidence="low"),
        DishTranslated(name_ko="C", name_zh="C", name_en="C", confidence="medium"),
    ]
    bundle = _bundle_with_dishes({"중식B": dishes})
    [meal] = group_into_meals(bundle, lambda *a, **k: None)
    assert meal["confidence"] == "low"


def test_group_attaches_photo_urls():
    dishes = [
        DishTranslated(name_ko="김치", name_zh="泡菜", name_en="Kimchi"),
        DishTranslated(name_ko="밥", name_zh="米饭", name_en="Rice"),
    ]
    bundle = _bundle_with_dishes({"중식B": dishes})

    def resolver(cid, ko, en):
        return f"https://example.com/{cid}/{ko}.jpg" if ko == "김치" else None

    [meal] = group_into_meals(bundle, resolver)
    photos = [ln["photo_url"] for blk in meal["categories"] for ln in blk["dishes"]]
    assert photos == ["https://example.com/science/김치.jpg", None]


def test_group_skips_weekend_days():
    sat = TranslatedDaySection(date=date(2026, 4, 25), weekday="SAT", categories={
        "중식B": [DishTranslated(name_ko="A", name_zh="A", name_en="A")]
    })
    cm = TranslatedCafeteriaMenu(
        cafeteria_id="science",
        cafeteria_name_ko="x", cafeteria_name_zh="x", cafeteria_name_en="x",
        week_start=date(2026, 4, 20), days=[sat],
        source_url="u", fetched_at=datetime(2026, 4, 20, 9, 0),
    )
    bundle = TranslatedWeeklyBundle(week_start=date(2026, 4, 20), cafeterias=[cm])
    assert group_into_meals(bundle, lambda *a, **k: None) == []


def _meal(**overrides):
    base = {
        "week_monday": date(2026, 4, 20),
        "day": "Mon",
        "date": date(2026, 4, 20),
        "cafeteria_id": "science",
        "cafeteria_name_zh_full": "自然科学校区学生食堂",
        "cafeteria_name_en_full": "Science Cafeteria",
        "meal": "午餐",
        "categories": [
            {"label_ko": "중식B", "dishes": [
                {"name_ko": "김치찌개", "name_zh": "泡菜汤", "name_en": "Kimchi Stew",
                 "is_new": True, "photo_url": "https://example.com/kimchi.jpg"},
            ]},
        ],
        "dish_count": 1,
        "new_count": 1,
        "confidence": "high",
        "source_url": "https://korea.ac.kr/ko/504",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
@respx.mock
async def test_upsert_meal_inserts_when_not_found():
    respx.post("https://api.notion.com/v1/databases/dbid/query").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    created = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=httpx.Response(200, json={"id": "new-page-id"})
    )

    async with NotionWriter(token="tk", database_id="dbid", parent_page_id="pid") as w:
        result = await w.upsert_meal(_meal())
    assert result == "inserted"
    assert created.called

    body = created.calls.last.request.content.decode()
    assert '"database_id": "dbid"' in body
    assert "午餐" in body
    assert "泡菜汤" in body  # zh name appears in Dishes render
    assert "김치찌개" not in body  # Korean excluded from dish render by design
    assert "★" in body  # is_new marker
    # Regression guard: switching from httpx json= to content=bytes
    # must keep the client's default Content-Type header intact.
    assert created.calls.last.request.headers["content-type"] == "application/json"


@pytest.mark.asyncio
@respx.mock
async def test_upsert_meal_updates_when_found():
    respx.post("https://api.notion.com/v1/databases/dbid/query").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "existing-page-id"}]})
    )
    updated = respx.patch("https://api.notion.com/v1/pages/existing-page-id").mock(
        return_value=httpx.Response(200, json={"id": "existing-page-id"})
    )

    async with NotionWriter(token="tk", database_id="dbid", parent_page_id="pid") as w:
        result = await w.upsert_meal(_meal())
    assert result == "updated"
    assert updated.called


@pytest.mark.asyncio
@respx.mock
async def test_upsert_meal_retries_on_429():
    responses = iter([
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"results": []}),
    ])
    respx.post("https://api.notion.com/v1/databases/dbid/query").mock(
        side_effect=lambda req: next(responses)
    )
    respx.post("https://api.notion.com/v1/pages").mock(
        return_value=httpx.Response(200, json={"id": "p1"})
    )

    async with NotionWriter(token="tk", database_id="dbid", parent_page_id="pid") as w:
        result = await w.upsert_meal(_meal())
    assert result == "inserted"


@pytest.mark.asyncio
@respx.mock
async def test_upsert_meal_returns_failed_on_4xx():
    respx.post("https://api.notion.com/v1/databases/dbid/query").mock(
        return_value=httpx.Response(400, json={"message": "bad request"})
    )

    async with NotionWriter(token="tk", database_id="dbid", parent_page_id="pid") as w:
        result = await w.upsert_meal(_meal())
    assert result == "failed"


def test_cafeteria_short_zh_covers_all_ids():
    assert set(CAFETERIA_SHORT_ZH) == {
        "science", "anam", "sanhak", "alumni", "student_center",
    }


def test_render_dishes_truncates_over_soft_limit():
    # Build a block whose rendered text will exceed _DISHES_SOFT_LIMIT=2000.
    dishes = [
        {
            "name_ko": "x", "name_zh": "x" * 50, "name_en": "x" * 50,
            "is_new": False, "photo_url": None,
        }
        for _ in range(40)  # ~40 * ~105 chars/line = ~4200 chars
    ]
    categories = [{"label_ko": "중식B", "dishes": dishes}]
    out = _render_dishes_text(categories)
    assert len(out) <= 2000
    assert "more)" in out  # truncation suffix present


@pytest.mark.asyncio
@respx.mock
async def test_build_summary_page_creates_expected_blocks():
    captured: dict = {}

    def respond(req):
        captured["body"] = req.content.decode()
        return httpx.Response(200, json={
            "id": "summary-page-id",
            "url": "https://www.notion.so/summary-page",
        })

    respx.post("https://api.notion.com/v1/pages").mock(side_effect=respond)

    bundle = _bundle_with_dishes({
        "중식B": [DishTranslated(name_ko="김치찌개", name_zh="泡菜汤", name_en="Kimchi Stew", is_new=True)],
        "석식": [DishTranslated(name_ko="불고기", name_zh="烤肉", name_en="Bulgogi")],
    })
    bundle.new_dish_count = 5
    meals = group_into_meals(bundle, lambda *a, **k: None)

    async with NotionWriter(token="tk", database_id="dbid", parent_page_id="pid") as w:
        url = await w.build_summary_page(bundle, meals)

    assert url == "https://www.notion.so/summary-page"
    body = captured["body"]
    # parent points to the user's KU Cafeteria Menu page
    assert '"page_id": "pid"' in body
    # title mentions the Monday date
    assert "2026/04/20" in body
    # new-dish callout number
    assert '"5"' in body or "5 道" in body
    # both meal headers present
    assert "🍚" in body  # lunch
    assert "🌙" in body  # dinner
    # category heading present
    assert "【중식B】" in body
    assert "【석식】" in body
    # dish name present with star
    assert "泡菜汤 ★ / Kimchi Stew" in body


@pytest.mark.asyncio
@respx.mock
async def test_build_summary_page_empty_cafeteria_renders_placeholder():
    # Cafeteria parses but has no dishes → H2 + italic "本周该食堂未提供数据"
    cm_empty = TranslatedCafeteriaMenu(
        cafeteria_id="anam",
        cafeteria_name_ko="x", cafeteria_name_zh="安岩学舍食堂", cafeteria_name_en="Anam",
        week_start=date(2026, 4, 20), days=[],
        source_url="u", fetched_at=datetime(2026, 4, 20, 9, 0),
    )
    bundle = TranslatedWeeklyBundle(week_start=date(2026, 4, 20), cafeterias=[cm_empty])
    captured: dict = {}

    def respond_empty(req):
        captured["body"] = req.content.decode()
        return httpx.Response(200, json={"url": "u", "id": "i"})

    respx.post("https://api.notion.com/v1/pages").mock(side_effect=respond_empty)
    async with NotionWriter(token="tk", database_id="dbid", parent_page_id="pid") as w:
        await w.build_summary_page(bundle, [])

    assert "本周该食堂未提供数据" in captured["body"]
    assert "安岩" in captured["body"]
