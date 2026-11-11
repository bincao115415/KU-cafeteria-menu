# Korea University Cafeteria Weekly Menu → Notion

Auto-scrapes 5 Korea University cafeteria weekly menus every Monday morning,
translates new Korean dish names to Chinese + English with DeepSeek
(`deepseek-chat`, two-pass self-reflection), and publishes the results to a
Notion database + weekly summary page. GitHub Actions cron starts are best-effort;
they do not guarantee a publication deadline.

## Architecture

See `docs/superpowers/specs/2026-04-20-ku-cafeteria-menu-design.md` and
`docs/superpowers/plans/2026-04-21-notion-migration.md` for the current design
and implementation plan.

Pipeline:

```
scrape (httpx) → parse (BeautifulSoup)
  → translate (DeepSeek chat_json + chat_reflect, 2-pass, cached)
  → group into (cafeteria × day × meal) rows
  → resolve photos (local data/photos → Unsplash fallback)
  → upsert to Notion DB + build summary page
```

State lives in `data/translations.json` (learned dish dictionary) and
`data/state.json` (last-run bookkeeping). Both are committed back to the repo
by the workflow so the next week starts with a warmer cache.

## Notion publishing

The workflow writes to a Notion database with one row per
(cafeteria × day × lunch/dinner), and creates a weekly summary page under a
parent page. The DB must already exist with the following properties:

| Property     | Type    | Notes                                      |
| ------------ | ------- | ------------------------------------------ |
| Name         | title   | `YYYY-MM-DD Day · Cafeteria · Meal`        |
| Week         | date    | the Monday of that week                    |
| Day          | select  | `Mon`/`Tue`/`Wed`/`Thu`/`Fri`              |
| Cafeteria    | select  | `科学`/`安岩`/`产学`/`校友`/`学生中心`     |
| Meal         | select  | `午餐`/`晚餐`                              |
| Photo        | files   | external URLs (up to 25 per row)           |
| Dishes       | rich_text | rendered `• 中文 ★ / English` lines      |
| Dish Count   | number  |                                            |
| New Count    | number  | dishes never seen in prior weeks           |
| Confidence   | select  | `high`/`medium`/`low`/`failed`             |
| Source URL   | url     | original Korean cafeteria page             |

## Setup

1. Create a **private** GitHub repo and push this code.
2. In Notion, create an integration at <https://www.notion.com/my-integrations>,
   share the parent page + database with it, and copy the Internal Integration
   Token.
3. Get a DeepSeek API key at <https://platform.deepseek.com/api_keys>.
4. Optional: get an Unsplash access key at
   <https://unsplash.com/developers> for dish-photo fallback.
5. In GitHub → Settings → Secrets and variables → Actions, add:
   - `DEEPSEEK_API_KEY`
   - `NOTION_TOKEN` — the integration token
   - `NOTION_PARENT_PAGE_ID` — the page ID (32-hex) where weekly summaries land
   - `NOTION_DATABASE_ID` — the database ID for meal rows
   - `UNSPLASH_ACCESS_KEY` (optional)
6. Manually trigger the **Weekly cafeteria menu** workflow (Actions tab →
   `Run workflow`) to validate the first run before the cron fires.

## Adding your own dish photos

Drop a `.jpg`/`.jpeg`/`.png`/`.webp` at
`data/photos/<cafeteria_id>/<slug>.<ext>`, where `<slug>` is the Korean dish
name passed through `src.photos.slugify_ko` (python-slugify → ASCII with a
SHA1[:10] fallback for symbol-only names). First match wins; extensions are
checked in the order above.

