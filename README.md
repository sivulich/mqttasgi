# mqttasgi - MQTT ASGI Protocol Server for Django
mqttasgi is an ASGI protocol server that implements a complete interface for MQTT for the Django development framework. Built following [daphne](https://github.com/django/daphne) protocol server.

![Downloads Shield Count](https://img.shields.io/pypi/dm/mqttasgi)
![GitHub License](https://img.shields.io/github/license/sivulich/mqttasgi)
![GitHub contributors](https://img.shields.io/github/contributors/sivulich/mqttasgi)

# Features
- Publish / Subscribe to any topic
- Multiple workers to handle different topics / subscriptions.
- Full Django ORM support within consumers.
- Full Channel Layers support.
- Full testing support to enable TDD (no broker required for unit tests).
- Lightweight.
- Django 3.2+ / Django 4.x / Django 5.x support
- Channels 3.x / Channels 4.x support
- paho-mqtt 1.x and 2.x support
- Python 3.9 – 3.13 support

# Installation
```bash
pip install mqttasgi
```

**IMPORTANT NOTE:** If legacy support for Django 2.x is required install the latest 0.x mqttasgi release.



# Usage
## Running the server
Mqttasgi provides a CLI to run the protocol server.
```bash
mqttasgi -H localhost -p 1883 my_application.asgi:application
```

| Parameter | Explanation | Environment variable | Default |
|-----------|-------------|:--------------------:|:-------:|
| -H / --host | MQTT broker host | MQTT_HOSTNAME | localhost |
| -p / --port | MQTT broker port | MQTT_PORT | 1883 |
| -c / --cleansession | MQTT Clean Session | MQTT_CLEAN | True |
| -v / --verbosity | Logging verbosity (0-2) | VERBOSITY | 0 |
| -U / --username | MQTT Username | MQTT_USERNAME | |
| -P / --password | MQTT Password | MQTT_PASSWORD | |
| -i / --id | MQTT Client ID | MQTT_CLIENT_ID | |
| -C / --cert | TLS Certificate | TLS_CERT | |
| -K / --key | TLS Key | TLS_KEY | |
| -S / --cacert | TLS CA Certificate | TLS_CA | |
| -SSL / --use-ssl | Use SSL (no certificate auth) | MQTT_USE_SSL | False |
| -T / --transport | Transport type (tcp or websockets) | MQTT_TRANSPORT | tcp |
| -r / --retries | Retries on disconnect (0 = unlimited) | MQTT_RETRIES | 3 |
| Last argument | ASGI Application | | |

Environment variables are supported via a `.env` file at the project root. A CLI argument always takes precedence over the corresponding environment variable.

## Consumer

Register your consumer in `asgi.py`:
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

Your consumer inherits from `MqttConsumer` and overrides three lifecycle methods:

```python
from mqttasgi.consumers import MqttConsumer

class MyMqttConsumer(MqttConsumer):

    async def connect(self):
        await self.subscribe('my/testing/topic', qos=2)

    async def receive(self, mqtt_message):
        print('Received at topic:', mqtt_message['topic'])
        print('Payload:', mqtt_message['payload'])
        print('QoS:', mqtt_message['qos'])

    async def disconnect(self):
        await self.unsubscribe('my/testing/topic')
```

## Consumer API

### MQTT

#### Publish

```python
await self.publish(topic, payload, qos=1, retain=False)
```

#### Subscribe

```python
await self.subscribe(topic, qos)
```

#### Unsubscribe

```python
await self.unsubscribe(topic)
```

### Worker API — Experimental

Allows running multiple consumers inside the same mqttasgi instance. Only the master consumer (the one started automatically, `instance_type='master'`) may spawn or kill workers.

#### Spawn Worker

`app_id` is a unique identifier, `consumer_path` is the dotted import path to the consumer class, and `consumer_params` is a dict merged into the consumer scope.

```python
await self.spawn_worker(app_id, consumer_path, consumer_params)
```

#### Kill Worker

```python
await self.kill_worker(app_id)
```

## Channel Layers

mqttasgi supports Django Channels layer communications and group messages following the [Channel Layers](https://channels.readthedocs.io/en/stable/topics/channel_layers.html) spec.

Outside the consumer:
```python
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

channel_layer = get_channel_layer()
async_to_sync(channel_layer.group_send)(
    "my.group",
    {"type": "my.custom.message", "text": "Hi from outside the consumer"}
)
```

Inside the consumer:
```python
from mqttasgi.consumers import MqttConsumer

class MyMqttConsumer(MqttConsumer):

    async def connect(self):
        await self.subscribe('my/testing/topic', qos=2)
        await self.channel_layer.group_add("my.group", self.channel_name)

    async def receive(self, mqtt_message):
        print('Received at topic:', mqtt_message['topic'])

    async def my_custom_message(self, event):
        print('Channel layer message:', event)

    async def disconnect(self):
        await self.unsubscribe('my/testing/topic')
```

## Testing

mqttasgi ships with `MqttComunicator`, an ASGI test helper that drives your consumer directly without a running MQTT broker — perfect for fast, isolated unit tests.

### Setup

Install test dependencies:
```bash
pip install pytest pytest-asyncio django channels
```

Create `pytest.ini` at the project root:
```ini
[pytest]
asyncio_mode = auto
```

Create `tests/conftest.py` to bootstrap Django before the tests run:
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

### Testing consumers

`MqttComunicator` simulates the full ASGI lifecycle: it sends events to your consumer and captures what the consumer sends back, with no broker involved.

```python
# tests/test_consumers.py
import pytest
from mqttasgi.testing import MqttComunicator
from mqttasgi.consumers import MqttConsumer


class EchoConsumer(MqttConsumer):
    async def connect(self):
        await self.subscribe('test/topic', qos=1)

    async def receive(self, mqtt_message):
        await self.publish('test/response', mqtt_message['payload'], qos=1)

    async def disconnect(self):
        await self.unsubscribe('test/topic')


async def test_connect_sends_subscribe():
    """connect() should subscribe to the expected topic."""
    comm = MqttComunicator(EchoConsumer.as_asgi(), app_id=1)
    response = await comm.connect()
    assert response['type'] == 'mqtt.sub'
    assert response['mqtt']['topic'] == 'test/topic'
    assert response['mqtt']['qos'] == 1
    await comm.disconnect()


async def test_disconnect_sends_unsubscribe():
    """disconnect() should unsubscribe from all topics."""
    comm = MqttComunicator(EchoConsumer.as_asgi(), app_id=1)
    await comm.connect()
    await comm.disconnect()
    response = await comm.receive_from()
    assert response['type'] == 'mqtt.usub'
    assert response['mqtt']['topic'] == 'test/topic'


async def test_echo():
    """Consumer should publish a response for each received message."""
    comm = MqttComunicator(EchoConsumer.as_asgi(), app_id=1)
    await comm.connect()
    await comm.publish('test/topic', b'hello', qos=1)
    response = await comm.receive_from()
    assert response['type'] == 'mqtt.pub'
    assert response['mqtt']['topic'] == 'test/response'
    assert response['mqtt']['payload'] == b'hello'
    await comm.disconnect()


async def test_consumer_params_passed_to_scope():
    """Custom parameters should be available in the consumer scope."""
    received = {}

    class ParamConsumer(MqttConsumer):
        async def connect(self):
            received.update(self.scope)
            await self.subscribe('dummy', 1)
        async def receive(self, mqtt_message): pass
        async def disconnect(self): pass

    comm = MqttComunicator(
        ParamConsumer.as_asgi(),
        app_id=5,
        consumer_parameters={'device_id': 'sensor-01'},
    )
    await comm.connect()
    assert received['device_id'] == 'sensor-01'
    assert received['app_id'] == 5
    await comm.disconnect()
```

### MqttComunicator API

| Method | Description |
|--------|-------------|
| `MqttComunicator(app, app_id, instance_type='worker', consumer_parameters=None)` | Create a communicator for the given ASGI app |
| `await comm.connect(timeout=1)` | Send `mqtt.connect` to the consumer and return the first response |
| `await comm.publish(topic, payload, qos)` | Send an `mqtt.msg` event to the consumer |
| `await comm.receive_from(timeout=1)` | Receive the next message the consumer sent (e.g. `mqtt.pub`, `mqtt.sub`) |
| `await comm.disconnect(code=1000, timeout=1)` | Send `mqtt.disconnect` and wait for the consumer to close |

### Integration tests (optional, requires a broker)

For end-to-end tests against a real MQTT broker, start mosquitto and run:

```bash
# macOS
brew install mosquitto

# Run only integration tests
pytest tests/test_integration.py -v
```

Integration tests are automatically skipped when no broker is available, so they never break CI in environments without one.

# What's new in 2.0.0

- **paho-mqtt 2.x compatibility** — automatically detects the installed paho-mqtt version and uses the correct `CallbackAPIVersion` (2.x) or legacy API (1.x). Both versions are supported with no code changes required.
- **Python 3.10 – 3.13 compatibility** — removed deprecated `asyncio.ensure_future(loop=...)` calls, replaced with `loop.create_task()`. Removed Python < 3.9 compatibility shims.
- **Bug fix: integer `client_id`** — the default `client_id` was stored as an integer, causing paho-mqtt to raise `TypeError` at connection time. It is now always coerced to a string.
- **Better error logging** — connection failures now surface the actual exception at `ERROR` level instead of being silently swallowed.
- **Test suite** — a full pytest-based test suite is included covering server internals, consumer lifecycle, and optional broker integration tests (auto-skipped when no broker is available).

# AI Assistant Skill

mqttasgi is available as an [OpenClaw](https://clawhub.ai/) skill. AI assistants that support OpenClaw skills can install it to get full knowledge of the API, consumer patterns, testing utilities, and home automation use cases.

- **Slug:** `mqttasgi`
- **Display name:** `mqttasgi - MQTT ASGI for Django`
- **Skill file:** [`claude_skill/SKILL.md`](claude_skill/SKILL.md)

# Supporters

## MAPER - IIOT Asset Monitoring - [Webpage](https://home.mapertech.com/en/)

Predict failures before they happen.

Real time health monitoring to avoid unexpected downtimes and organize maintenance in industrial plants.

Combining IoT Technology and Artificial Intelligence, we deliver a complete view of your assets like never before.

With real time health diagnostics you will increase the reliability of the whole production process, benefitting both the company and its staff.
