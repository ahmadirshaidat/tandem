"""Backend-only adapters with fixed endpoints and safe, redacted errors."""

from dataclasses import dataclass

from google import genai
from google.genai import types
from openai import OpenAI

from app.core.config import settings

PROVIDERS = ("groq", "gemini", "deepseek", "openai")
BASE_URLS = {"groq": "https://api.groq.com/openai/v1", "deepseek": "https://api.deepseek.com/v1"}
INSTRUCTIONS = "You are Tandem's helpful AI teammate. Answer this single test question concisely. You have no access to workspace content, tools, files, or actions. Never claim to have performed an action."


@dataclass
class Completion:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ProviderFailure(Exception):
    def __init__(self, category: str, status: int | None = None):
        self.category = category
        self.status = status
        super().__init__(category)


def provider_key(name: str):
    value = getattr(settings, "tandem_openai_api_key" if name == "openai" else f"{name}_api_key")
    return value.get_secret_value() if value else None


def provider_model(name: str):
    return getattr(settings, f"{name}_model")


def classify_failure(exception: Exception):
    # Never retain upstream error bodies/URLs: they may contain credentials.
    status = getattr(exception, "status_code", None) or getattr(exception, "code", None)
    if not isinstance(status, int):
        status = None
    if status in {401, 403}:
        return ProviderFailure("authentication_or_access", status)
    if status == 402:
        return ProviderFailure("billing_required", status)
    if status == 429:
        return ProviderFailure("rate_limited", status)
    if status and 400 <= status < 500:
        return ProviderFailure("invalid_request", status)
    return ProviderFailure("unavailable", status)


def complete(name: str, prompt: str) -> Completion:
    key = provider_key(name)
    if not key:
        raise ProviderFailure("not_configured")
    try:
        if name == "gemini":
            with genai.Client(
                api_key=key,
                http_options=types.HttpOptions(
                    timeout=int(settings.ai_provider_timeout_seconds * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ) as client:
                response = client.models.generate_content(
                    model=provider_model(name),
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=INSTRUCTIONS,
                        max_output_tokens=settings.ai_max_output_tokens,
                        thinking_config=types.ThinkingConfig(thinking_budget=0)
                        if provider_model(name).startswith("gemini-2.5-flash")
                        else None,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        ),
                    ),
                )
                result = Completion(
                    response.text or "",
                    getattr(response.usage_metadata, "prompt_token_count", None),
                    getattr(response.usage_metadata, "candidates_token_count", None),
                )
        else:
            with OpenAI(
                api_key=key,
                base_url=BASE_URLS.get(name, "https://api.openai.com/v1"),
                timeout=settings.ai_provider_timeout_seconds,
                max_retries=0,
            ) as client:
                if name == "openai":
                    response = client.responses.create(
                        model=provider_model(name),
                        instructions=INSTRUCTIONS,
                        input=prompt,
                        max_output_tokens=settings.ai_max_output_tokens,
                        store=False,
                    )
                    result = Completion(
                        response.output_text,
                        getattr(response.usage, "input_tokens", None),
                        getattr(response.usage, "output_tokens", None),
                    )
                else:
                    response = client.chat.completions.create(
                        model=provider_model(name),
                        messages=[
                            {"role": "system", "content": INSTRUCTIONS},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=settings.ai_max_output_tokens,
                    )
                    result = Completion(
                        response.choices[0].message.content or "",
                        getattr(response.usage, "prompt_tokens", None),
                        getattr(response.usage, "completion_tokens", None),
                    )
        if not result.text.strip():
            raise ProviderFailure("empty_response")
        result.text = result.text[:16000]
        return result
    except ProviderFailure:
        raise
    except Exception as exception:
        raise classify_failure(exception) from None
