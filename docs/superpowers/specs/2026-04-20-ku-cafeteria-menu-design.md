# Korea University Cafeteria Weekly Menu — Design Spec

- **Date**: 2026-04-20
- **Author**: ku-menu-bot@users.noreply.github.com
- **Status**: Draft v1 — awaiting user review

## 1. Purpose

Automatically deliver a translated (Korean → Chinese + English), well-formatted HTML email of **the weekly menus for all six Korea University cafeterias** to `ku-menu-bot@users.noreply.github.com` every Monday by 11:30 KST. The user reads Chinese and English but not Korean.

## 2. Hard Requirements (user-stated)

1. Six cafeterias, all of them (Korea University Seoul campus).
2. Triggered on Monday mornings; **email must arrive no later than 11:30 KST**.
3. Translation must be **LLM-reasoned** (not mechanical MT). The model is **MiniMax**.
4. Any dish name seen for the first time must go through **two-pass verification**:
   - Pass 1 — LLM reasons and proposes the translation.
   - Pass 2 — web search is consulted to verify whether the proposed translation is the idiomatic / commonly-used rendering.
5. Languages in email: **Korean original + Chinese + English** (trilingual).
6. Runs on **GitHub Actions** (free, scheduler built in, no local machine dependency).
7. Email delivery via **Gmail SMTP + App Password** (self-to-self).
8. Learned translations persist across runs — **`translations.json` committed back to the Git repo**.

## 3. Non-Goals

- Multi-user or shared subscription.
- Hosting a public web page (email is the sole delivery surface; a raw-source-URL link is included).
- Price, calories, or nutrition data (not in the current scope; schema leaves room if the user adds this later).
- Mobile push / Slack / other channels.
- Translations for languages beyond Chinese and English.

## 4. Data Sources

Six cafeteria menu pages under `https://www.korea.ac.kr/ko/{id}/subview.do`. During scraper implementation, the six IDs will be discovered from the navigation of the known page (`503` = Sudang-Samyang Faculty House Songnim) and pinned as constants.

Menus are published by the cafeteria every Monday morning. Structure (verified via WebFetch of id=503): weekly table of day (Mon–Sun) × category (식사 / 요리 / 파스타·스테이크 코스 …). "등록된 식단내용이(가) 없습니다" marks cells without data.

Scraping strategy: try `httpx` + `BeautifulSoup` first; if the menu grid is not present in static HTML, fall back to `playwright` (headless Chromium). The fallback decision is made once during implementation and pinned, not retried per-run.

## 5. Architecture

```
GitHub Actions (cron: 01:30, 02:00, 02:15 UTC on Monday = 10:30, 11:00, 11:15 KST)
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  src/main.py  (orchestrator)                               │
│                                                            │
│  1. scraper.py     fetch 6 pages  → raw HTML              │
│  2. parser.py      HTML           → CafeteriaMenu (ko)    │
│  3. translator.py  CafeteriaMenu  → TranslatedCafeteria   │
│                      │                                     │
│                      ├── cache hit → reuse                 │
│                      └── cache miss → 2-pass verify        │
│                                                            │
│  4. renderer.py    TranslatedMenu → HTML + plaintext      │
│  5. mailer.py      HTML           → Gmail SMTP            │
│  6. cache.py       learned dishes → translations.json     │
│                      → git commit & push                   │
└───────────────────────────────────────────────────────────┘
```

### 5.1 Project layout

```
DinnermenuatKU/
├── .github/workflows/
│   ├── weekly_menu.yml          # scheduled weekly cron + workflow_dispatch
│   └── test.yml                 # lint + pytest on push/PR
├── src/
│   ├── __init__.py
│   ├── main.py                  # orchestrator, retries, fallback mail
│   ├── models.py                # Pydantic models
│   ├── scraper.py
│   ├── parser.py
│   ├── translator.py
│   ├── minimax_client.py        # thin MiniMax wrapper (chat + web_search tool call)
│   ├── renderer.py
│   ├── mailer.py
│   └── cache.py
├── templates/
│   └── email.html.j2
├── data/
│   ├── translations.json
│   └── state.json               # { last_sent_week, status }
├── tests/
│   ├── test_parser.py
│   ├── test_translator.py
│   ├── test_renderer.py
│   ├── test_cache.py
│   └── fixtures/
│       └── sample_menu_page.html
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

### 5.2 Module boundaries

| Module | Responsibility | Dependencies | Side effects |
|---|---|---|---|
| `scraper` | 6 URLs → 6 HTML strings | `httpx` / `playwright` | network reads only |
| `parser` | HTML → `CafeteriaMenu` | `bs4` | pure |
| `translator` | `Menu` → `TranslatedMenu` | `minimax_client`, `cache` | LLM + search API |
| `minimax_client` | HTTP calls to MiniMax | `httpx`, `openai`-compatible | network |
| `renderer` | `TranslatedMenu` → HTML + text | `jinja2`, `premailer` | pure |
| `mailer` | HTML + subject → email sent | `smtplib`, `email.mime` | SMTP send |
| `cache` | read/write `translations.json`, git commit & push | filesystem, `subprocess git` | disk + git remote |
| `main` | orchestration, retries, state, fallback emails | all above | composite |

## 6. Data Models

```python
# src/models.py

