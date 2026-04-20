# Korea University Cafeteria Weekly Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Korean/Chinese/English weekly cafeteria menu HTML email to `ku-menu-bot@users.noreply.github.com` every Monday by 11:30 KST, scraping all six Korea University cafeteria pages and using MiniMax LLM + web-search for first-time dish translations with two-pass verification.

**Architecture:** Python 3.11 app scheduled via GitHub Actions cron. Pipeline = scrape (httpx/BeautifulSoup) → parse → translate (MiniMax chat + built-in web_search tool call with two-pass verification for new dishes, cached in `data/translations.json` committed back to repo) → render (Jinja2 + premailer) → send (Gmail SMTP). State machine in `main.py` manages 3-retry cron window (10:30/11:00/11:15 KST) with a fallback email on exhaustion.

**Tech Stack:** Python 3.11, `httpx`, `beautifulsoup4`, `lxml`, `pydantic>=2`, `jinja2`, `premailer`, `openai`-compatible client for MiniMax, `smtplib` (stdlib), `pytest`, `pytest-asyncio`, `respx`, `inline-snapshot`, `ruff`, `uv` (or `pip`).

**Source spec:** `docs/superpowers/specs/2026-04-20-ku-cafeteria-menu-design.md`

---

## File Structure

```
DinnermenuatKU/
├── .github/workflows/
│   ├── weekly_menu.yml          # cron + workflow_dispatch
│   └── test.yml                 # lint + pytest on push/PR
├── src/
│   ├── __init__.py
│   ├── main.py                  # orchestrator
│   ├── models.py                # Pydantic models
│   ├── utils.py                 # normalize(), get_current_monday_kst()
│   ├── config.py                # load env vars, cafeteria constants
│   ├── scraper.py               # httpx fetch
│   ├── parser.py                # HTML → CafeteriaMenu
│   ├── translator.py            # two-pass pipeline
│   ├── minimax_client.py        # MiniMax chat + web_search
│   ├── renderer.py              # Jinja2 + premailer → HTML/text
│   ├── mailer.py                # SMTP send
│   └── cache.py                 # translations.json + state.json + git push
├── templates/
│   └── email.html.j2
├── data/
│   ├── translations.json        # committed, initial = {"schema_version":1,"entries":{}}
│   └── state.json               # committed
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_utils.py
│   ├── test_models.py
│   ├── test_cache.py
│   ├── test_parser.py
│   ├── test_scraper.py
│   ├── test_minimax_client.py
│   ├── test_translator.py
│   ├── test_renderer.py
│   ├── test_mailer.py
│   ├── test_main.py
│   └── fixtures/
│       ├── sample_menu_page.html
│       ├── sample_empty_page.html
│       └── expected_email.html
├── pyproject.toml
├── .env.example
├── .gitignore
├── .ruff.toml
└── README.md
```

---

