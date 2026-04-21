import json
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.main import run_once
from src.models import TranslatedCafeteriaMenu


def _seed(tmp_path, state: dict) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "translations.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "x", "entries": {}})
    )
    (tmp_path / "data" / "state.json").write_text(json.dumps(state))


def _set_notion_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dk")
    monkeypatch.setenv("NOTION_TOKEN", "tk")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "pid")
    monkeypatch.setenv("NOTION_DATABASE_ID", "dbid")


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")  # Mon 10:30 KST
async def test_skip_when_already_sent_this_week(tmp_path, monkeypatch):
    _seed(tmp_path, {"last_sent_week": "2026-04-20", "last_run_at": "x", "status": "done"})
    monkeypatch.setattr("src.main.DATA", tmp_path / "data")

    with patch("src.main.fetch_all", new=AsyncMock()) as fa:
        result = await run_once(trigger_index=0, total_triggers=3)

    assert result == "skipped_already_sent"
    fa.assert_not_awaited()


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")
async def test_all_empty_on_first_trigger_sets_pending(tmp_path, monkeypatch):
    _seed(tmp_path, {"last_sent_week": None, "last_run_at": None, "status": "idle"})
    monkeypatch.setattr("src.main.DATA", tmp_path / "data")

    empty_menu = MagicMock()
    empty_menu.days = [MagicMock(categories={}) for _ in range(7)]
    empty_menu.errors = []

    async def fake_fetch(cafs):
        return [(c["cafeteria_id"], "<html></html>", None) for c in cafs]

    with (
        patch("src.main.fetch_all", side_effect=fake_fetch),
        patch("src.main.parse_cafeteria_page", return_value=empty_menu),
        patch("src.main.git_commit_and_push", return_value=True),
    ):
        result = await run_once(trigger_index=0, total_triggers=3)

    assert result == "pending"
    state = json.loads((tmp_path / "data" / "state.json").read_text())
    assert state["status"] == "pending"


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")
async def test_all_empty_on_last_trigger_silent(tmp_path, monkeypatch):
    _seed(tmp_path, {"last_sent_week": None, "last_run_at": None, "status": "idle"})
    monkeypatch.setattr("src.main.DATA", tmp_path / "data")
    _set_notion_env(monkeypatch)

    empty_menu = MagicMock()
    empty_menu.days = [MagicMock(categories={}) for _ in range(7)]
    empty_menu.errors = []

    async def fake_fetch(cafs):
        return [(c["cafeteria_id"], None, "boom") for c in cafs]

    with (
        patch("src.main.fetch_all", side_effect=fake_fetch),
        patch("src.main.parse_cafeteria_page", return_value=empty_menu),
        patch("src.main.git_commit_and_push", return_value=True),
    ):
        result = await run_once(trigger_index=2, total_triggers=3)

    assert result == "failed_silent"
    state = json.loads((tmp_path / "data" / "state.json").read_text())
    assert state["status"] == "failed_silent"


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")
async def test_happy_path_publishes_to_notion_and_persists_state(tmp_path, monkeypatch):
    """Wire-level guard: when menus are non-empty, run_once calls NotionWriter.publish,
    persists state to 'done', and returns 'published'."""
    _seed(tmp_path, {"last_sent_week": None, "last_run_at": None, "status": "idle"})
    monkeypatch.setattr("src.main.DATA", tmp_path / "data")
    _set_notion_env(monkeypatch)

    non_empty_menu = MagicMock()
    non_empty_menu.days = [MagicMock(categories={"중식B": [MagicMock()]})]
    non_empty_menu.cafeteria_id = "science"
    non_empty_menu.errors = []

    # Real pydantic model — TranslatedWeeklyBundle validates its cafeterias list.
    translated = TranslatedCafeteriaMenu(
        cafeteria_id="science",
        cafeteria_name_ko="x", cafeteria_name_zh="x", cafeteria_name_en="x",
        week_start=date(2026, 4, 20), days=[],
        source_url="https://example.com",
        fetched_at=datetime(2026, 4, 20, 9, 0),
    )

    async def fake_fetch(cafs):
        return [(c["cafeteria_id"], "<html></html>", None) for c in cafs]

    translator_mock = MagicMock()
    translator_mock.translate_menu = AsyncMock(return_value=translated)

    writer_mock = AsyncMock()
    writer_mock.publish = AsyncMock(return_value={
        "meals_inserted": 10, "meals_updated": 0,
        "meals_failed": 0, "summary_page_url": "https://www.notion.so/x",
    })
    writer_mock.__aenter__ = AsyncMock(return_value=writer_mock)
    writer_mock.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("src.main.fetch_all", side_effect=fake_fetch),
        patch("src.main.parse_cafeteria_page", return_value=non_empty_menu),
        patch("src.main.DeepSeekClient"),
        patch("src.main.Translator", return_value=translator_mock),
        patch("src.main.NotionWriter", return_value=writer_mock),
        patch("src.main.git_commit_and_push", return_value=True),
    ):
        result = await run_once(trigger_index=0, total_triggers=3)

    assert result == "published"
    writer_mock.publish.assert_awaited_once()
    state = json.loads((tmp_path / "data" / "state.json").read_text())
    assert state["status"] == "done"
    assert state["last_sent_week"] == "2026-04-20"
