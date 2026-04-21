# Notion Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Gmail email delivery with Notion publishing — one row per **meal** (cafeteria × day × lunch/dinner) containing a categorized list of dishes, plus an auto-generated weekly summary page. Add a hybrid photo resolution pipeline (local upload first, Unsplash fallback).

**Architecture:** Keep all scraping / translation / cache / state logic and the existing `TranslatedWeeklyBundle` pydantic model. Swap the last-mile delivery: `render_email(bundle) + send_mail(...)` → `NotionWriter.publish(bundle)`. Meal grouping (dish → meal row) lives inside `notion_writer.py`. Add `src/photos.py` for photo URL resolution. Delete `src/mailer.py`, `src/renderer.py`, `templates/email.html.j2`.

**Tech Stack:** Python 3.11, httpx (async, Notion REST direct — no `notion-client` lib), tenacity (retry/backoff), python-slugify (new, Korean→slug), respx (test HTTP mocks), freezegun, pytest-asyncio.

**Reference spec:** `docs/superpowers/specs/2026-04-21-notion-migration-design.md`.

**Notion resources (already provisioned):**
- Parent page ID: `3490ee0039a180668d42d2a38cefafcf`
- Database ID: `3490ee00-39a1-81e9-9647-dabd41cdf713` (meal-per-row schema)
- GitHub repo: `bincao115415/KU-cafeteria-menu`
- GH Secrets: `NOTION_TOKEN`, `NOTION_PARENT_PAGE_ID`, `NOTION_DATABASE_ID`, `DEEPSEEK_API_KEY` all set; Gmail secrets removed.

---

## File Map

**New:**
- `src/photos.py` — slug + local lookup + Unsplash search
- `src/notion_writer.py` — types + meal grouping + NotionWriter (upsert, summary page, publish)
- `tests/test_photos.py`
- `tests/test_notion_writer.py`
- `data/photos/<cafeteria_id>/.gitkeep` for 5 cafeterias (science, anam, sanhak, alumni, student_center)

**Modified:**
- `src/config.py` — add Notion/Unsplash fields; drop Gmail fields (Task 8)
- `src/main.py` — swap mailer+renderer for NotionWriter; silent failure (Task 8)
- `pyproject.toml` — add `python-slugify`, drop `premailer`+`jinja2` (Tasks 1, 9)
- `.github/workflows/weekly_menu.yml` — swap env vars (Task 9)
- `README.md` — describe Notion output + photo workflow (Task 9)
- `tests/test_config.py`, `tests/test_main.py` — updated env / interfaces (Tasks 1, 8)

**Deleted:**
- `src/mailer.py`, `src/renderer.py`, `templates/email.html.j2`, `tests/test_mailer.py`, `tests/test_renderer.py` (Task 9)

---

## Task 1: Add `python-slugify` dep + Notion/Unsplash fields to `Settings` (non-breaking)

Keep Gmail fields for now (still used by main.py until Task 8). Add Notion fields as **required**, `unsplash_access_key` as **optional**.

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add `python-slugify` to pyproject**

Edit `pyproject.toml` — under `[project].dependencies` append:
```toml
    "python-slugify>=8.0",
```

- [ ] **Step 2: Install and verify**

Run: `pip install -e .`
Expected: `python-slugify` appears in `pip list`.

- [ ] **Step 3: Write failing test for new Settings fields**

Edit `tests/test_config.py`, add:
```python
def test_load_settings_with_notion_fields(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dk")
    monkeypatch.setenv("GMAIL_USERNAME", "u@x")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "p")
    monkeypatch.setenv("MAIL_TO", "to@x")
    monkeypatch.setenv("NOTION_TOKEN", "ntn_x")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "pid")
    monkeypatch.setenv("NOTION_DATABASE_ID", "dbid")

    from src.config import load_settings
    s = load_settings()
    assert s.notion_token == "ntn_x"
    assert s.notion_parent_page_id == "pid"
    assert s.notion_database_id == "dbid"
    assert s.unsplash_access_key is None  # optional, default None


def test_load_settings_with_unsplash(monkeypatch):
    for k, v in {
        "DEEPSEEK_API_KEY": "dk",
        "GMAIL_USERNAME": "u@x",
        "GMAIL_APP_PASSWORD": "p",
        "MAIL_TO": "to@x",
        "NOTION_TOKEN": "ntn_x",
        "NOTION_PARENT_PAGE_ID": "pid",
        "NOTION_DATABASE_ID": "dbid",
        "UNSPLASH_ACCESS_KEY": "us_key",
    }.items():
        monkeypatch.setenv(k, v)
    from src.config import load_settings
    assert load_settings().unsplash_access_key == "us_key"


def test_load_settings_missing_notion_token_raises(monkeypatch):
    for k, v in {
        "DEEPSEEK_API_KEY": "dk",
        "GMAIL_USERNAME": "u@x",
        "GMAIL_APP_PASSWORD": "p",
        "MAIL_TO": "to@x",
        "NOTION_PARENT_PAGE_ID": "pid",
        "NOTION_DATABASE_ID": "dbid",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    from src.config import load_settings
    import pytest
    with pytest.raises(RuntimeError, match="NOTION_TOKEN"):
        load_settings()
```

- [ ] **Step 4: Run tests, verify failure**

Run: `pytest tests/test_config.py -v`
Expected: three tests fail (`AttributeError: Settings has no attribute 'notion_token'`).

- [ ] **Step 5: Update `src/config.py`**

Replace the `Settings` dataclass and `load_settings()` with:

```python
import os
from dataclasses import dataclass

# CAFETERIAS list unchanged — keep as is.

@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    gmail_username: str
    gmail_app_password: str
    mail_to: str
    notion_token: str
    notion_parent_page_id: str
    notion_database_id: str
    unsplash_access_key: str | None = None


def load_settings() -> Settings:
    def req(key: str) -> str:
        v = os.environ.get(key)
        if not v:
            raise RuntimeError(f"Missing required env var: {key}")
        return v

    return Settings(
        deepseek_api_key=req("DEEPSEEK_API_KEY"),
        gmail_username=req("GMAIL_USERNAME"),
        gmail_app_password=req("GMAIL_APP_PASSWORD"),
        mail_to=req("MAIL_TO"),
        notion_token=req("NOTION_TOKEN"),
        notion_parent_page_id=req("NOTION_PARENT_PAGE_ID"),
        notion_database_id=req("NOTION_DATABASE_ID"),
        unsplash_access_key=os.environ.get("UNSPLASH_ACCESS_KEY") or None,
    )
```

