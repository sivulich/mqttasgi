---
name: mqttasgi
description: MQTT ASGI protocol server for Django — bridge MQTT messages to Django Channels consumers with full ORM, Channel Layers, and testing support. The perfect backbone for your home automation projects, IoT pipelines, and real-time device integrations.
version: 1.0.0
metadata:
  openclaw:
    emoji: "📡"
    homepage: https://github.com/sivulich/mqttasgi
---

# mqttasgi

mqttasgi is an ASGI protocol server that bridges MQTT (via paho-mqtt) and Django Channels, inspired by Daphne. It lets Django consumers subscribe/publish to MQTT topics with full ORM and Channel Layers support.

Supports: Django 3.2–5.x · Channels 3.x–4.x · paho-mqtt 1.x and 2.x · Python 3.9–3.13

## Installation

```bash
pip install mqttasgi
```

## Running the server

```bash
mqttasgi -H localhost -p 1883 my_application.asgi:application
```

| Parameter | Env variable | Default | Purpose |
|-----------|-------------|---------|---------|
| `-H / --host` | `MQTT_HOSTNAME` | `localhost` | MQTT broker host |
| `-p / --port` | `MQTT_PORT` | `1883` | MQTT broker port |
| `-U / --username` | `MQTT_USERNAME` | | Broker username |
| `-P / --password` | `MQTT_PASSWORD` | | Broker password |
| `-c / --cleansession` | `MQTT_CLEAN` | `True` | MQTT clean session |
| `-v / --verbosity` | `VERBOSITY` | `0` | Logging level (0–2) |
| `-i / --id` | `MQTT_CLIENT_ID` | | MQTT client ID |
| `-C / --cert` | `TLS_CERT` | | TLS certificate |
| `-K / --key` | `TLS_KEY` | | TLS key |
| `-S / --cacert` | `TLS_CA` | | TLS CA certificate |
| `-SSL / --use-ssl` | `MQTT_USE_SSL` | `False` | SSL without cert auth |
| `-T / --transport` | `MQTT_TRANSPORT` | `tcp` | Transport: `tcp` or `websockets` |
| `-r / --retries` | `MQTT_RETRIES` | `3` | Reconnect retries (0 = unlimited) |

All parameters can also be set via a `.env` file at the project root. CLI args take precedence over env vars.

## asgi.py setup

```python
import os
import django
from channels.routing import ProtocolTypeRouter
from my_application.consumers import MyMqttConsumer
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_application.settings')
django.setup()

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'mqtt': MyMqttConsumer.as_asgi(),
})
```

## Writing a consumer

```python
from mqttasgi.consumers import MqttConsumer

class MyMqttConsumer(MqttConsumer):

    async def connect(self):
        """Called when connected to the broker. Subscribe here."""
        await self.subscribe('my/topic', qos=2)

    async def receive(self, mqtt_message):
        """Called for each incoming MQTT message."""
        topic   = mqtt_message['topic']
        payload = mqtt_message['payload']   # bytes
        qos     = mqtt_message['qos']
        await self.publish('response/topic', payload, qos=1, retain=False)

    async def disconnect(self):
        """Called on broker disconnect. Clean up here."""
        await self.unsubscribe('my/topic')
```

### Consumer API

| Method | Description |
|--------|-------------|
| `await self.subscribe(topic, qos)` | Subscribe to an MQTT topic |
| `await self.unsubscribe(topic)` | Unsubscribe from an MQTT topic |
| `await self.publish(topic, payload, qos=1, retain=False)` | Publish an MQTT message |
| `self.scope` | ASGI scope dict (includes `app_id`, `instance_type`, and any `consumer_parameters`) |

## Channel Layers

```python
# Outside the consumer (e.g. Django view or management command)
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

channel_layer = get_channel_layer()
async_to_sync(channel_layer.group_send)(
    "my.group",
    {"type": "my.custom.message", "text": "Hello from outside"}
)

# Inside the consumer
class MyMqttConsumer(MqttConsumer):

    async def connect(self):
        await self.subscribe('my/topic', qos=2)
        await self.channel_layer.group_add("my.group", self.channel_name)

    async def my_custom_message(self, event):
        # Handler name must match the `type` field (dots become underscores)
        print('Channel layer message:', event)

    async def receive(self, mqtt_message): ...
    async def disconnect(self): ...
```

