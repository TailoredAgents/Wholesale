import os
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass
from itertools import count
from time import perf_counter
from typing import Any, Literal

import sentry_sdk
import structlog
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine, ExceptionContext
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings

logger = structlog.get_logger()

SLOW_REQUEST_THRESHOLD_MS = 1_000
HIGH_QUERY_COUNT_THRESHOLD = 50
HIGH_SQL_TIME_THRESHOLD_MS = 500
LARGE_PAYLOAD_THRESHOLD_BYTES = 1_000_000
MAX_REPORTED_CONTENT_LENGTH_BYTES = 1_000_000_000
HEALTHY_REQUEST_SAMPLE_EVERY = 20


@dataclass
class RequestDatabaseMetrics:
    active: bool = True
    query_count: int = 0
    query_time_ms: float = 0.0
    max_query_time_ms: float = 0.0
    engine: Engine | None = None


@dataclass(frozen=True)
class DatabasePoolSnapshot:
    pool_class: str
    size: int | None
    checked_in: int | None
    checked_out: int | None
    overflow: int | None


PgStatStatementsStatus = Literal[
    "available",
    "unavailable",
    "not_applicable",
    "check_failed",
]


@dataclass(frozen=True)
class DatabaseObservabilitySnapshot:
    dialect: str
    pg_stat_statements: PgStatStatementsStatus
    pool: DatabasePoolSnapshot


_request_database_metrics: ContextVar[RequestDatabaseMetrics | None] = ContextVar(
    "request_database_metrics",
    default=None,
)
_sqlalchemy_observers_installed = False
_query_started_at_attribute = "_stonegate_observability_query_started_at"
_healthy_request_counter = count(1)


def initialize_error_monitoring(settings: Settings, *, service_name: str) -> bool:
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment or settings.app_env,
        release=os.getenv("RENDER_GIT_COMMIT"),
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
    )
    sentry_sdk.set_tag("stonegate.service", service_name)
    return True


def install_sqlalchemy_observers() -> None:
    """Install process-wide SQL timing hooks once.

    Request state lives in a ContextVar. FastAPI copies that context into its
    sync-endpoint worker threads; the mutable metrics object lets SQLAlchemy's
    synchronous callbacks report measurements back to the surrounding ASGI
    request without changing database behavior.
    """

    global _sqlalchemy_observers_installed
    if _sqlalchemy_observers_installed:
        return
    event.listen(Engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(Engine, "after_cursor_execute", _after_cursor_execute)
    event.listen(Engine, "handle_error", _handle_cursor_error)
    _sqlalchemy_observers_installed = True


def _before_cursor_execute(
    connection: Connection,
    _cursor: Any,
    _statement: str,
    _parameters: Any,
    context: Any,
    _executemany: bool,
) -> None:
    metrics = _request_database_metrics.get()
    if metrics is None or not metrics.active:
        return
    metrics.query_count += 1
    metrics.engine = connection.engine
    setattr(context, _query_started_at_attribute, perf_counter())


def _after_cursor_execute(
    _connection: Connection,
    _cursor: Any,
    _statement: str,
    _parameters: Any,
    context: Any,
    _executemany: bool,
) -> None:
    _finish_query_timing(context)


def _handle_cursor_error(exception_context: ExceptionContext) -> None:
    execution_context = exception_context.execution_context
    if execution_context is not None:
        _finish_query_timing(execution_context)


def _finish_query_timing(context: Any) -> None:
    started_at = getattr(context, _query_started_at_attribute, None)
    if not isinstance(started_at, (float, int)):
        return
    setattr(context, _query_started_at_attribute, None)
    metrics = _request_database_metrics.get()
    if metrics is None or not metrics.active:
        return
    duration_ms = max(0.0, (perf_counter() - float(started_at)) * 1_000)
    metrics.query_time_ms += duration_ms
    metrics.max_query_time_ms = max(metrics.max_query_time_ms, duration_ms)


class RequestObservabilityMiddleware:
    """Emit one bounded, low-cardinality performance event per API request."""

    def __init__(self, app: ASGIApp, *, database_engine: Engine) -> None:
        self.app = app
        self.database_engine = database_engine

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        database_metrics = RequestDatabaseMetrics()
        token = _request_database_metrics.set(database_metrics)
        status_code = 500
        request_body_bytes = 0
        response_body_bytes = 0
        response_completed_at: float | None = None
        error_type: str | None = None

        async def observed_receive() -> Message:
            nonlocal request_body_bytes
            message = await receive()
            if message["type"] == "http.request":
                request_body_bytes += len(message.get("body", b""))
            return message

        async def observed_send(message: Message) -> None:
            nonlocal response_body_bytes, response_completed_at, status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            elif message["type"] == "http.response.body":
                response_body_bytes += len(message.get("body", b""))
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                # Stop attributing SQL as soon as the client-visible response
                # has finished. Detached tasks inherit ContextVars, and yield
                # dependency cleanup may continue after this point.
                response_completed_at = perf_counter()
                database_metrics.active = False

        try:
            await self.app(scope, observed_receive, observed_send)
        except BaseException as exc:
            error_type = type(exc).__name__
            raise
        finally:
            database_metrics.active = False
            try:
                finished_at = response_completed_at or perf_counter()
                duration_ms = max(0.0, (finished_at - started_at) * 1_000)
                route_template = _route_template(scope)
                declared_request_bytes = _content_length(scope)
                performance_flags = _performance_flags(
                    duration_ms=duration_ms,
                    query_count=database_metrics.query_count,
                    query_time_ms=database_metrics.query_time_ms,
                    request_bytes=max(request_body_bytes, declared_request_bytes),
                    response_bytes=response_body_bytes,
                )
                if _should_log_request(
                    route_template=route_template,
                    status_code=status_code,
                    performance_flags=performance_flags,
                    error_type=error_type,
                ):
                    pool = database_pool_snapshot(database_metrics.engine or self.database_engine)
                    logger.info(
                        "api_request_completed",
                        method=str(scope.get("method") or "UNKNOWN"),
                        route=route_template,
                        status_code=status_code,
                        duration_ms=round(duration_ms, 3),
                        request_content_length_bytes=declared_request_bytes,
                        request_body_bytes_read=request_body_bytes,
                        response_body_bytes=response_body_bytes,
                        db_query_count=database_metrics.query_count,
                        db_query_time_ms=round(database_metrics.query_time_ms, 3),
                        db_max_query_time_ms=round(database_metrics.max_query_time_ms, 3),
                        db_pool_class=pool.pool_class,
                        db_pool_size=pool.size,
                        db_pool_checked_in=pool.checked_in,
                        db_pool_checked_out=pool.checked_out,
                        db_pool_overflow=pool.overflow,
                        performance_flags=performance_flags,
                        error_type=error_type,
                    )
            except Exception:
                # Telemetry must never change an API response or mask the
                # application exception that caused the request to finish.
                pass
            finally:
                _request_database_metrics.reset(token)


def database_pool_snapshot(engine: Engine) -> DatabasePoolSnapshot:
    pool = engine.pool
    return DatabasePoolSnapshot(
        pool_class=type(pool).__name__,
        size=_pool_metric(pool, "size"),
        checked_in=_pool_metric(pool, "checkedin"),
        checked_out=_pool_metric(pool, "checkedout"),
        overflow=_pool_metric(pool, "overflow"),
    )


def database_observability_snapshot(db: Session) -> DatabaseObservabilitySnapshot:
    """Return safe database instrumentation availability and pool counters.

    The pg_stat_statements check reads only the extension catalog. It never
    reads captured statement text, query parameters, or connection details.
    """

    bind = db.get_bind()
    engine = bind if isinstance(bind, Engine) else bind.engine
    dialect = bind.dialect.name
    # Capture pool state before the probe checks out its own connection.
    pool = database_pool_snapshot(engine)
    pg_stat_statements: PgStatStatementsStatus = "not_applicable"
    if dialect == "postgresql":
        try:
            installed = db.scalar(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM pg_catalog.pg_extension "
                    "WHERE extname = 'pg_stat_statements'"
                    ")"
                )
            )
            if installed is True:
                # Extension presence alone is insufficient when PostgreSQL has
                # not preloaded the module. A zero-row view query proves the
                # statement statistics view is usable by this connection.
                db.execute(text("SELECT 1 FROM pg_stat_statements LIMIT 0"))
                pg_stat_statements = "available"
            else:
                pg_stat_statements = "unavailable"
        except Exception:
            pg_stat_statements = "check_failed"

    # Keep the diagnostic usable when the log exporter is the component being
    # investigated.
    with suppress(Exception):
        logger.info(
            "database_observability_checked",
            database_dialect=dialect,
            pg_stat_statements=pg_stat_statements,
            db_pool_class=pool.pool_class,
            db_pool_size=pool.size,
            db_pool_checked_in=pool.checked_in,
            db_pool_checked_out=pool.checked_out,
            db_pool_overflow=pool.overflow,
        )
    return DatabaseObservabilitySnapshot(
        dialect=dialect,
        pg_stat_statements=pg_stat_statements,
        pool=pool,
    )


