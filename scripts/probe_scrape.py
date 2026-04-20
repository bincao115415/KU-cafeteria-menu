"""One-off probe: fetches Songnim page, reports whether menu text is in static HTML, dumps fixture."""
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

URL = "https://www.korea.ac.kr/ko/503/subview.do"


def main() -> int:
    r = httpx.get(URL, timeout=30, follow_redirects=True, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
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

    # Look for sidebar nav links that match /ko/NNN/subview.do patterns — these are the 6 cafeterias
    import re
    pattern = re.compile(r"/ko/(\d+)/subview\.do")
    ids_found = sorted(set(pattern.findall(r.text)))
    print(f"candidate cafeteria IDs in page: {ids_found}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