- [ ] **Step 6: Run all tests, verify pass**

Run: `pytest tests/test_config.py -v`
Expected: all pass.
Run: `pytest` (full suite)
Expected: all existing tests still pass (we didn't break anything).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/config.py tests/test_config.py
git commit -m "feat(config): add Notion + Unsplash settings fields"
```

---

## Task 2: `src/photos.py` — slugify + local file lookup

Resolves a dish photo to an `https://raw.githubusercontent.com/...` URL when the user has uploaded a file at `data/photos/<cafeteria_id>/<slug>.<ext>`. Unsplash fallback comes in Task 3.

**Files:**
- Create: `src/photos.py`
- Create: `tests/test_photos.py`

- [ ] **Step 1: Write failing test for slugify + local hit**

Create `tests/test_photos.py`:
```python
from pathlib import Path

from src.photos import resolve_photo_url, slugify_ko


def test_slugify_ko_produces_ascii_slug():
    # Korean is transliterable by python-slugify
    result = slugify_ko("된장찌개")
    assert result
    assert all(c.isalnum() or c == "-" for c in result)


def test_slugify_ko_falls_back_to_sha1_on_empty():
    # python-slugify returns empty for pure-symbol strings
    result = slugify_ko("※★※")
    assert len(result) == 10
    assert all(c in "0123456789abcdef" for c in result)


def test_resolve_local_hit_returns_raw_github_url(tmp_path):
    cafe_dir = tmp_path / "photos" / "science"
    cafe_dir.mkdir(parents=True)
    slug = slugify_ko("된장찌개")
    (cafe_dir / f"{slug}.jpg").write_bytes(b"\xff\xd8\xff")  # fake jpg

    url = resolve_photo_url(
        "science", "된장찌개", "Soybean Paste Stew",
        data_dir=tmp_path,
        repo_slug="bincao115415/KU-cafeteria-menu",
    )
    assert url == (
        f"https://raw.githubusercontent.com/bincao115415/KU-cafeteria-menu/"
        f"main/photos/science/{slug}.jpg"
    )


def test_resolve_local_miss_no_key_returns_none(tmp_path):
    (tmp_path / "photos" / "science").mkdir(parents=True)
    url = resolve_photo_url(
        "science", "없는음식", "Nonexistent",
        data_dir=tmp_path,
    )
    assert url is None


def test_resolve_tries_multiple_extensions(tmp_path):
    cafe_dir = tmp_path / "photos" / "anam"
    cafe_dir.mkdir(parents=True)
    slug = slugify_ko("김치")
    (cafe_dir / f"{slug}.webp").write_bytes(b"RIFF")
    url = resolve_photo_url(
        "anam", "김치", "Kimchi",
        data_dir=tmp_path,
        repo_slug="bincao115415/KU-cafeteria-menu",
    )
    assert url and url.endswith(f"{slug}.webp")
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/test_photos.py -v`
Expected: `ModuleNotFoundError: No module named 'src.photos'`.

- [ ] **Step 3: Implement `src/photos.py` (local lookup only)**

Create `src/photos.py`:
```python
import hashlib
import logging
from pathlib import Path

from slugify import slugify

log = logging.getLogger(__name__)

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

_PHOTO_EXTS = ("jpg", "jpeg", "png", "webp")


def slugify_ko(name_ko: str) -> str:
    """Slug a Korean dish name. Falls back to sha1[:10] if transliteration yields empty."""
    s = slugify(name_ko, lowercase=True)
    if s:
        return s
    return hashlib.sha1(name_ko.encode("utf-8")).hexdigest()[:10]


def resolve_photo_url(
    cafeteria_id: str,
    name_ko: str,
    name_en: str,
    *,
    data_dir: Path = DATA,
    unsplash_key: str | None = None,
    repo_slug: str = "bincao115415/KU-cafeteria-menu",
) -> str | None:
    """Return a photo URL for a dish: local file first, Unsplash fallback, else None."""
    slug = slugify_ko(name_ko)
    cafe_dir = data_dir / "photos" / cafeteria_id
    for ext in _PHOTO_EXTS:
        candidate = cafe_dir / f"{slug}.{ext}"
        if candidate.exists():
            # data_dir may be `<repo>/data` (real) or a tmp_path (test). We want
            # the path relative to the repo root so the URL works on github.
            rel = candidate.relative_to(data_dir.parent) if candidate.is_absolute() else candidate
            return f"https://raw.githubusercontent.com/{repo_slug}/main/{rel.as_posix()}"

    if unsplash_key:
        # Task 3 fills this in
        return None
    log.debug("no local photo for %s/%s (slug=%s); no unsplash key", cafeteria_id, name_ko, slug)
    return None
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_photos.py -v`
Expected: all 5 tests pass.

Note on test `test_resolve_local_hit_returns_raw_github_url`: `data_dir=tmp_path` means photos live at `tmp_path/photos/science/<slug>.jpg`. `candidate.relative_to(data_dir.parent)` yields `<basename-of-tmp_path>/photos/science/<slug>.jpg`, which does NOT match the expected URL. **Fix before commit**: compute the relative part differently.

Update `resolve_photo_url` to build the URL from the known structure rather than `relative_to`:
```python
    for ext in _PHOTO_EXTS:
        candidate = cafe_dir / f"{slug}.{ext}"
        if candidate.exists():
            return (
                f"https://raw.githubusercontent.com/{repo_slug}/main/"
                f"photos/{cafeteria_id}/{slug}.{ext}"
            )
```

(Using `photos/` as the in-repo path — user will commit photos under `data/photos/<id>/` and the URL segment in the raw.github URL is `data/photos/<id>/` on prod, but test uses `photos/` sub-path under tmp_path. To align: put photos under `data/photos/<id>/` in real repo, and tests use `data_dir=tmp_path`, so local disk path is `tmp_path/photos/<id>/`. The raw github path for production is `data/photos/<id>/<slug>.<ext>`. Tests assert `main/photos/science/...`.) Align path prefix between test expectation and implementation:

Final choice: local disk structure is `<data_dir>/photos/<cafeteria_id>/<slug>.<ext>` (already what tests create), and URL is `https://raw.githubusercontent.com/<repo_slug>/main/data/photos/<cafeteria_id>/<slug>.<ext>`. Update tests' expected URL to include `/main/data/photos/...` and keep the implementation using that prefix:

```python
            return (
                f"https://raw.githubusercontent.com/{repo_slug}/main/"
                f"data/photos/{cafeteria_id}/{slug}.{ext}"
            )
```

And update the test expected string to `f"https://raw.githubusercontent.com/bincao115415/KU-cafeteria-menu/main/data/photos/science/{slug}.jpg"`.

Rerun: `pytest tests/test_photos.py -v` — all pass.

- [ ] **Step 5: Commit**

```bash
git add src/photos.py tests/test_photos.py
git commit -m "feat(photos): resolve dish photos from local data/photos tree"
```

---

## Task 3: `src/photos.py` — Unsplash fallback

When `unsplash_key` is provided and no local photo exists, query `api.unsplash.com/search/photos`.

**Files:**
- Modify: `src/photos.py`
- Modify: `tests/test_photos.py`

- [ ] **Step 1: Write failing tests for Unsplash path**

Append to `tests/test_photos.py`:
```python
import httpx
import pytest
import respx


@respx.mock
def test_resolve_unsplash_hit(tmp_path):
    (tmp_path / "photos" / "science").mkdir(parents=True)
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(200, json={
            "results": [{"urls": {"regular": "https://images.unsplash.com/photo-xyz"}}]
        })
    )
    url = resolve_photo_url(
        "science", "된장찌개", "Soybean Paste Stew",
        data_dir=tmp_path, unsplash_key="us_key",
    )
    assert url == "https://images.unsplash.com/photo-xyz"


@respx.mock
def test_resolve_unsplash_miss_returns_none(tmp_path):
    (tmp_path / "photos" / "science").mkdir(parents=True)
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    url = resolve_photo_url(
        "science", "없는메뉴", "Unknown",
        data_dir=tmp_path, unsplash_key="us_key",
    )
    assert url is None


@respx.mock
def test_resolve_unsplash_http_error_returns_none(tmp_path):
    (tmp_path / "photos" / "science").mkdir(parents=True)
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(500)
    )
    url = resolve_photo_url(
        "science", "아무거나", "Anything",
        data_dir=tmp_path, unsplash_key="us_key",
    )
    assert url is None


def test_resolve_local_takes_precedence_over_unsplash(tmp_path):
    # Local file present — Unsplash must NOT be called.
    cafe_dir = tmp_path / "photos" / "science"
    cafe_dir.mkdir(parents=True)
    slug = slugify_ko("된장찌개")
    (cafe_dir / f"{slug}.jpg").write_bytes(b"\xff\xd8\xff")
    with respx.mock() as mock:
        route = mock.get("https://api.unsplash.com/search/photos").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        url = resolve_photo_url(
            "science", "된장찌개", "Soybean Paste Stew",
            data_dir=tmp_path, unsplash_key="us_key",
        )
        assert not route.called
    assert url and url.endswith(".jpg")
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/test_photos.py -v -k unsplash`
Expected: three tests fail (Unsplash never called; returns `None`).

- [ ] **Step 3: Add Unsplash search to `src/photos.py`**

Insert before the `resolve_photo_url` call to Unsplash:
```python
import httpx


def _search_unsplash(query: str, access_key: str) -> str | None:
    try:
        resp = httpx.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query": query,
                "per_page": 1,
                "orientation": "landscape",
            },
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=10.0,
        )
    except httpx.HTTPError as e:
        log.warning("unsplash request failed: %s", e)
        return None
    if resp.status_code != 200:
        log.warning("unsplash %s: %s", resp.status_code, resp.text[:200])
        return None
    data = resp.json()
    results = data.get("results") or []
    if not results:
        return None
    return results[0].get("urls", {}).get("regular")
```

And in `resolve_photo_url`, replace the `if unsplash_key: return None` stub with:
```python
    if unsplash_key:
        query = f"{name_en} korean cafeteria food"
        hit = _search_unsplash(query, unsplash_key)
        if hit:
            return hit
        log.warning("unsplash miss for %s (query=%r)", name_ko, query)
        return None
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_photos.py -v`
Expected: all 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/photos.py tests/test_photos.py
git commit -m "feat(photos): add Unsplash fallback when no local file exists"
```

---

## Task 4: `src/notion_writer.py` — types, meal grouping, HTTP plumbing

Build the type system and the pure-function `group_into_meals` that collapses `TranslatedWeeklyBundle` into `MealRow` records. Also stub the async HTTP client wrapper with 429/5xx retry.

**Files:**
- Create: `src/notion_writer.py`
- Create: `tests/test_notion_writer.py`

- [ ] **Step 1: Write failing tests for meal grouping**

Create `tests/test_notion_writer.py`:
```python
from datetime import date, datetime

from src.models import (
    DishTranslated,
    TranslatedCafeteriaMenu,
    TranslatedDaySection,
    TranslatedWeeklyBundle,
)
from src.notion_writer import classify_meal, group_into_meals


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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/test_notion_writer.py -v`
Expected: `ModuleNotFoundError: No module named 'src.notion_writer'`.

- [ ] **Step 3: Implement types, grouping, and HTTP skeleton**

Create `src/notion_writer.py`:
```python
import asyncio
import logging
from datetime import date
from typing import Callable, Literal, TypedDict

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.models import TranslatedWeeklyBundle

log = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

Meal = Literal["午餐", "晚餐"]
DayCode = Literal["Mon", "Tue", "Wed", "Thu", "Fri"]
Confidence = Literal["high", "medium", "low", "failed"]

WEEKDAY_CODE: dict[str, DayCode] = {
    "MON": "Mon", "TUE": "Tue", "WED": "Wed", "THU": "Thu", "FRI": "Fri",
}

CAFETERIA_SHORT_ZH: dict[str, str] = {
    "science": "科学",
    "anam": "安岩",
    "sanhak": "产学",
    "alumni": "校友",
    "student_center": "学生中心",
}

_HIDDEN_CATEGORIES = {"조식", "천원의아침", "천원의아침(테이크아웃)", "아침"}
_CONF_ORDER: dict[Confidence, int] = {"high": 0, "medium": 1, "low": 2, "failed": 3}

PhotoResolver = Callable[[str, str, str], str | None]


class DishLine(TypedDict):
    name_ko: str
    name_zh: str
    name_en: str
    is_new: bool
    photo_url: str | None


class CategoryBlock(TypedDict):
    label_ko: str
    dishes: list[DishLine]


class MealRow(TypedDict):
    week_monday: date
    day: DayCode
    date: date
    cafeteria_id: str
    cafeteria_name_zh_full: str
    cafeteria_name_en_full: str
    meal: Meal
    categories: list[CategoryBlock]
    dish_count: int
    new_count: int
    confidence: Confidence
    source_url: str


class PublishResult(TypedDict):
    meals_inserted: int
    meals_updated: int
    meals_failed: int
    summary_page_url: str | None


def classify_meal(category_ko: str) -> Meal:
    return "晚餐" if "석식" in category_ko else "午餐"


def _worst_confidence(confidences: list[Confidence]) -> Confidence:
    if not confidences:
        return "high"
    return max(confidences, key=lambda c: _CONF_ORDER[c])


def group_into_meals(
    bundle: TranslatedWeeklyBundle,
    resolve_photo: PhotoResolver,
) -> list[MealRow]:
    meals: list[MealRow] = []
    for cm in bundle.cafeterias:
        for d in cm.days:
            if d.weekday not in WEEKDAY_CODE:
                continue
            by_meal: dict[Meal, dict[str, list[DishLine]]] = {"午餐": {}, "晚餐": {}}
            conf_by_meal: dict[Meal, list[Confidence]] = {"午餐": [], "晚餐": []}

            for cat_ko, dishes in d.categories.items():
                if cat_ko in _HIDDEN_CATEGORIES or not dishes:
                    continue
                meal = classify_meal(cat_ko)
                bucket = by_meal[meal].setdefault(cat_ko, [])
                for dish in dishes:
                    bucket.append({
                        "name_ko": dish.name_ko,
                        "name_zh": dish.name_zh,
                        "name_en": dish.name_en,
                        "is_new": dish.is_new,
                        "photo_url": resolve_photo(cm.cafeteria_id, dish.name_ko, dish.name_en),
                    })
                    conf_by_meal[meal].append(dish.confidence)

            for meal in ("午餐", "晚餐"):
                if not by_meal[meal]:
                    continue
                cats: list[CategoryBlock] = [
                    {"label_ko": label, "dishes": lines}
                    for label, lines in by_meal[meal].items()
                ]
                all_lines = [ln for blk in cats for ln in blk["dishes"]]
                meals.append({
                    "week_monday": bundle.week_start,
                    "day": WEEKDAY_CODE[d.weekday],
                    "date": d.date,
                    "cafeteria_id": cm.cafeteria_id,
                    "cafeteria_name_zh_full": cm.cafeteria_name_zh,
                    "cafeteria_name_en_full": cm.cafeteria_name_en,
                    "meal": meal,
                    "categories": cats,
                    "dish_count": len(all_lines),
                    "new_count": sum(1 for ln in all_lines if ln["is_new"]),
                    "confidence": _worst_confidence(conf_by_meal[meal]),
                    "source_url": cm.source_url,
                })
    return meals


# --- HTTP plumbing (used by Tasks 5-7) ---

class _Retryable(Exception):
    """Raised on 429/5xx to trigger tenacity backoff."""


class NotionWriter:
    def __init__(
        self,
        *,
        token: str,
        database_id: str,
        parent_page_id: str,
        repo_slug: str = "bincao115415/KU-cafeteria-menu",
        unsplash_key: str | None = None,
    ):
        self._token = token
        self.database_id = database_id
        self.parent_page_id = parent_page_id
        self._repo_slug = repo_slug
        self._unsplash_key = unsplash_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "NotionWriter":
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(min=1, max=30),
        retry=retry_if_exception_type(_Retryable),
        reraise=True,
    )
    async def _http(self, method: str, path: str, *, json: dict | None = None) -> dict:
        assert self._client is not None, "use `async with NotionWriter(...)`"
        resp = await self._client.request(method, f"{NOTION_API}{path}", json=json)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "1"))
            log.warning("notion 429; sleeping %.1fs", retry_after)
            await asyncio.sleep(retry_after)
            raise _Retryable("429")
        if 500 <= resp.status_code < 600:
            raise _Retryable(f"{resp.status_code}")
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Notion {method} {path} → {resp.status_code}: {resp.text[:400]}"
            )
        return resp.json()
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_notion_writer.py -v`
Expected: all 7 grouping tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/notion_writer.py tests/test_notion_writer.py
git commit -m "feat(notion): add meal grouping + HTTP retry skeleton"
```

