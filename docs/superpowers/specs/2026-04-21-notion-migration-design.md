# Notion Migration Design

**Date:** 2026-04-21
**Status:** Approved (pending user review of this doc)

## Goal

Replace Gmail email delivery with Notion publishing. Each Monday, push the weekly menu to a Notion database (one row per dish) and auto-generate a human-readable weekly summary page. Dish photos use a hybrid strategy: user-uploaded local JPGs first, then Unsplash search as fallback.

## Architecture

Unchanged:
- Scraper (`src/scraper.py`), cafeteria parser (`src/cafeteria_parser.py`), DeepSeek translator (`src/translator.py` + `src/deepseek_client.py`), translations cache (`data/translations.json`), state machine (`data/state.json`), weekly GitHub Actions cron (Mon 10:30 / 11:00 / 11:15 KST), 3-slot retry fallback (`trigger_index=0/1/2`).

Replaced:
- Email pipeline (`src/mailer.py` + `templates/email.html.j2` + `premailer` dep) → Notion pipeline (`src/notion_writer.py`).
- HTML aggregation in `src/renderer.py` → data-shape aggregation in `src/aggregator.py` (rename + gut Jinja).

Added:
- `src/photos.py` — photo resolution (local disk → Unsplash → None).
- `data/photos/<cafeteria_id>/<slug>.jpg` tree — user-uploaded photos, committed to repo, served via `raw.githubusercontent.com`.

## Notion Data Model

### Database: `KU Cafeteria Meals`

Parent: page `KU Cafeteria Menu` (`3490ee0039a180668d42d2a38cefafcf`).
Database ID: `3490ee00-39a1-81e9-9647-dabd41cdf713`.

**Row granularity: one meal (cafeteria × day × lunch-or-dinner).** One week = up to 5 cafeterias × 5 days × 2 meals = 50 rows. Individual dishes are listed inside the `Dishes` rich-text column, grouped by their original Korean category label.

Intended column order (Name is forced leftmost by Notion; remaining order set via the API request but Notion may re-shuffle in the UI — user drags once to finalize):

| Property | Type | Notes |
|---|---|---|
| **Name** | Title | Composite: `YYYY-MM-DD Day · Cafeteria · Meal` (e.g., `2026-04-20 Mon · 科学 · 午餐`) |
| Week | Date | Monday of the week (ISO date) — primary filter/sort axis |
| Day | Select | `Mon` / `Tue` / `Wed` / `Thu` / `Fri` |
| Cafeteria | Select | `科学` / `安岩` / `产学` / `校友` / `学生中心` (matches `cafeteria_name_zh` in `config.py`) |
| Meal | Select | `午餐` / `晚餐` |
| Photo | Files & media | Multiple external URLs (one per dish in the meal); local disk → Unsplash → skip per dish |
| Dishes | Rich text | Multi-line body. Each category renders as `【<Korean category>】` header, then one `• 中文 ★ / English` line per dish (the `★` only on new dishes) |
| Dish Count | Number | Total dishes in this meal |
| New Count | Number | Dishes first seen in the translations cache this run |
| Confidence | Select | Worst-case across the meal: `high` if all dishes high; `medium`/`low`/`failed` if any dish falls to that level |
| Source URL | URL | Cafeteria page on korea.ac.kr |

### Meal classification rule

Input: Korean category string.
- If category starts with or contains `석식` → `晚餐`.
- Otherwise → `午餐`.
- Breakfast categories (`조식`, `천원의아침`, `아침`) are filtered out upstream by `_HIDDEN_CATEGORIES` and never reach Notion.

### Dishes field format

```
【중식B】
• 大酱汤 ★ / Soybean Paste Stew
• 米饭 / Rice
• 烤鸡胸 / Grilled Chicken Breast

【반찬】
• 泡菜 / Kimchi
• 凉拌菠菜 / Seasoned Spinach
```

Rendered as a single `rich_text` property. Notion caps rich-text property size at 2000 characters per request; if a meal exceeds this (very rare — our worst observed meal has ~15 dishes ≈ 500 chars), truncate with `… (+N more)` and log WARN.

### Deduplication

Primary key for upsert: `(Week, Cafeteria, Day, Meal)`.

Before inserting any row, query the DB with a composite filter on these four fields. If a row exists, update it (refreshes `Dishes`, `Photo`, `New Count`, `Confidence`). Otherwise create new. This makes re-running the same week's trigger idempotent and lets users re-run to pull in newly-uploaded photos.

### Weekly Summary Page

