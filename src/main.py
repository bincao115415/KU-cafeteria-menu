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

    if not dry_run and state.last_sent_week == this_monday.isoformat() and state.status == "done":
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
                section_filter=c.get("section_filter"),
            )
            menus.append(menu)
        except Exception as e:
            log.exception("parse failed for %s", cid)
            fetch_errors.append(f"{cid}: parse {e}")

    non_empty = [m for m in menus if _has_any_menu(m)]

    if not non_empty:
        if dry_run:
            log.error("DRY RUN: no menu data; errors=%s", fetch_errors)
            return "dry_run_failed"
        is_last = trigger_index == total_triggers - 1
        if is_last:
            log.error("no menu data after %d triggers; errors=%s", total_triggers, fetch_errors)
            state.update(
                last_run_at=datetime.now(KST).isoformat(timespec="seconds"),
                status="failed_silent",
            )
            state.persist()
            _commit_state(this_monday, "failed_silent")
            return "failed_silent"
        state.update(
            last_run_at=datetime.now(KST).isoformat(timespec="seconds"),
            status="pending",
        )
        state.persist()
        _commit_state(this_monday, "pending")
        return "pending"

    settings = load_settings(require_notion=not dry_run)
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
    for menu in translated_list:
        global_errors.extend(f"{menu.cafeteria_id}: {error}" for error in menu.errors)
        if any(dish.confidence == "failed" for day in menu.days
               for dishes in day.categories.values() for dish in dishes):
            global_errors.append(f"{menu.cafeteria_id}: failed dish translations")
    bundle.global_errors = global_errors

    if dry_run:
        print(f"DRY RUN: would publish {len(translated_list)} cafeterias, "
              f"{new_count} new dishes, week {this_monday}")
        if global_errors:
            log.error("DRY RUN: incomplete input: %s", global_errors)
            return "dry_run_failed"
        return "dry_run_ok"

    success = False
    if global_errors:
        log.error("incomplete input; publication deferred: %s", global_errors)
    else:
        try:
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
            success = (
                result["meals_failed"] == 0
                and result["meals_inserted"] + result["meals_updated"] > 0
                and bool(result["summary_page_url"])
            )
        except Exception:
            log.exception("publication failed; a later trigger can retry")

    cache.persist()
    state.update(
        last_run_at=datetime.now(KST).isoformat(timespec="seconds"),
        status="done" if success else "failed",
    )
    if success:
        state.update(last_sent_week=this_monday.isoformat())
    state.persist()

    msg = (f"chore(cache): learn {len(cache.new_keys)} dishes for week {this_monday}; "
           f"status={'done' if success else 'failed'}")
    git_commit_and_push(
        [DATA / "translations.json", DATA / "state.json"],
        message=msg, repo_dir=REPO,
    )
    return "published" if success else "publish_failed"


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
    return 1 if result in {"publish_failed", "failed_silent", "dry_run_failed"} else 0


if __name__ == "__main__":
    sys.exit(main())