## Multiple workers (experimental)

Only the master consumer (`instance_type='master'`, `app_id=0`) may spawn or kill workers.

```python
class MasterConsumer(MqttConsumer):

    async def connect(self):
        # Spawn a worker with a unique app_id
        await self.spawn_worker(
            app_id=1,
            consumer_path='my_application.consumers.WorkerConsumer',
            consumer_params={'device_id': 'sensor-01'},
        )

    async def receive(self, mqtt_message):
        if condition:
            await self.kill_worker(app_id=1)

    async def disconnect(self): ...
```

## Testing (no broker required)

`MqttComunicator` drives consumers directly through the ASGI interface — no running broker needed.

### pytest.ini

```ini
[pytest]
asyncio_mode = auto
```

### tests/conftest.py

```python
import django
from django.conf import settings

def pytest_configure(config):
    if not settings.configured:
        settings.configure(
            SECRET_KEY='test-secret-key',
            INSTALLED_APPS=['channels'],
            DATABASES={},
            CHANNEL_LAYERS={
                'default': {
                    'BACKEND': 'channels.layers.InMemoryChannelLayer',
                }
            },
        )
        django.setup()
```

### Writing tests

```python
import pytest
from mqttasgi.testing import MqttComunicator  # note: one 'm' in Comunicator
from my_application.consumers import MyMqttConsumer

async def test_subscribe_on_connect():
    comm = MqttComunicator(MyMqttConsumer.as_asgi(), app_id=1)
    response = await comm.connect()          # returns first message from consumer
    assert response['type'] == 'mqtt.sub'
    assert response['mqtt']['topic'] == 'my/topic'
    await comm.disconnect()

async def test_publish_on_message():
    comm = MqttComunicator(MyMqttConsumer.as_asgi(), app_id=1)
    await comm.connect()
    await comm.publish('my/topic', b'hello', qos=1)
    response = await comm.receive_from()    # next message from consumer
    assert response['type'] == 'mqtt.pub'
    assert response['mqtt']['payload'] == b'hello'
    await comm.disconnect()
```

### MqttComunicator API

| Method | Description |
|--------|-------------|
| `MqttComunicator(app, app_id, instance_type='worker', consumer_parameters=None)` | Create communicator |
| `await comm.connect(timeout=1)` | Send `mqtt.connect`; returns first consumer response |
| `await comm.publish(topic, payload, qos)` | Send `mqtt.msg` event to the consumer |
| `await comm.receive_from(timeout=1)` | Receive next message the consumer sent |
| `await comm.disconnect(timeout=1)` | Send `mqtt.disconnect` and wait for shutdown |

Consumer responses have this shape:

```python
{
    'type': 'mqtt.sub',   # or mqtt.pub / mqtt.usub
    'mqtt': {
        'topic': 'my/topic',
        'payload': b'...',   # only for mqtt.pub
        'qos': 1,
    }
}
```

## Internal message types (for advanced use)

**Server → Consumer:** `mqtt.connect`, `mqtt.msg`, `mqtt.disconnect`

**Consumer → Server:** `mqtt.pub`, `mqtt.sub`, `mqtt.usub`, `mqttasgi.worker.spawn`, `mqttasgi.worker.kill`

## Common pitfalls

- `MqttComunicator.connect()` returns the **first message** the consumer sends. If `connect()` does nothing (no subscribe, no publish), the call will time out — always subscribe or send something in `connect()`.
- The class is spelled `MqttComunicator` (one `m`) — this is an intentional (legacy) typo in the library.
- Worker spawn/kill is only allowed from the master consumer (`app_id=0`). Calling it from a worker raises an error.
- With mosquitto 2.x you need `allow_anonymous true` and an explicit `listener` line in `mosquitto.conf` for integration tests.
- `connect_max_retries=0` means retry forever with exponential back-off (capped at 30 s).
