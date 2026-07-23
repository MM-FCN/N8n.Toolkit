import json
import logging
import time
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi import Request
from pydantic import BaseModel
from email_parse import parse_eml_b64
from crawl_request import CustomerInputRequest as CrawlCustomerInputRequest
from crawl_request import crawlRequest

app = FastAPI()

def _load_app_config() -> dict[str, Any]:
    config_path = Path(__file__).with_name("appsettings.json")
    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)

    if isinstance(loaded, dict):
        return loaded

    return {}


APP_CONFIG = _load_app_config()
CUSTOMER_INPUT_DATA_ROOT = APP_CONFIG.get("DataRootPath")
LOG_ROOT_PATH = APP_CONFIG.get("LogRootPath", "logs")
LOG_RETENTION_DAYS = APP_CONFIG.get("LogRetentionDays", 10)


def _resolve_path(path_value: Any, fallback_dir_name: str) -> Path:
    base_dir = Path(__file__).resolve().parent
    if isinstance(path_value, str) and path_value.strip():
        configured_path = Path(path_value.strip())
        if configured_path.is_absolute():
            return configured_path
        return base_dir / configured_path

    return base_dir / fallback_dir_name


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
    logger.info("Configured DataRootPath: %s", CUSTOMER_INPUT_DATA_ROOT or "<default:data>")
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


class CustomerInputApiRequest(BaseModel):
    customer_name: str
    container_no: list[str]
    resume_url: str


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


@app.post("/api/customer-input")
async def create_customer_input(request: CustomerInputApiRequest):
    logger.info(
        "/api/customer-input called | customer_name=%s | container_count=%s",
        request.customer_name,
        len(request.container_no),
    )
    try:
        crawl_request = CrawlCustomerInputRequest(
            customer_name=request.customer_name,
            container_no=request.container_no,
            resume_url=request.resume_url,
        )
        crawl_configuration = None
        if isinstance(CUSTOMER_INPUT_DATA_ROOT, str) and CUSTOMER_INPUT_DATA_ROOT.strip():
            crawl_configuration = {"DataRootPath": CUSTOMER_INPUT_DATA_ROOT.strip()}

        result = await crawlRequest(
            request=crawl_request,
            configuration=crawl_configuration,
            content_root_path=".",
            logger=logger,
        )
        logger.info(
            "/api/customer-input completed successfully | file_path=%s",
            result.get("file_path"),
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception("/api/customer-input failed")
        return {"status": "error", "message": str(e)}
