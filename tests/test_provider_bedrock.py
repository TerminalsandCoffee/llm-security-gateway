"""Tests for src/providers/bedrock.py — Bedrock Converse API provider."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.providers.bedrock import BedrockProvider


@pytest.fixture
def provider():
    return BedrockProvider()


# --- Request translation tests (pure logic, no mocking) ---


class TestTranslateRequest:

    def test_system_and_user_messages(self):
        body = {
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
            ],
        }
        result = BedrockProvider._translate_request(body, "anthropic.claude-3-sonnet")
        assert result["modelId"] == "anthropic.claude-3-sonnet"
        assert result["system"] == [{"text": "You are helpful."}]
        assert result["messages"] == [
            {"role": "user", "content": [{"text": "Hello"}]},
        ]

    def test_user_and_assistant_messages(self):
        body = {
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
                {"role": "user", "content": "How are you?"},
            ],
        }
        result = BedrockProvider._translate_request(body, "model-id")
        assert len(result["messages"]) == 3
        assert "system" not in result

    def test_inference_params(self):
        body = {
            "messages": [{"role": "user", "content": "x"}],
            "temperature": 0.5,
            "max_tokens": 100,
            "top_p": 0.9,
        }
        result = BedrockProvider._translate_request(body, "model-id")
        assert result["inferenceConfig"] == {
            "temperature": 0.5,
            "maxTokens": 100,
            "topP": 0.9,
        }

    def test_stop_sequences(self):
        body = {
            "messages": [{"role": "user", "content": "x"}],
            "stop": ["END", "STOP"],
        }
        result = BedrockProvider._translate_request(body, "model-id")
        assert result["inferenceConfig"]["stopSequences"] == ["END", "STOP"]

    def test_no_inference_config_when_empty(self):
        body = {"messages": [{"role": "user", "content": "x"}]}
        result = BedrockProvider._translate_request(body, "model-id")
        assert "inferenceConfig" not in result

    def test_multiple_system_messages(self):
        body = {
            "messages": [
                {"role": "system", "content": "Rule 1"},
                {"role": "system", "content": "Rule 2"},
                {"role": "user", "content": "Go"},
            ],
        }
        result = BedrockProvider._translate_request(body, "model-id")
        assert len(result["system"]) == 2
        assert result["system"][0]["text"] == "Rule 1"


# --- Response translation tests ---


class TestTranslateResponse:

    def test_basic_response(self):
        response = {
            "output": {"message": {"content": [{"text": "Hello!"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 10, "outputTokens": 5},
        }
        result = BedrockProvider._translate_response(response, "anthropic.claude-3-sonnet")
        assert result["object"] == "chat.completion"
        assert result["model"] == "anthropic.claude-3-sonnet"
        assert result["choices"][0]["message"]["content"] == "Hello!"
        assert result["choices"][0]["finish_reason"] == "stop"
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 5
        assert result["usage"]["total_tokens"] == 15

    def test_max_tokens_stop_reason(self):
        response = {
            "output": {"message": {"content": [{"text": "truncated"}]}},
            "stopReason": "max_tokens",
            "usage": {"inputTokens": 5, "outputTokens": 100},
        }
        result = BedrockProvider._translate_response(response, "model-id")
        assert result["choices"][0]["finish_reason"] == "length"

    def test_multi_text_blocks(self):
        response = {
            "output": {"message": {"content": [
                {"text": "Part 1 "},
                {"text": "Part 2"},
            ]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 2},
        }
        result = BedrockProvider._translate_response(response, "model-id")
        assert result["choices"][0]["message"]["content"] == "Part 1 Part 2"


# --- chat_completion tests (mock _call_converse) ---


class TestChatCompletion:

    async def test_success(self, provider):
        converse_response = {
            "output": {"message": {"content": [{"text": "Hi there"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 8, "outputTokens": 3},
        }
        provider._call_converse = MagicMock(return_value=converse_response)

        result = await provider.chat_completion(
            body={"messages": [{"role": "user", "content": "Hello"}]},
            api_key="ignored",
            model_id="anthropic.claude-3-sonnet",
        )
        assert result.status_code == 200
        assert result.body["choices"][0]["message"]["content"] == "Hi there"

    async def test_missing_model_id_raises_400(self, provider):
        with pytest.raises(HTTPException) as exc_info:
            await provider.chat_completion(body={}, api_key="", model_id="")
        assert exc_info.value.status_code == 400
        assert "bedrock_model_id" in exc_info.value.detail

    async def test_throttling_raises_429(self, provider):
        exc = Exception("Rate exceeded")
        exc.response = {"Error": {"Code": "ThrottlingException"}}
        provider._call_converse = MagicMock(side_effect=exc)

        with pytest.raises(HTTPException) as exc_info:
            await provider.chat_completion(
                body={"messages": [{"role": "user", "content": "x"}]},
                api_key="", model_id="model-id",
            )
        assert exc_info.value.status_code == 429

    async def test_validation_raises_400(self, provider):
        exc = Exception("Invalid input")
        exc.response = {"Error": {"Code": "ValidationException"}}
        provider._call_converse = MagicMock(side_effect=exc)

        with pytest.raises(HTTPException) as exc_info:
            await provider.chat_completion(
                body={"messages": [{"role": "user", "content": "x"}]},
                api_key="", model_id="model-id",
            )
        assert exc_info.value.status_code == 400

    async def test_access_denied_raises_403(self, provider):
        exc = Exception("Not authorized")
        exc.response = {"Error": {"Code": "AccessDeniedException"}}
        provider._call_converse = MagicMock(side_effect=exc)

        with pytest.raises(HTTPException) as exc_info:
            await provider.chat_completion(
                body={"messages": [{"role": "user", "content": "x"}]},
                api_key="", model_id="model-id",
            )
        assert exc_info.value.status_code == 403

    async def test_generic_error_raises_502(self, provider):
        exc = Exception("Something broke")
        provider._call_converse = MagicMock(side_effect=exc)

        with pytest.raises(HTTPException) as exc_info:
            await provider.chat_completion(
                body={"messages": [{"role": "user", "content": "x"}]},
                api_key="", model_id="model-id",
            )
        assert exc_info.value.status_code == 502


# --- Streaming tests ---


class TestBedrockStreaming:

    async def test_stream_yields_content_chunks(self, provider):
        """contentBlockDelta events should yield StreamChunks with text."""
        stream_events = [
            {"contentBlockDelta": {"delta": {"text": "Hello"}}},
            {"contentBlockDelta": {"delta": {"text": " world"}}},
            {"messageStop": {"stopReason": "end_turn"}},
        ]
        provider._call_converse_stream = MagicMock(
            return_value={"stream": stream_events}
        )

        chunks = []
        async for chunk in provider.chat_completion_stream(
            body={"messages": [{"role": "user", "content": "hi"}]},
            api_key="",
            model_id="anthropic.claude-3-sonnet",
        ):
            chunks.append(chunk)

        # 2 content + 1 finish_reason + 1 [DONE]
        assert len(chunks) == 4
        assert chunks[0].text_delta == "Hello"
        assert chunks[1].text_delta == " world"
        assert not chunks[0].is_done
        assert chunks[3].is_done
        assert chunks[3].data == "[DONE]"

        # Verify OpenAI-compatible chunk format
        parsed = json.loads(chunks[0].data)
        assert parsed["object"] == "chat.completion.chunk"
        assert parsed["choices"][0]["delta"]["content"] == "Hello"

    async def test_stream_max_tokens_finish_reason(self, provider):
        """max_tokens stop reason maps to 'length' finish_reason."""
        stream_events = [
            {"contentBlockDelta": {"delta": {"text": "trunca"}}},
            {"messageStop": {"stopReason": "max_tokens"}},
        ]
        provider._call_converse_stream = MagicMock(
            return_value={"stream": stream_events}
        )

        chunks = []
        async for chunk in provider.chat_completion_stream(
            body={"messages": [{"role": "user", "content": "x"}]},
            api_key="",
            model_id="model-id",
        ):
            chunks.append(chunk)

        # finish_reason chunk (second-to-last before [DONE])
        finish_chunk = json.loads(chunks[-2].data)
        assert finish_chunk["choices"][0]["finish_reason"] == "length"

    async def test_stream_missing_model_id(self, provider):
        with pytest.raises(HTTPException) as exc_info:
            async for _ in provider.chat_completion_stream(
                body={}, api_key="", model_id=""
            ):
                pass
        assert exc_info.value.status_code == 400

    async def test_stream_throttling_error(self, provider):
        exc = Exception("Rate exceeded")
        exc.response = {"Error": {"Code": "ThrottlingException"}}
        provider._call_converse_stream = MagicMock(side_effect=exc)

        with pytest.raises(HTTPException) as exc_info:
            async for _ in provider.chat_completion_stream(
                body={"messages": [{"role": "user", "content": "x"}]},
                api_key="",
                model_id="model-id",
            ):
                pass
        assert exc_info.value.status_code == 429
