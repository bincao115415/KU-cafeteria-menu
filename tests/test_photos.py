from pathlib import Path

import httpx
import pytest
import respx

from src.photos import resolve_photo_url, slugify_ko


def test_slugify_ko_produces_ascii_slug():
    # Korean is transliterable by python-slugify
    result = slugify_ko("된장찌개")
    assert result
    assert all(c.isalnum() or c == "-" for c in result)


def test_slugify_ko_falls_back_to_sha1_on_empty():
    # python-slugify returns empty for pure-symbol strings
    result = slugify_ko("※★※")
    assert len(result) == 10
    assert all(c in "0123456789abcdef" for c in result)


def test_resolve_local_hit_returns_raw_github_url(tmp_path):
    cafe_dir = tmp_path / "photos" / "science"
    cafe_dir.mkdir(parents=True)
    slug = slugify_ko("된장찌개")
    (cafe_dir / f"{slug}.jpg").write_bytes(b"\xff\xd8\xff")  # fake jpg

    url = resolve_photo_url(
        "science", "된장찌개", "Soybean Paste Stew",
        data_dir=tmp_path,
        repo_slug="bincao115415/KU-cafeteria-menu",
    )
    assert url == (
        f"https://raw.githubusercontent.com/bincao115415/KU-cafeteria-menu/"
        f"main/data/photos/science/{slug}.jpg"
    )


def test_resolve_local_miss_no_key_returns_none(tmp_path):
    (tmp_path / "photos" / "science").mkdir(parents=True)
    url = resolve_photo_url(
        "science", "없는음식", "Nonexistent",
        data_dir=tmp_path,
    )
    assert url is None


def test_resolve_tries_multiple_extensions(tmp_path):
    cafe_dir = tmp_path / "photos" / "anam"
    cafe_dir.mkdir(parents=True)
    slug = slugify_ko("김치")
    (cafe_dir / f"{slug}.webp").write_bytes(b"RIFF")
    url = resolve_photo_url(
        "anam", "김치", "Kimchi",
        data_dir=tmp_path,
        repo_slug="bincao115415/KU-cafeteria-menu",
    )
    assert url and url.endswith(f"{slug}.webp")


@respx.mock
def test_resolve_unsplash_hit(tmp_path):
    (tmp_path / "photos" / "science").mkdir(parents=True)
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(200, json={
            "results": [{"urls": {"regular": "https://images.unsplash.com/photo-xyz"}}]
        })
    )
    url = resolve_photo_url(
        "science", "된장찌개", "Soybean Paste Stew",
        data_dir=tmp_path, unsplash_key="us_key",
    )
    assert url == "https://images.unsplash.com/photo-xyz"


@respx.mock
def test_resolve_unsplash_miss_returns_none(tmp_path):
    (tmp_path / "photos" / "science").mkdir(parents=True)
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    url = resolve_photo_url(
        "science", "없는메뉴", "Unknown",
        data_dir=tmp_path, unsplash_key="us_key",
    )
    assert url is None


@respx.mock
def test_resolve_unsplash_http_error_returns_none(tmp_path):
    (tmp_path / "photos" / "science").mkdir(parents=True)
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(500)
    )
    url = resolve_photo_url(
        "science", "아무거나", "Anything",
        data_dir=tmp_path, unsplash_key="us_key",
    )
    assert url is None


def test_resolve_local_takes_precedence_over_unsplash(tmp_path):
    # Local file present — Unsplash must NOT be called.
    cafe_dir = tmp_path / "photos" / "science"
    cafe_dir.mkdir(parents=True)
    slug = slugify_ko("된장찌개")
    (cafe_dir / f"{slug}.jpg").write_bytes(b"\xff\xd8\xff")
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get("https://api.unsplash.com/search/photos").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        url = resolve_photo_url(
            "science", "된장찌개", "Soybean Paste Stew",
            data_dir=tmp_path, unsplash_key="us_key",
        )
        assert not route.called
    assert url and url.endswith(".jpg")