---

## Task 5: `NotionWriter.upsert_meal` — query, insert, update, 429 retry

Given a `MealRow`, find an existing DB page by `(Week, Day, Cafeteria, Meal)` and update it, or insert a new one.

**Files:**
- Modify: `src/notion_writer.py`
- Modify: `tests/test_notion_writer.py`

- [ ] **Step 1: Write failing tests for upsert**

Append to `tests/test_notion_writer.py`:
```python
import httpx
import pytest
import respx

from src.notion_writer import CAFETERIA_SHORT_ZH, NotionWriter


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
    assert "김치찌개" in body
    assert "★" in body  # is_new marker


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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/test_notion_writer.py::test_upsert_meal_inserts_when_not_found -v`
Expected: `AttributeError: 'NotionWriter' has no attribute 'upsert_meal'`.

- [ ] **Step 3: Implement upsert_meal + properties builder**

Append to `src/notion_writer.py`:
```python
_DISHES_SOFT_LIMIT = 2000  # Notion rich_text content limit


def _render_dishes_text(categories: list[CategoryBlock]) -> str:
    lines: list[str] = []
    for blk in categories:
        lines.append(f"【{blk['label_ko']}】")
        for dish in blk["dishes"]:
            star = " ★" if dish["is_new"] else ""
            zh = dish["name_zh"] or dish["name_ko"]
            en = dish["name_en"] or ""
            lines.append(f"• {zh}{star} / {en}".rstrip(" /"))
        lines.append("")
    text = "\n".join(lines).rstrip()
    if len(text) <= _DISHES_SOFT_LIMIT:
        return text
    truncated = text[: _DISHES_SOFT_LIMIT - 24].rstrip()
    dropped = text[len(truncated):].count("\n•")
    return f"{truncated}\n… (+{dropped} more)"


def _meal_properties(meal: MealRow) -> dict:
    title = (
        f"{meal['date'].isoformat()} {meal['day']} · "
        f"{CAFETERIA_SHORT_ZH[meal['cafeteria_id']]} · {meal['meal']}"
    )
    photo_urls: list[str] = [
        ln["photo_url"]
        for blk in meal["categories"] for ln in blk["dishes"]
        if ln["photo_url"]
    ]
    return {
        "Name": {"title": [{"text": {"content": title}}]},
        "Week": {"date": {"start": meal["week_monday"].isoformat()}},
        "Day": {"select": {"name": meal["day"]}},
        "Cafeteria": {"select": {"name": CAFETERIA_SHORT_ZH[meal["cafeteria_id"]]}},
        "Meal": {"select": {"name": meal["meal"]}},
        "Photo": {"files": [
            {
                "type": "external",
                "name": (url.rsplit("/", 1)[-1] or "photo")[:100],
                "external": {"url": url},
            }
            for url in photo_urls[:25]  # Notion limit: 25 files per property
        ]},
        "Dishes": {"rich_text": [{"text": {"content": _render_dishes_text(meal["categories"])}}]},
        "Dish Count": {"number": meal["dish_count"]},
        "New Count": {"number": meal["new_count"]},
        "Confidence": {"select": {"name": meal["confidence"]}},
        "Source URL": {"url": meal["source_url"]},
    }
```

