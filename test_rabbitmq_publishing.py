import asyncio
import json
import os
import unittest
from unittest.mock import MagicMock, patch

import pika
from fastapi import HTTPException

from source import main
from source.rabbitmq_publisher import (
    RabbitMqConfigurationError,
    RabbitMqPublishError,
    RabbitMqRouteNotFoundError,
    RabbitMqSettings,
    load_rabbitmq_settings,
    publish_message,
    resolve_route_key,
)


class RabbitMqSettingsTests(unittest.TestCase):
    def test_environment_value_overrides_file_value(self):
        values = {
            "RabbitMqUrl": "amqp://file-host",
            "RabbitMqExchangeName": "file-exchange",
            "RabbitMqExchangeType": "direct",
            "RabbitMqRouteKeyCategoryMap": [
                {"RouteKey": "file.route", "CategoryIds": [1]}
            ],
        }

        def get_value(env_name, config_key, default=None):
            return "amqp://environment-host" if env_name == "RabbitMqUrl" else values.get(config_key, default)

        settings = load_rabbitmq_settings(get_value)

        self.assertEqual("amqp://environment-host", settings.url)

    def test_invalid_exchange_type_is_rejected(self):
        values = {
            "RabbitMqUrl": "amqp://localhost",
            "RabbitMqExchangeName": "events",
            "RabbitMqExchangeType": "fanout",
            "RabbitMqRouteKeyCategoryMap": [
                {"RouteKey": "event.created", "CategoryIds": [1]}
            ],
        }

        with self.assertRaises(RabbitMqConfigurationError):
            load_rabbitmq_settings(lambda _env, key, default=None: values.get(key, default))

    def test_category_map_environment_json_is_parsed(self):
        values = {
            "RabbitMqUrl": "amqp://localhost",
            "RabbitMqExchangeName": "events",
            "RabbitMqExchangeType": "topic",
            "RabbitMqRouteKeyCategoryMap": [
                {"RouteKey": "file.route", "CategoryIds": [1]}
            ],
        }

        def get_value(env_name, config_key, default=None):
            if env_name == "RabbitMqRouteKeyCategoryMap":
                return '[{"RouteKey":"environment.route","CategoryIds":[9,10]}]'
            return values.get(config_key, default)

        settings = load_rabbitmq_settings(get_value)

        self.assertEqual("environment.route", resolve_route_key(settings, "9"))

    def test_duplicate_category_mapping_is_rejected(self):
        values = {
            "RabbitMqUrl": "amqp://localhost",
            "RabbitMqExchangeName": "events",
            "RabbitMqExchangeType": "topic",
            "RabbitMqRouteKeyCategoryMap": [
                {"RouteKey": "first.route", "CategoryIds": [1]},
                {"RouteKey": "second.route", "CategoryIds": [1]},
            ],
        }

        with self.assertRaises(RabbitMqConfigurationError):
            load_rabbitmq_settings(lambda _env, key, default=None: values.get(key, default))

    def test_unmapped_category_is_rejected(self):
        settings = RabbitMqSettings("amqp://localhost", "events", "topic", {"1": "route"})

        with self.assertRaises(RabbitMqRouteNotFoundError):
            resolve_route_key(settings, "2")


class RabbitMqPublisherTests(unittest.TestCase):
    def setUp(self):
        self.settings = RabbitMqSettings(
            url="amqp://guest:guest@localhost:5672/%2F",
            exchange_name="events",
            exchange_type="topic",
            category_route_keys={"9": "orders.created"},
        )

    @patch("source.rabbitmq_publisher.pika.BlockingConnection")
    def test_declares_exchange_and_publishes_confirmed_message(self, blocking_connection):
        connection = MagicMock()
        connection.is_open = True
        channel = connection.channel.return_value
        channel.basic_publish.return_value = True
        blocking_connection.return_value = connection

        publish_message(self.settings, b'{"category":"9"}', "9", "orders.created")

        channel.confirm_delivery.assert_called_once_with()
        channel.exchange_declare.assert_called_once_with(
            exchange="events", exchange_type="topic", durable=True
        )
        publish_arguments = channel.basic_publish.call_args.kwargs
        self.assertEqual("events", publish_arguments["exchange"])
        self.assertEqual("orders.created", publish_arguments["routing_key"])
        self.assertEqual(b'{"category":"9"}', publish_arguments["body"])
        self.assertTrue(publish_arguments["mandatory"])
        self.assertEqual("application/json", publish_arguments["properties"].content_type)
        self.assertEqual("utf-8", publish_arguments["properties"].content_encoding)
        self.assertEqual(2, publish_arguments["properties"].delivery_mode)
        self.assertEqual("9", publish_arguments["properties"].type)
        connection.close.assert_called_once_with()

    @patch("source.rabbitmq_publisher.pika.BlockingConnection")
    def test_connection_failure_does_not_expose_url(self, blocking_connection):
        blocking_connection.side_effect = pika.exceptions.AMQPConnectionError("connection failed")

        with self.assertRaises(RabbitMqPublishError) as raised:
            publish_message(self.settings, b"{}", "9", "orders.created")

        self.assertNotIn(self.settings.url, str(raised.exception))

    @patch("source.rabbitmq_publisher.pika.BlockingConnection")
    def test_unconfirmed_message_is_rejected(self, blocking_connection):
        connection = MagicMock()
        connection.is_open = True
        connection.channel.return_value.basic_publish.return_value = False
        blocking_connection.return_value = connection

        with self.assertRaises(RabbitMqPublishError):
            publish_message(self.settings, b"{}", "9", "orders.created")

    @patch("source.rabbitmq_publisher.pika.BlockingConnection")
    def test_exchange_conflict_is_reported_as_publish_failure(self, blocking_connection):
        connection = MagicMock()
        connection.is_open = True
        connection.channel.return_value.exchange_declare.side_effect = (
            pika.exceptions.ChannelClosedByBroker(406, "PRECONDITION_FAILED")
        )
        blocking_connection.return_value = connection

        with self.assertRaises(RabbitMqPublishError):
            publish_message(self.settings, b"{}", "9", "orders.created")


