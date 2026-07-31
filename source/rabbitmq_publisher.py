import json
from dataclasses import dataclass
from typing import Any, Callable

import pika


class RabbitMqConfigurationError(ValueError):
    """Raised when RabbitMQ settings are missing or invalid."""


class RabbitMqPublishError(RuntimeError):
    """Raised when RabbitMQ cannot confirm a published message."""


class RabbitMqRouteNotFoundError(ValueError):
    """Raised when a message category has no configured routing key."""


@dataclass(frozen=True)
class RabbitMqSettings:
    url: str
    exchange_name: str
    exchange_type: str
    category_route_keys: dict[str, str]


def _required_config_value(get_value: Callable[[str, str, Any], Any], key: str) -> str:
    value = get_value(key, key)
    if not isinstance(value, str) or not value.strip():
        raise RabbitMqConfigurationError(f"Missing RabbitMQ configuration: {key}")
    return value.strip()


def _parse_category_map(value: Any) -> list[Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RabbitMqConfigurationError(
                "RabbitMqRouteKeyCategoryMap must be a JSON array"
            ) from exc

    if not isinstance(value, list) or not value:
        raise RabbitMqConfigurationError("RabbitMqRouteKeyCategoryMap must be a non-empty array")
    return value


def _normalized_route_key(route_key: Any) -> str:
    if not isinstance(route_key, str) or not route_key.strip():
        raise RabbitMqConfigurationError("RabbitMqRouteKeyCategoryMap contains an invalid route key")
    return route_key.strip()


def _normalized_categories(categories: Any) -> list[str]:
    if not isinstance(categories, list) or not categories:
        raise RabbitMqConfigurationError(
            "RabbitMqRouteKeyCategoryMap category lists must be non-empty"
        )

    normalized: list[str] = []
    for category in categories:
        if isinstance(category, bool) or not isinstance(category, (str, int)):
            raise RabbitMqConfigurationError(
                "RabbitMqRouteKeyCategoryMap categories must be strings or integers"
            )
        normalized_category = str(category).strip()
        if not normalized_category:
            raise RabbitMqConfigurationError(
                "RabbitMqRouteKeyCategoryMap categories must be non-empty and unique"
            )
        normalized.append(normalized_category)
    return normalized


def _mapping_values(mapping: Any) -> tuple[Any, Any]:
    if not isinstance(mapping, dict):
        raise RabbitMqConfigurationError(
            "RabbitMqRouteKeyCategoryMap entries must be objects"
        )
    return mapping.get("RouteKey"), mapping.get("CategoryIds")


def _load_category_route_keys(get_value: Callable[[str, str, Any], Any]) -> dict[str, str]:
    value = get_value("RabbitMqRouteKeyCategoryMap", "RabbitMqRouteKeyCategoryMap")
    configured_mappings = _parse_category_map(value)

    category_route_keys: dict[str, str] = {}
    for mapping in configured_mappings:
        route_key, categories = _mapping_values(mapping)
        normalized_route_key = _normalized_route_key(route_key)
        for normalized_category in _normalized_categories(categories):
            if normalized_category in category_route_keys:
                raise RabbitMqConfigurationError(
                    "RabbitMqRouteKeyCategoryMap categories must be non-empty and unique"
                )
            category_route_keys[normalized_category] = normalized_route_key

    return category_route_keys


def load_rabbitmq_settings(get_value: Callable[[str, str, Any], Any]) -> RabbitMqSettings:
    exchange_type = _required_config_value(get_value, "RabbitMqExchangeType").lower()
    if exchange_type not in {"direct", "topic"}:
        raise RabbitMqConfigurationError("RabbitMqExchangeType must be 'direct' or 'topic'")

    return RabbitMqSettings(
        url=_required_config_value(get_value, "RabbitMqUrl"),
        exchange_name=_required_config_value(get_value, "RabbitMqExchangeName"),
        exchange_type=exchange_type,
        category_route_keys=_load_category_route_keys(get_value),
    )


def resolve_route_key(settings: RabbitMqSettings, category: str) -> str:
    try:
        return settings.category_route_keys[category.strip()]
    except KeyError as exc:
        raise RabbitMqRouteNotFoundError("No RabbitMQ route configured for category") from exc


def publish_message(
    settings: RabbitMqSettings, body: bytes, category: str, route_key: str
) -> None:
    """Declare the configured exchange and publish one confirmed persistent message."""
    connection = None
    try:
        parameters = pika.URLParameters(settings.url)
        parameters.connection_attempts = 1
        parameters.socket_timeout = 10
        parameters.blocked_connection_timeout = 10

        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.confirm_delivery()
        channel.exchange_declare(
            exchange=settings.exchange_name,
            exchange_type=settings.exchange_type,
            durable=True,
        )
        confirmed = channel.basic_publish(
            exchange=settings.exchange_name,
            routing_key=route_key,
            body=body,
            properties=pika.BasicProperties(
                content_type="application/json",
                content_encoding="utf-8",
                delivery_mode=2,
                type=category,
            ),
            mandatory=True,
        )
        if confirmed is False:
            raise RabbitMqPublishError("RabbitMQ did not confirm the published message")
    except RabbitMqPublishError:
        raise
    except Exception as exc:
        raise RabbitMqPublishError("RabbitMQ message publishing failed") from exc
    finally:
        if connection is not None and connection.is_open:
            connection.close()