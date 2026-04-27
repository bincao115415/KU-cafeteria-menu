import logging
import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from src.models import CafeteriaMenu, DaySection, DishRaw
from src.utils import KST

log = logging.getLogger(__name__)

_WEEKDAY_KO_TO_EN = {
    "월": "MON", "화": "TUE", "수": "WED", "목": "THU",
    "금": "FRI", "토": "SAT", "일": "SUN",
}
_WEEKDAYS_ORDER = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
_DATE_RE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_EMPTY_MARKER = "등록된 식단내용이"
_SECTION_MARKER_RE = re.compile(r"\[([^\]]+)\]")
_PRICE_ONLY_RE = re.compile(r"^(?:₩\s*)?\d[\d,]*(?:\s*(?:원|₩))?$")
_ORIGIN_LINE_RE = re.compile(r"^\([^)]*:[^)]*\)$")
_META_LINE_RE = re.compile(r"^(?:Small\s+Large|Small|Large|면류|밥류|한식|요리류|런치|디너)$", re.IGNORECASE)


def _find_menu_table(soup: BeautifulSoup):
    """Menu table has caption '일주일간 식단 안내'; fall back to first table with the Korean day markers."""
    for t in soup.find_all("table"):
        cap = t.find("caption")
        if cap and "식단" in cap.get_text(strip=True):
            return t
    for t in soup.find_all("table"):
        text = t.get_text(" ", strip=True)
        if "식단구분" in text:
            return t
    tables = soup.find_all("table")
    return tables[0] if tables else None


def _parse_day_header(text: str) -> tuple[date | None, str | None]:
    """Header cell like '2026.04.20. ( 월 )' → (date(2026,4,20), 'MON')."""
    m = _DATE_RE.search(text)
    if not m:
        return None, None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        dt = date(y, mo, d)
    except ValueError:
        return None, None
    wd = None
    for ko, en in _WEEKDAY_KO_TO_EN.items():
        if ko in text:
            wd = en
            break
    if wd is None:
        wd = _WEEKDAYS_ORDER[dt.weekday()]
    return dt, wd


def _filter_section(cell_text: str, section_filter: str) -> str:
    """Keep only lines belonging to the section whose [label] matches section_filter.

    Input format (seen on 504/subview.do):
        [학생식당] 6,000₩
        dish1 dish2 ...
        (사이드메뉴: ...)
        [교직원식당] 7,000₩
        dish3 dish4 ...

    Header lines (matching [...]) are stripped; non-header lines belong to the
    most recent section above them. If no header is seen, lines are kept as-is
    (caller expected section_filter=None in that case, but we tolerate it).
    """
    kept: list[str] = []
    current: str | None = None
    for line in cell_text.splitlines():
        m = _SECTION_MARKER_RE.match(line.strip())
        if m:
            current = m.group(1).strip()
            continue
        if current is None or current == section_filter:
            kept.append(line)
    return "\n".join(kept)


def _split_dishes(cell_text: str) -> list[DishRaw]:
    t = cell_text.strip()
    if not t or _EMPTY_MARKER in t:
        return []

    dishes = []
    for line in t.splitlines():
        line = line.strip(" \t·-,")
        if not line or _EMPTY_MARKER in line:
            continue
        if line.lower().startswith("or "):
            line = line[3:].strip()
        if line.startswith("(") and line.endswith(")") and "사이드메뉴:" in line:
            line = line[1:-1].split(":", 1)[1].strip()
        if _PRICE_ONLY_RE.fullmatch(line) or _META_LINE_RE.fullmatch(line):
            continue
        if _ORIGIN_LINE_RE.fullmatch(line):
            continue
        if not line or _PRICE_ONLY_RE.fullmatch(line) or _META_LINE_RE.fullmatch(line):
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
    section_filter: str | None = None,
) -> CafeteriaMenu:
    soup = BeautifulSoup(html, "lxml")
    table = _find_menu_table(soup)

    days_in_order: list[tuple[date, str, dict[str, list[DishRaw]]]] = []

    if table is not None:
        tbody = table.find("tbody") or table
        current_day: tuple[date, str] | None = None
        current_cats: dict[str, list[DishRaw]] = {}

        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            if not cells:
                continue

            first = cells[0]
            # A new day starts when <th> appears (rowspan > 1 indicates day grouping)
            if first.name == "th":
                if current_day is not None:
                    days_in_order.append((current_day[0], current_day[1], current_cats))
                header_text = first.get_text(" ", strip=True)
                d, wd = _parse_day_header(header_text)
                if d is None:
                    continue
                current_day = (d, wd)
                current_cats = {}
                data_cells = cells[1:]
            else:
                data_cells = cells

            if current_day is None or not data_cells:
                continue

            category = data_cells[0].get_text(" ", strip=True)
            # Columns: 식단구분(category) | 식단제목(title) | 식단내용(dishes) | 기타정보(extra).
            # Empty rows collapse to a single colspan cell: [category, content].
            if len(data_cells) >= 3:
                content_cell = data_cells[2]
            elif len(data_cells) == 2:
                content_cell = data_cells[1]
            else:
                continue
            dish_text = content_cell.get_text("\n", strip=True)
            if section_filter:
                dish_text = _filter_section(dish_text, section_filter)
            dishes = _split_dishes(dish_text)
            if category:
                current_cats.setdefault(category, []).extend(dishes)

        if current_day is not None:
            days_in_order.append((current_day[0], current_day[1], current_cats))

    if days_in_order:
        week_start = min(d[0] for d in days_in_order)
        week_start = week_start - timedelta(days=week_start.weekday())
    else:
        today = datetime.now(KST).date()
        week_start = today - timedelta(days=today.weekday())

    by_weekday = {entry[1]: entry for entry in days_in_order}
    days: list[DaySection] = []
    for i, wd in enumerate(_WEEKDAYS_ORDER):
        entry = by_weekday.get(wd)
        if entry is not None:
            _, _, cats = entry
            days.append(DaySection(
                date=week_start + timedelta(days=i),
                weekday=wd,
                categories=cats,
            ))
        else:
            days.append(DaySection(
                date=week_start + timedelta(days=i),
                weekday=wd,
                categories={},
            ))

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
