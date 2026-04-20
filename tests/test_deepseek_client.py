import httpx
import pytest
import respx

from src.deepseek_client import DeepSeekClient


@pytest.mark.asyncio
@respx.mock
async def test_chat_json_returns_parsed_json():
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [
                {"message": {"content": '{"zh": "大酱汤", "en": "Soybean Paste Stew"}'}}
            ]
        })
    )
    c = DeepSeekClient(api_key="k")
    out = await c.chat_json("x")
    assert out == {"zh": "大酱汤", "en": "Soybean Paste Stew"}


@pytest.mark.asyncio
@respx.mock
async def test_chat_json_retries_on_5xx():
    respx.post("https://api.deepseek.com/chat/completions").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}),
        ]
    )
    c = DeepSeekClient(api_key="k")
    out = await c.chat_json("x")
    assert out == {}


@pytest.mark.asyncio
@respx.mock
async def test_chat_reflect_posts_same_shape_without_tools():
    captured: dict = {}

    def responder(request):
        captured["body"] = request.content
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"verdict": "confirm"}'}}]
        })

    respx.post("https://api.deepseek.com/chat/completions").mock(side_effect=responder)
    c = DeepSeekClient(api_key="k")
    out = await c.chat_reflect("review this", system="sys")
    assert out == {"verdict": "confirm"}
    assert b"web_search" not in captured["body"]
    assert b"response_format" in captured["body"]


@pytest.mark.asyncio
@respx.mock
async def test_error_response_raises():
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "error": {"code": "invalid_api_key", "message": "bad key"}
        })
    )
    c = DeepSeekClient(api_key="k")
    with pytest.raises(RuntimeError, match="invalid_api_key"):
        await c.chat_json("x")


def test_safe_json_strips_code_fences():
    from src.deepseek_client import _safe_json

    assert _safe_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _safe_json('```\n{"a": 2}\n```') == {"a": 2}
    assert _safe_json('not json') == {}


def test_safe_json_extracts_object_from_prose():
    from src.deepseek_client import _safe_json

    wrapped = (
        '让我为您翻译这个韩国料理菜名。\n\n'
        '{"zh": "大酱汤", "en": "Soybean Paste Stew"}\n\n'
        '这个菜名来自韩国大学食堂。'
    )
    assert _safe_json(wrapped) == {"zh": "大酱汤", "en": "Soybean Paste Stew"}


def test_safe_json_handles_nested_and_strings_with_braces():
    from src.deepseek_client import _safe_json

    wrapped = 'prefix {"outer": {"inner": "has } brace"}, "ok": true} suffix'
    assert _safe_json(wrapped) == {"outer": {"inner": "has } brace"}, "ok": True}