class SendMqApiTests(unittest.TestCase):
    def setUp(self):
        self.rabbitmq_environment = {
            "RabbitMqUrl": "amqp://guest:guest@localhost:5672/%2F",
            "RabbitMqExchangeName": "events",
            "RabbitMqExchangeType": "direct",
            "RabbitMqRouteKeyCategoryMap": (
                '[{"RouteKey":"orders.created","CategoryIds":[9,10]}]'
            ),
        }

    def test_success_builds_json_envelope_and_uses_category_mapped_route(self):
        request = main.SendMqRequest(category="9", content='{"orderId":"123"}')
        with patch.dict(os.environ, self.rabbitmq_environment, clear=False):
            with patch("source.main.publish_message") as publish:
                result = asyncio.run(main.send_mq(request))

        self.assertEqual({"status": "success", "message": "Message published"}, result)
        settings, body, category, route_key = publish.call_args.args
        self.assertEqual("orders.created", settings.category_route_keys["9"])
        self.assertEqual("9", category)
        self.assertEqual("orders.created", route_key)
        self.assertEqual(
            {"category": "9", "content": {"orderId": "123"}},
            json.loads(body.decode("utf-8")),
        )

    def test_numeric_category_is_supported_and_preserved_in_envelope(self):
        request = main.SendMqRequest(category=9, content='{"orderId":"123"}')
        with patch.dict(os.environ, self.rabbitmq_environment, clear=False):
            with patch("source.main.publish_message") as publish:
                result = asyncio.run(main.send_mq(request))

        self.assertEqual({"status": "success", "message": "Message published"}, result)
        _, body, category, route_key = publish.call_args.args
        self.assertEqual("9", category)
        self.assertEqual("orders.created", route_key)
        self.assertEqual(
            {"category": 9, "content": {"orderId": "123"}},
            json.loads(body.decode("utf-8")),
        )

    def test_empty_category_is_rejected_before_publishing(self):
        request = main.SendMqRequest(category="   ", content="{}")
        with patch("source.main.publish_message") as publish:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.send_mq(request))

        self.assertEqual(422, raised.exception.status_code)
        publish.assert_not_called()

    def test_invalid_json_is_rejected_before_publishing(self):
        request = main.SendMqRequest(category="order.created", content="not-json")
        with patch("source.main.publish_message") as publish:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.send_mq(request))

        self.assertEqual(422, raised.exception.status_code)
        publish.assert_not_called()

    def test_broker_failure_returns_service_unavailable_without_url(self):
        request = main.SendMqRequest(category="9", content="{}")
        with patch.dict(os.environ, self.rabbitmq_environment, clear=False):
            with patch(
                "source.main.publish_message",
                side_effect=RabbitMqPublishError("publishing failed"),
            ):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(main.send_mq(request))

        self.assertEqual(503, raised.exception.status_code)
        self.assertNotIn(self.rabbitmq_environment["RabbitMqUrl"], str(raised.exception.detail))

    def test_unmapped_category_is_rejected_before_publishing(self):
        request = main.SendMqRequest(category="999", content="{}")
        with patch.dict(os.environ, self.rabbitmq_environment, clear=False):
            with patch("source.main.publish_message") as publish:
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(main.send_mq(request))

        self.assertEqual(422, raised.exception.status_code)
        publish.assert_not_called()
