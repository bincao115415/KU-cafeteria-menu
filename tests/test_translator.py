import json
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

from src.cache import TranslationCache
from src.models import CafeteriaMenu, DaySection, DishRaw
from src.translator import Translator


def _menu_with(dishes: list[str]) -> CafeteriaMenu:
    return CafeteriaMenu(
        cafeteria_id="x",
        cafeteria_name_ko="x", cafeteria_name_zh="x", cafeteria_name_en="x",
        week_start=date(2026, 4, 20),
        days=[DaySection(
            date=date(2026, 4, 20), weekday="MON",
            categories={"식사": [DishRaw(name_ko=n, raw_text=n) for n in dishes]},
        )] + [
            DaySection(date=date(2026, 4, 20 + i), weekday=w, categories={})
            for i, w in enumerate(["TUE", "WED", "THU", "FRI", "SAT", "SUN"], start=1)
        ],
        source_url="https://x/",
        fetched_at=datetime(2026, 4, 20, 10, 30),
    )


@pytest.fixture
def empty_cache(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"schema_version": 1, "updated_at": "x", "entries": {}}))
    return TranslationCache(path=p)


@pytest.mark.asyncio
async def test_cache_hit_skips_llm(empty_cache):
    empty_cache.set("된장찌개", {
        "zh": "大酱汤", "en": "Soybean Paste Stew",
        "note_zh": None, "note_en": None,
        "learned_at": "2026-04-20", "source": "cached",
        "search_confirmed": True, "confidence": "high",
    })
    empty_cache.new_keys.clear()

    client = AsyncMock()
    t = Translator(client=client, cache=empty_cache)
    out = await t.translate_menu(_menu_with(["된장찌개"]))
    dish = out.days[0].categories["식사"][0]
    assert dish.name_zh == "大酱汤"
    assert dish.is_new is False
    client.chat_json.assert_not_awaited()
    client.chat_reflect.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_pass_confirm(empty_cache):
    client = AsyncMock()
    client.chat_json.return_value = {
        "zh": "大酱汤", "en": "Soybean Paste Stew",
        "note_zh": "韩式豆瓣酱炖豆腐", "note_en": "Korean stew",
    }
    client.chat_reflect.return_value = {"verdict": "confirm"}

    t = Translator(client=client, cache=empty_cache)
    out = await t.translate_menu(_menu_with(["된장찌개"]))
    dish = out.days[0].categories["식사"][0]
    assert dish.name_zh == "大酱汤"
    assert dish.is_new is True
    assert dish.confidence == "high"
    assert empty_cache.get("된장찌개")["search_confirmed"] is True


@pytest.mark.asyncio
async def test_two_pass_revise(empty_cache):
    client = AsyncMock()
    client.chat_json.return_value = {
        "zh": "豆酱锅", "en": "Bean Paste Pot",
        "note_zh": "", "note_en": "",
    }
    client.chat_reflect.return_value = {
        "verdict": "revise",
        "revised": {
            "zh": "大酱汤", "en": "Soybean Paste Stew",
            "note_zh": "常用译法", "note_en": "common rendering",
        },
    }
    t = Translator(client=client, cache=empty_cache)
    out = await t.translate_menu(_menu_with(["된장찌개"]))
    dish = out.days[0].categories["식사"][0]
    assert dish.name_zh == "大酱汤"
    assert dish.confidence == "medium"


@pytest.mark.asyncio
async def test_two_pass_no_signal(empty_cache):
    client = AsyncMock()
    client.chat_json.return_value = {
        "zh": "甲", "en": "A",
        "note_zh": None, "note_en": None,
    }
    client.chat_reflect.return_value = {"verdict": "no_signal"}
    t = Translator(client=client, cache=empty_cache)
    out = await t.translate_menu(_menu_with(["된장찌개"]))
    dish = out.days[0].categories["식사"][0]
    assert dish.confidence == "low"
    assert empty_cache.get("된장찌개")["search_confirmed"] is False


@pytest.mark.asyncio
async def test_llm_failure_yields_placeholder(empty_cache):
    client = AsyncMock()
    client.chat_json.side_effect = Exception("upstream boom")
    t = Translator(client=client, cache=empty_cache)
    out = await t.translate_menu(_menu_with(["된장찌개"]))
    dish = out.days[0].categories["식사"][0]
    assert dish.confidence == "failed"
    assert "[translation failed]" in dish.name_zh or "[translation failed]" in dish.name_en
    assert out.errors
    assert empty_cache.get("된장찌개") is None


@pytest.mark.asyncio
async def test_same_dish_across_days_resolved_once(empty_cache):
    """If the same dish shows up on multiple days, only one LLM call pair."""
    client = AsyncMock()
    client.chat_json.return_value = {
        "zh": "大酱汤", "en": "Soybean Paste Stew", "note_zh": None, "note_en": None,
    }
    client.chat_reflect.return_value = {"verdict": "confirm"}

    menu = _menu_with(["된장찌개"])
    menu.days[1] = DaySection(
        date=menu.days[1].date, weekday=menu.days[1].weekday,
        categories={"식사": [DishRaw(name_ko="된장찌개", raw_text="된장찌개")]},
    )
    t = Translator(client=client, cache=empty_cache)
    out = await t.translate_menu(menu)
    assert client.chat_json.await_count == 1
    assert client.chat_reflect.await_count == 1
    assert out.days[0].categories["식사"][0].name_zh == "大酱汤"
    assert out.days[1].categories["식사"][0].name_zh == "大酱汤"