## Task 0: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.ruff.toml`
- Create: `src/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Create: `data/translations.json`
- Create: `data/state.json`
- Modify: `.gitignore`

- [ ] **Step 0.1: Write `pyproject.toml`**

```toml
[project]
name = "ku-cafeteria-menu"
version = "0.1.0"
description = "Weekly Korea University cafeteria menu translator and mailer"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "lxml>=5.1",
    "pydantic>=2.6",
    "jinja2>=3.1",
    "premailer>=3.10",
    "python-dateutil>=2.9",
    "tenacity>=8.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.20",
    "inline-snapshot>=0.10",
    "ruff>=0.4",
    "freezegun>=1.4",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["src*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 0.2: Write `.ruff.toml`**

```toml
line-length = 100
target-version = "py311"

[lint]
select = ["E", "F", "I", "W", "UP", "B"]
ignore = ["E501"]
```

- [ ] **Step 0.3: Write `.env.example`**

```
MINIMAX_API_KEY=
MINIMAX_GROUP_ID=
GMAIL_USERNAME=ku-menu-bot@users.noreply.github.com
GMAIL_APP_PASSWORD=
MAIL_TO=ku-menu-bot@users.noreply.github.com
```

- [ ] **Step 0.4: Append to `.gitignore`** (already has base entries, add nothing if absent)

Verify `.env` is listed; if not, add it.

- [ ] **Step 0.5: Create `data/translations.json`**

```json
{
  "schema_version": 1,
  "updated_at": "2026-04-20T00:00:00+09:00",
  "entries": {}
}
```

- [ ] **Step 0.6: Create `data/state.json`**

```json
{
  "last_sent_week": null,
  "last_run_at": null,
  "status": "idle"
}
```

- [ ] **Step 0.7: Create empty `src/__init__.py` and `tests/__init__.py`**

- [ ] **Step 0.8: Create `tests/conftest.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 0.9: Install dev dependencies**

Run: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
Expected: successful install.

- [ ] **Step 0.10: Commit**

```bash
git add pyproject.toml .ruff.toml .env.example .gitignore src/__init__.py tests/__init__.py tests/conftest.py data/
git commit -m "chore: project scaffold"
```

---

## Task 1: Utility functions (`utils.py`)

**Files:**
- Create: `src/utils.py`
- Test: `tests/test_utils.py`

- [ ] **Step 1.1: Write the failing test**

Create `tests/test_utils.py`:

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from src.utils import get_current_monday_kst, normalize_dish_name


def test_normalize_strips_whitespace():
    assert normalize_dish_name("  된장찌개  ") == "된장찌개"


def test_normalize_collapses_inner_whitespace():
    assert normalize_dish_name("된장\t찌개\n") == "된장 찌개"


def test_normalize_unifies_middle_dot():
    # U+00B7 (·) and U+30FB (・) both normalize to U+00B7
    assert normalize_dish_name("파스타・스테이크") == "파스타·스테이크"


def test_normalize_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        normalize_dish_name("   ")


@freeze_time("2026-04-22 05:00:00", tz_offset=0)  # Wed 14:00 KST
def test_get_current_monday_kst_midweek():
    assert get_current_monday_kst() == date(2026, 4, 20)


@freeze_time("2026-04-20 01:30:00", tz_offset=0)  # Mon 10:30 KST
def test_get_current_monday_kst_on_monday_morning():
    assert get_current_monday_kst() == date(2026, 4, 20)


@freeze_time("2026-04-19 23:00:00", tz_offset=0)  # Sun 08:00 KST next day? check
def test_get_current_monday_kst_sunday_returns_previous_monday():
    # Sun 2026-04-19 08:00 KST → previous Monday is 2026-04-13
    assert get_current_monday_kst() == date(2026, 4, 13)
```

- [ ] **Step 1.2: Run test to verify failure**

Run: `pytest tests/test_utils.py -v`
Expected: FAIL — module `src.utils` does not exist.

- [ ] **Step 1.3: Implement `src/utils.py`**

```python
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

_MIDDLE_DOTS = str.maketrans({"・": "·", "‧": "·"})


def normalize_dish_name(name: str) -> str:
    s = name.translate(_MIDDLE_DOTS)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        raise ValueError("dish name is empty after normalization")
    return s


def get_current_monday_kst() -> date:
    now = datetime.now(KST)
    return (now - timedelta(days=now.weekday())).date()
```

- [ ] **Step 1.4: Run test to verify passing**

Run: `pytest tests/test_utils.py -v`
Expected: 6 passed.

- [ ] **Step 1.5: Commit**

```bash
git add src/utils.py tests/test_utils.py
git commit -m "feat(utils): normalize_dish_name and KST Monday helper"
```

---

## Task 2: Pydantic models (`models.py`)

**Files:**
- Create: `src/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 2.1: Write the failing test**

Create `tests/test_models.py`:

```python
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from src.models import (
    CafeteriaMenu,
    DaySection,
    DishRaw,
    DishTranslated,
    TranslatedCafeteriaMenu,
    TranslatedDaySection,
    WeeklyBundle,
)


def test_dish_raw_minimal():
    d = DishRaw(name_ko="된장찌개", raw_text="된장찌개")
    assert d.name_ko == "된장찌개"


def test_day_section_weekday_enum():
    with pytest.raises(ValidationError):
        DaySection(date=date(2026, 4, 20), weekday="FOO", categories={})


def test_cafeteria_menu_round_trip():
    m = CafeteriaMenu(
        cafeteria_id="songnim",
        cafeteria_name_ko="수당삼양 Faculty House 송림",
        cafeteria_name_zh="수당삼양教职工之家 松林",
        cafeteria_name_en="Sudang-Samyang Faculty House Songnim",
        week_start=date(2026, 4, 20),
        days=[DaySection(date=date(2026, 4, 20), weekday="MON", categories={})],
        source_url="https://www.korea.ac.kr/ko/503/subview.do",
        fetched_at=datetime(2026, 4, 20, 10, 30),
    )
    dumped = m.model_dump_json()
    restored = CafeteriaMenu.model_validate_json(dumped)
    assert restored == m


def test_dish_translated_defaults():
    d = DishTranslated(name_ko="A", name_zh="甲", name_en="A")
    assert d.is_new is False
    assert d.confidence == "high"
    assert d.note_zh is None
```

- [ ] **Step 2.2: Run tests to verify failure**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — module missing.

- [ ] **Step 2.3: Implement `src/models.py`**

```python
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Weekday = Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
Confidence = Literal["high", "medium", "low", "failed"]


class DishRaw(BaseModel):
    name_ko: str
    raw_text: str


class DaySection(BaseModel):
    date: date
    weekday: Weekday
    categories: dict[str, list[DishRaw]] = Field(default_factory=dict)


class CafeteriaMenu(BaseModel):
    cafeteria_id: str
    cafeteria_name_ko: str
    cafeteria_name_zh: str
    cafeteria_name_en: str
    week_start: date
    days: list[DaySection]
    source_url: str
    fetched_at: datetime


class WeeklyBundle(BaseModel):
    week_start: date
    cafeterias: list[CafeteriaMenu]


class DishTranslated(BaseModel):
    name_ko: str
    name_zh: str
    name_en: str
    note_zh: Optional[str] = None
    note_en: Optional[str] = None
    is_new: bool = False
    confidence: Confidence = "high"


class TranslatedDaySection(BaseModel):
    date: date
    weekday: Weekday
    categories: dict[str, list[DishTranslated]] = Field(default_factory=dict)


class TranslatedCafeteriaMenu(BaseModel):
    cafeteria_id: str
    cafeteria_name_ko: str
    cafeteria_name_zh: str
    cafeteria_name_en: str
    week_start: date
    days: list[TranslatedDaySection]
    source_url: str
    fetched_at: datetime
    errors: list[str] = Field(default_factory=list)


class TranslatedWeeklyBundle(BaseModel):
    week_start: date
    cafeterias: list[TranslatedCafeteriaMenu]
    new_dish_count: int = 0
    global_errors: list[str] = Field(default_factory=list)
```

- [ ] **Step 2.4: Run tests**

Run: `pytest tests/test_models.py -v`
Expected: 4 passed.

- [ ] **Step 2.5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat(models): pydantic schemas for menu, cache, and translation"
```

---

## Task 3: Config and cafeteria constants (`config.py`)

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`

**Note on cafeteria IDs:** The spec defers the exact 6 IDs to scraper probing. For now, hard-code known `503` (Songnim) and five placeholders; Task 5 updates these after live probing.

- [ ] **Step 3.1: Write the failing test**

Create `tests/test_config.py`:

```python
from src.config import CAFETERIAS, load_settings


def test_cafeterias_count_is_six():
    assert len(CAFETERIAS) == 6


def test_cafeterias_have_required_fields():
    for c in CAFETERIAS:
        assert c["cafeteria_id"]
        assert c["source_url"].startswith("https://www.korea.ac.kr/")
        assert c["cafeteria_name_ko"]
        assert c["cafeteria_name_zh"]
        assert c["cafeteria_name_en"]


def test_load_settings_reads_env(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.setenv("MINIMAX_GROUP_ID", "g")
    monkeypatch.setenv("GMAIL_USERNAME", "u@x")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "p")
    monkeypatch.setenv("MAIL_TO", "to@x")
    s = load_settings()
    assert s.minimax_api_key == "k"
    assert s.gmail_username == "u@x"
```

- [ ] **Step 3.2: Run test to verify failure**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3.3: Implement `src/config.py`**

```python
import os
from dataclasses import dataclass

CAFETERIAS: list[dict] = [
    {
        "cafeteria_id": "songnim",
        "source_url": "https://www.korea.ac.kr/ko/503/subview.do",
        "cafeteria_name_ko": "수당삼양 Faculty House 송림",
        "cafeteria_name_zh": "수당삼양教职工之家 松林",
        "cafeteria_name_en": "Sudang-Samyang Faculty House Songnim",
        "hours": "Lunch 11:00-14:00 · Dinner 17:00-21:00",
    },
    # Placeholders — real IDs filled in during Task 5 live probing.
    {
        "cafeteria_id": "science",
        "source_url": "https://www.korea.ac.kr/ko/TBD_SCIENCE/subview.do",
        "cafeteria_name_ko": "이공계캠퍼스 학생식당",
        "cafeteria_name_zh": "理工校区学生食堂",
        "cafeteria_name_en": "Science Campus Student Cafeteria",
        "hours": "",
    },
    {
        "cafeteria_id": "anam",
        "source_url": "https://www.korea.ac.kr/ko/TBD_ANAM/subview.do",
        "cafeteria_name_ko": "안암학사 식당",
        "cafeteria_name_zh": "安岩宿舍食堂",
        "cafeteria_name_en": "Anam Dormitory Cafeteria",
        "hours": "",
    },
    {
        "cafeteria_id": "sanhak",
        "source_url": "https://www.korea.ac.kr/ko/TBD_SANHAK/subview.do",
        "cafeteria_name_ko": "산학관 식당",
        "cafeteria_name_zh": "产学馆食堂",
        "cafeteria_name_en": "Sanhakgwan Cafeteria",
        "hours": "",
    },
    {
        "cafeteria_id": "alumni",
        "source_url": "https://www.korea.ac.kr/ko/TBD_ALUMNI/subview.do",
        "cafeteria_name_ko": "교우회관 식당",
        "cafeteria_name_zh": "校友会馆食堂",
        "cafeteria_name_en": "Alumni Association Cafeteria",
        "hours": "",
    },
    {
        "cafeteria_id": "student_center",
        "source_url": "https://www.korea.ac.kr/ko/TBD_SC/subview.do",
        "cafeteria_name_ko": "학생회관 식당",
        "cafeteria_name_zh": "学生会馆食堂",
        "cafeteria_name_en": "Student Center Cafeteria",
        "hours": "",
    },
]


@dataclass(frozen=True)
class Settings:
    minimax_api_key: str
    minimax_group_id: str
    gmail_username: str
    gmail_app_password: str
    mail_to: str


def load_settings() -> Settings:
    def req(key: str) -> str:
        v = os.environ.get(key)
        if not v:
            raise RuntimeError(f"Missing required env var: {key}")
        return v

    return Settings(
        minimax_api_key=req("MINIMAX_API_KEY"),
        minimax_group_id=req("MINIMAX_GROUP_ID"),
        gmail_username=req("GMAIL_USERNAME"),
        gmail_app_password=req("GMAIL_APP_PASSWORD"),
        mail_to=req("MAIL_TO"),
    )
```

- [ ] **Step 3.4: Run tests**

Run: `pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 3.5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat(config): cafeteria constants and settings loader"
```

---

## Task 4: Cache module (`cache.py`)

**Files:**
- Create: `src/cache.py`
- Test: `tests/test_cache.py`

- [ ] **Step 4.1: Write the failing test**

Create `tests/test_cache.py`:

```python
import json
from pathlib import Path

import pytest

from src.cache import StateFile, TranslationCache


@pytest.fixture
def tmp_cache(tmp_path):
    p = tmp_path / "translations.json"
    p.write_text(json.dumps({"schema_version": 1, "updated_at": "x", "entries": {}}))
    return TranslationCache(path=p)


def test_cache_get_miss_returns_none(tmp_cache):
    assert tmp_cache.get("된장찌개") is None


def test_cache_set_and_get(tmp_cache):
    tmp_cache.set(
        "된장찌개",
        {
            "zh": "大酱汤",
            "en": "Soybean Paste Stew",
            "note_zh": None,
            "note_en": None,
            "learned_at": "2026-04-20",
            "source": "minimax-two-pass",
            "search_confirmed": True,
            "confidence": "high",
        },
    )
    hit = tmp_cache.get("된장찌개")
    assert hit["zh"] == "大酱汤"


def test_cache_persist_writes_to_disk(tmp_cache, tmp_path):
    tmp_cache.set("A", {"zh": "甲", "en": "A", "note_zh": None, "note_en": None,
                        "learned_at": "2026-04-20", "source": "minimax-two-pass",
                        "search_confirmed": True, "confidence": "high"})
    tmp_cache.persist()
    disk = json.loads((tmp_path / "translations.json").read_text())
    assert disk["entries"]["A"]["zh"] == "甲"


def test_cache_new_keys_tracked(tmp_cache):
    tmp_cache.set("A", {"zh": "甲", "en": "A", "note_zh": None, "note_en": None,
                        "learned_at": "2026-04-20", "source": "minimax-two-pass",
                        "search_confirmed": True, "confidence": "high"})
    assert "A" in tmp_cache.new_keys


def test_state_read_and_write(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"last_sent_week": None, "last_run_at": None, "status": "idle"}))
    s = StateFile(path=p)
    s.update(last_sent_week="2026-04-20", status="done", last_run_at="2026-04-20T10:30:00+09:00")
    s.persist()
    disk = json.loads(p.read_text())
    assert disk["status"] == "done"
    assert disk["last_sent_week"] == "2026-04-20"
