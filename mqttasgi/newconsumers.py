"""
newconsumers.py

Extensão do MqttConsumer base do mqttasgi com suporte a MQTTv5 properties.
Usa herança e polimorfismo — não modifica o código original da lib.

Mudanças em relação ao base:
- publish() aceita `properties` dict com CorrelationData, ResponseTopic, etc.
- mqtt_msg() repassa properties ao receive()
- Logging estruturado em todos os métodos
"""

import logging
from mqttasgi.consumers import MqttConsumer

logger = logging.getLogger(__name__)


class MqttConsumerV5(MqttConsumer):
    """
    MqttConsumer com suporte a MQTTv5 properties.

    O servidor (newserver.py) já inclui `properties` no evento mqtt.msg.
    Esta classe repassa as properties ao receive() e permite publicar
    com properties via o método publish().
    """

    async def publish(self, topic, payload, qos=1, retain=False, properties=None):
        """
        Sobrescreve o publish base para incluir MQTTv5 properties.

        properties: dict com chaves opcionais:
            - CorrelationData: bytes | str
            - ResponseTopic: str
            - ContentType: str
            - UserProperty: list[tuple[str, str]]
        """
        logger.debug(
            "[MqttConsumerV5][publish] topic=%s qos=%d retain=%s properties=%s",
            topic, qos, retain, properties
        )

        msg = {
            'topic': topic,
            'payload': payload,
            'qos': qos,
            'retain': retain,
        }

        if properties:
            msg['properties'] = properties

        await self.send({
            'type': 'mqtt.pub',
            'mqtt': msg,
        })

    async def mqtt_msg(self, event):
        """
        Sobrescreve o handler base para repassar properties ao receive().
        O evento inclui 'properties' quando o servidor é MQTTv5.
        """
        mqtt_message = event['mqtt']

        logger.debug(
            "[MqttConsumerV5][mqtt_msg] topic=%s properties=%s",
            mqtt_message.get('topic'),
            mqtt_message.get('properties', {})
        )

        await self.receive(mqtt_message)

    async def receive(self, mqtt_message):
        """
        Sobrescreva este método nos consumers filhos.
        mqtt_message agora inclui:
            - topic: str
            - payload: bytes
            - qos: int
            - properties: dict  ← MQTTv5, pode estar vazio
                - CorrelationData: bytes
                - ResponseTopic: str
                - ContentType: str
                - UserProperty: list
        """
        pass

    async def connect(self):
        logger.debug("[MqttConsumerV5][connect] app_id=%s", self.scope.get('app_id'))

    async def disconnect(self):
        logger.debug("[MqttConsumerV5][disconnect] app_id=%s", self.scope.get('app_id'))

    async def mqtt_connect(self, event):
        if self.subscribed_topics:
            logger.warning(
                "[MqttConsumerV5][mqtt_connect] clearing %d stale subscriptions before connect: %s",
                len(self.subscribed_topics),
                self.subscribed_topics,
            )
            self.subscribed_topics.clear()
        logger.info(
            "[MqttConsumerV5][mqtt_connect] app_id=%s instance_type=%s",
            self.scope.get('app_id'),
            self.scope.get('instance_type')
        )
        await self.connect()

    async def mqtt_disconnect(self, event):
        logger.info(
            "[MqttConsumerV5][mqtt_disconnect] app_id=%s",
            self.scope.get('app_id')
        )
        await self.disconnect()
        from channels.exceptions import StopConsumer
        raise StopConsumer