Add these methods to `NotionWriter`:
```python
    async def _find_existing(self, meal: MealRow) -> str | None:
        body = {
            "filter": {"and": [
                {"property": "Week", "date": {"equals": meal["week_monday"].isoformat()}},
                {"property": "Day", "select": {"equals": meal["day"]}},
                {"property": "Cafeteria",
                 "select": {"equals": CAFETERIA_SHORT_ZH[meal["cafeteria_id"]]}},
                {"property": "Meal", "select": {"equals": meal["meal"]}},
            ]},
            "page_size": 1,
        }
        resp = await self._http(
            "POST", f"/databases/{self.database_id}/query", json=body
        )
        results = resp.get("results") or []
        return results[0]["id"] if results else None

    async def upsert_meal(self, meal: MealRow) -> Literal["inserted", "updated", "failed"]:
        try:
            existing_id = await self._find_existing(meal)
            props = _meal_properties(meal)
            if existing_id:
                await self._http(
                    "PATCH", f"/pages/{existing_id}", json={"properties": props}
                )
                return "updated"
            await self._http("POST", "/pages", json={
                "parent": {"database_id": self.database_id},
                "properties": props,
            })
            return "inserted"
        except Exception:
            log.exception(
                "upsert failed: %s %s %s %s",
                meal["cafeteria_id"], meal["day"], meal["meal"], meal["week_monday"],
            )
            return "failed"
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_notion_writer.py -v`
Expected: all tests pass (7 grouping + 5 upsert = 12).