```

- [ ] **Step 4.2: Run test to verify failure**

Run: `pytest tests/test_cache.py -v`
Expected: FAIL — module missing.

- [ ] **Step 4.3: Implement `src/cache.py`**

```python
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


class TranslationCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._schema_version = raw.get("schema_version", 1)
        self._entries: dict[str, dict] = raw.get("entries", {})
        self.new_keys: set[str] = set()

    def get(self, key: str) -> Optional[dict]:
        return self._entries.get(key)

    def set(self, key: str, entry: dict) -> None:
        self._entries[key] = entry
        self.new_keys.add(key)

    def persist(self) -> None:
        payload = {
            "schema_version": self._schema_version,
            "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "entries": dict(sorted(self._entries.items())),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


class StateFile:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data = json.loads(self.path.read_text(encoding="utf-8"))

    @property
    def last_sent_week(self) -> Optional[str]:
        return self._data.get("last_sent_week")

    @property
    def status(self) -> str:
        return self._data.get("status", "idle")

    def update(self, **kwargs) -> None:
        self._data.update(kwargs)

    def persist(self) -> None:
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def git_commit_and_push(paths: list[Path], message: str, repo_dir: Path) -> bool:
    """Stage, commit, push. Returns True on success. Logs and returns False on failure."""
    try:
        subprocess.run(
            ["git", "-C", str(repo_dir), "add", *[str(p) for p in paths]],
            check=True, capture_output=True,
        )
        r = subprocess.run(
            ["git", "-C", str(repo_dir), "diff", "--cached", "--quiet"],
        )
        if r.returncode == 0:
            log.info("no cache changes to commit")
            return True
        subprocess.run(
            ["git", "-C", str(repo_dir), "commit", "-m", message],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_dir), "push"],
            check=True, capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        log.warning("git commit/push failed: %s", e.stderr.decode(errors="replace"))
        return False
```

- [ ] **Step 4.4: Run tests**

Run: `pytest tests/test_cache.py -v`
Expected: 5 passed.

- [ ] **Step 4.5: Commit**

```bash
git add src/cache.py tests/test_cache.py
git commit -m "feat(cache): translations.json and state.json I/O with git push helper"
```

---

## Task 5: Scraper live probe + fixture capture

**Goal:** Confirm the real page yields menu data via static `httpx` fetch. Capture a real HTML snapshot for the parser tests. Pin the six cafeteria IDs in `config.py`.

**Files:**
- Create: `scripts/probe_scrape.py` (one-off helper, committed)
- Create: `tests/fixtures/sample_menu_page.html`
- Modify: `src/config.py` (fill in real IDs for all 6 cafeterias)

- [ ] **Step 5.1: Write `scripts/probe_scrape.py`**

```python
"""One-off probe: fetches the Songnim page and prints whether menu text is in static HTML."""
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

URL = "https://www.korea.ac.kr/ko/503/subview.do"


