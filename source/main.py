import json
import logging
import os
import time
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel, StrictInt, StrictStr
from starlette.concurrency import run_in_threadpool
from source.email_parse import parse_eml_b64
from source.rabbitmq_publisher import (
    RabbitMqConfigurationError,
    RabbitMqPublishError,
    RabbitMqRouteNotFoundError,
    load_rabbitmq_settings,
    publish_message,
    resolve_route_key,
)

app = FastAPI()


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_app_config() -> dict[str, Any]:
    config_path = PROJECT_ROOT / "appsettings.json"
    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)

    if isinstance(loaded, dict):
        return loaded

    return {}


APP_CONFIG = _load_app_config()


def _get_config_value(env_name: str, config_key: str, default: Any = None) -> Any:
    env_value = os.getenv(env_name)
    if env_value is not None and env_value.strip():
        return env_value.strip()
    return APP_CONFIG.get(config_key, default)


LOG_ROOT_PATH = _get_config_value("LogRootPath", "LogRootPath", "logs")
LOG_RETENTION_DAYS = _get_config_value("LogRetentionDays", "LogRetentionDays", 10)


def _resolve_path(path_value: Any, fallback_dir_name: str) -> Path:
    if isinstance(path_value, str) and path_value.strip():
        configured_path = Path(path_value.strip())
        if configured_path.is_absolute():
            return configured_path
        return PROJECT_ROOT / configured_path

    return PROJECT_ROOT / fallback_dir_name


def _normalize_retention_days(value: Any, fallback: int = 10) -> int:
    try:
        retention_days = int(value)
        return retention_days if retention_days > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _cleanup_old_log_files(log_file_path: Path, retention_days: int) -> None:
    cutoff = datetime.now() - timedelta(days=retention_days)
    for candidate in log_file_path.parent.glob(f"{log_file_path.name}.*"):
        if not candidate.is_file():
            continue

        modified_at = datetime.fromtimestamp(candidate.stat().st_mtime)
        if modified_at < cutoff:
            candidate.unlink(missing_ok=True)


def _configure_logging() -> tuple[logging.Logger, Path, int]:
    log_root_dir = _resolve_path(LOG_ROOT_PATH, "logs")
    retention_days = _normalize_retention_days(LOG_RETENTION_DAYS, fallback=10)
    log_root_dir.mkdir(parents=True, exist_ok=True)

    log_file_path = log_root_dir / "service.log"
    log_format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    formatter = logging.Formatter(log_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        filename=str(log_file_path),
        when="midnight",
        interval=1,
        backupCount=retention_days,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    _cleanup_old_log_files(log_file_path, retention_days)

    return logging.getLogger("email_parser_api"), log_root_dir, retention_days


logger, ACTIVE_LOG_ROOT_DIR, ACTIVE_LOG_RETENTION_DAYS = _configure_logging()
logger = logging.getLogger("n8n_toolkit_api")


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Service startup complete")
    logger.info("Configured LogRootPath: %s", ACTIVE_LOG_ROOT_DIR)
    logger.info("Configured LogRetentionDays: %s", ACTIVE_LOG_RETENTION_DAYS)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Service shutdown complete")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    logger.info("Request started: %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Request completed: %s %s | status=%s | duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "Request failed: %s %s | duration_ms=%.2f",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise


class EmlRequest(BaseModel):
    eml_payload: str


class SendMqRequest(BaseModel):
    category: StrictInt | StrictStr
    content: StrictStr


@app.post("/api/parse-eml")
async def parse_eml(request: EmlRequest):
    logger.info("/api/parse-eml called")
    try:
        result = parse_eml_b64(request.eml_payload)
        logger.info("/api/parse-eml completed successfully")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception("/api/parse-eml failed")
        return {"status": "error", "message": str(e)}


@app.post("/api/send-mq")
async def send_mq(request: SendMqRequest):
    if isinstance(request.category, str) and not request.category.strip():
        raise HTTPException(status_code=422, detail="category must not be empty")
    category = request.category
    normalized_category = str(category).strip()

    try:
        content = json.loads(request.content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="content must be a valid JSON string") from None

    try:
        settings = load_rabbitmq_settings(_get_config_value)
    except RabbitMqConfigurationError:
        logger.error("/api/send-mq rejected due to invalid RabbitMQ configuration")
        raise HTTPException(status_code=500, detail="RabbitMQ service configuration is invalid") from None

    try:
        route_key = resolve_route_key(settings, normalized_category)
    except RabbitMqRouteNotFoundError:
        raise HTTPException(status_code=422, detail="category has no configured RabbitMQ route") from None

    body = json.dumps(
        {"category": category, "content": content},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    try:
        await run_in_threadpool(
            publish_message, settings, body, normalized_category, route_key
        )
    except RabbitMqPublishError:
        logger.error("/api/send-mq failed to publish category=%s", category)
        raise HTTPException(status_code=503, detail="RabbitMQ service is unavailable") from None

    logger.info("/api/send-mq published category=%s", category)
    return {"status": "success", "message": "Message published"}
