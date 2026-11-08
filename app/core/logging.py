import logging
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")
tenant_id_log_ctx_var: ContextVar[str] = ContextVar("tenant_id_log", default="-")


def add_context_fields(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    event_dict["request_id"] = request_id_ctx_var.get()
    event_dict["tenant_id"] = tenant_id_log_ctx_var.get()
    # Redact sensitive fields if ever passed accidentally
    for sensitive_key in (
        "password",
        "raw_password",
        "token",
        "refresh_token",
        "access_token",
        "api_key",
        "secret",
        "prompt_raw",
    ):
        if sensitive_key in event_dict:
            event_dict[sensitive_key] = "[REDACTED]"
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            add_context_fields,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "akademia_ai") -> Any:
    return structlog.get_logger(name)
