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


def _day_shape(day) -> dict:
    return {
        "label": f"{_WEEKDAY_LABELS[day.weekday]} {day.date.strftime('%m/%d')}",
        "categories": day.categories,
    }


def _cafeteria_shape(cm) -> dict:
    all_cats: list[str] = []
    seen: set[str] = set()
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
    lines = [
        f"高丽大学食堂周菜单 {bundle.week_start.isoformat()} - "
        f"{(bundle.week_start + timedelta(days=6)).isoformat()}",
        f"本周新菜 {bundle.new_dish_count} 道",
        "",
    ]
    for c in bundle.cafeterias:
        lines.append(f"== {c.cafeteria_name_zh} / {c.cafeteria_name_en} ==")
        for d in c.days:
            if not d.categories:
                continue
            lines.append(f"[{_WEEKDAY_LABELS[d.weekday]} {d.date}]")
            for cat, ds in d.categories.items():
                for dish in ds:
                    tag = " ★新" if dish.is_new else ""
                    lines.append(
                        f"  [{cat}] {dish.name_ko} / {dish.name_zh} / {dish.name_en}{tag}"
                    )
        lines.append("")
    return "\n".join(lines)


def render_email(bundle: TranslatedWeeklyBundle) -> tuple[str, str, str]:
    """Returns (html, subject, plaintext)."""
    tmpl = _env.get_template("email.html.j2")
    next_monday = bundle.week_start + timedelta(days=7)
    subject = (
        f"[高大食堂] {bundle.week_start.strftime('%Y/%m/%d')} 周菜单 · "
        f"{bundle.new_dish_count} 道新菜"
    )
    context = {
        "subject": subject,
        "week_label": f"{bundle.week_start.strftime('%Y/%m/%d')} – "
                      f"{(bundle.week_start + timedelta(days=6)).strftime('%m/%d')}",
        "new_dish_count": bundle.new_dish_count,
        "cafeterias": [_cafeteria_shape(c) for c in bundle.cafeterias],
        "next_monday_label": next_monday.strftime("%Y/%m/%d (Mon)"),
        "global_errors": bundle.global_errors,
    }
    raw_html = tmpl.render(**context)
    inlined = transform(raw_html, strip_important=False, keep_style_tags=False)
    return inlined, subject, _plaintext(bundle)
