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
    # anam allows both lunch and dinner with no price — keeps fixtures simple.
    cm = TranslatedCafeteriaMenu(
        cafeteria_id="anam",
        cafeteria_name_ko="안암학사", cafeteria_name_zh="安岩学舍食堂", cafeteria_name_en="Anam",
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
    assert photos == ["https://example.com/anam/김치.jpg", None]


def test_group_skips_weekend_days():
    sat = TranslatedDaySection(date=date(2026, 4, 25), weekday="SAT", categories={
        "중식B": [DishTranslated(name_ko="A", name_zh="A", name_en="A")]
    })
    cm = TranslatedCafeteriaMenu(
        cafeteria_id="anam",
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
        "cafeteria_id": "anam",
        "cafeteria_name_zh_full": "安岩学舍食堂",
        "cafeteria_name_en_full": "Anam Dormitory Cafeteria",
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
        "source_url": "https://korea.ac.kr/ko/505",
        "price_krw": None,
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
        "science_student", "science_faculty",
        "anam", "sanhak", "student_center",
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
    meal = _meal(categories=[{"label_ko": "중식B", "dishes": dishes}])
    out = _render_dishes_text(meal)
    assert len(out) <= 2000
    assert "more)" in out  # truncation suffix present


def test_render_dishes_text_includes_price_when_set():
    meal = _meal(price_krw=6000)
    out = _render_dishes_text(meal)
    assert out.startswith("₩6,000")


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
    # no "本周新菜 X 道" callout — the user adds their own hero imagery to the page
    assert "本周新菜" not in body
    # both meal column headers present in the summary table
    assert "🍚" in body  # lunch
    assert "🌙" in body  # dinner
    # table cells omit category labels to stay compact
    assert "【중식B】" not in body
    assert "【석식】" not in body
    # dish name present with star
    assert "泡菜汤 ★ / Kimchi Stew" in body
    # hero image for anam is embedded in the cafeteria section
    assert "heroes/anam.jpg" in body


def test_summary_blocks_respect_notion_block_limits():
    """Realistic 5-cafeteria × 5-day × 2-meal bundle must fit Notion's 100-per-array
    block ceiling (top-level children AND each toggle's children)."""
    from src.notion_writer import _summary_blocks

    cafeterias = []
    for cid, zh in [
        ("science_student", "自然科学校区学生食堂"),
        ("science_faculty", "自然科学校区教职员食堂"),
        ("anam", "安岩学舍食堂"),
        ("sanhak", "产学馆食堂"),
        ("student_center", "学生会馆食堂"),
    ]:
        days = []
        for i, wd in enumerate(["MON", "TUE", "WED", "THU", "FRI"]):
            lunch = [DishTranslated(name_ko=f"L{j}", name_zh=f"午{j}", name_en=f"Lunch{j}")
                     for j in range(8)]
            dinner = [DishTranslated(name_ko=f"D{j}", name_zh=f"晚{j}", name_en=f"Dinner{j}")
                      for j in range(8)]
            days.append(TranslatedDaySection(
                date=date(2026, 4, 20 + i), weekday=wd,
                categories={"중식B": lunch, "석식": dinner},
            ))
        cafeterias.append(TranslatedCafeteriaMenu(
            cafeteria_id=cid,
            cafeteria_name_ko=zh, cafeteria_name_zh=zh, cafeteria_name_en=cid,
            week_start=date(2026, 4, 20), days=days,
            source_url="https://example.com", fetched_at=datetime(2026, 4, 20, 9, 0),
        ))
    bundle = TranslatedWeeklyBundle(week_start=date(2026, 4, 20), cafeterias=cafeterias)
    bundle.new_dish_count = 0
    meals = group_into_meals(bundle, lambda *a, **k: None)

    blocks = _summary_blocks(bundle, meals)
    assert len(blocks) <= 100, f"top-level blocks={len(blocks)} exceeds Notion 100 limit"

    for b in blocks:
        children = b.get(b["type"], {}).get("children")
        if children is not None:
            assert len(children) <= 100, (
                f"toggle children={len(children)} exceeds Notion 100 limit"
            )


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


@pytest.mark.asyncio
@respx.mock
async def test_publish_happy_path(monkeypatch):
    monkeypatch.setattr("src.notion_writer.resolve_photo_url", lambda *a, **k: None)
    respx.post("https://api.notion.com/v1/databases/dbid/query").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    pages_route = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=httpx.Response(200, json={
            "id": "p", "url": "https://www.notion.so/summary",
        })
    )

    bundle = _bundle_with_dishes({
        "중식B": [DishTranslated(name_ko="A", name_zh="A", name_en="A")],
        "석식": [DishTranslated(name_ko="B", name_zh="B", name_en="B")],
    })

    async with NotionWriter(token="tk", database_id="dbid", parent_page_id="pid") as w:
        result = await w.publish(bundle)

    assert result["meals_inserted"] == 2
    assert result["meals_updated"] == 0
    assert result["meals_failed"] == 0
    assert result["summary_page_url"] == "https://www.notion.so/summary"
    assert pages_route.call_count == 3  # 2 upserts + 1 summary


@pytest.mark.asyncio
@respx.mock
async def test_publish_aborts_summary_when_failures_over_threshold(monkeypatch):
    monkeypatch.setattr("src.notion_writer.resolve_photo_url", lambda *a, **k: None)
    respx.post("https://api.notion.com/v1/databases/dbid/query").mock(
        return_value=httpx.Response(400, json={"message": "boom"})
    )
    pages_route = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=httpx.Response(200, json={"id": "p", "url": "u"})
    )
    bundle = _bundle_with_dishes({
        "중식B": [DishTranslated(name_ko="A", name_zh="A", name_en="A")],
        "석식": [DishTranslated(name_ko="B", name_zh="B", name_en="B")],
    })

    async with NotionWriter(token="tk", database_id="dbid", parent_page_id="pid") as w:
        result = await w.publish(bundle)

    assert result["meals_failed"] == 2
    assert result["meals_inserted"] == 0
    assert result["summary_page_url"] is None
    assert pages_route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_publish_builds_summary_when_failure_rate_below_threshold(monkeypatch):
    # 1 failure out of 4 meals = 25%, below 30% threshold → summary still built.
    monkeypatch.setattr("src.notion_writer.resolve_photo_url", lambda *a, **k: None)
    query_responses = iter([
        httpx.Response(400, json={"message": "boom"}),  # first meal upsert fails
        httpx.Response(200, json={"results": []}),
        httpx.Response(200, json={"results": []}),
        httpx.Response(200, json={"results": []}),
    ])
    respx.post("https://api.notion.com/v1/databases/dbid/query").mock(
        side_effect=lambda req: next(query_responses)
    )
    respx.post("https://api.notion.com/v1/pages").mock(
        return_value=httpx.Response(200, json={"id": "p", "url": "https://www.notion.so/s"})
    )

    # Build 4 meals across 2 days (2 cafeterias × 2 days would be simpler, but
    # _bundle_with_dishes gives 1 day × 1 cafeteria so we expand inline).
    days = [
        TranslatedDaySection(date=date(2026, 4, 20 + i), weekday=wd, categories={
            "중식B": [DishTranslated(name_ko=f"L{i}", name_zh=f"L{i}", name_en=f"L{i}")],
            "석식": [DishTranslated(name_ko=f"D{i}", name_zh=f"D{i}", name_en=f"D{i}")],
        })
        for i, wd in enumerate(["MON", "TUE"])
    ]
    cm = TranslatedCafeteriaMenu(
        cafeteria_id="anam",
        cafeteria_name_ko="x", cafeteria_name_zh="安岩学舍食堂", cafeteria_name_en="Anam",
        week_start=date(2026, 4, 20), days=days,
        source_url="u", fetched_at=datetime(2026, 4, 20, 9, 0),
    )
    bundle = TranslatedWeeklyBundle(week_start=date(2026, 4, 20), cafeterias=[cm])

    async with NotionWriter(token="tk", database_id="dbid", parent_page_id="pid") as w:
        result = await w.publish(bundle)

    assert result["meals_failed"] == 1
    assert result["meals_inserted"] == 3
    assert result["summary_page_url"] == "https://www.notion.so/s"