- [ ] **Step 5: Commit**

```bash
git add src/notion_writer.py tests/test_notion_writer.py
git commit -m "feat(notion): upsert_meal with composite-filter dedup and 429 retry"
```

---

## Task 6: `NotionWriter.build_summary_page` — weekly summary page

Create a plain-block page under the parent with: H1 title, callout (new-dish count), divider, then per-cafeteria sections (H2 + paragraph + H3 per meal + toggle per day containing category headers and dish bullets).

**Files:**
- Modify: `src/notion_writer.py`
- Modify: `tests/test_notion_writer.py`

- [ ] **Step 1: Write failing test for summary page**

Append to `tests/test_notion_writer.py`:
```python
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
    respx.post("https://api.notion.com/v1/pages").mock(
        side_effect=lambda req: (captured.setdefault("body", req.content.decode())
                                 or httpx.Response(200, json={"url": "u", "id": "i"}))
    )
    async with NotionWriter(token="tk", database_id="dbid", parent_page_id="pid") as w:
        await w.build_summary_page(bundle, [])

    assert "本周该食堂未提供数据" in captured["body"]
    assert "安岩" in captured["body"]
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/test_notion_writer.py::test_build_summary_page_creates_expected_blocks -v`
Expected: `AttributeError: 'NotionWriter' object has no attribute 'build_summary_page'`.

- [ ] **Step 3: Implement `build_summary_page` with block helpers**

