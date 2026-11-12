"""Validated platform session metadata for the existing Web agent launchers."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

from .platform_config import load_platform


UNBOUND = object()
_CONTEXT_KEYS = {
    "schema_version", "platform_id", "execution_mode", "browser_profile",
    "start_url", "allowed_hosts", "max_steps", "config_revision",
}
_PROVIDERS = {
    "openai", "anthropic", "google", "groq", "openrouter", "cerebras",
    "together", "perplexity", "aws", "requesty",
}


class SessionContextError(ValueError):
    """An invalid platform or unsupported session setting."""

    status_code = 400


class SessionConflictError(SessionContextError):
    """A conversation binding or platform revision cannot be silently changed."""

    status_code = 409


def _execution_mode(value: object) -> str:
    if not isinstance(value, str) or value not in ("supervised", "auto"):
        raise SessionContextError("execution_mode must be supervised or auto.")
    return value


def build_platform_context(
    platform_id: str,
    execution_mode: str = "supervised",
    *,
    root: Path | None = None,
) -> dict:
    """Build immutable-by-value run metadata exclusively from trusted config."""
    mode = _execution_mode(execution_mode)
    try:
        platform = load_platform(platform_id, root=root)
    except (OSError, ValueError, TypeError) as error:
        raise SessionContextError(f"Invalid platform configuration: {error}") from error
    technical = {
        "schema_version": platform.schema_version,
        "id": platform.id,
        "name": platform.name,
        "engine": platform.engine,
        "start_url": platform.start_url,
        "allowed_hosts": list(platform.allowed_hosts),
        "browser": platform.browser,
        "max_steps": platform.max_steps,
    }
    revision = hashlib.sha256(
        json.dumps(technical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "platform_id": platform.id,
        "execution_mode": mode,
        "browser_profile": f"saccade-{platform.id}",
        "start_url": platform.start_url,
        "allowed_hosts": list(platform.allowed_hosts),
        "max_steps": platform.max_steps,
        "config_revision": revision,
    }


def _validate_context(context: object, *, root: Path | None = None) -> dict:
    if (
        not isinstance(context, dict)
        or set(context) != _CONTEXT_KEYS
        or type(context.get("schema_version")) is not int
        or context.get("schema_version") != 1
        or type(context.get("max_steps")) is not int
        or not isinstance(context.get("allowed_hosts"), list)
        or any(not isinstance(host, str) for host in context.get("allowed_hosts", []))
    ):
        raise SessionContextError("Invalid platform session context schema.")
    expected = build_platform_context(
        context.get("platform_id"), context.get("execution_mode"), root=root
    )
    if context != expected:
        raise SessionConflictError(
            "The platform session configuration changed or is invalid. Open a new chat after operator review."
        )
    return expected


def resolve_platform_context(
    request_data: dict,
    *,
    saved_context: object = UNBOUND,
    root: Path | None = None,
) -> dict | None:
    """Resolve explicit selection or resume an existing conversation binding.

    UNBOUND is a fresh chat; None is an explicitly bound generic Web chat.
    Persisted auto mode represents an earlier explicit operator selection.
    """
    if not isinstance(request_data, dict):
        raise SessionContextError("The session request must be a JSON object.")
    existing = saved_context
    if existing is not UNBOUND and existing is not None:
        try:
            existing = _validate_context(existing, root=root)
        except SessionContextError as error:
            raise SessionConflictError(str(error)) from error
    selected = request_data.get(
        "platform_id", existing["platform_id"] if isinstance(existing, dict) else None
    )
    if selected == "":
        selected = None
    if selected is not None and not isinstance(selected, str):
        raise SessionContextError("platform_id must be a registered identifier or null.")
    if existing is not UNBOUND:
        previous_id = existing["platform_id"] if isinstance(existing, dict) else None
        if selected != previous_id:
            raise SessionConflictError("This chat is bound to its platform. Open a new chat to change platforms.")
    default_mode = existing["execution_mode"] if isinstance(existing, dict) else "supervised"
    mode = _execution_mode(request_data.get("execution_mode", default_mode))
    if isinstance(existing, dict) and mode != existing["execution_mode"]:
        raise SessionConflictError("This chat's execution mode is fixed. Open a new chat to change it.")
    if selected is None:
        if mode != "supervised":
            raise SessionContextError("Auto execution mode requires a selected platform.")
        return None
    return build_platform_context(selected, mode, root=root)


def _registered_vision_model(provider: str, model: str) -> bool:
    """Use the existing model tables without accepting their unknown-model fallback."""
    if not isinstance(provider, str) or provider not in _PROVIDERS or not isinstance(model, str):
        return False
    try:
        view = importlib.import_module(f"AutoCua.llm_provider.{provider}.view")
        metadata = view.MODEL_MAPPINGS.get(model)
    except (ImportError, AttributeError):
        return False
    return isinstance(metadata, dict) and metadata.get("vision") is True


def validate_session_settings(
    context: dict | None,
    provider: str,
    model: str,
    speed: str | None,
    headless: bool,
    browser_profile: str | None,
) -> None:
    """Fail closed for unsupported scoped settings; generic runs keep their behavior."""
    if context is None:
        return
    if headless is not False or speed not in (None, "quality"):
        raise SessionContextError("Platform sessions require visible Chrome and Quality mode.")
    if browser_profile != context["browser_profile"]:
        raise SessionContextError("Platform sessions require their dedicated Chrome profile.")
    if not _registered_vision_model(provider, model):
        raise SessionContextError("Choose a registered image-capable model for the platform session.")


def validate_native_context(
    context: object,
    provider: str,
    model: str,
    speed: str | None,
    headless: bool,
    browser_profile: str | None,
) -> dict | None:
    """Revalidate native entry arguments before Chrome, model or tool startup."""
    if context is None:
        return None
    validated = _validate_context(context)
    validate_session_settings(validated, provider, model, speed, headless, browser_profile)
    return validated
