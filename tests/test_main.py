import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.main import run_once


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