Append to `src/notion_writer.py`:
```python
# --- Summary page block builders ---

def _rt(text: str, *, italic: bool = False, bold: bool = False, link: str | None = None) -> dict:
    content = {"type": "text", "text": {"content": text}}
    if link:
        content["text"]["link"] = {"url": link}
    annotations: dict = {}
    if italic:
        annotations["italic"] = True
    if bold:
        annotations["bold"] = True
    if annotations:
        content["annotations"] = annotations
    return content


def _heading(level: int, text: str) -> dict:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": [_rt(text)]}}


def _paragraph(spans: list[dict]) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": spans}}


def _callout(text: str, emoji: str = "🍱") -> dict:
    return {
        "object": "block", "type": "callout",
        "callout": {"rich_text": [_rt(text)], "icon": {"type": "emoji", "emoji": emoji}},
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _bullet(spans: list[dict]) -> dict:
    return {
        "object": "block", "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": spans},
    }


def _toggle(text: str, children: list[dict]) -> dict:
    return {
        "object": "block", "type": "toggle",
        "toggle": {"rich_text": [_rt(text)], "children": children},
    }


def _day_toggle_children(categories: list[CategoryBlock]) -> list[dict]:
    blocks: list[dict] = []
    for blk in categories:
        blocks.append(_paragraph([_rt(f"【{blk['label_ko']}】", bold=True)]))
        for dish in blk["dishes"]:
            star = " ★" if dish["is_new"] else ""
            zh = dish["name_zh"] or dish["name_ko"]
            en = dish["name_en"]
            text = f"{zh}{star} / {en}" if en else f"{zh}{star}"
            blocks.append(_bullet([_rt(text)]))
    return blocks


_MEAL_EMOJI: dict[Meal, str] = {"午餐": "🍚", "晚餐": "🌙"}


def _cafeteria_section(
    cm, meals: list[MealRow]
) -> list[dict]:
    """Build blocks for one cafeteria: H2 + paragraph + (H3 + toggles per meal)."""
    blocks: list[dict] = []
    header = f"🏛 {cm.cafeteria_name_zh} · {cm.cafeteria_name_en}"
    blocks.append(_heading(2, header))

    if not meals:
        blocks.append(_paragraph([_rt("本周该食堂未提供数据", italic=True)]))
        return blocks

    blocks.append(_paragraph([
        _rt("📍 "),
        _rt("原始页面 →", link=cm.source_url),
    ]))

    by_meal: dict[Meal, list[MealRow]] = {"午餐": [], "晚餐": []}
    for m in meals:
        by_meal[m["meal"]].append(m)

    for meal in ("午餐", "晚餐"):
        if not by_meal[meal]:
            continue
        blocks.append(_heading(3, f"{_MEAL_EMOJI[meal]} {meal}"))
        for m in sorted(by_meal[meal], key=lambda x: x["date"]):
            toggle_title = f"{m['day']} · {m['date'].isoformat()}"
            blocks.append(_toggle(toggle_title, _day_toggle_children(m["categories"])))
    return blocks


def _summary_blocks(bundle: TranslatedWeeklyBundle, meals: list[MealRow]) -> list[dict]:
    blocks: list[dict] = []
    week_label_slash = bundle.week_start.strftime("%Y/%m/%d")
    blocks.append(_heading(1, f"{week_label_slash} 周菜单 · KU 食堂"))
    blocks.append(_callout(
        f"本周新菜 {bundle.new_dish_count} 道 · {len(bundle.cafeterias)} 个食堂"
    ))
    blocks.append(_divider())

    meals_by_cafe: dict[str, list[MealRow]] = {}
    for m in meals:
        meals_by_cafe.setdefault(m["cafeteria_id"], []).append(m)

    for cm in bundle.cafeterias:
        blocks.extend(_cafeteria_section(cm, meals_by_cafe.get(cm.cafeteria_id, [])))

    blocks.append(_divider())
    blocks.append(_paragraph([_rt("翻译由 DeepSeek 两轮反思验证 · 每周一 10:30 KST 自动运行")]))
    return blocks
```

Add the method to `NotionWriter`:
```python
    async def build_summary_page(
        self,
        bundle: TranslatedWeeklyBundle,
        meals: list[MealRow],
    ) -> str:
        week_label_slash = bundle.week_start.strftime("%Y/%m/%d")
        resp = await self._http("POST", "/pages", json={
            "parent": {"type": "page_id", "page_id": self.parent_page_id},
            "properties": {
                "title": {"title": [{"text": {"content": f"{week_label_slash} 周菜单 · KU 食堂"}}]},
            },
            "children": _summary_blocks(bundle, meals),
        })
        return resp.get("url", "")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_notion_writer.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/notion_writer.py tests/test_notion_writer.py
git commit -m "feat(notion): build weekly summary page with per-meal toggles"
```

---

## Task 7: `NotionWriter.publish` — orchestration + failure threshold

Integrates Tasks 2–6. Groups bundle into meals (resolving photos), upserts each, and builds summary page unless >30% of upserts failed.

**Files:**
- Modify: `src/notion_writer.py`
- Modify: `tests/test_notion_writer.py`

- [ ] **Step 1: Write failing tests for publish**

Append to `tests/test_notion_writer.py`:
```python
@pytest.mark.asyncio
@respx.mock
async def test_publish_happy_path(monkeypatch):
    # 2 meals, both inserted, summary page built.
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
    # 2 query + 2 upsert + 1 summary = 5 /pages|query calls total, pages called 3x
    assert pages_route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_publish_aborts_summary_when_failures_over_threshold(monkeypatch):
    monkeypatch.setattr("src.notion_writer.resolve_photo_url", lambda *a, **k: None)
    # every query 400s → every upsert fails
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
    assert result["summary_page_url"] is None  # summary skipped
    assert pages_route.call_count == 0  # never hit /pages
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/test_notion_writer.py::test_publish_happy_path -v`
Expected: `AttributeError: 'NotionWriter' object has no attribute 'publish'`.

- [ ] **Step 3: Implement `publish` and wire `resolve_photo_url`**

At the top of `src/notion_writer.py`, add import:
```python
from src.photos import resolve_photo_url
```

Add to `NotionWriter`:
```python
    _FAILURE_THRESHOLD = 0.3

    def _photo_resolver(self) -> PhotoResolver:
        def resolver(cafeteria_id: str, name_ko: str, name_en: str) -> str | None:
            return resolve_photo_url(
                cafeteria_id, name_ko, name_en,
                unsplash_key=self._unsplash_key,
                repo_slug=self._repo_slug,
            )
        return resolver

    async def publish(self, bundle: TranslatedWeeklyBundle) -> PublishResult:
        meals = group_into_meals(bundle, self._photo_resolver())
        inserted = updated = failed = 0
        for meal in meals:
            status = await self.upsert_meal(meal)
            if status == "inserted":
                inserted += 1
            elif status == "updated":
                updated += 1
            else:
                failed += 1

        total = max(1, inserted + updated + failed)
        summary_url: str | None = None
        if failed / total > self._FAILURE_THRESHOLD:
            log.error(
                "meal upsert failure rate %.0f%% > %.0f%% → skipping summary page",
                failed / total * 100, self._FAILURE_THRESHOLD * 100,
            )
        else:
            try:
                summary_url = await self.build_summary_page(bundle, meals)
            except Exception:
                log.exception("summary page creation failed")

        return {
            "meals_inserted": inserted,
            "meals_updated": updated,
            "meals_failed": failed,
            "summary_page_url": summary_url,
        }
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_notion_writer.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/notion_writer.py tests/test_notion_writer.py
git commit -m "feat(notion): publish() orchestration with partial-failure threshold"
```

---

## Task 8: Rewire `src/main.py` + drop Gmail from `Settings`

Swap the mailer+renderer block for `NotionWriter.publish(bundle)`. Make the failure path silent (no fallback email). Remove Gmail fields from Settings. Update `tests/test_main.py`.