def _pool_metric(pool: object, method_name: str) -> int | None:
    method = getattr(pool, method_name, None)
    if not callable(method):
        return None
    try:
        value = method()
    except Exception:
        return None
    return value if isinstance(value, int) else None


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return "__unmatched__"


def _content_length(scope: Scope) -> int:
    for name, value in scope.get("headers", []):
        if name.lower() != b"content-length":
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        if parsed < 0:
            return 0
        return min(parsed, MAX_REPORTED_CONTENT_LENGTH_BYTES)
    return 0


def _performance_flags(
    *,
    duration_ms: float,
    query_count: int,
    query_time_ms: float,
    request_bytes: int,
    response_bytes: int,
) -> tuple[str, ...]:
    flags: list[str] = []
    if duration_ms >= SLOW_REQUEST_THRESHOLD_MS:
        flags.append("slow_request")
    if query_count >= HIGH_QUERY_COUNT_THRESHOLD:
        flags.append("high_query_count")
    if query_time_ms >= HIGH_SQL_TIME_THRESHOLD_MS:
        flags.append("high_sql_time")
    if request_bytes >= LARGE_PAYLOAD_THRESHOLD_BYTES:
        flags.append("large_request")
    if response_bytes >= LARGE_PAYLOAD_THRESHOLD_BYTES:
        flags.append("large_response")
    return tuple(flags)


def _should_log_request(
    *,
    route_template: str,
    status_code: int,
    performance_flags: tuple[str, ...],
    error_type: str | None = None,
) -> bool:
    # Failures and measurable performance problems are never sampled.
    if status_code >= 400 or performance_flags or error_type is not None:
        return True
    # Render polls this route frequently. Keep healthy, fast liveness probes out
    # of application logs entirely.
    if route_template == "/health":
        return False
    # Ordinary successful traffic is sampled so high-frequency polling does
    # not turn observability itself into material CPU and log-volume overhead.
    sample_every = max(1, HEALTHY_REQUEST_SAMPLE_EVERY)
    return next(_healthy_request_counter) % sample_every == 0
