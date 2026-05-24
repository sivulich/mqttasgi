from .server import Server as _BaseServer
import asyncio
import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes
from asyncio import sleep


def _properties_to_dict(props) -> dict:
    """Converte objeto Properties do paho para dict serializável."""
    if props is None:
        return {}
    result = {}
    # properties mais relevantes do MQTTv5
    for attr in [
        'CorrelationData',
        'ResponseTopic',
        'ContentType',
        'UserProperty',
        'MessageExpiryInterval',
        'PayloadFormatIndicator',
    ]:
        val = getattr(props, attr, None)
        if val is not None:
            result[attr] = val
    return result


class Server(_BaseServer):
    def __init__(self, *args, protocol=mqtt.MQTTProtocolVersion.MQTTv311, **kwargs):
        super().__init__(*args, **kwargs)
        self.protocol = protocol

        self._clean_session = None if protocol == mqtt.MQTTProtocolVersion.MQTTv5 else kwargs.get('clean_session', True)

        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            transport=self.transport,
            userdata={"server": self, "host": self.host, "port": self.port},
            clean_session=self._clean_session,
            protocol=protocol,
        )
        self.client.enable_logger(self.log)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        # on_message com suporte a properties MQTTv5
        self.client.on_message = lambda client, userdata, message: \
            self._mqtt_receive(
                -1,
                message.topic,
                message.payload,
                message.qos,
                _properties_to_dict(getattr(message, 'properties', None))
            )

        print(f'[SERVER] protocol={self.protocol} transport={self.transport}')

    def _strip_shared(self, topic: str) -> str:
        """Extrai o tópico real de um shared subscription ($share/grupo/topico)."""
        if topic.startswith('$share/'):
            parts = topic.split('/', 2)
            if len(parts) == 3:
                stripped = parts[2]
                self.log.debug(f'[STRIP] {topic} -> {stripped}')
                return stripped
        return topic

    def _mqtt_receive(self, subscription, topic, payload, qos, properties=None):
        """Override para incluir properties MQTTv5 na mensagem entregue ao consumer."""
        if properties is None:
            properties = {}

        if subscription == -1:
            self.log.warning(
                "[mqttasgi][mqtt][receive] - Received message that no app is subscribed"
                " to topic:{} adding to queue".format(topic)
            )
            if topic not in self.topic_queues:
                self.topic_queues[topic] = []
            self.topic_queues[topic].append({
                'topic': topic,
                'payload': payload,
                'qos': qos,
                'properties': properties,
            })
            return

        for app_id in self.topics_subscription[subscription]['apps']:
            try:
                self.application_data[app_id]['receive'].put_nowait({
                    'type': 'mqtt.msg',
                    'mqtt': {
                        'topic': topic,
                        'payload': payload,
                        'qos': qos,
                        'properties': properties,
                    }
                })
            except Exception as e:
                self.log.error("[mqttasgi][mqtt][receive] - Cant add to queue of {}".format(app_id))
                self.log.exception(e)

    async def mqtt_subscribe(self, app_id, msg):
        """Override para suportar shared subscriptions e properties."""
        sub = msg['mqtt']
        raw_topic = sub['topic']
        topic = self._strip_shared(raw_topic)
        qos = sub['qos']

        if topic not in self.topics_subscription:
            self.topics_subscription[topic] = {'qos': -1, 'apps': set()}
        status = self.topics_subscription[topic]
        qos_diff = qos - status['qos']

        if topic in self.application_data[app_id]['subscriptions'] and \
                qos == self.application_data[app_id]['subscriptions'][topic]:
            self.log.warning(
                "[mqttasgi][app][subscribe] - Subscription of {} to {}:{} already exists"
                .format(app_id, topic, qos)
            )

        self.application_data[app_id]['subscriptions'][topic] = qos

        if qos_diff > 0 and len(status['apps']) > 0:
            self.client.unsubscribe(raw_topic)
            self.client.subscribe(raw_topic, qos)
            status['qos'] = qos
        elif len(status['apps']) == 0:
            # callback com properties
            self.client.message_callback_add(
                topic,
                lambda client, userdata, message, t=topic: self._mqtt_receive(
                    t,
                    message.topic,
                    message.payload,
                    message.qos,
                    _properties_to_dict(getattr(message, 'properties', None))
                )
            )
            self.client.subscribe(raw_topic, qos)
            status['qos'] = qos
        else:
            self.log.debug(
                "[mqttasgi][app][subscribe] - Subscription to {}:{} has {} listeners"
                .format(topic, status['qos'], len(status['apps']) + 1)
            )

        status['apps'].add(app_id)
        self.topics_subscription[topic] = status

        # flush de mensagens enfileiradas antes da subscription
        flushed_topics = []
        for msg_topic in self.topic_queues:
            if mqtt.topic_matches_sub(topic, msg_topic):
                self.log.info(
                    "[mqttasgi][app][subscribe] - Flushing {} with {} messages"
                    .format(msg_topic, len(self.topic_queues[msg_topic]))
                )
                while len(self.topic_queues[msg_topic]) > 0:
                    queued = self.topic_queues[msg_topic].pop(0)
                    try:
                        self.application_data[app_id]['receive'].put_nowait({
                            'type': 'mqtt.msg',
                            'mqtt': queued
                        })
                    except Exception as e:
                        self.log.exception(e)
                flushed_topics.append(msg_topic)

        for msg_topic in flushed_topics:
            del self.topic_queues[msg_topic]

    async def mqtt_unsubscribe(self, app_id, msg, soft=False):
        """Override para suportar shared subscriptions no unsubscribe."""
        raw_topic = msg['mqtt']['topic']
        topic = self._strip_shared(raw_topic)

        if topic not in self.topics_subscription:
            self.log.error("[mqttasgi][app][unsubscribe] - Non existing topic {}".format(topic))
            return
        status = self.topics_subscription[topic]

        if app_id not in self.topics_subscription[topic]['apps']:
            self.log.error(
                "[mqttasgi][app][unsubscribe] - App {} not subscribed to {}"
                .format(app_id, topic)
            )
            return

        if topic in self.application_data[app_id]['subscriptions']:
            del self.application_data[app_id]['subscriptions'][topic]

        if len(status['apps']) == 1:
            if not soft:
                self.client.unsubscribe(raw_topic)
            self.client.message_callback_remove(topic)
            self.topics_subscription[topic] = {'qos': 0, 'apps': set()}
        elif len(status['apps']) > 1:
            self.topics_subscription[topic]['apps'].remove(app_id)

    async def mqtt_publish(self, app_id, msg):
        """Override para suportar properties MQTTv5 no publish."""
        pub = msg['mqtt']
        props = None

        if self.protocol == mqtt.MQTTProtocolVersion.MQTTv5:
            props = Properties(PacketTypes.PUBLISH)
            raw_props = pub.get('properties', {})

            if 'CorrelationData' in raw_props:
                val = raw_props['CorrelationData']
                props.CorrelationData = val if isinstance(val, bytes) else str(val).encode()

            if 'ResponseTopic' in raw_props:
                props.ResponseTopic = raw_props['ResponseTopic']

            if 'ContentType' in raw_props:
                props.ContentType = raw_props['ContentType']

            if 'UserProperty' in raw_props:
                props.UserProperty = raw_props['UserProperty']

        self.log.debug(
            "[mqttasgi][app][publish] - Application {} publishing at {}:{}"
            .format(app_id, pub['topic'], pub.get('qos', 1))
        )

        kwargs = dict(
            topic=pub['topic'],
            payload=pub['payload'],
            qos=pub.get('qos', 1),
            retain=pub.get('retain', False),
        )
        if props is not None:
            kwargs['properties'] = props

        self.client.publish(**kwargs)

    def _handle_reconnect(self, on_connect=False):
        """Override para respeitar transport unix e MQTTv5 no reconnect."""
        import time
        tries = 0
        while tries < self.connect_max_retries or self.connect_max_retries == 0:
            self.log.info("[mqttasgi][connection][reconnect] - Attempting {} reconnect".format(tries))
            try:
                if on_connect is False:
                    self.client.reconnect()
                elif self.transport == 'unix':
                    self.client.connect(self.host)
                elif self.protocol == mqtt.MQTTProtocolVersion.MQTTv5:
                    self.client.connect(self.host, self.port, clean_start=self._clean_session)
                else:
                    self.client.connect(self.host, self.port)
                self.log.warning(
                    "[mqttasgi][connection][reconnect] - Reconnected after {} attempts".format(tries)
                )
                break
            except KeyboardInterrupt as e:
                raise e
            except Exception:
                self.log.debug("[mqttasgi][connection][reconnect] - Exception during reconnect", exc_info=True)
                time.sleep(min(tries, 30))
            tries += 1
        else:
            self._handle_reconnect_failure()

    async def mqtt_receive_loop(self):
        """Override para respeitar transport unix e MQTTv5 no connect inicial.

        Usa asyncio socket callbacks em vez de polling (loop + sleep a 50Hz).
        O event loop acorda apenas quando há dados no socket MQTT — CPU idle ≈ 0.
        loop_misc() a cada 1s cuida de keepalives e ping timeouts.
        """
        if self.username:
            self.client.username_pw_set(self.username, self.password)

        if all([self.cert, self.key, self.ca_cert]):
            self.client.tls_set(ca_certs=self.ca_cert, certfile=self.cert, keyfile=self.key)
        elif self.use_ssl:
            self.client.tls_set()

        loop = asyncio.get_event_loop()

        def _on_socket_open(client, userdata, sock):
            loop.add_reader(sock, client.loop_read)

        def _on_socket_close(client, userdata, sock):
            loop.remove_reader(sock)

        def _on_socket_register_write(client, userdata, sock):
            loop.add_writer(sock, client.loop_write)

        def _on_socket_unregister_write(client, userdata, sock):
            loop.remove_writer(sock)

        self.client.on_socket_open             = _on_socket_open
        self.client.on_socket_close            = _on_socket_close
        self.client.on_socket_register_write   = _on_socket_register_write
        self.client.on_socket_unregister_write = _on_socket_unregister_write

        try:
            if self.transport == 'unix':
                self.client.connect(self.host)
            elif self.protocol == mqtt.MQTTProtocolVersion.MQTTv5:
                self.client.connect(self.host, self.port, clean_start=self._clean_session)
            else:
                self.client.connect(self.host, self.port)
        except Exception as e:
            self.log.error("[mqttasgi][connect] - Initial connection failed: %s", e, exc_info=True)
            try:
                self._handle_reconnect(on_connect=True)
            except Exception:
                await self.shutdown('CONNECTION_ERROR')

        self.log.info("MQTT loop start")
        try:
            while not self.stop:
                self.client.loop_misc()
                await sleep(1)
        except Exception:
            await self.shutdown('Exception in receive loop')