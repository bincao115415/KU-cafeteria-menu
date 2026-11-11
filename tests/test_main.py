import json
from contextlib import ExitStack
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
    non_empty_menu.cafeteria_id = "science_student"
    non_empty_menu.errors = []

    # Real pydantic model — TranslatedWeeklyBundle validates its cafeterias list.
    translated = TranslatedCafeteriaMenu(
        cafeteria_id="science_student",
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


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    _seed(tmp_path, {"last_sent_week": "2026-04-13", "status": "done"})
    monkeypatch.setattr("src.main.DATA", tmp_path / "data")
    _set_notion_env(monkeypatch)
    raw = MagicMock()
    raw.days = [MagicMock(categories={"중식": [MagicMock()]})]
    raw.cafeteria_id = "science_student"
    translated = TranslatedCafeteriaMenu(
        cafeteria_id="science_student", cafeteria_name_ko="x",
        cafeteria_name_zh="x", cafeteria_name_en="x",
        week_start=date(2026, 4, 20), days=[], source_url="https://example.com",
        fetched_at=datetime(2026, 4, 20, 9, 0),
    )
    translator = MagicMock()
    translator.translate_menu = AsyncMock(return_value=translated)
    writer = AsyncMock()
    writer.__aenter__.return_value = writer
    writer.publish.return_value = {
        "meals_inserted": 0, "meals_updated": 10, "meals_failed": 0,
        "summary_page_url": "https://www.notion.so/summary",
    }
    fetch = AsyncMock(return_value=[("science_student", "<html/>", None)])
    with ExitStack() as stack:
        for target, value in {
            "fetch_all": fetch, "parse_cafeteria_page": MagicMock(return_value=raw),
            "DeepSeekClient": MagicMock(), "Translator": MagicMock(return_value=translator),
            "NotionWriter": MagicMock(return_value=writer),
            "git_commit_and_push": MagicMock(return_value=True),
        }.items():
            stack.enter_context(patch(f"src.main.{target}", value))
        yield {"writer": writer, "fetch": fetch, "translator": translator,
               "translated": translated, "data": tmp_path / "data"}


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")
@pytest.mark.parametrize("inserted,updated,failed,summary", [
    (0, 0, 10, None), (9, 0, 1, None),
    (9, 0, 1, "https://www.notion.so/incomplete"),
    (10, 0, 0, None), (0, 0, 0, "https://www.notion.so/empty"),
])
async def test_incomplete_publication_stays_retryable(pipeline, inserted, updated, failed, summary):
    pipeline["writer"].publish.return_value = {
        "meals_inserted": inserted, "meals_updated": updated,
        "meals_failed": failed, "summary_page_url": summary,
    }
    assert await run_once(trigger_index=0, total_triggers=3) == "publish_failed"
    state = json.loads((pipeline["data"] / "state.json").read_text())
    assert state["status"] == "failed"
    assert state["last_sent_week"] == "2026-04-13"


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")
async def test_failed_publish_retries_then_skips_only_after_success(pipeline):
    writer = pipeline["writer"]
    writer.publish.side_effect = [
        {"meals_inserted": 9, "meals_updated": 0, "meals_failed": 1,
         "summary_page_url": None},
        {"meals_inserted": 1, "meals_updated": 9, "meals_failed": 0,
         "summary_page_url": "https://www.notion.so/summary"},
    ]
    assert await run_once(trigger_index=0, total_triggers=3) == "publish_failed"
    assert await run_once(trigger_index=1, total_triggers=3) == "published"
    assert await run_once(trigger_index=2, total_triggers=3) == "skipped_already_sent"
    assert writer.publish.await_count == 2
    assert pipeline["fetch"].await_count == 2
    state = json.loads((pipeline["data"] / "state.json").read_text())
    assert state["status"] == "done"
    assert state["last_sent_week"] == "2026-04-20"


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")
async def test_publisher_exception_is_recorded_as_retryable(pipeline):
    pipeline["writer"].publish.side_effect = RuntimeError("Notion unavailable")
    assert await run_once(trigger_index=0, total_triggers=3) == "publish_failed"
    state = json.loads((pipeline["data"] / "state.json").read_text())
    assert state["status"] == "failed"
    assert state["last_sent_week"] == "2026-04-13"


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")
@pytest.mark.parametrize("failure", ["fetch", "translate", "dish"])
async def test_upstream_errors_do_not_publish_or_mark_done(pipeline, failure):
    if failure == "fetch":
        pipeline["fetch"].return_value.append(("anam", None, "timeout"))
    elif failure == "translate":
        pipeline["translator"].translate_menu.side_effect = RuntimeError("LLM unavailable")
    else:
        pipeline["translated"].errors = ["된장찌개: translation failed"]
    assert await run_once(trigger_index=0, total_triggers=3) == "publish_failed"
    pipeline["writer"].publish.assert_not_awaited()


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")
async def test_dry_run_does_not_mutate_state_or_publish(pipeline, monkeypatch):
    state_path = pipeline["data"] / "state.json"
    state_path.write_text(json.dumps({"last_sent_week": "2026-04-20", "status": "done"}))
    before = {p.name: p.read_bytes() for p in pipeline["data"].iterdir()}
    for name in ("NOTION_TOKEN", "NOTION_PARENT_PAGE_ID", "NOTION_DATABASE_ID"):
        monkeypatch.delenv(name)
    assert await run_once(trigger_index=0, total_triggers=3, dry_run=True) == "dry_run_ok"
    assert pipeline["fetch"].await_count == 1
    pipeline["writer"].publish.assert_not_awaited()
    assert before == {p.name: p.read_bytes() for p in pipeline["data"].iterdir()}


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")
async def test_empty_dry_run_does_not_change_state_or_commit(pipeline):
    state_path = pipeline["data"] / "state.json"
    before = state_path.read_bytes()
    pipeline["fetch"].return_value = [("science_student", None, "timeout")]
    with patch("src.main.git_commit_and_push") as commit:
        assert await run_once(trigger_index=2, total_triggers=3, dry_run=True) == "dry_run_failed"
    assert state_path.read_bytes() == before
    commit.assert_not_called()


@pytest.mark.parametrize("result,exit_code", [
    ("publish_failed", 1), ("failed_silent", 1), ("dry_run_failed", 1),
    ("published", 0), ("pending", 0), ("skipped_already_sent", 0),
])
def test_cli_reports_failures(result, exit_code):
    from src.main import main
    with patch("sys.argv", ["menu"]), patch("src.main.run_once", AsyncMock(return_value=result)):
        assert main() == exit_code