def main():
    r = httpx.get(URL, timeout=30, follow_redirects=True, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    r.raise_for_status()
    print(f"status={r.status_code} bytes={len(r.text)}")

    out = Path("tests/fixtures/sample_menu_page.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(r.text, encoding="utf-8")
    print(f"wrote {out}")

    soup = BeautifulSoup(r.text, "lxml")
    tables = soup.find_all("table")
    print(f"tables found: {len(tables)}")
    has_no_menu = "등록된 식단내용" in r.text
    print(f'contains "등록된 식단내용": {has_no_menu}')
    if has_no_menu:
        print("OK — static HTML contains menu markers (static scrape is viable).")
    else:
        print("WARN — may need Playwright fallback. Open the HTML and inspect.")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5.2: Run the probe**

Run: `python scripts/probe_scrape.py`
Expected: prints `status=200`, writes `tests/fixtures/sample_menu_page.html`, prints presence of `등록된 식단내용` marker.

- [ ] **Step 5.3: Inspect captured HTML to find navigation to all 6 cafeterias**

Read the saved `tests/fixtures/sample_menu_page.html` and look for links in the side nav matching `/ko/NNN/subview.do`. Record the six IDs and names.

- [ ] **Step 5.4: Update `src/config.py` with real cafeteria IDs**

Replace each `TBD_*` placeholder URL with the real `/ko/NNN/subview.do` discovered from the nav. Keep the Chinese and English names from the existing placeholders unless the nav reveals a better Korean name.

- [ ] **Step 5.5: Verify `test_config.py` still passes**

Run: `pytest tests/test_config.py -v`
Expected: 3 passed.

**Decision point — scraping strategy:**

If the probe showed `contains "등록된 식단내용": True` AND menu rows are visible in the saved HTML, static scraping is sufficient. Proceed with `httpx` in Task 6.

If the menu rows were empty placeholders in the static HTML, stop here and amend the plan to add `playwright` (`pip install playwright && playwright install chromium`) before continuing.

- [ ] **Step 5.6: Commit**

```bash
git add scripts/probe_scrape.py tests/fixtures/sample_menu_page.html src/config.py
git commit -m "chore: probe live page, pin 6 cafeteria IDs, capture fixture"
```

---

## Task 6: Parser (`parser.py`)

**Files:**
- Create: `src/parser.py`
- Test: `tests/test_parser.py`
- Dependency: `tests/fixtures/sample_menu_page.html` from Task 5

- [ ] **Step 6.1: Write the failing test**

Create `tests/test_parser.py`:

```python
from datetime import date
from pathlib import Path

from src.parser import parse_cafeteria_page

FIXTURE = Path(__file__).parent / "fixtures" / "sample_menu_page.html"


def test_parse_returns_seven_days():
    html = FIXTURE.read_text(encoding="utf-8")
    menu = parse_cafeteria_page(
        html,
        cafeteria_id="songnim",
        cafeteria_name_ko="수당삼양 Faculty House 송림",
        cafeteria_name_zh="수당삼양教职工之家 松林",
        cafeteria_name_en="Sudang-Samyang Faculty House Songnim",
        source_url="https://www.korea.ac.kr/ko/503/subview.do",
    )
    assert len(menu.days) == 7
    weekdays = [d.weekday for d in menu.days]
    assert weekdays == ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def test_parse_extracts_week_start_monday():
    html = FIXTURE.read_text(encoding="utf-8")
    menu = parse_cafeteria_page(
        html,
        cafeteria_id="songnim",
        cafeteria_name_ko="x", cafeteria_name_zh="x", cafeteria_name_en="x",
        source_url="https://example/",
    )
    assert menu.week_start.weekday() == 0  # Monday


def test_parse_empty_cells_yield_no_dishes():
    # A page where no menu registered should yield 7 days each with empty categories.
    html = """
    <table class='tbl-menu'>
      <thead><tr><th>구분</th><th>월(4/20)</th><th>화(4/21)</th><th>수(4/22)</th>
      <th>목(4/23)</th><th>금(4/24)</th><th>토(4/25)</th><th>일(4/26)</th></tr></thead>
      <tbody><tr><th>식사</th><td>등록된 식단내용이(가) 없습니다.</td>
      <td></td><td></td><td></td><td></td><td></td><td></td></tr></tbody>
    </table>
    """
    menu = parse_cafeteria_page(
        html,
        cafeteria_id="x", cafeteria_name_ko="x", cafeteria_name_zh="x",
        cafeteria_name_en="x", source_url="https://x/",
    )
    for day in menu.days:
        assert all(len(v) == 0 for v in day.categories.values()) or day.categories == {}
```

- [ ] **Step 6.2: Run test to verify failure**

Run: `pytest tests/test_parser.py -v`
Expected: FAIL — module missing.

- [ ] **Step 6.3: Implement `src/parser.py`**

Note: The exact CSS selectors below should be adjusted to match the fixture structure; if the probe showed a different table structure, adapt accordingly. The logic is: find the menu table, read the header row to map each column to a date (Mon–Sun), iterate body rows where the first cell is the category name and subsequent cells are dishes for each day.

```python
import logging
import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from src.models import CafeteriaMenu, DaySection, DishRaw
from src.utils import KST

log = logging.getLogger(__name__)

WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
_EMPTY_MARKERS = ("등록된 식단내용이", "등록된 식단내용이(가) 없습니다")
_DATE_PATTERN = re.compile(r"(\d{1,2})[./\-](\d{1,2})")


def _parse_week_from_header(header_texts: list[str]) -> date:
    """Headers like '월(4/20)'. Pick the Monday column, return a date in the most recent year context."""
    for text in header_texts:
        m = _DATE_PATTERN.search(text)
        if m and ("월" in text or "MON" in text.upper()):
            month, day = int(m.group(1)), int(m.group(2))
            year = datetime.now(KST).year
            candidate = date(year, month, day)
            # If candidate is > 180 days ahead, it's probably last year; roll back.
            if (candidate - datetime.now(KST).date()).days > 180:
                candidate = date(year - 1, month, day)
            return candidate
    # Fallback: use this week's Monday in KST.
    today = datetime.now(KST).date()
    return today - timedelta(days=today.weekday())


def _split_dishes(cell_text: str) -> list[DishRaw]:
    t = cell_text.strip()
    if not t:
        return []
    if any(marker in t for marker in _EMPTY_MARKERS):
        return []
    # One dish per non-empty line.
    dishes = []
    for line in t.splitlines():
        line = line.strip()
        if not line or any(marker in line for marker in _EMPTY_MARKERS):
            continue
        dishes.append(DishRaw(name_ko=line, raw_text=line))
    return dishes


def parse_cafeteria_page(
    html: str,
    *,
    cafeteria_id: str,
    cafeteria_name_ko: str,
    cafeteria_name_zh: str,
    cafeteria_name_en: str,
    source_url: str,
) -> CafeteriaMenu:
    soup = BeautifulSoup(html, "lxml")

    table = soup.select_one("table.tbl-menu, table.menu, div.sub_area table")
    if table is None:
        tables = soup.find_all("table")
        table = tables[0] if tables else None
    if table is None:
        log.warning("no menu table found on page %s", source_url)
        week_start = _parse_week_from_header([])
        days = [
            DaySection(date=week_start + timedelta(days=i), weekday=WEEKDAYS[i], categories={})
            for i in range(7)
        ]
        return CafeteriaMenu(
            cafeteria_id=cafeteria_id,
            cafeteria_name_ko=cafeteria_name_ko,
            cafeteria_name_zh=cafeteria_name_zh,
            cafeteria_name_en=cafeteria_name_en,
            week_start=week_start,
            days=days,
            source_url=source_url,
            fetched_at=datetime.now(KST),
        )

    thead = table.find("thead") or table
    header_cells = [th.get_text(" ", strip=True) for th in thead.find_all(["th"])[:8]]
    day_headers = header_cells[1:8] if len(header_cells) >= 8 else header_cells
    week_start = _parse_week_from_header(day_headers)

    categories_per_day: list[dict[str, list[DishRaw]]] = [{} for _ in range(7)]
    for row in table.find("tbody").find_all("tr") if table.find("tbody") else []:
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        category = cells[0].get_text(" ", strip=True)
        for i, cell in enumerate(cells[1:8]):
            dishes = _split_dishes(cell.get_text("\n", strip=True))
            if dishes:
                categories_per_day[i].setdefault(category, []).extend(dishes)

    days = [
        DaySection(
            date=week_start + timedelta(days=i),
            weekday=WEEKDAYS[i],
            categories=categories_per_day[i],
        )
        for i in range(7)
    ]
    return CafeteriaMenu(
        cafeteria_id=cafeteria_id,
        cafeteria_name_ko=cafeteria_name_ko,
        cafeteria_name_zh=cafeteria_name_zh,
        cafeteria_name_en=cafeteria_name_en,
        week_start=week_start,
        days=days,
        source_url=source_url,
        fetched_at=datetime.now(KST),
    )
```

- [ ] **Step 6.4: Run tests**

Run: `pytest tests/test_parser.py -v`
Expected: 3 passed. If the fixture's table class differs, update the selector and re-run until tests pass. **Do not** add more selectors than needed.

- [ ] **Step 6.5: Commit**

```bash
git add src/parser.py tests/test_parser.py
git commit -m "feat(parser): HTML table → CafeteriaMenu"
```

---

## Task 7: Scraper (`scraper.py`)

**Files:**
- Create: `src/scraper.py`
- Test: `tests/test_scraper.py`

- [ ] **Step 7.1: Write the failing test**

Create `tests/test_scraper.py`:

```python
import httpx
import pytest
import respx

from src.scraper import fetch_all, fetch_one


@pytest.mark.asyncio
@respx.mock
async def test_fetch_one_returns_html_on_200():
    route = respx.get("https://example.com/page").mock(
        return_value=httpx.Response(200, text="<html>OK</html>")
    )
    html = await fetch_one("https://example.com/page")
    assert html == "<html>OK</html>"
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_fetch_one_retries_on_500_then_succeeds():
    respx.get("https://example.com/p").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, text="<html>OK</html>"),
        ]
    )
    html = await fetch_one("https://example.com/p")
    assert html == "<html>OK</html>"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_one_raises_after_max_retries():
    respx.get("https://example.com/p").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_one("https://example.com/p")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_all_collects_results_and_errors():
    respx.get("https://example.com/a").mock(return_value=httpx.Response(200, text="A"))
    respx.get("https://example.com/b").mock(return_value=httpx.Response(500))
    results = await fetch_all([
        {"cafeteria_id": "a", "source_url": "https://example.com/a"},
        {"cafeteria_id": "b", "source_url": "https://example.com/b"},
    ])
    assert results[0] == ("a", "A", None)
    assert results[1][0] == "b"
    assert results[1][1] is None
    assert results[1][2] is not None  # error
```

- [ ] **Step 7.2: Run test to verify failure**

Run: `pytest tests/test_scraper.py -v`
Expected: FAIL — module missing.

- [ ] **Step 7.3: Implement `src/scraper.py`**

```python
import asyncio
import logging
from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=15),
    retry=retry_if_exception_type((httpx.HTTPError,)),
    reraise=True,
)
async def fetch_one(url: str, *, timeout: float = 30.0) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": _UA})
        r.raise_for_status()
        r.encoding = r.encoding or "utf-8"
        return r.text


async def fetch_all(cafeterias: list[dict]) -> list[tuple[str, Optional[str], Optional[str]]]:
    """Returns [(cafeteria_id, html_or_None, error_or_None), ...]."""
    async def one(c):
        try:
            html = await fetch_one(c["source_url"])
            return (c["cafeteria_id"], html, None)
        except Exception as e:
            log.warning("fetch failed for %s: %s", c["cafeteria_id"], e)
            return (c["cafeteria_id"], None, str(e))

    return await asyncio.gather(*[one(c) for c in cafeterias])
```

- [ ] **Step 7.4: Run tests**

Run: `pytest tests/test_scraper.py -v`
Expected: 4 passed.

- [ ] **Step 7.5: Commit**

```bash
git add src/scraper.py tests/test_scraper.py
git commit -m "feat(scraper): async httpx fetch with retries"
```

---

## Task 8: MiniMax client (`minimax_client.py`)

**Files:**
- Create: `src/minimax_client.py`
- Test: `tests/test_minimax_client.py`

**MiniMax API reference:** Uses `https://api.minimax.io/v1/text/chatcompletion_v2` (OpenAI-compatible). `web_search` is a built-in plugin exposed via `tools: [{"type":"web_search"}]`. If the actual MiniMax API shape differs at implementation time, adapt `_post_chat` but keep the public interface (`chat_json`, `chat_with_web_search`) intact.

- [ ] **Step 8.1: Write the failing test**

Create `tests/test_minimax_client.py`:

```python
import httpx
import pytest
import respx

from src.minimax_client import MiniMaxClient


@pytest.mark.asyncio
@respx.mock
async def test_chat_json_returns_parsed_json():
    respx.post("https://api.minimax.io/v1/text/chatcompletion_v2").mock(
        return_value=httpx.Response(200, json={
            "choices": [
                {"message": {"content": '{"zh": "大酱汤", "en": "Soybean Paste Stew"}'}}
            ]
        })
    )
    c = MiniMaxClient(api_key="k", group_id="g")
    out = await c.chat_json("x")
    assert out == {"zh": "大酱汤", "en": "Soybean Paste Stew"}


@pytest.mark.asyncio
@respx.mock
async def test_chat_json_retries_on_5xx():
    respx.post("https://api.minimax.io/v1/text/chatcompletion_v2").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}),
        ]
    )
    c = MiniMaxClient(api_key="k", group_id="g")
    out = await c.chat_json("x")
    assert out == {}


@pytest.mark.asyncio
@respx.mock
async def test_chat_with_web_search_passes_tool():
    captured = {}

    def responder(request):
        captured["body"] = request.content
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"verdict": "confirm"}'}}]
        })

    respx.post("https://api.minimax.io/v1/text/chatcompletion_v2").mock(side_effect=responder)
    c = MiniMaxClient(api_key="k", group_id="g")
    out = await c.chat_with_web_search("search for something", system="sys")
    assert out == {"verdict": "confirm"}
    assert b"web_search" in captured["body"]
```

- [ ] **Step 8.2: Run test to verify failure**

Run: `pytest tests/test_minimax_client.py -v`
Expected: FAIL — module missing.

- [ ] **Step 8.3: Implement `src/minimax_client.py`**

```python
import json
import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.minimax.io/v1/text/chatcompletion_v2"
_DEFAULT_MODEL = "MiniMax-Text-01"


class MiniMaxClient:
    def __init__(
        self,
        api_key: str,
        group_id: str,
        model: str = _DEFAULT_MODEL,
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.group_id = group_id
        self.model = model
        self.timeout = timeout

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        retry=retry_if_exception_type((httpx.HTTPError,)),
        reraise=True,
    )
    async def _post_chat(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                _ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
            r.raise_for_status()
            return r.json()

    @staticmethod
    def _extract_content(resp: dict) -> str:
        return resp["choices"][0]["message"]["content"]

    async def chat_json(self, user: str, *, system: str | None = None) -> dict:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        resp = await self._post_chat({
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        })
        content = self._extract_content(resp)
        return _safe_json(content)

    async def chat_with_web_search(self, user: str, *, system: str | None = None) -> dict:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        resp = await self._post_chat({
            "model": self.model,
            "messages": messages,
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        })
        content = self._extract_content(resp)
        return _safe_json(content)


def _safe_json(raw: str) -> dict:
    raw = raw.strip()
    # Some models wrap JSON in ```json ... ``` — strip if present.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("MiniMax returned non-JSON content: %r", raw[:200])
        return {}
```

- [ ] **Step 8.4: Run tests**

Run: `pytest tests/test_minimax_client.py -v`
Expected: 3 passed.

- [ ] **Step 8.5: Commit**

```bash
git add src/minimax_client.py tests/test_minimax_client.py
git commit -m "feat(minimax): chat_json and chat_with_web_search wrappers"
```

---

## Task 9: Translator (`translator.py`)

**Files:**
- Create: `src/translator.py`
- Test: `tests/test_translator.py`

- [ ] **Step 9.1: Write the failing test**

Create `tests/test_translator.py`:

```python
from datetime import date, datetime
from pathlib import Path
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
        )] + [DaySection(date=date(2026, 4, 20 + i), weekday=w, categories={})
              for i, w in enumerate(["TUE","WED","THU","FRI","SAT","SUN"], start=1)],
        source_url="https://x/",
        fetched_at=datetime(2026, 4, 20, 10, 30),
    )


@pytest.fixture
def empty_cache(tmp_path):
    import json
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
    client.chat_with_web_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_pass_confirm(empty_cache):
    client = AsyncMock()
    client.chat_json.return_value = {
        "zh": "大酱汤", "en": "Soybean Paste Stew",
        "note_zh": "韩式豆瓣酱炖豆腐", "note_en": "Korean stew",
    }
    client.chat_with_web_search.return_value = {"verdict": "confirm"}

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
    client.chat_with_web_search.return_value = {
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
    client.chat_with_web_search.return_value = {"verdict": "no_signal"}
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
    assert out.errors  # one error recorded
    assert empty_cache.get("된장찌개") is None  # not cached
```

- [ ] **Step 9.2: Run test to verify failure**

Run: `pytest tests/test_translator.py -v`
Expected: FAIL — module missing.

- [ ] **Step 9.3: Implement `src/translator.py`**

```python
import asyncio
import logging
from datetime import date
from typing import Protocol

from src.cache import TranslationCache
from src.models import (
    CafeteriaMenu,
    DishRaw,
    DishTranslated,
    TranslatedCafeteriaMenu,
    TranslatedDaySection,
)
from src.utils import KST, normalize_dish_name

log = logging.getLogger(__name__)

_SYSTEM_PASS1 = """你是韩国餐饮翻译专家。给出一个韩国料理菜名的中文名、英文名，以及一句成分/做法说明。
- 中文名优先使用中国大陆常见译法（例如 된장찌개 → 大酱汤，而不是字面直译）。
- 英文名使用餐饮业常见英文说法（例如 Soybean Paste Stew）。
- note_zh 和 note_en 是可选的一句话成分说明，<=30 字/单词。
严格只输出 JSON：{"zh": "...", "en": "...", "note_zh": "... or null", "note_en": "... or null"}。"""

_SYSTEM_PASS2 = """你在审阅另一个 LLM 对韩国料理菜名的翻译。
你可以使用 web_search 工具查询这道菜的常用中文/英文译法。
给出裁定：
- "confirm" 如果原译已经是常用/惯用说法；
- "revise" 如果搜索到更通用的译法（在 revised 字段里给出新的 zh/en/note_zh/note_en）；
- "no_signal" 如果搜索无法给出有效信号。
严格只输出 JSON：{"verdict": "confirm"|"revise"|"no_signal", "revised": {...} }。revised 仅在 verdict==revise 时需要。"""


class ChatClient(Protocol):
    async def chat_json(self, user: str, *, system: str | None = None) -> dict: ...
    async def chat_with_web_search(self, user: str, *, system: str | None = None) -> dict: ...


class Translator:
    def __init__(self, client: ChatClient, cache: TranslationCache, *, concurrency: int = 5):
        self.client = client
        self.cache = cache
        self._sem = asyncio.Semaphore(concurrency)

    async def translate_menu(self, menu: CafeteriaMenu) -> TranslatedCafeteriaMenu:
        errors: list[str] = []
        new_dishes_this_run: dict[str, DishTranslated] = {}

        unique_keys: dict[str, DishRaw] = {}
        for day in menu.days:
            for cat_dishes in day.categories.values():
                for d in cat_dishes:
                    try:
                        k = normalize_dish_name(d.name_ko)
                    except ValueError:
                        continue
                    unique_keys.setdefault(k, d)

        async def resolve(key: str, raw: DishRaw) -> tuple[str, DishTranslated]:
            async with self._sem:
                hit = self.cache.get(key)
                if hit is not None:
                    return key, DishTranslated(
                        name_ko=raw.name_ko,
                        name_zh=hit["zh"],
                        name_en=hit["en"],
                        note_zh=hit.get("note_zh"),
                        note_en=hit.get("note_en"),
                        is_new=False,
                        confidence=hit.get("confidence", "high"),
                    )
                try:
                    p1 = await self.client.chat_json(
                        f"菜名：{raw.name_ko}", system=_SYSTEM_PASS1,
                    )
                    p2 = await self.client.chat_with_web_search(
                        f'菜名韩文：{raw.name_ko}\n初版翻译：{p1}',
                        system=_SYSTEM_PASS2,
                    )
                    verdict = p2.get("verdict", "no_signal")
                    if verdict == "confirm":
                        chosen, confidence, searched = p1, "high", True
                    elif verdict == "revise":
                        chosen, confidence, searched = p2.get("revised") or p1, "medium", True
                    else:
                        chosen, confidence, searched = p1, "low", False

                    entry = {
                        "zh": chosen["zh"],
                        "en": chosen["en"],
                        "note_zh": chosen.get("note_zh"),
                        "note_en": chosen.get("note_en"),
                        "learned_at": date.today().isoformat(),
                        "source": "minimax-two-pass",
                        "search_confirmed": searched,
                        "confidence": confidence,
                    }
                    self.cache.set(key, entry)
                    return key, DishTranslated(
                        name_ko=raw.name_ko,
                        name_zh=entry["zh"],
                        name_en=entry["en"],
                        note_zh=entry["note_zh"],
                        note_en=entry["note_en"],
                        is_new=True,
                        confidence=confidence,
                    )
                except Exception as e:
                    log.warning("translate failed for %s: %s", raw.name_ko, e)
                    errors.append(f"{raw.name_ko}: {e}")
                    return key, DishTranslated(
                        name_ko=raw.name_ko,
                        name_zh="[translation failed]",
                        name_en="[translation failed]",
                        is_new=True,
                        confidence="failed",
                    )

        results = await asyncio.gather(*[resolve(k, d) for k, d in unique_keys.items()])
        resolved_by_key = {k: dt for k, dt in results}

        new_days: list[TranslatedDaySection] = []
        for day in menu.days:
            tcat: dict[str, list[DishTranslated]] = {}
            for cat, ds in day.categories.items():
                tcat[cat] = []
                for d in ds:
                    try:
                        k = normalize_dish_name(d.name_ko)
                    except ValueError:
                        continue
                    tcat[cat].append(resolved_by_key[k])
            new_days.append(TranslatedDaySection(
                date=day.date, weekday=day.weekday, categories=tcat,
            ))

        return TranslatedCafeteriaMenu(
            cafeteria_id=menu.cafeteria_id,
            cafeteria_name_ko=menu.cafeteria_name_ko,
            cafeteria_name_zh=menu.cafeteria_name_zh,
            cafeteria_name_en=menu.cafeteria_name_en,
            week_start=menu.week_start,
            days=new_days,
            source_url=menu.source_url,
            fetched_at=menu.fetched_at,
            errors=errors,
        )
```

- [ ] **Step 9.4: Run tests**

Run: `pytest tests/test_translator.py -v`
Expected: 5 passed.

- [ ] **Step 9.5: Commit**

```bash
git add src/translator.py tests/test_translator.py
git commit -m "feat(translator): two-pass verification with cache"
```

---

## Task 10: Email template + renderer (`renderer.py`)

**Files:**
- Create: `templates/email.html.j2`
- Create: `src/renderer.py`
- Test: `tests/test_renderer.py`
- Create: `tests/fixtures/expected_email.html` (generated on first run of snapshot test)

- [ ] **Step 10.1: Write the template `templates/email.html.j2`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ subject }}</title>
<style>
  body { margin:0; padding:0; background:#FAF8F5; color:#2A2A2A;
         font-family:-apple-system,"Noto Sans CJK KR","PingFang SC",sans-serif;
         font-size:14px; line-height:1.5; }
  .wrap { width:600px; max-width:100%; margin:0 auto; padding:20px 0; }
  .banner { background:#8B0029; color:#FFF; padding:18px 20px; border-radius:8px 8px 0 0; }
  .banner h1 { margin:0; font-size:18px; }
  .banner .sub { font-size:12px; opacity:0.85; margin-top:4px; }
  .card { background:#FFF; border:1px solid #EEE; border-top:0;
          padding:16px 18px; }
  .cafeteria { border-radius:0; }
  .cafeteria:last-of-type { border-radius:0 0 8px 8px; }
  .cname-ko { font-weight:700; font-size:15px; }
  .cname-zh { font-size:14px; color:#444; }
  .cname-en { font-size:12px; color:#666; font-style:italic; }
  .hours { font-size:11px; color:#888; margin-top:4px; }
  .src { font-size:11px; color:#8B0029; text-decoration:none; }
  .grid { width:100%; border-collapse:collapse; margin-top:12px; }
  .grid th, .grid td { border:1px solid #EEE; vertical-align:top; padding:6px;
                        font-size:12px; width:14.28%; }
  .grid th { background:#FAF8F5; font-weight:600; }
  .cat { font-size:11px; color:#8B0029; font-weight:600; text-transform:uppercase;
         letter-spacing:.05em; margin-top:10px; margin-bottom:4px; }
  .dish { margin-bottom:6px; padding:4px 6px; background:#FAF8F5; border-radius:4px; }
  .dish-ko { font-size:13px; }
  .dish-zh { font-weight:600; font-size:12px; color:#2A2A2A; }
  .dish-en { font-size:11px; color:#666; font-style:italic; }
  .dish-note { font-size:10px; color:#888; margin-top:2px; }
  .new-badge { background:#D4A437; color:#FFF; font-size:10px;
               padding:1px 5px; border-radius:8px; margin-left:4px; }
  .warn-badge { background:#D97706; color:#FFF; font-size:10px;
                padding:1px 5px; border-radius:8px; margin-left:4px; }
  .empty { color:#BBB; font-size:11px; }
  .footer { background:#FAF8F5; padding:14px 18px; border:1px solid #EEE;
            border-top:0; border-radius:0 0 8px 8px; font-size:11px; color:#666; }
  .errlist { color:#D97706; }
</style>
</head>
<body>
  <div class="wrap">
    <div class="banner">
      <h1>🍴 高丽大学食堂周菜单</h1>
      <div class="sub">{{ week_label }} · 本周新菜 {{ new_dish_count }} 道 · 共 {{ cafeterias|length }} 个食堂</div>
    </div>

    {% for c in cafeterias %}
    <div class="card cafeteria">
      <div class="cname-ko">{{ c.cafeteria_name_ko }}</div>
      <div class="cname-zh">{{ c.cafeteria_name_zh }}</div>
      <div class="cname-en">{{ c.cafeteria_name_en }}</div>
      {% if c.hours %}<div class="hours">{{ c.hours }}</div>{% endif %}
      <div><a class="src" href="{{ c.source_url }}">🔗 原始页面</a></div>

      {% set categories = c.all_categories %}
      {% for cat in categories %}
        <div class="cat">{{ cat }}</div>
        <table class="grid" role="presentation" cellspacing="0" cellpadding="0">
          <tr>
            {% for d in c.days %}<th>{{ d.label }}</th>{% endfor %}
          </tr>
          <tr>
            {% for d in c.days %}
              <td>
                {% set dishes = d.categories.get(cat, []) %}
                {% if not dishes %}
                  <div class="empty">未更新</div>
                {% else %}
                  {% for dish in dishes %}
                    <div class="dish">
                      <div class="dish-ko">{{ dish.name_ko }}{% if dish.is_new %}<span class="new-badge">★ 新</span>{% endif %}{% if dish.confidence == "failed" %}<span class="warn-badge">⚠</span>{% endif %}</div>
                      <div class="dish-zh">{{ dish.name_zh }}</div>
                      <div class="dish-en">{{ dish.name_en }}</div>
                      {% if dish.note_zh %}<div class="dish-note">{{ dish.note_zh }}</div>{% endif %}
                    </div>
                  {% endfor %}
                {% endif %}
              </td>
            {% endfor %}
          </tr>
        </table>
      {% endfor %}

      {% if c.errors %}
      <div class="errlist">⚠ 解析/翻译异常 {{ c.errors|length }} 条</div>
      {% endif %}
    </div>
    {% endfor %}

    <div class="footer">
      {% if global_errors %}
      <div class="errlist">⚠ 全局异常：{{ global_errors|join('; ') }}</div>
      {% endif %}
      📦 下次推送：{{ next_monday_label }} 10:30 KST<br>
      🤖 自动翻译，新菜名经 MiniMax 两轮验证后入库
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 10.2: Write the failing test**

Create `tests/test_renderer.py`:

```python
from datetime import date, datetime

from src.models import (
    DishTranslated,
    TranslatedCafeteriaMenu,
    TranslatedDaySection,
    TranslatedWeeklyBundle,
)
from src.renderer import render_email


def _make_bundle() -> TranslatedWeeklyBundle:
    cm = TranslatedCafeteriaMenu(
        cafeteria_id="songnim",
        cafeteria_name_ko="수당삼양 Faculty House 송림",
        cafeteria_name_zh="수당삼양教职工之家 松林",
        cafeteria_name_en="Sudang-Samyang Faculty House Songnim",
        week_start=date(2026, 4, 20),
        days=[
            TranslatedDaySection(
                date=date(2026, 4, 20), weekday="MON",
                categories={"식사": [DishTranslated(
                    name_ko="된장찌개", name_zh="大酱汤", name_en="Soybean Paste Stew",
                    note_zh="韩式豆瓣酱", is_new=True, confidence="high",
                )]},
            ),
            *[TranslatedDaySection(date=date(2026, 4, 20+i), weekday=w, categories={})
              for i, w in enumerate(["TUE","WED","THU","FRI","SAT","SUN"], start=1)],
        ],
        source_url="https://www.korea.ac.kr/ko/503/subview.do",
        fetched_at=datetime(2026, 4, 20, 10, 30),
    )
    return TranslatedWeeklyBundle(
        week_start=date(2026, 4, 20), cafeterias=[cm], new_dish_count=1,
    )


def test_render_contains_korean_and_chinese_names():
    html, subject, text = render_email(_make_bundle())
    assert "된장찌개" in html
    assert "大酱汤" in html
    assert "Soybean Paste Stew" in html
    assert "[高大食堂]" in subject
    assert "1" in subject  # new dish count
    assert "大酱汤" in text  # plaintext alternative


def test_render_uses_new_badge():
    html, _, _ = render_email(_make_bundle())
    assert "★" in html


def test_render_empty_days_show_placeholder():
    html, _, _ = render_email(_make_bundle())
    assert "未更新" in html


def test_render_contains_source_link():
    html, _, _ = render_email(_make_bundle())
    assert "https://www.korea.ac.kr/ko/503/subview.do" in html


def test_render_inlines_css():
    """premailer should convert <style> selectors into inline style attrs."""
    html, _, _ = render_email(_make_bundle())
    assert 'style="' in html  # at least some inlined styles
```

- [ ] **Step 10.3: Run test to verify failure**

Run: `pytest tests/test_renderer.py -v`
Expected: FAIL — module missing.

- [ ] **Step 10.4: Implement `src/renderer.py`**

```python
from datetime import timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from premailer import transform

from src.models import TranslatedWeeklyBundle

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

_WEEKDAY_LABELS = {
    "MON": "周一 Mon", "TUE": "周二 Tue", "WED": "周三 Wed",
    "THU": "周四 Thu", "FRI": "周五 Fri", "SAT": "周六 Sat", "SUN": "周日 Sun",
}

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


def _day_shape(day):
    return {
        "label": f"{_WEEKDAY_LABELS[day.weekday]}\n{day.date.strftime('%m/%d')}",
        "categories": day.categories,
    }


def _cafeteria_shape(cm):
    all_cats: list[str] = []
    seen = set()
    for d in cm.days:
        for cat in d.categories.keys():
            if cat not in seen:
                seen.add(cat)
                all_cats.append(cat)
    return {
        "cafeteria_name_ko": cm.cafeteria_name_ko,
        "cafeteria_name_zh": cm.cafeteria_name_zh,
        "cafeteria_name_en": cm.cafeteria_name_en,
        "hours": getattr(cm, "hours", ""),
        "source_url": cm.source_url,
        "days": [_day_shape(d) for d in cm.days],
        "all_categories": all_cats,
        "errors": cm.errors,
    }


def _plaintext(bundle: TranslatedWeeklyBundle) -> str:
    lines = [f"高丽大学食堂周菜单 {bundle.week_start.isoformat()} - "
             f"{(bundle.week_start + timedelta(days=6)).isoformat()}"]
    lines.append(f"本周新菜 {bundle.new_dish_count} 道\n")
    for c in bundle.cafeterias:
        lines.append(f"== {c.cafeteria_name_zh} / {c.cafeteria_name_en} ==")
        for d in c.days:
            if not d.categories:
                continue
            lines.append(f"[{_WEEKDAY_LABELS[d.weekday]} {d.date}]")
            for cat, ds in d.categories.items():
                for dish in ds:
                    tag = " ★新" if dish.is_new else ""
                    lines.append(f"  [{cat}] {dish.name_ko} / {dish.name_zh} / {dish.name_en}{tag}")
        lines.append("")
    return "\n".join(lines)


def render_email(bundle: TranslatedWeeklyBundle) -> tuple[str, str, str]:
    """Returns (html, subject, plaintext)."""
    tmpl = _env.get_template("email.html.j2")
    next_monday = bundle.week_start + timedelta(days=7)
    context = {
        "subject": f"[高大食堂] {bundle.week_start.strftime('%Y/%m/%d')} 周菜单 · {bundle.new_dish_count} 道新菜",
        "week_label": f"{bundle.week_start.strftime('%Y/%m/%d')} – "
                      f"{(bundle.week_start + timedelta(days=6)).strftime('%m/%d')}",
        "new_dish_count": bundle.new_dish_count,
        "cafeterias": [_cafeteria_shape(c) for c in bundle.cafeterias],
        "next_monday_label": next_monday.strftime("%Y/%m/%d (Mon)"),
        "global_errors": bundle.global_errors,
    }
    raw_html = tmpl.render(**context)
    inlined = transform(raw_html, strip_important=False, keep_style_tags=False)
    return inlined, context["subject"], _plaintext(bundle)
```

- [ ] **Step 10.5: Run tests**

Run: `pytest tests/test_renderer.py -v`
Expected: 5 passed.

- [ ] **Step 10.6: Commit**

```bash
git add templates/email.html.j2 src/renderer.py tests/test_renderer.py
git commit -m "feat(renderer): Jinja2 email template with inline CSS"
```

---

## Task 11: Mailer (`mailer.py`)

**Files:**
- Create: `src/mailer.py`
- Test: `tests/test_mailer.py`

- [ ] **Step 11.1: Write the failing test**

Create `tests/test_mailer.py`:

```python
from unittest.mock import MagicMock, patch

from src.mailer import send_mail


def test_send_mail_calls_smtp_ssl():
    with patch("src.mailer.smtplib.SMTP_SSL") as smtp_cls:
        smtp_obj = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp_obj
        send_mail(
            host="smtp.gmail.com", port=465,
            username="u@x", password="p",
            sender="u@x", recipient="to@x",
            subject="s", html="<b>h</b>", text="h",
        )
    smtp_obj.login.assert_called_once_with("u@x", "p")
    args, _ = smtp_obj.send_message.call_args
    msg = args[0]
    assert msg["Subject"] == "s"
    assert msg["From"] == "u@x"
    assert msg["To"] == "to@x"
```

- [ ] **Step 11.2: Run test to verify failure**

Run: `pytest tests/test_mailer.py -v`
Expected: FAIL — module missing.

- [ ] **Step 11.3: Implement `src/mailer.py`**

```python
import logging
import smtplib
from email.message import EmailMessage

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

log = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(5),
    retry=retry_if_exception_type((smtplib.SMTPException, OSError)),
    reraise=True,
)
def send_mail(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    sender: str,
    recipient: str,
    subject: str,
    html: str,
    text: str,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP_SSL(host, port) as s:
        s.login(username, password)
        s.send_message(msg)
    log.info("email sent to %s: %s", recipient, subject)
```

- [ ] **Step 11.4: Run tests**

Run: `pytest tests/test_mailer.py -v`
Expected: 1 passed.

- [ ] **Step 11.5: Commit**

```bash
git add src/mailer.py tests/test_mailer.py
git commit -m "feat(mailer): Gmail SMTP_SSL with retry"
```

---

## Task 12: Main orchestrator (`main.py`)

**Files:**
- Create: `src/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 12.1: Write the failing test**

Create `tests/test_main.py`:

```python
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.main import run_once


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")  # Mon 10:30 KST
async def test_skip_when_already_sent_this_week(tmp_path, monkeypatch):
    import json
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "translations.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "x", "entries": {}})
    )
    (tmp_path / "data" / "state.json").write_text(
        json.dumps({"last_sent_week": "2026-04-20", "last_run_at": "x", "status": "done"})
    )

    with patch("src.main.fetch_all", new=AsyncMock()) as fa:
        result = await run_once(trigger_index=0, total_triggers=3)

    assert result == "skipped_already_sent"
    fa.assert_not_awaited()


@pytest.mark.asyncio
@freeze_time("2026-04-20 01:30:00")  # first trigger
async def test_all_empty_on_first_trigger_sets_pending(tmp_path, monkeypatch):
    import json
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "translations.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "x", "entries": {}})
    )
    (tmp_path / "data" / "state.json").write_text(
        json.dumps({"last_sent_week": None, "last_run_at": None, "status": "idle"})
    )

    async def fake_fetch(cafs):
        return [(c["cafeteria_id"], "<html></html>", None) for c in cafs]

    with patch("src.main.fetch_all", side_effect=fake_fetch), \
         patch("src.main.parse_cafeteria_page", return_value=MagicMock(
             days=[MagicMock(categories={})]*7, errors=[],
         )):
        result = await run_once(trigger_index=0, total_triggers=3)

    assert result == "pending"
    state = json.loads((tmp_path / "data" / "state.json").read_text())
    assert state["status"] == "pending"
```

Note: these are smoke tests; full end-to-end testing happens via `workflow_dispatch` in Task 14. Additional coverage (successful send, fallback email on last trigger) can be added post-MVP if needed.

- [ ] **Step 12.2: Run test to verify failure**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — module missing.

- [ ] **Step 12.3: Implement `src/main.py`**

```python
import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.cache import StateFile, TranslationCache, git_commit_and_push
from src.config import CAFETERIAS, load_settings
from src.mailer import send_mail
from src.minimax_client import MiniMaxClient
from src.parser import parse_cafeteria_page
from src.renderer import render_email
from src.scraper import fetch_all
from src.translator import Translator
from src.models import TranslatedWeeklyBundle
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


async def run_once(*, trigger_index: int, total_triggers: int, dry_run: bool = False) -> str:
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
            _send_fallback_email(this_monday, fetch_errors, dry_run=dry_run)
            state.update(
                last_sent_week=this_monday.isoformat(),
                last_run_at=datetime.now(KST).isoformat(timespec="seconds"),
                status="failed_sent",
            )
            state.persist()
            _commit_state(this_monday, "failed_sent")
            return "failed_sent_fallback"
        state.update(
            last_sent_week=None,
            last_run_at=datetime.now(KST).isoformat(timespec="seconds"),
            status="pending",
        )
        state.persist()
        _commit_state(this_monday, "pending")
        return "pending"

    settings = load_settings()
    client = MiniMaxClient(api_key=settings.minimax_api_key, group_id=settings.minimax_group_id)
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
        1 for tm in translated_list for d in tm.days for ds in d.categories.values()
        for dish in ds if dish.is_new and dish.confidence != "failed"
    )
    bundle = TranslatedWeeklyBundle(
        week_start=this_monday,
        cafeterias=translated_list,
        new_dish_count=new_count,
        global_errors=global_errors,
    )

    html, subject, text = render_email(bundle)

    if dry_run:
        print(subject)
        print(text)
        return "dry_run_ok"

    send_mail(
        host="smtp.gmail.com", port=465,
        username=settings.gmail_username, password=settings.gmail_app_password,
        sender=settings.gmail_username, recipient=settings.mail_to,
        subject=subject, html=html, text=text,
    )

    cache.persist()
    state.update(
        last_sent_week=this_monday.isoformat(),
        last_run_at=datetime.now(KST).isoformat(timespec="seconds"),
        status="done",
    )
    state.persist()

    new_keys = sorted(cache.new_keys)
    msg = f"chore(cache): learn {len(new_keys)} dishes for week {this_monday}" if new_keys \
          else f"chore(state): mark week {this_monday} as done"
    git_commit_and_push(
        [DATA / "translations.json", DATA / "state.json"],
        message=msg, repo_dir=REPO,
    )
    return "sent"


def _send_fallback_email(this_monday, errors: list[str], *, dry_run: bool) -> None:
    settings = load_settings()
    subject = f"[高大食堂] ⚠ {this_monday} 菜单抓取失败"
    body = (
        f"三次尝试均未抓到本周菜单。\n\n错误：\n" + "\n".join(f"  - {e}" for e in errors)
        + "\n\n请访问原页面：https://www.korea.ac.kr/ko/503/subview.do\n"
        f"下次自动推送：下周一 10:30 KST"
    )
    html = f"<pre style='font-family:monospace'>{body}</pre>"
    if dry_run:
        print(subject); print(body); return
    send_mail(
        host="smtp.gmail.com", port=465,
        username=settings.gmail_username, password=settings.gmail_app_password,
        sender=settings.gmail_username, recipient=settings.mail_to,
        subject=subject, html=html, text=body,
    )


def _commit_state(this_monday, status: str) -> None:
    git_commit_and_push(
        [DATA / "state.json"],
        message=f"chore(state): {status} for week {this_monday}",
        repo_dir=REPO,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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

- [ ] **Step 12.4: Run tests**

Run: `pytest tests/test_main.py -v`
Expected: 2 passed.

- [ ] **Step 12.5: Run full test suite to verify integration**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 12.6: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat(main): orchestrator with state machine and fallback email"
```

---

## Task 13: GitHub Actions workflows

**Files:**
- Create: `.github/workflows/weekly_menu.yml`
- Create: `.github/workflows/test.yml`

- [ ] **Step 13.1: Write `.github/workflows/weekly_menu.yml`**

```yaml
name: Weekly cafeteria menu

on:
  schedule:
    - cron: "30 1 * * 1"    # 10:30 KST Mon (trigger 0 of 3)
    - cron: "0  2 * * 1"    # 11:00 KST Mon (trigger 1 of 3)
    - cron: "15 2 * * 1"    # 11:15 KST Mon (trigger 2 of 3)
  workflow_dispatch:
    inputs:
      trigger_index:
        description: "which cron slot to simulate (0/1/2)"
        default: "0"

permissions:
  contents: write

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: Install
        run: pip install -e ".[dev]"
      - name: Derive trigger index from cron
        id: idx
        run: |
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            echo "idx=${{ github.event.inputs.trigger_index }}" >> "$GITHUB_OUTPUT"
          else
            case "${{ github.event.schedule }}" in
              "30 1 * * 1") echo "idx=0" >> "$GITHUB_OUTPUT" ;;
              "0 2 * * 1")  echo "idx=1" >> "$GITHUB_OUTPUT" ;;
              "15 2 * * 1") echo "idx=2" >> "$GITHUB_OUTPUT" ;;
              *)            echo "idx=0" >> "$GITHUB_OUTPUT" ;;
            esac
          fi
      - name: Run pipeline
        env:
          MINIMAX_API_KEY: ${{ secrets.MINIMAX_API_KEY }}
          MINIMAX_GROUP_ID: ${{ secrets.MINIMAX_GROUP_ID }}
          GMAIL_USERNAME: ${{ secrets.GMAIL_USERNAME }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          MAIL_TO: ${{ secrets.MAIL_TO }}
        run: |
          git config user.email "ku-menu-bot@users.noreply.github.com"
          git config user.name  "ku-menu-bot"
          python -m src.main \
            --trigger-index ${{ steps.idx.outputs.idx }} \
            --total-triggers 3
```

- [ ] **Step 13.2: Write `.github/workflows/test.yml`**

```yaml
name: Test

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -v
```

- [ ] **Step 13.3: Commit**

```bash
git add .github/workflows/
git commit -m "ci: weekly cron + lint/test workflows"
```

---

## Task 14: README and first-run validation

**Files:**
- Create: `README.md`

- [ ] **Step 14.1: Write `README.md`**

```markdown
# Korea University Cafeteria Weekly Menu Mailer

Auto-scrapes the 6 Korea University cafeteria weekly menus every Monday morning,
translates new Korean dish names to Chinese + English with MiniMax (two-pass
verification + web search), and emails a formatted HTML digest to
`ku-menu-bot@users.noreply.github.com` by 11:30 KST.

## Architecture

See `docs/superpowers/specs/2026-04-20-ku-cafeteria-menu-design.md`.

## Setup

1. Create a private GitHub repo and push this code.
2. Generate a Gmail App Password at <https://myaccount.google.com/apppasswords>.
3. Get MiniMax credentials from the MiniMax console (API key + Group ID).
4. In GitHub → Settings → Secrets and variables → Actions, add:
   - `MINIMAX_API_KEY`, `MINIMAX_GROUP_ID`
   - `GMAIL_USERNAME` = `ku-menu-bot@users.noreply.github.com`
   - `GMAIL_APP_PASSWORD` = the 16-char app password
   - `MAIL_TO` = `ku-menu-bot@users.noreply.github.com`
5. Manually trigger the `Weekly cafeteria menu` workflow (Actions tab →
   `Run workflow`) to validate the first run.

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in secrets
pytest -v              # run unit tests
python -m src.main --dry-run  # prints subject + plaintext, doesn't send or cache
```

## Schedule

- `30 1 * * 1` UTC = 10:30 KST Mon (first try)
- `0 2 * * 1`  UTC = 11:00 KST Mon (second try)
- `15 2 * * 1` UTC = 11:15 KST Mon (last try, falls back to error email)
```

- [ ] **Step 14.2: Commit**

```bash
git add README.md
git commit -m "docs: README with setup and schedule"
```

- [ ] **Step 14.3: Push to GitHub**

```bash
# After creating the private repo on GitHub:
git remote add origin git@github.com:<your-user>/DinnermenuatKU.git
git push -u origin main
```

- [ ] **Step 14.4: Add GitHub Secrets (manual)**

Follow README Setup step 4. Confirm all 5 secrets exist.

- [ ] **Step 14.5: Manually trigger `Weekly cafeteria menu` workflow**

GitHub → Actions tab → select workflow → `Run workflow` → `main` branch.

- [ ] **Step 14.6: Verify**

- Check the email inbox for `ku-menu-bot@users.noreply.github.com`: HTML email with 6 cafeterias, correct translations, source links.
- Check the repo: `data/translations.json` should have a new commit with learned dishes; `data/state.json` should show `status: done` and `last_sent_week` = this Monday.
- Check workflow run log: no unexpected errors; summary shows cafeteria count, new dish count, errors.

If any checks fail, open an issue in the repo describing the observation, debug the relevant module, add a regression test if feasible, fix, and re-run.
