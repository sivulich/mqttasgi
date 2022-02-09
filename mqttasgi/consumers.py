from channels.consumer import AsyncConsumer, SyncConsumer
from asgiref.sync import async_to_sync
from urllib.parse import parse_qs
import zlib
import json
from channels.exceptions import StopConsumer
from channels.db import database_sync_to_async
import asyncio
import logging
import signal

logger = logging.getLogger(__name__)


class MqttConsumer(AsyncConsumer):

    def __init__(self):
        self.subscribed_topics = set()

    async def connect(self):
        pass

    async def receive(self, mqtt_message):
        pass

    async def disconnect(self):
        pass

    async def publish(self, topic, payload, qos=1, retain=False):
        await self.send({
            'type': 'mqtt.pub',
            'mqtt': {
                'topic': topic,
                'payload': payload,
                'qos': qos,
                'retain': retain,
            }
        })

    async def subscribe(self, topic, qos):
        if topic not in self.subscribed_topics:
            self.subscribed_topics.add(topic)

        await self.send({
            'type': 'mqtt.sub',
            'mqtt': {
                'topic': topic,
                'qos': qos
            }
        })

    async def unsubscribe(self, topic):
        if topic in self.subscribed_topics:
            self.subscribed_topics.remove(topic)
        await self.send({
            'type': 'mqtt.usub',
            'mqtt': {
                'topic': topic
            }
        })


    async def mqtt_connect(self, event):
        await self.connect()

    async def mqtt_disconnect(self, event):
        await self.disconnect()
        raise StopConsumer

    async def mqtt_msg(self, event):
        mqtt_message = event['mqtt']
        await self.receive(mqtt_message)

    async def spawn_worker(self, app_id, consumer_path, consumer_params):
        mqttasgi_command = {
            'type': 'mqttasgi.worker.spawn',
            'command': {
                'app_id': app_id,
                'consumer_path': consumer_path,
                'consumer_params': consumer_params
            }
        }
        await self.send(mqttasgi_command)

    async def kill_worker(self, app_id):
        mqttasgi_command = {
            'type': 'mqttasgi.worker.kill',
            'command': {
                'app_id': app_id
            }
        }
        await self.send(mqttasgi_command)


class TestMqttConsumer(MqttConsumer):
    async def connect(self):
        logger.debug('[mqttasgi][consumer][connect] - Connected!')
        if self.scope['instance_type'] == 'master':
            await self.subscribe('spawn', 2)
            await self.subscribe('kill', 2)
        else:
            await self.subscribe(f'{self.scope["app_id"]}', 2)
            await self.subscribe('workers', 2)
            print(self.scope)
        self.count = 0
        pass

    async def receive(self, mqtt_message):
        if self.scope['instance_type'] == 'master':
            logger.debug(f'[mqttasgi][consumer][receive] - Received {mqtt_message["topic"]}:{mqtt_message["payload"]}')
            if mqtt_message['topic'] == 'spawn':
                await self.spawn_worker(mqtt_message['payload'].decode('utf-8'), 'mqttasgi.consumers:TestMqttConsumer', {'test': 'test'})
            elif mqtt_message['topic'] == 'kill':
                await self.kill_worker(mqtt_message['payload'].decode('utf-8'))
        else:
            logger.debug(f'[mqttasgi][consumer][receive] - Received {mqtt_message["topic"]}:{mqtt_message["payload"]}')
        pass

    async def disconnect(self):
        logger.debug('[mqttasgi][consumer][disconnect] - Disconnected!')
        pass