**Files:**
- Modify: `src/main.py`
- Modify: `src/config.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Update main.py tests first**

Replace the entire contents of `tests/test_main.py`:
```python
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/test_main.py -v`
Expected: `test_all_empty_on_last_trigger_silent` fails (returns `"failed_sent_fallback"` or equivalent — old behavior).

- [ ] **Step 3: Rewrite `src/main.py`**

Replace the entire contents of `src/main.py`:
```python
import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.cache import StateFile, TranslationCache, git_commit_and_push
from src.config import CAFETERIAS, load_settings
from src.deepseek_client import DeepSeekClient
from src.models import TranslatedWeeklyBundle
from src.notion_writer import NotionWriter
from src.parser import parse_cafeteria_page
from src.scraper import fetch_all
from src.translator import Translator
from src.utils import KST, get_current_monday_kst

log = logging.getLogger(__name__)
REPO = Path(__file__).parent.parent
DATA = REPO / "data"


def _has_any_menu(menu) -> bool:
    for d in menu.days:
        for cat_dishes in d.categories.values():
            if cat_dishes:
                return True
    return False


async def run_once(
    *,
    trigger_index: int,
    total_triggers: int,
    dry_run: bool = False,
) -> str:
    this_monday = get_current_monday_kst()
    cache = TranslationCache(DATA / "translations.json")
    state = StateFile(DATA / "state.json")

    if state.last_sent_week == this_monday.isoformat() and state.status == "done":
        log.info("already sent for week %s; skipping", this_monday)
        return "skipped_already_sent"

    fetched = await fetch_all(CAFETERIAS)
    by_id = {c["cafeteria_id"]: c for c in CAFETERIAS}

    menus = []
    fetch_errors: list[str] = []
    for cid, html, err in fetched:
        if err or not html:
            fetch_errors.append(f"{cid}: {err or 'empty'}")
            continue
        c = by_id[cid]
        try:
            menu = parse_cafeteria_page(
                html,
                cafeteria_id=c["cafeteria_id"],
                cafeteria_name_ko=c["cafeteria_name_ko"],
                cafeteria_name_zh=c["cafeteria_name_zh"],
                cafeteria_name_en=c["cafeteria_name_en"],
                source_url=c["source_url"],
            )
            menus.append(menu)
        except Exception as e:
            log.exception("parse failed for %s", cid)
            fetch_errors.append(f"{cid}: parse {e}")

    non_empty = [m for m in menus if _has_any_menu(m)]

    if not non_empty:
        is_last = trigger_index == total_triggers - 1
        if is_last:
            log.error("no menu data after %d triggers; errors=%s", total_triggers, fetch_errors)
            state.update(
                last_sent_week=this_monday.isoformat(),
                last_run_at=datetime.now(KST).isoformat(timespec="seconds"),
                status="failed_silent",
            )
            state.persist()
            _commit_state(this_monday, "failed_silent")
            return "failed_silent"
        state.update(
            last_sent_week=None,
            last_run_at=datetime.now(KST).isoformat(timespec="seconds"),
            status="pending",
        )
        state.persist()
        _commit_state(this_monday, "pending")
        return "pending"

    settings = load_settings()
    client = DeepSeekClient(api_key=settings.deepseek_api_key)
    translator = Translator(client=client, cache=cache)

    translated_list = []
    global_errors = list(fetch_errors)
    for menu in menus:
        try:
            translated_list.append(await translator.translate_menu(menu))
        except Exception as e:
            log.exception("translate failed for %s", menu.cafeteria_id)
            global_errors.append(f"{menu.cafeteria_id}: translate {e}")

    new_count = sum(
        1
        for tm in translated_list
        for d in tm.days
        for ds in d.categories.values()
        for dish in ds
        if dish.is_new and dish.confidence != "failed"
    )
    bundle = TranslatedWeeklyBundle(
        week_start=this_monday,
        cafeterias=translated_list,
        new_dish_count=new_count,
        global_errors=global_errors,
    )

    if dry_run:
        print(f"DRY RUN: would publish {len(translated_list)} cafeterias, "
              f"{new_count} new dishes, week {this_monday}")
        return "dry_run_ok"

    async with NotionWriter(
        token=settings.notion_token,
        database_id=settings.notion_database_id,
        parent_page_id=settings.notion_parent_page_id,
        unsplash_key=settings.unsplash_access_key,
    ) as writer:
        result = await writer.publish(bundle)

    log.info(
        "notion publish: inserted=%d updated=%d failed=%d summary=%s",
        result["meals_inserted"], result["meals_updated"],
        result["meals_failed"], result["summary_page_url"],
    )

    cache.persist()
    state.update(
        last_sent_week=this_monday.isoformat(),
        last_run_at=datetime.now(KST).isoformat(timespec="seconds"),
        status="done",
    )
    state.persist()

    new_keys = sorted(cache.new_keys)
    msg = (
        f"chore(cache): learn {len(new_keys)} dishes for week {this_monday}"
        if new_keys
        else f"chore(state): mark week {this_monday} as done"
    )
    git_commit_and_push(
        [DATA / "translations.json", DATA / "state.json"],
        message=msg, repo_dir=REPO,
    )
    return "published"


