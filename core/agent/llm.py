"""OpenAI-compatible LLM client supporting provider chains, fallback, and budgeting.

Supports Groq as primary provider and Ollama as local backup.
Enforces daily token budgeting, rate-limit backoff, and strict isolation
from sensitive data or large GeoJSON arrays.
"""

from dataclasses import dataclass, field
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx
import openai
from openai import OpenAI

from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Global thread-safe daily token usage accounting
_TOTAL_TOKENS_USED: int = 0
_TOKEN_LOCK = threading.Lock()


def get_total_tokens_used() -> int:
    """Return the total number of tokens consumed by the process so far."""
    with _TOKEN_LOCK:
        return _TOTAL_TOKENS_USED


def reset_total_tokens_used() -> None:
    """Reset token usage accounting (used primarily in tests)."""
    global _TOTAL_TOKENS_USED
    with _TOKEN_LOCK:
        _TOTAL_TOKENS_USED = 0


class LLMUnavailable(Exception):
    """Raised when LLM providers are exhausted, budget is exceeded, or API fails."""

    def __init__(self, message: str = "LLM unavailable", reason: str = "unknown") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass
class LLMResponse:
    """Standardized response from an LLM chat invocation."""

    text: Optional[str]
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    provider: str = ""
    model: str = ""
    fallback_used: bool = False


@dataclass
class ProviderSpec:
    """Parsed provider and model descriptor."""

    provider: str  # 'groq', 'ollama'
    model: str


def parse_provider_spec(spec_str: str) -> Optional[ProviderSpec]:
    """Parse a provider spec string like 'groq:llama-3.1-8b-instant'."""
    clean = spec_str.strip()
    if not clean:
        return None
    if ":" in clean:
        parts = clean.split(":", 1)
        return ProviderSpec(provider=parts[0].strip().lower(), model=parts[1].strip())
    # Default to groq if no prefix provided
    return ProviderSpec(provider="groq", model=clean)


def _get_chain_specs(settings: Settings, role: str) -> List[ProviderSpec]:
    """Build the ordered list of provider specs for a given operational role."""
    primary_model_str = (
        settings.LLM_PLANNER_MODEL if role == "planner" else settings.LLM_BRIEFING_MODEL
    )
    primary_spec = parse_provider_spec(primary_model_str)

    chain_specs: List[ProviderSpec] = []
    if primary_spec:
        chain_specs.append(primary_spec)

    for item in settings.LLM_CHAIN.split(","):
        spec = parse_provider_spec(item)
        if spec and (spec.provider != primary_spec.provider or spec.model != primary_spec.model):
            chain_specs.append(spec)

    return chain_specs


def _build_client_for_spec(spec: ProviderSpec, settings: Settings) -> Tuple[OpenAI, str]:
    """Construct an OpenAI-compatible client and effective model name."""
    if spec.provider == "groq":
        base_url = settings.GROQ_BASE_URL.rstrip("/")
        api_key = settings.GROQ_API_KEY.strip()
        # If Groq key is missing, raise to trigger next provider
        if not api_key:
            raise LLMUnavailable("GROQ_API_KEY is not configured", reason="auth")
        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=float(settings.LLM_TIMEOUT_S),
            max_retries=0,  # We manage chain fallback explicitly
        )
        return client, spec.model
    elif spec.provider == "ollama":
        base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        # Ollama expects an OpenAI-compatible endpoint at /v1
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        client = OpenAI(
            base_url=base_url,
            api_key="ollama",  # Dummy key required by OpenAI client
            timeout=float(settings.LLM_TIMEOUT_S),
            max_retries=0,
        )
        return client, spec.model
    else:
        raise LLMUnavailable(f"Unsupported LLM provider: {spec.provider}", reason="config")


def is_available(settings: Optional[Settings] = None) -> bool:
    """Cheap health check without spending tokens.

    Returns True if Groq API key is present or Ollama is locally reachable.
    """
    if settings is None:
        settings = get_settings()

    if settings.SIMULATE_API_FAILURE == "llm":
        return False

    if settings.GROQ_API_KEY.strip():
        return True

    # Check local Ollama reachability with a 1-second timeout
    try:
        ollama_root = settings.OLLAMA_BASE_URL.rstrip("/")
        if ollama_root.endswith("/v1"):
            ollama_root = ollama_root[:-3]
        resp = httpx.get(f"{ollama_root}/api/tags", timeout=1.0)
        return resp.status_code == 200
    except Exception:
        return False


