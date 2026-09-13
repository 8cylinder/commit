from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Protocol

import boto3
from botocore.exceptions import (
    CredentialRetrievalError,
    NoCredentialsError,
    PartialCredentialsError,
    ProfileNotFound,
    SSOError,
    TokenRetrievalError,
)

from .config import DEFAULT_ENV_FILE
from .prompt import wrap_message


class ProviderError(Exception):
    """A provider failed to produce a message."""


class AuthError(ProviderError):
    """A provider could not authenticate; the message carries a fix-it hint."""


class HttpResponse(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...


class Provider(Protocol):
    name: str

    def generate(self, prompt: str) -> str: ...


class BedrockClaudeProvider:
    name = "bedrock"

    def __init__(
        self,
        model: str,
        profile: str = "bedrock",
        region: str = "us-west-2",
        session_factory: Callable[..., boto3.Session] | None = None,
    ) -> None:
        self.model = model
        self.profile = profile
        self.region = region
        self._session_factory = session_factory or boto3.Session

    def generate(self, prompt: str) -> str:
        try:
            session = self._session_factory(profile_name=self.profile)
            client = session.client("bedrock-runtime", region_name=self.region)
            response = client.invoke_model(
                modelId=self.model,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                ),
            )
        except (
            NoCredentialsError,
            TokenRetrievalError,
            SSOError,
            CredentialRetrievalError,
            ProfileNotFound,
            PartialCredentialsError,
        ) as exc:
            raise AuthError(
                "AWS session has expired or credentials are missing.\n"
                f"Run aws sso login --profile {self.profile}"
            ) from exc

        body = json.loads(response["body"].read())
        raw = body["content"][0]["text"].strip()
        return wrap_message(raw)


class DeepSeekProvider:
    name = "deepseek"

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        urlopen: Callable[..., HttpResponse] | None = None,
        timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise AuthError(
                "DEEPSEEK_API_KEY is not set. Export it or add it to "
                f"{DEFAULT_ENV_FILE}."
            )
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._urlopen = urlopen or urllib.request.urlopen
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                }
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            response = self._urlopen(request, timeout=self.timeout)
            try:
                payload = json.loads(response.read())
            finally:
                response.close()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AuthError(
                    "DeepSeek rejected the API key.\n"
                    "Check DEEPSEEK_API_KEY or run cm with --provider bedrock."
                ) from exc
            raise ProviderError(
                f"DeepSeek request failed with HTTP {exc.code}."
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(
                f"Could not reach DeepSeek at {self.base_url}: {exc.reason}"
            ) from exc

        raw = payload["choices"][0]["message"]["content"].strip()
        return wrap_message(raw)
