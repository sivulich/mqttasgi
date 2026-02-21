"""
Consumer unit tests using MqttComunicator.

These tests do NOT require a running MQTT broker. MqttComunicator drives the
consumer directly via the ASGI interface, so you can test your business logic
in complete isolation.
"""

import pytest

from mqttasgi.consumers import MqttConsumer
from mqttasgi.testing import MqttComunicator


# ---------------------------------------------------------------------------
# Example consumers used by the tests below
# ---------------------------------------------------------------------------

class SubscribingConsumer(MqttConsumer):
    """Subscribes to one topic on connect, unsubscribes on disconnect."""

    async def connect(self):
        await self.subscribe('test/topic', qos=1)

    async def receive(self, mqtt_message):
        pass

    async def disconnect(self):
        await self.unsubscribe('test/topic')


class EchoConsumer(MqttConsumer):
    """Publishes back whatever payload it receives."""

    async def connect(self):
        await self.subscribe('test/echo', qos=1)

    async def receive(self, mqtt_message):
        await self.publish('test/echo/response', mqtt_message['payload'], qos=1)

    async def disconnect(self):
        pass


class MultiSubscribeConsumer(MqttConsumer):
    """Subscribes to two topics on connect."""

    async def connect(self):
        await self.subscribe('topic/a', qos=0)
        await self.subscribe('topic/b', qos=2)

    async def receive(self, mqtt_message):
        pass

    async def disconnect(self):
        pass


# ---------------------------------------------------------------------------
# Connect / disconnect lifecycle
# ---------------------------------------------------------------------------

class TestConsumerLifecycle:
    async def test_connect_sends_subscribe(self):
        """connect() triggers a mqtt.sub sent back to the server."""
        comm = MqttComunicator(SubscribingConsumer.as_asgi(), app_id=1)
        response = await comm.connect()
        assert response['type'] == 'mqtt.sub'
        assert response['mqtt']['topic'] == 'test/topic'
        assert response['mqtt']['qos'] == 1
        await comm.disconnect()

    async def test_disconnect_sends_unsubscribe(self):
        """disconnect() sends mqtt.usub for each subscribed topic."""
        comm = MqttComunicator(SubscribingConsumer.as_asgi(), app_id=1)
        await comm.connect()  # consumes the mqtt.sub response
        await comm.disconnect()
        # The usub is sent before StopConsumer — receive it
        response = await comm.receive_from()
        assert response['type'] == 'mqtt.usub'
        assert response['mqtt']['topic'] == 'test/topic'

    async def test_consumer_scope_contains_app_id(self):
        """The scope passed to the consumer includes the app_id."""
        received_scope = {}

        class ScopeInspector(MqttConsumer):
            async def connect(self):
                received_scope.update(self.scope)
                await self.subscribe('dummy', 1)  # emit a response so connect() doesn't timeout

            async def receive(self, mqtt_message):
                pass

            async def disconnect(self):
                pass

        comm = MqttComunicator(ScopeInspector.as_asgi(), app_id=42)
        await comm.connect()
        assert received_scope['app_id'] == 42
        await comm.disconnect()


# ---------------------------------------------------------------------------
# Publish / receive
# ---------------------------------------------------------------------------

class TestConsumerMessaging:
    async def test_echo_consumer(self):
        """Consumer receives a message and publishes a response."""
        comm = MqttComunicator(EchoConsumer.as_asgi(), app_id=1)
        await comm.connect()  # subscribe response

        await comm.publish('test/echo', b'hello world', qos=1)
        response = await comm.receive_from()

        assert response['type'] == 'mqtt.pub'
        assert response['mqtt']['topic'] == 'test/echo/response'
        assert response['mqtt']['payload'] == b'hello world'
        assert response['mqtt']['qos'] == 1
        await comm.disconnect()

    async def test_multiple_messages(self):
        """Consumer handles multiple sequential messages."""
        comm = MqttComunicator(EchoConsumer.as_asgi(), app_id=1)
        await comm.connect()

        payloads = [b'msg1', b'msg2', b'msg3']
        for payload in payloads:
            await comm.publish('test/echo', payload, qos=1)
            response = await comm.receive_from()
            assert response['mqtt']['payload'] == payload

        await comm.disconnect()


# ---------------------------------------------------------------------------
# Subscribe / unsubscribe tracking
# ---------------------------------------------------------------------------

class TestSubscriptionTracking:
    async def test_subscribed_topics_set(self):
        """MqttConsumer.subscribed_topics is populated on subscribe."""
        comm = MqttComunicator(SubscribingConsumer.as_asgi(), app_id=1)
        # We can't directly inspect the consumer instance here, but we verify
        # the correct mqtt.sub event is emitted.
        response = await comm.connect()
        assert response['mqtt']['topic'] == 'test/topic'
        await comm.disconnect()

    async def test_multiple_subscriptions(self):
        """Multiple subscribe() calls each emit a separate mqtt.sub."""
        comm = MqttComunicator(MultiSubscribeConsumer.as_asgi(), app_id=1)
        await comm.send_input({'type': 'mqtt.connect'})

        sub_a = await comm.receive_output(timeout=1)
        sub_b = await comm.receive_output(timeout=1)

        topics = {sub_a['mqtt']['topic'], sub_b['mqtt']['topic']}
        assert topics == {'topic/a', 'topic/b'}
        await comm.disconnect()


# ---------------------------------------------------------------------------
# Consumer parameters
# ---------------------------------------------------------------------------

class TestConsumerParameters:
    async def test_custom_params_in_scope(self):
        """consumer_parameters are merged into the scope."""
        received = {}

        class ParamConsumer(MqttConsumer):
            async def connect(self):
                received.update(self.scope)
                await self.subscribe('dummy', 1)  # emit a response so connect() doesn't timeout

            async def receive(self, mqtt_message):
                pass

            async def disconnect(self):
                pass

        comm = MqttComunicator(
            ParamConsumer.as_asgi(),
            app_id=5,
            consumer_parameters={'device_id': 'sensor-01', 'site': 'warehouse'},
        )
        await comm.connect()
        assert received['device_id'] == 'sensor-01'
        assert received['site'] == 'warehouse'
        assert received['app_id'] == 5
        await comm.disconnect()