def _commit_state(this_monday, status: str) -> None:
    git_commit_and_push(
        [DATA / "state.json"],
        message=f"chore(state): {status} for week {this_monday}",
        repo_dir=REPO,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser()
    p.add_argument("--trigger-index", type=int, default=0)
    p.add_argument("--total-triggers", type=int, default=3)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    result = asyncio.run(run_once(
        trigger_index=args.trigger_index,
        total_triggers=args.total_triggers,
        dry_run=args.dry_run,
    ))
    log.info("run_once → %s", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Drop Gmail fields from `Settings`**

Update `src/config.py`:
```python
@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    notion_token: str
    notion_parent_page_id: str
    notion_database_id: str
    unsplash_access_key: str | None = None


def load_settings() -> Settings:
    def req(key: str) -> str:
        v = os.environ.get(key)
        if not v:
            raise RuntimeError(f"Missing required env var: {key}")
        return v

    return Settings(
        deepseek_api_key=req("DEEPSEEK_API_KEY"),
        notion_token=req("NOTION_TOKEN"),
        notion_parent_page_id=req("NOTION_PARENT_PAGE_ID"),
        notion_database_id=req("NOTION_DATABASE_ID"),
        unsplash_access_key=os.environ.get("UNSPLASH_ACCESS_KEY") or None,
    )
```

Update `tests/test_config.py`: remove Gmail env vars from the three test setups added in Task 1, and drop any `gmail_*` assertions. Keep the happy-path + Unsplash test + missing-token test.

- [ ] **Step 5: Run all tests, verify pass**

Run: `pytest`
Expected: all pass. Tests that reference old Gmail behavior should be updated or removed.

- [ ] **Step 6: Commit**

```bash
git add src/main.py src/config.py tests/test_main.py tests/test_config.py
git commit -m "feat(main): publish to Notion instead of Gmail; drop Gmail Settings"
```

---

## Task 9: Delete legacy files, drop deps, update workflow + README, scaffold photo dirs

Final cleanup: remove mailer/renderer/templates, drop `jinja2` + `premailer` from pyproject, replace workflow env vars, scaffold `data/photos/<cafeteria_id>/.gitkeep` for 5 cafeterias, refresh README.

**Files:**
- Delete: `src/mailer.py`, `src/renderer.py`, `templates/email.html.j2`, `tests/test_mailer.py`, `tests/test_renderer.py`
- Modify: `pyproject.toml`, `.github/workflows/weekly_menu.yml`, `README.md`
- Create: `data/photos/science/.gitkeep`, `data/photos/anam/.gitkeep`, `data/photos/sanhak/.gitkeep`, `data/photos/alumni/.gitkeep`, `data/photos/student_center/.gitkeep`

- [ ] **Step 1: Delete legacy source + test files**

```bash
git rm src/mailer.py src/renderer.py
git rm -r templates/
git rm tests/test_mailer.py tests/test_renderer.py
```

- [ ] **Step 2: Drop `jinja2` and `premailer` from pyproject**

In `pyproject.toml` under `[project].dependencies`, remove the lines for `jinja2` and `premailer`.

Run `pip install -e .` to refresh the environment.
Run `pip list | grep -iE 'jinja2|premailer'` — expected: empty (or only transitive, which we don't use directly).

- [ ] **Step 3: Update workflow env vars**

Edit `.github/workflows/weekly_menu.yml`. Find the `env:` block for the run step and replace:
```yaml
          GMAIL_USERNAME: ${{ secrets.GMAIL_USERNAME }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          MAIL_TO: ${{ secrets.MAIL_TO }}
```
with:
```yaml
          NOTION_TOKEN: ${{ secrets.NOTION_TOKEN }}
          NOTION_PARENT_PAGE_ID: ${{ secrets.NOTION_PARENT_PAGE_ID }}
          NOTION_DATABASE_ID: ${{ secrets.NOTION_DATABASE_ID }}
          UNSPLASH_ACCESS_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}
```

- [ ] **Step 4: Scaffold `data/photos/<cafeteria_id>/.gitkeep`**

```bash
mkdir -p data/photos/science data/photos/anam data/photos/sanhak data/photos/alumni data/photos/student_center
touch data/photos/science/.gitkeep \
      data/photos/anam/.gitkeep \
      data/photos/sanhak/.gitkeep \
      data/photos/alumni/.gitkeep \
      data/photos/student_center/.gitkeep
git add data/photos/
```

- [ ] **Step 5: Refresh README**

In `README.md` replace any email/Gmail/SMTP setup sections with a "Notion publishing" section describing:
- parent page + database already provisioned
- required GitHub secrets (`NOTION_TOKEN`, `NOTION_PARENT_PAGE_ID`, `NOTION_DATABASE_ID`; optional `UNSPLASH_ACCESS_KEY`)
- how users add their own dish photos: drop a `.jpg`/`.png`/`.webp` at `data/photos/<cafeteria_id>/<slug>.<ext>` where `<slug>` is the Korean dish name slugified (see `src.photos.slugify_ko`)
- advisory: keep each photo under ~200 KB for fast load

- [ ] **Step 6: Full test sweep + ruff**

Run: `pytest`
Expected: all pass, no references to deleted modules.
Run: `ruff check src tests`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .github/workflows/weekly_menu.yml README.md
git commit -m "chore: remove Gmail pipeline, scaffold photos dirs, update workflow secrets"
```

- [ ] **Step 8: Manual verification via workflow_dispatch**

Push branch, merge to main (or directly push to main). Then:

```bash
gh workflow run weekly_menu.yml -f trigger_index=2
gh run watch
```

Verify in Notion:
- New rows appear in the `KU Cafeteria Meals` DB, one per (cafeteria × day × meal) for the current week.
- Column order in the default view — if not `Name → Week → Day → Cafeteria → Meal → Photo → Dishes → Dish Count → New Count → Confidence → Source URL`, drag columns manually once; they persist.
- A new weekly summary page `YYYY/MM/DD 周菜单 · KU 食堂` appears under the parent page with H2 per cafeteria, H3 per meal, toggle per day.

If the run failed, check the Actions logs; `state.json` status will be `failed_silent` with a commit explaining.

---

## Self-Review Notes

- **Spec coverage**: all 11 DB properties (Name, Week, Day, Cafeteria, Meal, Photo, Dishes, Dish Count, New Count, Confidence, Source URL) are produced by `_meal_properties` in Task 5. Summary page layout (Task 6) matches spec: H1, callout, divider, H2 per cafeteria with empty placeholder, H3 meal split, day toggles with category subheads. Dedup composite filter (Task 5) matches spec's `(Week, Cafeteria, Day, Meal)` key. Failure threshold 30% implemented in Task 7. Silent failure mode implemented in Task 8.
- **Placeholder scan**: every step has complete code; no TBDs.
- **Type consistency**: `MealRow`, `CategoryBlock`, `DishLine`, `PublishResult` all defined in Task 4 and used verbatim in Tasks 5–7. `CAFETERIA_SHORT_ZH`, `_HIDDEN_CATEGORIES`, `_CONF_ORDER` defined once in Task 4. `classify_meal`, `_worst_confidence`, `group_into_meals`, `_render_dishes_text`, `_meal_properties`, block helpers all consistently named.
- **Out-of-band**: user still needs to (a) manually verify column order in Notion UI after first run, (b) optionally provide 5 cafeteria addresses to populate `CAFETERIAS[*]["address"]`, (c) optionally set `UNSPLASH_ACCESS_KEY` secret.