Keep each photo under ~200 KB for fast Notion load. Local files always take
precedence over the Unsplash fallback.

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v                           # run unit tests
ruff check .                        # lint
python -m src.main --dry-run        # prints the publish summary, no Notion writes
```

Dry-run requires `DEEPSEEK_API_KEY` for uncached translations and menu-line
splitting, but no Notion credentials. It runs even when the week is already
published, and does not change the cache, state files, Git, or Notion.

## Publication success and retries

A week becomes `done` only when input processing has no fetch/parse/translation
errors, at least one meal row is written, all meal upserts succeed, and the weekly
summary page is created. Any incomplete publication records `failed`, preserves
the previous `last_sent_week`, and exits with code 1 so Actions shows the failure.
Successful translations are saved even when publication fails.

The next scheduled trigger or a manual workflow rerun retries the week. Existing
meal rows are updated using `(Week, Day, Cafeteria, Meal)`; missing rows are
inserted. A partial write creates no summary page. After the last scheduled
trigger, a failed week needs a manual workflow rerun.

## Translation quality

- Breakfast and other meal categories excluded from publication are filtered
  before translation, avoiding unnecessary model calls and unrelated failures.
- Compound menu lines must preserve the original Korean letters and digits in
  order when split. Invalid splits fail the attempt so a later trigger can retry.
- Both Chinese and English names must be nonempty strings. Failed translations
  are not cached; low-confidence model translations are reconsidered on the next
  run rather than trusted permanently.
- Corrections in `src/translation_rules.py` take precedence over model output
  and legacy cache values. They include Buldak, Hayashi rice and Loco Moco.
- Unresolved names retain Korean text and appear with `⚠ 待核对` in meal rows and
  summary pages. The confidence labels describe model review, not measured
  translation accuracy. Model review does not perform web search;
  `search_confirmed` stays false for its output.

## Schedule (GitHub Actions cron, UTC)

| UTC cron      | KST time    | Trigger index | Behavior on all-empty          |
| ------------- | ----------- | ------------- | ------------------------------ |
| `30 1 * * 1`  | 10:30 Mon   | 0             | Record `pending`, exit         |
| `0 2 * * 1`   | 11:00 Mon   | 1             | Record `pending`, exit         |
| `15 2 * * 1`  | 11:15 Mon   | 2 (last)      | Record `failed_silent`, exit   |

Once any trigger successfully publishes the menus, subsequent triggers that
day see `status: done` and skip.

## Layout

```
src/
  main.py              orchestrator (state machine + retry tiers)
  scraper.py           async httpx fetch w/ tenacity retry
  parser.py            BeautifulSoup → CafeteriaMenu (day-major rowspan table)
  translator.py        two-pass DeepSeek pipeline, Semaphore-gated
  deepseek_client.py   chat_json / chat_reflect (OpenAI-compatible)
  notion_writer.py     grouping, upsert, summary-page, publish orchestration
  photos.py            slugify_ko + local/Unsplash photo resolver
  cache.py             TranslationCache, StateFile, git_commit_and_push
  models.py            Pydantic v2 schemas
  config.py            5 cafeterias + Settings
  utils.py             normalize_dish_name, get_current_monday_kst
data/
  translations.json    learned {ko → {zh, en, note_*, confidence}}
  state.json           {last_sent_week, status, last_run_at}
  photos/<cafeteria_id>/<slug>.<ext>   optional user-supplied dish photos
```

## Troubleshooting

- Check the workflow log on Actions for stack traces.
- `status: pending` in `data/state.json` between triggers is normal — the next
  cron will retry.
- `status: failed_silent` means all 3 triggers saw empty menus; no Notion
  publish happened. Visit
  <https://www.korea.ac.kr/ko/503/subview.do> to confirm the cafeteria site
  actually updated.
- If a dish is translated incorrectly, edit its entry in
  `data/translations.json` (just the `zh`/`en`/`note_*` fields) and commit.
  For a durable correction that must override future model output, add an exact
  entry to `src/translation_rules.py` and a regression test.
- `status: failed` means input processing, meal writes or summary creation was
  incomplete. Inspect the Actions log and rerun the workflow; the status does not
  suppress retries.
- Notion column order in the default view is not controlled by the API. If a
  view needs `Name → Week → Day → Cafeteria → Meal → Photo → Dishes → Dish
  Count → New Count → Confidence → Source URL`, drag once in the UI; it
  persists.
