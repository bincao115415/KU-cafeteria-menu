from datetime import timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from premailer import transform

from src.config import CAFETERIAS
from src.models import TranslatedWeeklyBundle

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

_WEEKDAY_LABELS = {
    "MON": "周一 Mon", "TUE": "周二 Tue", "WED": "周三 Wed",
    "THU": "周四 Thu", "FRI": "周五 Fri",
}
_RENDER_WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI")

# Breakfast categories filtered out of the rendered view (parser/cache untouched).
_HIDDEN_CATEGORIES = {"조식", "천원의아침", "천원의아침(테이크아웃)", "아침"}

# Korean meal-period → (zh + en) display label. Fallback: show raw Korean.
_CATEGORY_LABELS = {
    "중식": "午餐 Lunch",
    "석식": "晚餐 Dinner",
    "중식B": "午餐 B · Lunch B",
    "중식(일품반상)": "午餐·套餐 · Lunch (Premium Set)",
    "중식(한식반상)": "午餐·韩餐 · Lunch (Korean Set)",
    "식사": "用餐 · Meals",
    "요리": "主菜 · À la carte",
    "파스타/스테이크 코스": "意面/牛排套餐 · Pasta/Steak Course",
}

_ADDRESS_BY_ID = {c["cafeteria_id"]: c.get("address", "") for c in CAFETERIAS}

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


def _visible_categories(day_categories: dict) -> dict:
    return {k: v for k, v in day_categories.items() if k not in _HIDDEN_CATEGORIES}


def _day_shape(day) -> dict:
    return {
        "label": f"{_WEEKDAY_LABELS[day.weekday]} {day.date.strftime('%m/%d')}",
        "categories": _visible_categories(day.categories),
    }


def _cafeteria_shape(cm) -> dict:
    weekday_days = [d for d in cm.days if d.weekday in _RENDER_WEEKDAYS]
    all_cats: list[str] = []
    seen: set[str] = set()
    for d in weekday_days:
        for cat in d.categories.keys():
            if cat in _HIDDEN_CATEGORIES or cat in seen:
                continue
            seen.add(cat)
            all_cats.append(cat)
    categories_display = [
        {"key": c, "label": _CATEGORY_LABELS.get(c, c)} for c in all_cats
    ]
    return {
        "cafeteria_name_zh": cm.cafeteria_name_zh,
        "cafeteria_name_en": cm.cafeteria_name_en,
        "hours": getattr(cm, "hours", ""),
        "address": _ADDRESS_BY_ID.get(cm.cafeteria_id, ""),
        "source_url": cm.source_url,
        "days": [_day_shape(d) for d in weekday_days],
        "categories_display": categories_display,
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
        address = _ADDRESS_BY_ID.get(c.cafeteria_id, "")
        if address:
            lines.append(f"地址 {address}")
        for d in c.days:
            if d.weekday not in _RENDER_WEEKDAYS:
                continue
            visible = _visible_categories(d.categories)
            if not visible:
                continue
            lines.append(f"[{_WEEKDAY_LABELS[d.weekday]} {d.date}]")
            for cat, ds in visible.items():
                label = _CATEGORY_LABELS.get(cat, cat)
                for dish in ds:
                    tag = " ★新" if dish.is_new else ""
                    lines.append(
                        f"  [{label}] {dish.name_zh} / {dish.name_en}{tag}"
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
