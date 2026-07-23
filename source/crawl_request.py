import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class CustomerInputRequest:
    customer_name: str
    container_no: list[str]
    resume_url: str


def _resolve_data_root_path(
    configuration: Optional[Mapping[str, Any]],
    content_root_path: Optional[str],
) -> str:
    configured_data_root = None
    if configuration is not None:
        configured_data_root = configuration.get("DataRootPath")

    configured_data_root_str = (
        str(configured_data_root).strip() if configured_data_root is not None else ""
    )
    base_root = content_root_path or os.getcwd()

    if not configured_data_root_str:
        return str(Path(base_root) / "data")

    if os.path.isabs(configured_data_root_str):
        return configured_data_root_str

    return str(Path(base_root) / configured_data_root_str)


def _build_payload(request: CustomerInputRequest) -> dict[str, Any]:
    customer_name_lower = request.customer_name.lower()

    if "cargonavi" in customer_name_lower:
        return {
            "MAWB": request.container_no,
            "Uri": request.resume_url,
        }

    if "enx" in customer_name_lower:
        return {
            "HAWNO": request.container_no,
            "Uri": request.resume_url,
        }

    return {
        "ContainerNo": request.container_no,
        "Uri": request.resume_url,
    }


async def crawlRequest(
    request: CustomerInputRequest,
    configuration: Optional[Mapping[str, Any]] = None,
    content_root_path: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    cancellation_token: Optional[asyncio.Event] = None,
) -> dict[str, Any]:
    if cancellation_token is not None and cancellation_token.is_set():
        raise asyncio.CancelledError("Operation cancelled before file generation.")

    data_root_path = _resolve_data_root_path(configuration, content_root_path)
    customer_folder_path = Path(data_root_path) / request.customer_name
    customer_folder_path.mkdir(parents=True, exist_ok=True)

    sequence_number = random.randint(0, 999)
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S%f")[:-3]
    file_name = (
        f"{request.customer_name}_input_{timestamp}_{sequence_number:03d}.json"
    )
    file_path = customer_folder_path / file_name

    active_logger = logger or logging.getLogger(__name__)
    active_logger.info(
        "[%s] Generating customer input file, file name: %s",
        now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        file_name,
    )

    payload = _build_payload(request)
    content = json.dumps(payload, indent=2, ensure_ascii=False)

    if cancellation_token is not None and cancellation_token.is_set():
        raise asyncio.CancelledError("Operation cancelled before file write.")

    await asyncio.to_thread(file_path.write_text, content, "utf-8")

    return {
        "status": "ok",
        "file_path": str(file_path),
        "file_name": file_name,
    }


async def crawl_request(
    request: CustomerInputRequest,
    configuration: Optional[Mapping[str, Any]] = None,
    content_root_path: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    cancellation_token: Optional[asyncio.Event] = None,
) -> dict[str, Any]:
    return await crawlRequest(
        request=request,
        configuration=configuration,
        content_root_path=content_root_path,
        logger=logger,
        cancellation_token=cancellation_token,
    )