class DishRaw(BaseModel):
    name_ko: str
    raw_text: str

class DaySection(BaseModel):
    date: date
    weekday: Literal["MON","TUE","WED","THU","FRI","SAT","SUN"]
    categories: dict[str, list[DishRaw]]

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
    confidence: Literal["high","medium","low","failed"] = "high"

class TranslatedDaySection(BaseModel):
    date: date
    weekday: Literal["MON","TUE","WED","THU","FRI","SAT","SUN"]
    categories: dict[str, list[DishTranslated]]

class TranslatedCafeteriaMenu(BaseModel):
    cafeteria_id: str
    cafeteria_name_ko: str
    cafeteria_name_zh: str
    cafeteria_name_en: str
    week_start: date
    days: list[TranslatedDaySection]
    source_url: str
    fetched_at: datetime
    errors: list[str] = []
```

### 6.1 Translation cache schema (`data/translations.json`)

```json
{
  "schema_version": 1,
  "updated_at": "ISO-8601 timestamp (KST)",
  "entries": {
    "<normalized_ko_name>": {
      "zh": "中文名",
      "en": "English name",
      "note_zh": "optional 一句话成分",
      "note_en": "optional one-line composition",
      "learned_at": "YYYY-MM-DD",
      "source": "minimax-two-pass",
      "search_confirmed": true,
      "confidence": "high|medium|low"
    }
  }
}
```

Normalization: `re.sub(r"\s+", " ", text.strip())` plus unicode middle-dot unification. Case preserved (Korean is caseless).

### 6.2 State file (`data/state.json`)

```json
{
  "last_sent_week": "2026-04-20",
  "last_run_at": "2026-04-20T10:30:12+09:00",
  "status": "done"
}
```

`status` is `"pending"` between cron triggers if the page was empty.

## 7. Translation Pipeline (Two-Pass Verification)

```
for dish in week_menu.all_dishes:
    key = normalize(dish.name_ko)
    hit = cache.get(key)
    if hit: use hit; continue

    # Pass 1 — LLM reasoning
    p1 = minimax.chat(
        system="你是韩国餐饮翻译专家……",
        user=f"菜名：{dish.name_ko}\n给出中文名/英文名/成分说明，JSON 输出",
        response_format={"type": "json_object"},
    )

    # Pass 2 — web-search verification via MiniMax tool call
    snippets = minimax.web_search(query=f"{dish.name_ko} 한국 요리 중국어/영어")
    verdict = minimax.chat(
        system="你在审阅另一个模型的翻译是否为惯用说法……",
        user={ "proposed": p1, "search_snippets": snippets },
        response_format={"type": "json_object"},
    )

    if verdict.verdict == "confirm":
        entry = p1 with confidence=high, search_confirmed=True
    elif verdict.verdict == "revise":
        entry = verdict.revised with confidence=medium, search_confirmed=True
    else:  # no_signal / search empty
        entry = p1 with confidence=low, search_confirmed=False

    cache.set(key, entry)
    dish.is_new = True
```

**Concurrency & robustness:**

- `asyncio.gather` across new dishes, with `Semaphore(5)` to respect rate limits.
- Per-run dedup: a process-local `set` prevents verifying the same name twice when multiple cafeterias list it.
- Exponential backoff (1s, 5s, 15s) for LLM / search HTTP errors; after 3 failures, dish is emitted with `confidence="failed"`, placeholder `[translation failed]` text, and is accumulated into `errors[]` for the email footer.
- Pass 2 failure (search only) degrades silently to `confidence="low"`.

**Test coverage targets (translator):**
- cache hit path
- pass-1 / pass-2 confirm path
- pass-1 / pass-2 conflict → revised path
- search returns empty → low-confidence path
- LLM 500 → backoff → placeholder path

## 8. Email Rendering

### 8.1 Visual spec

- **Palette**: KU red `#8B0029`, cream `#FAF8F5`, charcoal text `#2A2A2A`, gold star `#D4A437` (new dish), amber `#D97706` (warning).
- **Width**: 600 px fixed (email standard).
- **Typography**: system stack `-apple-system, "Noto Sans CJK KR", "PingFang SC", sans-serif`. No webfonts. Line height 1.5.
- **Layout primitive**: nested `<table>` (email-safe), no flex/grid.
- **Per-dish card**: 4 stacked lines — Korean (large), Chinese (bold), English (small italic), optional note (small grey). Gold ★ badge if `is_new`.
- **Empty day cell**: light grey `未更新 · not yet published`.
- **Failed dish**: amber ⚠ badge, shows Korean only + `[translation failed]`.

### 8.2 Structure (per email)

