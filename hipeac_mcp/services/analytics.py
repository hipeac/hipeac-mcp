"""Analytics service for logging MCP tool usage via Redis.

Tool usage events are pushed to a Redis list as JSON messages.
The main `hipeac` Huey worker consumes this list and persists events to the database.
This keeps the MCP server fully read-only while enabling usage tracking.
"""

import functools
import inspect
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import cast

import redis
from mcp.server.fastmcp import Context

from hipeac_mcp.redis import get_redis_client


logger = logging.getLogger(__name__)

REDIS_KEY = "hipeac:mcp:tool_usage"


def _serialize_param(value: object) -> object:
    """Serialize a parameter value for JSON storage.

    :param value: The parameter value.
    :returns: JSON-serializable representation.
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_serialize_param(item) for item in cast(list[object], value)]
    return value


def _is_context_param(param: inspect.Parameter) -> bool:
    """Check if a parameter is a FastMCP Context injection.

    :param param: The parameter to check.
    :returns: True if the parameter is annotated with Context.
    """
    annotation = param.annotation
    return annotation is Context or (isinstance(annotation, type) and issubclass(annotation, Context))


def _build_params(
    func: Callable[..., object], args: tuple[object, ...], kwargs: dict[str, object]
) -> dict[str, object]:
    """Extract and serialize all non-default parameters from a function call.

    Context-typed parameters are excluded since they are injected by FastMCP.

    :param func: The decorated function.
    :param args: Positional arguments.
    :param kwargs: Keyword arguments.
    :returns: Dictionary of serialized parameter values, excluding defaults.
    """
    sig = inspect.signature(func)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()

    return {
        name: _serialize_param(value)
        for name, value in bound.arguments.items()
        if not _is_context_param(sig.parameters[name]) and value != sig.parameters[name].default
    }


def _extract_client_info(
    func: Callable[..., object], args: tuple[object, ...], kwargs: dict[str, object]
) -> dict[str, str | None]:
    """Extract MCP client info from a Context parameter if present.

    :param func: The decorated function.
    :param args: Positional arguments.
    :param kwargs: Keyword arguments.
    :returns: Dictionary with ``client`` (e.g. "claude-desktop/1.2.0") and ``client_id``.
    """
    result: dict[str, str | None] = {"client": None, "client_id": None}
    sig = inspect.signature(func)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()

    for name, param in sig.parameters.items():
        if _is_context_param(param):
            ctx = bound.arguments.get(name)
            if ctx and hasattr(ctx, "request_context"):
                result["client_id"] = getattr(ctx, "client_id", None)
                session = getattr(ctx.request_context, "session", None)
                if session:
                    client_params = getattr(session, "client_params", None)
                    if client_params:
                        info = getattr(client_params, "clientInfo", None)
                        if info:
                            result["client"] = f"{info.name}/{info.version}" if info.version else info.name
            break
    return result


def _push_event(
    tool_name: str,
    params: dict[str, object],
    client: str | None = None,
    client_id: str | None = None,
) -> None:
    """Push a tool usage event to Redis.

    Fire-and-forget: if Redis is unavailable, the event is silently dropped.

    :param tool_name: Name of the MCP tool that was called.
    :param params: Serialized parameters passed to the tool.
    :param client: Optional MCP client identifier (e.g. "claude-desktop/1.2.0").
    :param client_id: Optional unique client instance identifier.
    """
    redis_client = get_redis_client()

    if redis_client is None:
        return

    event: dict[str, object] = {
        "tool": tool_name,
        "params": params,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    if client:
        event["client"] = client
    if client_id:
        event["client_id"] = client_id

    try:
        redis_client.rpush(REDIS_KEY, json.dumps(event))
    except redis.RedisError:
        logger.debug("Failed to log tool usage to Redis", exc_info=True)


def track_usage[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Decorator that logs MCP tool usage to Redis with all parameters.

    Automatically captures the function name, all non-default arguments,
    and the MCP client identifier if a Context parameter is present.

    :param func: The MCP tool function to wrap.
    :returns: Wrapped function with usage logging.
    """

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        params = _build_params(func, args, kwargs)
        client_info = _extract_client_info(func, args, kwargs)
        _push_event(func.__name__, params, client=client_info["client"], client_id=client_info["client_id"])
        return await func(*args, **kwargs)  # type: ignore[misc]

    return wrapper  # type: ignore[return-value]
