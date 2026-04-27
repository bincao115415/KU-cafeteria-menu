from datetime import date
from pathlib import Path

from src.parser import parse_cafeteria_page

FIX = Path(__file__).parent / "fixtures"
EMPTY = FIX / "sample_menu_page.html"
WITH_DISHES = FIX / "sample_menu_with_dishes.html"


def _parse(html: str):
    return parse_cafeteria_page(
        html,
        cafeteria_id="songnim",
        cafeteria_name_ko="수당삼양패컬티하우스 송림",
        cafeteria_name_zh="修堂三养教员俱乐部 松林",
        cafeteria_name_en="Sudang-Samyang Faculty House Songnim",
        source_url="https://www.korea.ac.kr/ko/503/subview.do",
    )


def test_parse_returns_seven_days():
    menu = _parse(EMPTY.read_text(encoding="utf-8"))
    assert len(menu.days) == 7
    assert [d.weekday for d in menu.days] == ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def test_parse_week_start_is_monday():
    menu = _parse(EMPTY.read_text(encoding="utf-8"))
    assert menu.week_start.weekday() == 0
    assert menu.week_start == date(2026, 4, 20)


def test_parse_empty_page_yields_no_dishes():
    menu = _parse(EMPTY.read_text(encoding="utf-8"))
    for day in menu.days:
        total = sum(len(v) for v in day.categories.values())
        assert total == 0, f"day {day.date} should have no dishes"


def test_parse_with_dishes_extracts_them():
    menu = _parse(WITH_DISHES.read_text(encoding="utf-8"))
    mon = menu.days[0]
    assert mon.weekday == "MON"
    assert mon.date == date(2026, 4, 20)
    meal = mon.categories.get("식사", [])
    names = [d.name_ko for d in meal]
    assert "된장찌개" in names
    assert "김치볶음밥" in names
    cook = mon.categories.get("요리", [])
    assert [d.name_ko for d in cook] == ["제육볶음"]


def test_parse_dish_day_only_has_matching_days_filled():
    menu = _parse(WITH_DISHES.read_text(encoding="utf-8"))
    # Monday has dishes; Tue-Sun should be empty per fixture
    tue = menu.days[1]
    assert sum(len(v) for v in tue.categories.values()) == 0


def test_parse_cafeteria_metadata_set():
    menu = _parse(EMPTY.read_text(encoding="utf-8"))
    assert menu.cafeteria_id == "songnim"
    assert menu.cafeteria_name_ko == "수당삼양패컬티하우스 송림"
    assert menu.source_url.endswith("503/subview.do")


def test_parse_filters_price_origin_and_side_menu_lines():
    html = """
    <table>
      <tbody>
        <tr>
          <th>2026.04.27. <br>( 월 )</th>
          <td>조식</td>
          <td></td>
          <td>
            돈가스 컵밥<br>
            or 삼각김밥 세트<br>
            ₩1,000<br>
            (우육:호주산)<br>
            (사이드메뉴: 소떡소떡)
          </td>
          <td>-</td>
        </tr>
      </tbody>
    </table>
    """
    menu = _parse(html)
    names = [d.name_ko for d in menu.days[0].categories["조식"]]
    assert names == ["돈가스 컵밥", "삼각김밥 세트", "소떡소떡"]


def test_parse_filters_unavailable_marker_line():
    html = """
    <table>
      <tbody>
        <tr>
          <th>2026.04.27. <br>( 월 )</th>
          <td>석식</td>
          <td></td>
          <td>미운영</td>
          <td>-</td>
        </tr>
      </tbody>
    </table>
    """
    menu = _parse(html)
    assert menu.days[0].categories["석식"] == []


def test_parse_filters_unavailable_marker_after_or_prefix():
    html = """
    <table>
      <tbody>
        <tr>
          <th>2026.04.27. <br>( 월 )</th>
          <td>석식</td>
          <td></td>
          <td>or 미운영</td>
          <td>-</td>
        </tr>
      </tbody>
    </table>
    """
    menu = _parse(html)
    assert menu.days[0].categories["석식"] == []
