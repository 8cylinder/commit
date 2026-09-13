from __future__ import annotations

import json
import urllib.error
import urllib.request
from email.message import Message
from typing import cast

import pytest
from botocore.exceptions import NoCredentialsError, ProfileNotFound

from cm.providers import (
    AuthError,
    BedrockClaudeProvider,
    DeepSeekProvider,
    HttpResponse,
    ProviderError,
)


class FakeBody:
    def __init__(self, payload: dict[str, object]) -> None:
        self._data = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._data


class FakeBedrockClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.calls: list[dict[str, object]] = []
        self._payload = payload

    def invoke_model(self, **kwargs: str) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {"body": FakeBody(self._payload)}


class FakeSession:
    def __init__(self, client: FakeBedrockClient) -> None:
        self._client = client
        self.service_name: str | None = None
        self.region_name: str | None = None

    def client(
        self, service_name: str, region_name: str | None = None
    ) -> FakeBedrockClient:
        self.service_name = service_name
        self.region_name = region_name
        return self._client


class FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._data = json.dumps(payload).encode()
        self.closed = False

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        self.closed = True


def _bedrock_provider(
    client: FakeBedrockClient,
) -> tuple[BedrockClaudeProvider, FakeSession]:
    session = FakeSession(client)
    provider = BedrockClaudeProvider(
        model="model-id",
        profile="bedrock",
        region="us-west-2",
        session_factory=lambda **_: session,
    )
    return provider, session


def test_bedrock_generate_parses_response() -> None:
    client = FakeBedrockClient({"content": [{"text": "Subject\n\n* why"}]})
    provider, session = _bedrock_provider(client)

    assert provider.generate("the prompt") == "Subject\n\n* why"
    assert session.service_name == "bedrock-runtime"
    assert session.region_name == "us-west-2"

    call = client.calls[0]
    assert call["modelId"] == "model-id"
    assert call["contentType"] == "application/json"
    body = json.loads(cast(str, call["body"]))
    assert body["anthropic_version"] == "bedrock-2023-05-31"
    assert body["messages"] == [{"role": "user", "content": "the prompt"}]


@pytest.mark.parametrize(
    "error",
    [ProfileNotFound(profile="bedrock"), NoCredentialsError()],
)
def test_bedrock_auth_errors_map_to_auth_error(error: Exception) -> None:
    def factory(*_: object, **__: object) -> FakeSession:
        raise error

    provider = BedrockClaudeProvider(model="model-id", session_factory=factory)
    with pytest.raises(AuthError, match="aws sso login"):
        provider.generate("prompt")


def _deepseek_provider(
    response: HttpResponse | None = None,
    error: Exception | None = None,
    base_url: str = "https://api.deepseek.com",
) -> tuple[DeepSeekProvider, list[urllib.request.Request], list[float]]:
    captured_requests: list[urllib.request.Request] = []
    captured_timeouts: list[float] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> HttpResponse:
        captured_requests.append(request)
        captured_timeouts.append(timeout)
        if error is not None:
            raise error
        assert response is not None
        return response

    provider = DeepSeekProvider(
        model="deepseek-flash",
        api_key="secret",
        base_url=base_url,
        urlopen=urlopen,
    )
    return provider, captured_requests, captured_timeouts


def test_deepseek_request_shape_and_parse() -> None:
    response = FakeHttpResponse(
        {"choices": [{"message": {"content": "Subject\n\n* why"}}]}
    )
    provider, requests, timeouts = _deepseek_provider(response)

    assert provider.generate("the prompt") == "Subject\n\n* why"

    request = requests[0]
    assert request.full_url == "https://api.deepseek.com/chat/completions"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer secret"
    assert request.get_header("Content-type") == "application/json"

    payload = json.loads(cast(bytes, request.data))
    assert payload["model"] == "deepseek-flash"
    assert payload["stream"] is False
    assert payload["messages"] == [{"role": "user", "content": "the prompt"}]
    assert timeouts == [provider.timeout]
    assert response.closed is True


def test_deepseek_base_url_trailing_slash_normalized() -> None:
    response = FakeHttpResponse({"choices": [{"message": {"content": "x"}}]})
    provider, requests, _ = _deepseek_provider(
        response, base_url="http://localhost:8000/"
    )

    provider.generate("prompt")
    assert requests[0].full_url == "http://localhost:8000/chat/completions"


def test_deepseek_requires_api_key() -> None:
    with pytest.raises(AuthError, match="DEEPSEEK_API_KEY is not set"):
        DeepSeekProvider(model="model-id", api_key="")


def test_deepseek_401_maps_to_auth_error() -> None:
    error = urllib.error.HTTPError(
        "https://api.deepseek.com/chat/completions",
        401,
        "Unauthorized",
        Message(),
        None,
    )
    provider, _, _ = _deepseek_provider(error=error)
    with pytest.raises(AuthError, match="rejected the API key"):
        provider.generate("prompt")


def test_deepseek_http_error_maps_to_provider_error() -> None:
    error = urllib.error.HTTPError(
        "https://api.deepseek.com/chat/completions",
        500,
        "Server Error",
        Message(),
        None,
    )
    provider, _, _ = _deepseek_provider(error=error)
    with pytest.raises(ProviderError, match="HTTP 500"):
        provider.generate("prompt")


def test_deepseek_network_error_maps_to_provider_error() -> None:
    provider, _, _ = _deepseek_provider(error=urllib.error.URLError("refused"))
    with pytest.raises(ProviderError, match="Could not reach DeepSeek"):
        provider.generate("prompt")