def _extract_retry_after(exc: Exception) -> Optional[float]:
    """Attempt to parse Retry-After seconds from an HTTP 429 response."""
    try:
        response = getattr(exc, "response", None)
        if response is not None and hasattr(response, "headers"):
            retry_header = response.headers.get("retry-after")
            if retry_header:
                return float(retry_header)
    except Exception:
        pass
    return None


def chat(
    messages: List[Dict[str, Any]],
    role: str = "planner",
    tools: Optional[List[Dict[str, Any]]] = None,
    max_tokens: Optional[int] = None,
    settings: Optional[Settings] = None,
) -> LLMResponse:
    """Execute a chat completion with provider fallback and token budgeting.

    Args:
        messages: Chat prompt message list (system, user, assistant).
        role: 'planner' or 'briefing'.
        tools: Optional list of OpenAI-format tool schemas.
        max_tokens: Maximum tokens to generate (defaults: planner 150, briefing 350).
        settings: Application settings.

    Returns:
        LLMResponse containing text, tool calls, and usage info.

    Raises:
        LLMUnavailable: If all providers fail, budget is exceeded, or SIMULATE_API_FAILURE=llm.
    """
    global _TOTAL_TOKENS_USED

    if settings is None:
        settings = get_settings()

    if settings.SIMULATE_API_FAILURE == "llm":
        raise LLMUnavailable("Simulated LLM service failure", reason="simulated")

    # Enforce daily token budget before making any external calls
    with _TOKEN_LOCK:
        if _TOTAL_TOKENS_USED >= settings.LLM_DAILY_TOKEN_BUDGET:
            raise LLMUnavailable(
                f"Daily token budget exceeded: {_TOTAL_TOKENS_USED} >= {settings.LLM_DAILY_TOKEN_BUDGET}",
                reason="budget",
            )

    # Defaults per role
    if max_tokens is None:
        max_tokens = 150 if role == "planner" else 350
    temperature = 0.1 if role == "planner" else 0.2

    chain = _get_chain_specs(settings, role)
    if not chain:
        raise LLMUnavailable("No LLM provider specs configured", reason="config")

    primary_spec = chain[0]
    errors_encountered: List[str] = []

    for idx, spec in enumerate(chain):
        is_fallback = idx > 0
        try:
            client, model_name = _build_client_for_spec(spec, settings)

            kwargs: Dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            # Execute with single retry on 429 if Retry-After <= 5s
            attempt = 0
            while attempt < 2:
                attempt += 1
                try:
                    response = client.chat.completions.create(**kwargs)
                    break
                except openai.RateLimitError as rle:
                    retry_sec = _extract_retry_after(rle)
                    if retry_sec is not None and retry_sec <= 5.0 and attempt == 1:
                        logger.warning(
                            "HTTP 429 from %s:%s; waiting %.1fs before retry",
                            spec.provider,
                            spec.model,
                            retry_sec,
                        )
                        time.sleep(retry_sec)
                        continue
                    # Exceeded 5s or second 429: skip immediately to next provider
                    raise rle

            # Extract response details
            choice = response.choices[0]
            msg = choice.message
            content = msg.content

            # Normalize tool calls
            parsed_tools: List[Dict[str, Any]] = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    parsed_tools.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })

            # Usage accounting
            usage_dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            if response.usage:
                usage_dict = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
                with _TOKEN_LOCK:
                    _TOTAL_TOKENS_USED += usage_dict["total_tokens"]

            logger.info(
                "LLM call succeeded: provider=%s model=%s tokens=%d cumulative=%d fallback=%s",
                spec.provider,
                spec.model,
                usage_dict["total_tokens"],
                _TOTAL_TOKENS_USED,
                is_fallback,
            )

            return LLMResponse(
                text=content,
                tool_calls=parsed_tools,
                usage=usage_dict,
                provider=spec.provider,
                model=spec.model,
                fallback_used=is_fallback,
            )

        except Exception as exc:
            err_msg = f"{spec.provider}:{spec.model} failed: {exc}"
            logger.warning("LLM provider attempt failed: %s", err_msg)
            errors_encountered.append(err_msg)
            continue

    # All providers exhausted
    raise LLMUnavailable(
        f"All LLM providers in chain failed: {'; '.join(errors_encountered)}",
        reason="exhausted",
    )

