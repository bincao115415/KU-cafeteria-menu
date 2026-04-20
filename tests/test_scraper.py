import httpx
import pytest
import respx

from src.scraper import fetch_all, fetch_one


@pytest.mark.asyncio
@respx.mock
async def test_fetch_one_returns_html_on_200():
    route = respx.get("https://example.com/page").mock(
        return_value=httpx.Response(200, text="<html>OK</html>")
    )
    html = await fetch_one("https://example.com/page")
    assert html == "<html>OK</html>"
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_fetch_one_retries_on_500_then_succeeds():
    respx.get("https://example.com/p").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, text="<html>OK</html>"),
        ]
    )
    html = await fetch_one("https://example.com/p")
    assert html == "<html>OK</html>"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_one_raises_after_max_retries():
    respx.get("https://example.com/p").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_one("https://example.com/p")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_all_collects_results_and_errors():
    respx.get("https://example.com/a").mock(return_value=httpx.Response(200, text="A"))
    respx.get("https://example.com/b").mock(return_value=httpx.Response(500))
    results = await fetch_all([
        {"cafeteria_id": "a", "source_url": "https://example.com/a"},
        {"cafeteria_id": "b", "source_url": "https://example.com/b"},
    ])
    by_id = {r[0]: r for r in results}
    assert by_id["a"] == ("a", "A", None)
    assert by_id["b"][1] is None
    assert by_id["b"][2] is not None
