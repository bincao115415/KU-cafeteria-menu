# Publication retries and translation quality implementation plan

**Goal:** Mark a week complete only after a complete publication, allow retries after failure, and correct demonstrated translation problems.

**Architecture:** Keep the existing state machine and composite-key meal upserts. Require zero failed rows, at least one published row, a summary URL and no upstream errors before marking `done`. Create the summary only for complete input and successful meal writes. Save successful translations on failed runs for reuse; return a nonzero CLI status for failure.

**Tech Stack:** Python 3.11+, httpx, Pydantic, pytest, respx, Ruff.

## 1. Publication and retry regression tests

- Files: `tests/test_main.py`, `tests/test_notion_writer.py`.
- Cover total/partial write failure, missing summary, unexpected publisher exceptions, incomplete inputs, retry success, existing-row updates and CLI exit status.
- Run the new tests before changing implementation and confirm failures.

## 2. Publication handling

- Files: `src/main.py`, `src/notion_writer.py`.
- Persist `failed` without advancing `last_sent_week` on failure. Later triggers rerun and update existing meal rows. Suppress incomplete summaries.
- Keep dry-run free of state writes and allow it to inspect an already published week.

## 3. Translation quality

- Files: `src/translator.py`, `src/cache.py`, `src/translation_rules.py`, `src/notion_writer.py` and corresponding tests.
- Validate nonempty bilingual output, reject invented or omitted Korean text in compound-menu segmentation, and retry low-confidence or invalid cached model output.
- Improve translation/review prompts to retain dish identity and avoid inferred ingredients. Correct verified glossary mistakes in Buldak, Hayashi rice and Loco Moco; retain uncertainty for the unexplained `헐랭이` qualifier.
- Treat model review separately from external source verification. Display low-confidence translations with the Korean original.

## 4. Verification and documentation

- Run `.venv/bin/python -m pytest -q` and `.venv/bin/ruff check .`.
- Inspect current-week cached translations against captured menu input without writing to Notion.
- Update `README.md` and `CLAUDE.md` to describe the final behavior. Keep operational records in the repository; do not republish current menus as part of verification.

## Sources for glossary corrections

- Buldak is spicy chicken flavor: https://www.samyangfoods.com/eng/brand/view.do?pageIndex=1&pageUnit=10&seq=332
- Hayashi rice uses a Western-style brown sauce: https://www.sbfoods-worldwide.com/products/search/054.html
- Loco Moco is rice topped with a hamburger patty, gravy and egg: https://nutritioncenter.ctahr.hawaii.edu/loco-moco/
- `헐랭이수육`: the cafeteria source specifies `수육` (boiled meat) but does not establish what `헐랭이` means or the meat cut. Replace the unsupported pork-skin claim with a low-confidence label retaining the Korean qualifier.

## Verification completed on 2026-11-11 (Asia/Seoul)

- Regression tests failed against the original implementation, reproducing the incorrect completion state.
- Final suite: 155 tests passed; Ruff and `git diff --check` passed.
- HTTP-level retry tests verified that partial writes and a rejected summary can be retried without inserting duplicate meal rows.
- Live DeepSeek sample: three current-week menu lines expanded into 29 entries with no failed translations; source text preservation checks passed.
- Full live dry-run: all five cafeterias completed successfully for the week starting 2026-11-09. State and translation-cache checksums were unchanged. No Notion writes were made.
- The full run exposed unnecessary translation of hidden breakfast categories. Translation now uses the same meal-category selection as publishing, with a regression test.
- Updated 17 existing glossary/cache records, retaining uncertainty where the source did not support the old ingredient claim. This is a targeted correction, not an accuracy assessment of the full translation dictionary.
