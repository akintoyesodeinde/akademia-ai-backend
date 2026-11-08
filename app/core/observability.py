import time
import uuid
from collections import defaultdict

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger, request_id_ctx_var

logger = get_logger("observability")


class MetricsRegistry:
    """In-process operational telemetry collector for requests, jobs, and AI latency."""

    def __init__(self) -> None:
        self.request_counts: dict[str, int] = defaultdict(int)
        self.error_counts: dict[str, int] = defaultdict(int)
        self.ai_request_counts: dict[str, int] = defaultdict(int)
        self.total_requests: int = 0

    def record_http_request(self, method: str, path: str, status_code: int) -> None:
        self.total_requests += 1
        key = f"{method} {path} [{status_code}]"
        self.request_counts[key] += 1
        if status_code >= 500:
            self.error_counts[key] += 1

    def snapshot(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "routes": dict(self.request_counts),
            "server_errors": dict(self.error_counts),
            "ai_requests": dict(self.ai_request_counts),
        }


metrics_registry = MetricsRegistry()


class RequestTracingMiddleware:
    """Pure ASGI middleware that guarantees request dependency teardown and DB commit
    complete before the HTTP response finishes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        raw_req_id = headers.get(b"x-request-id")
        req_id = raw_req_id.decode("latin1") if raw_req_id else str(uuid.uuid4())
        token = request_id_ctx_var.set(req_id)
        scope.setdefault("state", {})["request_id"] = req_id

        start_time = time.perf_counter()
        status_code = 500
        buffered_messages: list[Message] = []

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                mut_headers = MutableHeaders(scope=message)
                mut_headers["X-Request-ID"] = req_id
                mut_headers["X-Content-Type-Options"] = "nosniff"
                mut_headers["X-Frame-Options"] = "DENY"
                mut_headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            buffered_messages.append(message)

        try:
            await self.app(scope, receive, send_wrapper)
            for msg in buffered_messages:
                await send(msg)
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            method = scope.get("method", "GET")
            path = scope.get("path", "/")
            metrics_registry.record_http_request(method, path, status_code)
            logger.info(
                "http_request_completed",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            request_id_ctx_var.reset(token)
