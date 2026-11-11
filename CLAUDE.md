# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"                          # install + test deps
pytest                                           # full suite (155 tests)
pytest tests/test_notion_writer.py -v            # single file
pytest tests/test_notion_writer.py::test_publish_happy_path -v   # single test
ruff check src tests                             # lint (fix with --fix)
python -m src.main --trigger-index 0 --total-triggers 3          # run pipeline locally
python -m src.main --dry-run                     # fetch+translate but skip Notion writes
```

Full suite runs in ~10s. Async tests use `pytest-asyncio` in `asyncio_mode = "auto"` (set in `pyproject.toml`), so no `@pytest.mark.asyncio` is needed on async test functions — they're picked up automatically. HTTP calls are mocked with `respx` throughout.

## Architecture

**Pipeline (orchestrated by `src/main.py::run_once`):**

```
fetch_all (httpx, tenacity retry) → parse_cafeteria_page (BS4 day-major rowspan state machine)
  → Translator.translate_menu (DeepSeek 2-pass: chat_json + chat_reflect, TranslationCache gated)
  → TranslatedWeeklyBundle (pydantic)
  → NotionWriter.publish: group_into_meals → upsert_meal per row → build_summary_page
  → cache.persist + state.persist + git_commit_and_push
```

**State machine (3-trigger cron at 10:30 / 11:00 / 11:15 KST Mon):** `data/state.json` holds `{last_sent_week, status}`. `status: done` short-circuits later triggers that day (`skipped_already_sent`). Empty menus on triggers 0-1 record `pending`; trigger 2 silently records `failed_silent` (no fallback email — deliberately silent).

**Meal-per-row Notion schema:** Each row is `(cafeteria × day × 午餐/晚餐)`, not per-dish. Composite title `YYYY-MM-DD Day · Cafeteria · Meal`. Dedup uses a composite filter on `(Week, Day, Cafeteria, Meal)` — `_find_existing` → PATCH if found, POST if not. This makes the whole pipeline idempotent across retries.

**Meal classification:** `classify_meal(category_ko)` routes any category containing `석식` to 晚餐, everything else to 午餐. `config.is_published_category` excludes breakfast and cafeteria-specific hidden meals both before translation and during meal grouping. Keep these filters consistent.

## Invariants that bite if violated

**Wire format for Notion requests.** `NotionWriter._http` serializes request bodies via `json.dumps(body, ensure_ascii=False).encode("utf-8")` + httpx `content=`, NOT httpx `json=`. The default `json=` ASCII-escapes CJK into `\uXXXX` sequences, which break readability when debugging requests via Notion's audit log. Tests assert literal CJK in the wire body AND that the Content-Type header stays `application/json` — don't "simplify" back to `json=`.

**Dish render contract.** `_render_dishes_text` emits `• 中文 ★ / English` per line — Korean is excluded by design (the user reads zh/en, not ko). `★` marks `is_new` dishes. Text truncates at `_DISHES_SOFT_LIMIT = 2000` (Notion rich_text limit) with a `… (+N more)` suffix. If `name_zh` is empty, falls back to `name_ko`.

**Retry semantics.** `_http` uses tenacity `wait_exponential(min=1, max=30)` on `_Retryable` (raised for 429/5xx). The `Retry-After` response header is LOGGED for observability but NOT honored — honoring it compounds with tenacity's own backoff and produces double-waits. If you add retry logic elsewhere, match this pattern.

**Publication success.** `NotionWriter.publish` skips the summary page for any failed meal, empty publication or upstream error. `run_once` marks `done` only when there are no upstream errors, at least one successful meal write, zero failed writes and a summary URL. Failure saves the translation cache, records `failed`, preserves `last_sent_week` and exits nonzero; later triggers retry through existing composite-key upserts. Dry-run bypasses the done check and never persists state or cache, commits or writes to Notion.

**Photo resolution.** `src/photos.resolve_photo_url` checks `data/photos/<cafeteria_id>/<slug>.<ext>` first (extensions tried in order: `jpg, jpeg, png, webp`). Local hits return a `raw.githubusercontent.com/...` URL. Only if local misses AND `unsplash_key` is set AND `name_en` is non-empty and not `"[translation failed]"` does it fall back to Unsplash. `slugify_ko` uses `python-slugify` with a `sha1()[:10]` fallback for pure-symbol names.

**Translation confidence levels.** `high` = pass-2 confirm or curated glossary entry, `medium` = valid pass-2 revision, `low` = uncertain or invalid review, `failed` = translation exception or invalid bilingual output. Low-confidence model cache entries are retranslated on the next run; explicit uncertain glossary entries retain their low confidence and Korean qualifier. `search_confirmed` is false for model review. Invalid compound-menu splits fail the cafeteria translation instead of being cached as single dishes. `_worst_confidence` in `notion_writer` uses `max` over an order dict so a single low dish tags the whole meal row as `low`.

**Storage discipline.** `data/translations.json` and `data/state.json` are committed back to the repo by the workflow (`git_commit_and_push` in `src/cache.py`). Don't add unbounded side-channel files; prefer recomputing from inputs. User photos live under `data/photos/` with `.gitkeep` sentinels per cafeteria; do not duplicate them on disk.

## Deferred item

`resolve_photo_url` is synchronous (`httpx.get` + filesystem) but called from async `NotionWriter.publish` via `group_into_meals`. This blocks the event loop during Unsplash lookups. Fix is to wrap the `group_into_meals` call in `asyncio.to_thread`. Not urgent — only matters when local photos miss AND Unsplash is configured.

## Key files

- `src/main.py` — `run_once` orchestrator, state machine, argparse CLI
- `src/notion_writer.py` — all Notion logic: types, meal grouping, block builders, HTTP plumbing, publish orchestration
- `src/translator.py` — two-pass DeepSeek pipeline with per-dish `asyncio.Semaphore`
- `src/parser.py` — BS4 state machine for day-major `<th rowspan>` cafeteria tables
- `src/photos.py` — slugify + local/Unsplash photo resolver
- `src/cache.py` — `TranslationCache`, `StateFile`, `git_commit_and_push` helper
- `src/models.py` — pydantic v2 schemas (`CafeteriaMenu`, `TranslatedWeeklyBundle`, etc.)
- `tests/conftest.py` + `tests/fixtures/` — shared HTML fixtures and pytest config
