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

### Database: `KU Cafeteria Dishes`

Parent: page `KU Cafeteria Menu` (`3490ee0039a180668d42d2a38cefafcf`).

| Property | Type | Notes |
|---|---|---|
| **Name** | Title | `name_zh` — Notion mandatory title |
| Name EN | Rich text | |
| Name KO | Rich text | Original Korean |
| Week | Date | Monday of the week (ISO date) — used for filter/sort |
| Day | Select | `Mon` / `Tue` / `Wed` / `Thu` / `Fri` |
| Cafeteria | Select | `科学` / `安岩` / `产学` / `校友` / `学生中心` (matches `cafeteria_name_zh` in `config.py`) |
| Meal | Select | `午餐` / `晚餐` |
| Category | Rich text | Original Korean category label (e.g., `중식B`, `파스타/스테이크 코스`) |
| Is New | Checkbox | `★ 新` — true when dish first appears in translations cache this run |
| Confidence | Select | `high` / `medium` / `low` / `failed` |
| Note | Rich text | Translator note (optional) |
| Photo | Files & media | External URL(s); first local, else Unsplash, else empty |
| Source URL | URL | Cafeteria page on korea.ac.kr |

### Meal classification rule

Input: Korean category string.
- If category starts with or contains `석식` → `晚餐`.
- Otherwise → `午餐`.
- Breakfast categories (`조식`, `천원의아침`, `아침`) are filtered out upstream by `_HIDDEN_CATEGORIES` and never reach Notion.

### Deduplication

Primary key for upsert: `(Week, Cafeteria, Day, Meal, Name KO)`.

Before inserting any row, query the DB for this tuple. If a row exists, update it (mainly to refresh `Photo`, `Is New`, `Confidence`). Otherwise create new. This makes re-running the same week's trigger idempotent and lets users re-run to pull in newly-uploaded photos.

### Weekly Summary Page

Created as a child of the parent page after all dishes are pushed. One page per week. Title: `YYYY/MM/DD 周菜单 · KU 食堂` (week's Monday date).

Layout (plain Notion blocks, no Linked Database view):

```
H1: 2026/04/20 周菜单 · KU 食堂
Callout: 本周新菜 213 道 · 5 个食堂
Divider

H2: 🏛 科学图书馆食堂 · Science Library Cafeteria
    📍 地址 · 🕒 时段 · [原始页面 →]
    H3: 🍚 午餐
        [toggle per day] Mon · 2026-04-20
            • 大酱汤 ★ / Soybean Paste Stew
            • 烤鸡胸 / Grilled Chicken Breast
            ... (Tue / Wed / Thu / Fri similarly)
    H3: 🌙 晚餐
        ... (same day toggles)

[... 4 more cafeterias, same structure ...]

Divider
Paragraph: 👉 全部菜品数据库 → [link to DB, filter by this Week]
Paragraph: 翻译由 DeepSeek 两轮反思验证 · 自动运行于每周一 10:30 KST
```

Day toggles are collapsed-by-default to keep the page scannable. Each toggle body is a bulleted list of `菜名中文 ★ / English Name` lines (the `★` only on new dishes).

If no dishes for a meal (cafeteria closed that day) → skip the toggle entirely. If no dishes at all for a cafeteria (parse empty) → still render the H2 header with an italic "本周该食堂未提供数据" line.

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
- `NOTION_DATABASE_ID` = (created programmatically once; value supplied after build).
- `UNSPLASH_ACCESS_KEY` = optional.
- Delete: `GMAIL_USERNAME`, `GMAIL_APP_PASSWORD`, `MAIL_TO`.

## Failure Behavior

User choice `c` (silent — inspect Actions UI):
- `trigger_index=0/1`: if scraping or translation fails → state → `pending`, exit 0.
- `trigger_index=2`: if still failing → log `ERROR` at INFO-visible level (`run_once → failed_no_data`), set state → `failed_silent`, exit 0. No email, no Notion page for the week. User sees it in Actions if they check.
- Notion API failures mid-run: log per-row ERROR, continue with remaining dishes; if >30% of rows fail, abort the summary page and set state → `failed_partial`.

## Module Interfaces

### `src/aggregator.py` (renamed from `renderer.py`)

```python
def build_weekly_data(
    cafeterias: list[CafeteriaConfig],
    parsed: dict[str, ParsedMenu],
    translations: Translations,
    week_monday: date,
) -> WeeklyData: ...
```

Returns a typed dict:
```python
class DayDishes(TypedDict):
    day: Literal["Mon", "Tue", "Wed", "Thu", "Fri"]
    date: date
    lunch: list[DishRow]     # post-meal-classification
    dinner: list[DishRow]

class CafeteriaWeek(TypedDict):
    cafeteria_id: str
    name_zh: str
    name_en: str
    address: str
    hours: str
    source_url: str
    days: list[DayDishes]
    errors: list[str]

class WeeklyData(TypedDict):
    week_monday: date
    week_label: str
    new_dish_count: int
    cafeterias: list[CafeteriaWeek]
    global_errors: list[str]
```

### `src/notion_writer.py`

```python
class NotionWriter:
    def __init__(self, token: str, database_id: str, parent_page_id: str,
                 repo_slug: str = "bincao115415/KU-cafeteria-menu"): ...

    async def publish(self, data: WeeklyData) -> PublishResult:
        """Upserts all dishes into the DB, then creates/updates the weekly summary page.
        Returns PublishResult{ dishes_inserted: int, dishes_updated: int,
                               dishes_failed: int, summary_page_url: str | None }."""

    async def upsert_dish(self, dish: DishRow) -> Literal["inserted", "updated", "failed"]: ...

    async def build_summary_page(self, data: WeeklyData) -> str:
        """Returns the created page URL."""
```

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

- `tests/test_aggregator.py`: meal classification, new-dish counting, empty-day skip, rename from `test_renderer.py`.
- `tests/test_photos.py`: slug correctness, local file hit, Unsplash miss returns None, Unsplash key absent skips search.
- `tests/test_notion_writer.py`: upsert hits both insert and update paths (respx-mocked query returns empty vs. returns existing page), 429 retry, batch failure → `failed_partial` state.
- Delete: `tests/test_mailer.py`, `tests/test_renderer.py`.
- Update: `tests/test_main.py`, `tests/test_config.py`.

Target: maintain current ~63 test count (some tests will be replaced rather than added).

## Dependencies

- **Remove**: `premailer`, `jinja2` (only used for email template).
- **Add**: `python-slugify` (for Korean slugify).
- **Keep**: `httpx`, `beautifulsoup4`, `lxml`, `pydantic`, `tenacity`, `python-dateutil`.

## Migration / Rollout

1. **This conversation**: build the database programmatically via REST (using the user's token in chat) and capture its `database_id`. Give the user the ID to add to GitHub Secrets.
2. **Implementation**: ship code changes; tests green; ruff clean.
3. **First run**: manual `workflow_dispatch` with `trigger_index=2` to force a push. Verify dishes appear in DB + summary page created.
4. **Cron takeover**: next Monday, normal cron fires and runs against Notion.

## Out of Scope

- Multi-week archive browsing UI (Notion can do this via database views — user configures manually after first run).
- Dish categorization beyond lunch/dinner split.
- Image optimization pipeline (user is responsible for ensuring uploaded photos are reasonable size; we only enforce a 200KB advisory warning in a pre-commit hook, not a hard block).
- Notifications of failure beyond Actions UI (user chose silent mode).