@pytest.mark.asyncio
@respx.mock
async def test_publish_returns_none_summary_url_when_summary_build_raises(monkeypatch):
    # Upserts succeed (below threshold), but summary /pages call returns 4xx →
    # build_summary_page raises → publish swallows, returns summary_page_url=None.
    monkeypatch.setattr("src.notion_writer.resolve_photo_url", lambda *a, **k: None)
    respx.post("https://api.notion.com/v1/databases/dbid/query").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    pages_responses = iter([
        httpx.Response(200, json={"id": "m1"}),  # upsert 1
        httpx.Response(200, json={"id": "m2"}),  # upsert 2
        httpx.Response(400, json={"message": "summary blew up"}),  # summary
    ])
    respx.post("https://api.notion.com/v1/pages").mock(
        side_effect=lambda req: next(pages_responses)
    )
    bundle = _bundle_with_dishes({
        "중식B": [DishTranslated(name_ko="A", name_zh="A", name_en="A")],
        "석식": [DishTranslated(name_ko="B", name_zh="B", name_en="B")],
    })

    async with NotionWriter(token="tk", database_id="dbid", parent_page_id="pid") as w:
        result = await w.publish(bundle)

    assert result["meals_inserted"] == 2
    assert result["meals_failed"] == 0
    assert result["summary_page_url"] is None
