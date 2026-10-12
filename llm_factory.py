"""LLM factory supporting multiple providers via the OpenAI-compatible SDK.

The default provider is DeepSeek. Providers can be switched either at
construction time or at runtime through :meth:`LLMFactory.switch_provider`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

from openai import OpenAI


@dataclass
class ProviderConfig:
    """Configuration for a single OpenAI-compatible provider."""

    base_url: str
    model: str
    api_key: Optional[str] = None


# Built-in provider presets. Any provider that exposes an OpenAI-compatible
# API can be added here or supplied directly to the factory.
PROVIDERS: Dict[str, ProviderConfig] = {
    "deepseek": ProviderConfig(
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
    ),
    "openai": ProviderConfig(
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
    ),
}


class LLMFactory:
    """Create and manage chat-completion clients across multiple providers.

    Args:
        provider: Name of the provider to use. Defaults to ``"deepseek"``.
        api_key: API key used for authentication. This is left as an instance
            variable so it can be supplied later or overridden per provider.
        base_url: Optional override for the provider's base URL.
        model: Optional override for the provider's default model.
        providers: Optional mapping of provider name to ``ProviderConfig``
            used to extend or replace the built-in ``PROVIDERS`` registry.
        **client_kwargs: Extra keyword arguments forwarded to ``OpenAI``.
    """

    DEFAULT_PROVIDER = "deepseek"

    def __init__(
        self,
        provider: str = DEFAULT_PROVIDER,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        providers: Optional[Dict[str, ProviderConfig]] = None,
        **client_kwargs: Any,
    ) -> None:
        # API key is intentionally a plain variable that callers may set or
        # replace at any time (e.g. from environment variables).
        self.api_key: Optional[str] = api_key

        self._providers: Dict[str, ProviderConfig] = {
            name: ProviderConfig(
                base_url=cfg.base_url,
                model=cfg.model,
                api_key=cfg.api_key,
            )
            for name, cfg in {**PROVIDERS, **(providers or {})}.items()
        }

        self._client_kwargs = client_kwargs

        self.provider: str = ""
        self.base_url: str = ""
        self.model: str = ""
        self.client: Optional[OpenAI] = None

        self.switch_provider(
            provider=provider,
            base_url=base_url,
            model=model,
        )

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------
    def switch_provider(
        self,
        provider: str,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> "LLMFactory":
        """Switch to another provider and (re)build the underlying client.

        Args:
            provider: Name of the provider to switch to.
            base_url: Optional base URL override for this provider.
            model: Optional model override for this provider.

        Returns:
            The factory instance, to allow chaining.
        """
        provider = provider or self.DEFAULT_PROVIDER

        if provider in self._providers:
            cfg = self._providers[provider]
            resolved_base_url = base_url or cfg.base_url
            resolved_model = model or cfg.model
            resolved_api_key = self.api_key or cfg.api_key
        else:
            # Allow ad-hoc providers that are not in the registry.
            if not base_url or not model:
                raise ValueError(
                    f"Unknown provider '{provider}'. Supply both 'base_url' "
                    f"and 'model', or register it via the 'providers' mapping."
                )
            resolved_base_url = base_url
            resolved_model = model
            resolved_api_key = self.api_key

        self.provider = provider
        self.base_url = resolved_base_url
        self.model = resolved_model
        if resolved_api_key:
            self.api_key = resolved_api_key

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            **self._client_kwargs,
        )
        return self

    def register_provider(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
    ) -> None:
        """Register (or overwrite) a provider configuration."""
        self._providers[name] = ProviderConfig(
            base_url=base_url,
            model=model,
            api_key=api_key,
        )

    def list_providers(self) -> List[str]:
        """Return the names of all known providers."""
        return sorted(self._providers.keys())

    # ------------------------------------------------------------------
    # Chat helpers
    # ------------------------------------------------------------------
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Send a chat completion request and return the assistant content.

        Args:
            messages: Chat messages in OpenAI format.
            model: Optional per-request model override.
            **kwargs: Extra parameters forwarded to ``chat.completions.create``.

        Returns:
            The assistant's reply as a string.
        """
        response = self.client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Stream a chat completion, yielding incremental content chunks."""
        stream = self.client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                yield delta.content