Created as a child of the parent page after all meal rows are upserted. One page per week. Title: `YYYY/MM/DD 周菜单 · KU 食堂` (week's Monday date).

Layout (plain Notion blocks, no Linked Database view):

```
H1: 2026/04/20 周菜单 · KU 食堂
Callout: 本周新菜 213 道 · 5 个食堂
Divider

H2: 🏛 科学图书馆食堂 · Science Library Cafeteria
    📍 地址 · 🕒 时段 · [原始页面 →]
    H3: 🍚 午餐
        [toggle per day] Mon · 2026-04-20
            【중식B】
            • 大酱汤 ★ / Soybean Paste Stew
            • 烤鸡胸 / Grilled Chicken Breast
            【반찬】
            • 泡菜 / Kimchi
            ... (Tue / Wed / Thu / Fri similarly)
    H3: 🌙 晚餐
        ... (same day toggles)

[... 4 more cafeterias, same structure ...]

Divider
Paragraph: 👉 全部餐次数据库 → [link to DB, filter by this Week]
Paragraph: 翻译由 DeepSeek 两轮反思验证 · 自动运行于每周一 10:30 KST
```

Day toggles are collapsed-by-default to keep the page scannable. Each toggle body mirrors the `Dishes` rich-text column: one `【Korean category】` heading per category, then `• 中文 ★ / English` bullets (the `★` only on new dishes).

If no meal data for a day (cafeteria closed that day) → skip the toggle entirely. If no data at all for a cafeteria (parse empty) → still render the H2 header with an italic "本周该食堂未提供数据" line.

### Rollover: old summary pages

Accumulate indefinitely under the parent page. User can manually archive old weeks. No automatic cleanup for now.

## Photo Resolution

`photos.resolve_photo_url(cafeteria_id, name_ko, name_en) -> str | None`:

1. Compute `slug = slugify(name_ko)` using `python-slugify` with the `ko` locale; if result is empty, fall back to `sha1(name_ko)[:10]`.
2. Check `data/photos/<cafeteria_id>/<slug>.{jpg,jpeg,png,webp}`.
   - If present → return `https://raw.githubusercontent.com/bincao115415/KU-cafeteria-menu/main/data/photos/<cafeteria_id>/<slug>.<ext>`.
3. Else, if `UNSPLASH_ACCESS_KEY` env is set:
   - Query `https://api.unsplash.com/search/photos?query=<name_en> korean cafeteria food&per_page=1&orientation=landscape`.
   - On hit → return the `urls.regular` link (Unsplash CDN-hosted).
   - On miss or HTTP error → return `None` (logged at WARN).
4. Else → return `None` (logged at DEBUG).

Cache of successful Unsplash hits lives in-memory for the run only (no disk cache — avoids stale links; re-run is cheap since Unsplash free tier = 50 req/hr, well above our ~200-dish cap).

## Configuration Changes

`src/config.py` `Settings`:
- **Remove**: `gmail_username`, `gmail_app_password`, `mail_to`.
- **Add**: `notion_token`, `notion_parent_page_id`, `notion_database_id`, `unsplash_access_key` (optional, default `None`).
- `load_settings()` raises `RuntimeError` for missing `NOTION_TOKEN`, `NOTION_PARENT_PAGE_ID`, `NOTION_DATABASE_ID`; `UNSPLASH_ACCESS_KEY` is optional.

`.github/workflows/weekly_menu.yml` `env:`:
- **Remove**: `GMAIL_USERNAME`, `GMAIL_APP_PASSWORD`, `MAIL_TO`.
- **Add**: `NOTION_TOKEN`, `NOTION_PARENT_PAGE_ID`, `NOTION_DATABASE_ID`, `UNSPLASH_ACCESS_KEY`.

GitHub Secrets to set (user action):
- `NOTION_TOKEN` = `ntn_...` (the integration token).
- `NOTION_PARENT_PAGE_ID` = `3490ee0039a180668d42d2a38cefafcf`.
- `NOTION_DATABASE_ID` = `3490ee00-39a1-81e9-9647-dabd41cdf713` (created programmatically; set in GitHub Secrets).
- `UNSPLASH_ACCESS_KEY` = optional.
- Delete: `GMAIL_USERNAME`, `GMAIL_APP_PASSWORD`, `MAIL_TO`.

## Failure Behavior

User choice `c` (silent — inspect Actions UI):
- `trigger_index=0/1`: if scraping or translation fails → state → `pending`, exit 0.
- `trigger_index=2`: if still failing → log `ERROR` at INFO-visible level (`run_once → failed_no_data`), set state → `failed_silent`, exit 0. No email, no Notion page for the week. User sees it in Actions if they check.
- Notion API failures mid-run: log per-meal ERROR, continue with remaining meals; if >30% of meal upserts fail, abort the summary page and set state → `failed_partial`.

## Module Interfaces

Aggregation (grouping translated dishes into meals) now lives inside `notion_writer.py` — no separate `aggregator` module. `src/renderer.py` is deleted outright rather than renamed.

### `src/notion_writer.py`

```python
class MealRow(TypedDict):
    week_monday: date
    day: Literal["Mon", "Tue", "Wed", "Thu", "Fri"]
    date: date
    cafeteria_id: str
    cafeteria_zh: str
    meal: Literal["午餐", "晚餐"]
    categories: list[CategoryBlock]  # ordered by first appearance in parsed menu
    dish_count: int
    new_count: int
    confidence: Literal["high", "medium", "low", "failed"]
    source_url: str

class CategoryBlock(TypedDict):
    label_ko: str                     # e.g., "중식B"
    dishes: list[DishLine]

class DishLine(TypedDict):
    name_ko: str
    name_zh: str
    name_en: str
    is_new: bool
    photo_url: str | None

class PublishResult(TypedDict):
    meals_inserted: int
    meals_updated: int
    meals_failed: int
    summary_page_url: str | None

class NotionWriter:
    def __init__(
        self,
        token: str,
        database_id: str,
        parent_page_id: str,
        repo_slug: str = "bincao115415/KU-cafeteria-menu",
        unsplash_key: str | None = None,
    ): ...

    async def publish(self, bundle: TranslatedWeeklyBundle) -> PublishResult:
        """Groups dishes into meals, resolves photos, upserts all meal rows into the DB,
        then creates the weekly summary page. Returns counts + summary page URL."""

    async def upsert_meal(self, meal: MealRow) -> Literal["inserted", "updated", "failed"]:
        """Query DB by (Week, Cafeteria, Day, Meal); update if present, else insert."""

    async def build_summary_page(
        self,
        bundle: TranslatedWeeklyBundle,
        meals: list[MealRow],
    ) -> str:
        """Creates the weekly summary page under the parent. Returns the page URL."""
```

Internally `publish()` does the grouping: iterate `bundle.cafeterias → days → categories`, filter `_HIDDEN_CATEGORIES`, classify each category to `午餐`/`晚餐` by presence of `석식`, collect into `MealRow` keyed by `(cafeteria_id, day, meal)`. Photo resolution happens per dish via `src/photos.py` before writing.

Uses `httpx.AsyncClient` directly (no `notion-client` dep — keeps stack minimal).
Auth: `Bearer {token}`, `Notion-Version: 2022-06-28`.
Rate-limit handling: retry on HTTP 429 with `Retry-After` header; tenacity with `retry_if_exception_type((httpx.HTTPError,))`.

### `src/photos.py`

```python
def slugify_ko(name_ko: str) -> str: ...

def resolve_photo_url(
    cafeteria_id: str,
    name_ko: str,
    name_en: str,
    data_dir: Path = DATA,
    unsplash_key: str | None = None,
    repo_slug: str = "bincao115415/KU-cafeteria-menu",
) -> str | None: ...
```

## Testing

Follow existing test style (pytest-asyncio + respx + freezegun):

- `tests/test_photos.py`: slug correctness (including Korean-only fallback to sha1), local file hit, Unsplash miss returns None, Unsplash key absent skips search.
- `tests/test_notion_writer.py`:
  - Meal grouping: `TranslatedWeeklyBundle` → list of `MealRow` with correct 午餐/晚餐 split, hidden categories filtered, new-count aggregation, confidence downgrading.
  - Dishes rich-text rendering: categories grouped with `【...】` header, `★` only on new dishes, 2000-char truncation with `… (+N more)`.
  - `upsert_meal` hits both insert and update paths (respx-mocked composite-filter query returns empty vs. returns existing page).
  - 429 retry honors `Retry-After` header.
  - Partial-failure threshold: >30% meal-upsert failures → `failed_partial`, summary page skipped.
  - Summary page builder emits valid block tree (H1, callout, H2 per cafeteria, H3 per meal, toggle per day).
- Delete: `tests/test_mailer.py`, `tests/test_renderer.py`.
- Update: `tests/test_main.py`, `tests/test_config.py`.

Target: maintain current ~63 test count (renderer/mailer tests replaced by notion_writer + photos tests).

## Dependencies

- **Remove**: `premailer`, `jinja2` (only used for email template).
- **Add**: `python-slugify` (for Korean slugify).
- **Keep**: `httpx`, `beautifulsoup4`, `lxml`, `pydantic`, `tenacity`, `python-dateutil`.

## Migration / Rollout

1. **Done**: database created (`3490ee00-39a1-81e9-9647-dabd41cdf713`); `NOTION_TOKEN`, `NOTION_PARENT_PAGE_ID`, `NOTION_DATABASE_ID` set in GitHub Secrets; old Gmail secrets deleted.
2. **User action (one-time)**: open the new Notion DB and drag columns into the intended order (the Notion REST API does not reliably set view column order on create). Target order: `Name → Week → Day → Cafeteria → Meal → Photo → Dishes → Dish Count → New Count → Confidence → Source URL`.
3. **Implementation**: ship code changes; tests green; ruff clean.
4. **First run**: manual `workflow_dispatch` with `trigger_index=2` to force a push. Verify meal rows appear in DB + summary page created.
5. **Cron takeover**: next Monday, normal cron fires and runs against Notion.

## Out of Scope

- Multi-week archive browsing UI (Notion can do this via database views — user configures manually after first run).
- Dish categorization beyond lunch/dinner split.
- Image optimization pipeline (user is responsible for ensuring uploaded photos are reasonable size; we only enforce a 200KB advisory warning in a pre-commit hook, not a hard block).
- Notifications of failure beyond Actions UI (user chose silent mode).
