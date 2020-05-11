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

    def __init__(self, scope):
        super().__init__(scope)
        self.subscribed_topics = []

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
            self.subscribed_topics.append(topic)

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


class TestMqttConsumer(MqttConsumer):
    async def connect(self):
        logger.debug('[mqttasgi][consumer][connect] - Connected!')
        await self.subscribe('test', 2)
        self.count = 0
        pass

    async def receive(self, mqtt_message):
        await self.publish('test2', 'Hola')
        logger.debug(f'[mqttasgi][consumer][msg] - Received message {mqtt_message}')
        self.count += 1
        if self.count == 3:
            logger.debug(f'[mqttasgi][consumer][msg] - After 3 messages unsubscribing')
            await self.unsubscribe('test')
        pass

    async def disconnect(self):
        logger.debug('[mqttasgi][consumer][disconnect] - Disconnected!')
        pass