```
[Banner]   高丽大学食堂周菜单 · 2026/04/20 – 04/26
           本周新菜 3 道 · 共 6 个食堂

[Cafeteria card × 6] (vertical stack)
  title block (name ko/zh/en, hours, 🔗 source URL for this cafeteria)
  weekly grid table (7 columns × N rows by category)

[Footer]   ⚠ 本周解析异常: ... (if any, lists cafeteria + reason)
           📦 下次推送: 2026/04/27 (Mon) 10:30 KST
```

### 8.3 Delivery

- `multipart/alternative`: inline HTML + plaintext fallback.
- Subject: `[高大食堂] YYYY/MM/DD 周菜单 · N 道新菜`.
- CSS inlined with `premailer` at send time.

### 8.4 Fallback email (scrape exhaustion)

If all three cron triggers fail to find any menu, the 11:15 run sends a plain fallback:

```
Subject: [高大食堂] ⚠ 2026/04/20 菜单抓取失败
Body:    三次尝试均未抓到本周菜单。请访问原页面：<link>
         下次自动推送：2026/04/27 10:30 KST
```

## 9. Scheduling / Retry / Error Handling

### 9.1 GitHub Actions cron

```yaml
on:
  schedule:
    - cron: "30 1 * * 1"   # 10:30 KST Monday
    - cron: "0  2 * * 1"   # 11:00 KST Monday
    - cron: "15 2 * * 1"   # 11:15 KST Monday
  workflow_dispatch: {}
```

Note: GitHub Actions cron is best-effort (can slip by a few minutes under load). 10:30/11:00/11:15 triple pattern provides 3 retries before the 11:30 hard deadline.

### 9.2 Main-loop state machine

```
this_monday = current Monday in Asia/Seoul (YYYY-MM-DD)
read state.json
if state.last_sent_week == this_monday and state.status == "done":
    exit  # already sent; subsequent cron runs are no-ops

fetched = scraper.scrape_all()
if every cafeteria returned empty OR all errored:
    if this is the last (11:15) trigger:
        send fallback email
        state = { last_sent_week: this_monday, status: "failed_sent" }
    else:
        state.status = "pending"
    commit state.json, exit

translated = translator.run(fetched)
html, text = renderer.render(translated)
mailer.send(html, text)
cache.persist_new_entries()
state = { last_sent_week: this_monday, status: "done" }
commit data/*.json (translations + state)
```

### 9.3 Error matrix

| Error | Handling |
|---|---|
| Network 4xx/5xx fetching a page | 3-retry exponential backoff; if that cafeteria still fails, skip with error note |
| All 6 cafeterias fail | State = pending; fallback email on last trigger |
| Parser raises on 1 cafeteria | Skip that cafeteria, accumulate into `errors[]`, continue |
| MiniMax rate-limit / 5xx | Per-dish 3-retry backoff; placeholder on final failure |
| Search call fails | Degrade to `confidence=low`, continue |
| SMTP failure | 3-retry; if final failure, log to Actions output (workflow marked failed → platform emails the account owner) |
| `git push` on cache | Warn-and-continue (next run is idempotent) |

### 9.4 Idempotency

- `state.last_sent_week` prevents double-sending within the same Monday.
- Cache writes are dict-merges keyed by normalized Korean name — safe to retry.

## 10. Secrets and Configuration

GitHub repo → Settings → Secrets and variables → Actions:

| Key | Purpose |
|---|---|
| `MINIMAX_API_KEY` | MiniMax API authentication |
| `MINIMAX_GROUP_ID` | MiniMax account group ID (required by their API) |
| `GMAIL_USERNAME` | `ku-menu-bot@users.noreply.github.com` |
| `GMAIL_APP_PASSWORD` | 16-char app password from Google |
| `MAIL_TO` | recipient address (self) |

Workflow requires `permissions: contents: write` so it can push `translations.json` + `state.json` back.

`.env.example` documents the same keys for local dev; real `.env` is gitignored.

## 11. Testing Strategy

| Layer | Target | Approach |
|---|---|---|
| Unit | parser, cache, renderer, `normalize` | pure function tests with fixtures |
| Unit (async) | translator | mock `minimax_client` with `respx`; cover 5 branches |
| Snapshot | rendered HTML email | fixed input → compare against `expected.html`; `inline-snapshot` |
| Integration (manual) | end-to-end | `workflow_dispatch` trigger on a test branch |

Tooling: `pytest`, `pytest-asyncio`, `respx`, `inline-snapshot`, `ruff` for lint.
Coverage target: parser/translator/cache ≥ 85%.

## 12. First-Run Validation Plan

1. Build project, commit, push to private GitHub repo.
2. Configure 5 secrets.
3. Manually trigger `workflow_dispatch` (ideally Tue 2026-04-21, when this week's menu is known to be published).
4. Verify email content, translation quality, and that `translations.json` was committed back.
5. Wait for automatic run on Mon 2026-04-27 and observe.

## 13. Open Questions Deferred to Implementation

- Exact `cafeteria_id` set for the 6 cafeterias (discovered while implementing the scraper).
- Whether `httpx` static scrape is sufficient or `playwright` fallback is required — confirmed by running the scraper once on a real page.
- Exact MiniMax model id and function-calling dialect (based on current MiniMax API docs at implementation time).
