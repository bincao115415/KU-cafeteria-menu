import httpx
import pytest
import respx

from src.minimax_client import MiniMaxClient


@pytest.mark.asyncio
@respx.mock
async def test_chat_json_returns_parsed_json():
    respx.post("https://api.minimaxi.com/v1/text/chatcompletion_v2").mock(
        return_value=httpx.Response(200, json={
            "choices": [
                {"message": {"content": '{"zh": "大酱汤", "en": "Soybean Paste Stew"}'}}
            ]
        })
    )
    c = MiniMaxClient(api_key="k", group_id="g")
    out = await c.chat_json("x")
    assert out == {"zh": "大酱汤", "en": "Soybean Paste Stew"}


@pytest.mark.asyncio
@respx.mock
async def test_chat_json_retries_on_5xx():
    respx.post("https://api.minimaxi.com/v1/text/chatcompletion_v2").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}),
        ]
    )
    c = MiniMaxClient(api_key="k", group_id="g")
    out = await c.chat_json("x")
    assert out == {}


@pytest.mark.asyncio
@respx.mock
async def test_chat_with_web_search_passes_tool():
    captured: dict = {}

    def responder(request):
        captured["body"] = request.content
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"verdict": "confirm"}'}}]
        })

    respx.post("https://api.minimaxi.com/v1/text/chatcompletion_v2").mock(side_effect=responder)
    c = MiniMaxClient(api_key="k", group_id="g")
    out = await c.chat_with_web_search("search for something", system="sys")
    assert out == {"verdict": "confirm"}
    assert b"web_search" in captured["body"]


def test_safe_json_strips_code_fences():
    from src.minimax_client import _safe_json

    assert _safe_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _safe_json('```\n{"a": 2}\n```') == {"a": 2}
    assert _safe_json('not json') == {}


def test_safe_json_extracts_object_from_prose():
    from src.minimax_client import _safe_json

    wrapped = (
        '让我为您翻译这个韩国料理菜名。\n\n'
        '{"zh": "大酱汤", "en": "Soybean Paste Stew"}\n\n'
        '这个菜名来自韩国大学食堂。'
    )
    assert _safe_json(wrapped) == {"zh": "大酱汤", "en": "Soybean Paste Stew"}


def test_safe_json_handles_nested_and_strings_with_braces():
    from src.minimax_client import _safe_json

    wrapped = 'prefix {"outer": {"inner": "has } brace"}, "ok": true} suffix'
    assert _safe_json(wrapped) == {"outer": {"inner": "has } brace"}, "ok": True}
