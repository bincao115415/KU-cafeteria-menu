# Korea University Cafeteria Weekly Menu Mailer

Auto-scrapes the 6 Korea University cafeteria weekly menus every Monday morning,
translates new Korean dish names to Chinese + English with MiniMax (two-pass
verification + web search), and emails a formatted HTML digest to
`bincao115415@gmail.com` by 11:30 KST.

## Architecture

See `docs/superpowers/specs/2026-04-20-ku-cafeteria-menu-design.md` for the
full design, and `docs/superpowers/plans/2026-04-20-ku-cafeteria-menu.md` for
the implementation plan.

Pipeline:

```
scrape (httpx) → parse (BeautifulSoup)
  → translate (MiniMax chat_json + chat_with_web_search, 2-pass, cached)
  → render (Jinja2 + premailer) → send (Gmail SMTP_SSL)
```

State lives in `data/translations.json` (learned dish dictionary) and
`data/state.json` (last-run bookkeeping). Both are committed back to the repo
by the workflow so the next week starts with a warmer cache.

## Setup

1. Create a **private** GitHub repo and push this code.
2. Generate a Gmail App Password at <https://myaccount.google.com/apppasswords>
   (requires 2-Step Verification).
3. Get MiniMax credentials from the MiniMax console (API key + Group ID).
4. In GitHub → Settings → Secrets and variables → Actions, add:
   - `MINIMAX_API_KEY`, `MINIMAX_GROUP_ID`
   - `GMAIL_USERNAME` = `bincao115415@gmail.com`
   - `GMAIL_APP_PASSWORD` = the 16-char app password
   - `MAIL_TO` = `bincao115415@gmail.com`
5. Manually trigger the **Weekly cafeteria menu** workflow (Actions tab →
   `Run workflow`) to validate the first run before the cron fires.

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v                           # run unit tests (55 tests)
ruff check .                        # lint
python -m src.main --dry-run        # prints subject + plaintext, no send/cache
```

Dry-run requires all five env vars set (the pipeline still loads settings even
when dry-running, if any cafeteria has dishes).

## Schedule (GitHub Actions cron, UTC)

| UTC cron      | KST time    | Trigger index | Behavior on all-empty        |
| ------------- | ----------- | ------------- | ---------------------------- |
| `30 1 * * 1`  | 10:30 Mon   | 0             | Record `pending`, exit       |
| `0 2 * * 1`   | 11:00 Mon   | 1             | Record `pending`, exit       |
| `15 2 * * 1`  | 11:15 Mon   | 2 (last)      | Send fallback error email    |

Once any trigger successfully sends the menu email, subsequent triggers that
day will see `status: done` and skip.

## Layout

```
src/
  main.py              orchestrator (state machine + retry tiers)
  scraper.py           async httpx fetch w/ tenacity retry
  parser.py            BeautifulSoup → CafeteriaMenu (day-major rowspan table)
  translator.py        two-pass MiniMax pipeline, Semaphore-gated
  minimax_client.py    chat_json / chat_with_web_search
  renderer.py          Jinja2 + premailer; subject + HTML + plaintext
  mailer.py            SMTP_SSL send with retry
  cache.py             TranslationCache, StateFile, git_commit_and_push
  models.py            Pydantic v2 schemas
  config.py            6 cafeterias + Settings
  utils.py             normalize_dish_name, get_current_monday_kst
templates/
  email.html.j2        inline-CSS trilingual email template
data/
  translations.json    learned {ko → {zh, en, note_*, confidence}}
  state.json           {last_sent_week, status, last_run_at}
```

## Troubleshooting

- Check the workflow log on Actions for stack traces.
- `status: pending` in `data/state.json` between triggers is normal — the next
  cron will retry.
- `status: failed_sent` means all 3 triggers saw empty menus; a plaintext
  fallback email was delivered. Visit <https://www.korea.ac.kr/ko/503/subview.do>
  to confirm the cafeteria actually updated.
- If a dish is translated incorrectly, edit its entry in
  `data/translations.json` (just the `zh`/`en`/`note_*` fields) and commit.
  The cache is trusted for cache hits.
