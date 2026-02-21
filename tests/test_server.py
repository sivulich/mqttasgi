"""
Unit tests for mqttasgi.server.

These tests do NOT require a running MQTT broker. They verify:
- paho-mqtt 1.x / 2.x compatibility shim works correctly
- Callback signatures accept both paho API versions
- Server initialises without errors
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

import paho.mqtt.client as mqtt

from mqttasgi.server import Server, _PAHO_MQTT_V2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_server():
    """Return a Server instance without starting the event loop."""
    mock_app = AsyncMock()
    return Server(mock_app, host='localhost', port=1883)


# ---------------------------------------------------------------------------
# paho version detection
# ---------------------------------------------------------------------------

class TestPahoVersionDetection:
    def test_flag_matches_installed_paho(self):
        """_PAHO_MQTT_V2 must agree with the actual installed paho version."""
        if hasattr(mqtt, 'CallbackAPIVersion'):
            assert _PAHO_MQTT_V2 is True, "paho 2.x detected but flag is False"
        else:
            assert _PAHO_MQTT_V2 is False, "paho 1.x detected but flag is True"

    def test_client_type(self):
        """Server.client must be a paho Client instance regardless of version."""
        server = _make_server()
        assert isinstance(server.client, mqtt.Client)


# ---------------------------------------------------------------------------
# on_connect callback — must work with both paho 1.x and 2.x signatures
# ---------------------------------------------------------------------------

class TestOnConnectCompatibility:
    def test_paho_v1_signature(self):
        """Accepts paho 1.x signature: (client, userdata, flags, rc)."""
        server = _make_server()
        server._on_connect(MagicMock(), {}, {}, 0)  # rc as positional arg

    def test_paho_v2_signature(self):
        """Accepts paho 2.x signature: (client, userdata, flags, reason_code, properties)."""
        server = _make_server()
        server._on_connect(MagicMock(), {}, {}, MagicMock(), MagicMock())

    def test_sends_connect_event_to_all_apps(self):
        """_on_connect must enqueue mqtt.connect for every registered application."""
        server = _make_server()

        # Manually register two fake applications with receive queues
        for app_id in (0, 1):
            server.application_data[app_id] = {'receive': asyncio.Queue()}

        server._on_connect(MagicMock(), {}, {}, 0)

        for app_id in (0, 1):
            event = server.application_data[app_id]['receive'].get_nowait()
            assert event['type'] == 'mqtt.connect'


# ---------------------------------------------------------------------------
# on_disconnect callback
# ---------------------------------------------------------------------------

class TestOnDisconnectCompatibility:
    def _make_stopped_server(self):
        server = _make_server()
        server.stop = True  # prevent reconnect attempt
        return server

    def test_paho_v1_signature(self):
        """Accepts paho 1.x signature: (client, userdata, rc)."""
        server = self._make_stopped_server()
        server._on_disconnect(MagicMock(), {}, 0)

    def test_paho_v2_signature(self):
        """Accepts paho 2.x signature: (client, userdata, disconnect_flags, reason_code, properties)."""
        server = self._make_stopped_server()
        server._on_disconnect(MagicMock(), {}, MagicMock(), MagicMock(), MagicMock())

    def test_no_reconnect_when_stopped(self):
        """Does not attempt reconnect if server.stop is True."""
        server = self._make_stopped_server()
        reconnect_called = []
        server._handle_reconnect = lambda: reconnect_called.append(True)
        server._on_disconnect(MagicMock(), {}, 0)
        assert reconnect_called == []


# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------

class TestServerInit:
    def test_default_message_types(self):
        server = _make_server()
        assert server.mqtt_type_pub == 'mqtt.pub'
        assert server.mqtt_type_sub == 'mqtt.sub'
        assert server.mqtt_type_usub == 'mqtt.usub'
        assert server.mqtt_type_msg == 'mqtt.msg'

    def test_custom_message_types(self):
        server = Server(
            AsyncMock(), 'localhost', 1883,
            mqtt_type_pub='custom.pub',
            mqtt_type_sub='custom.sub',
        )
        assert server.mqtt_type_pub == 'custom.pub'
        assert server.mqtt_type_sub == 'custom.sub'

    def test_empty_subscriptions_on_init(self):
        server = _make_server()
        assert server.topics_subscription == {}
        assert server.topic_queues == {}
        assert server.application_data == {}
