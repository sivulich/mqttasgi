from .server import Server as _BaseServer
import paho.mqtt.client as mqtt
from asyncio import sleep

class Server(_BaseServer):
    def __init__(self, *args, protocol=mqtt.MQTTProtocolVersion.MQTTv311, **kwargs):
        super().__init__(*args, **kwargs)
        self.protocol = protocol

        # recria o client com os parametros corretos
        self._clean_session = None if protocol == mqtt.MQTTProtocolVersion.MQTTv5 else kwargs.get('clean_session', True)
        #self.port = 0 if self.transport == 'unix' else self.port
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            transport=self.transport,   # paho ja aceita 'unix' nativamente
            userdata={"server": self, "host": self.host, "port": self.port},
            clean_session=self._clean_session,
            protocol=protocol,
        )
        self.client.enable_logger(self.log)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = lambda client, userdata, message: \
            self._mqtt_receive(-1, message.topic, message.payload, message.qos)

    async def mqtt_receive_loop(self):
        if self.username:
            self.client.username_pw_set(self.username, self.password)

        if all([self.cert, self.key, self.ca_cert]):
            self.client.tls_set(ca_certs=self.ca_cert, certfile=self.cert, keyfile=self.key)
        elif self.use_ssl:
            self.client.tls_set()

        try:
            if self.protocol == mqtt.MQTTProtocolVersion.MQTTv5:
                # MQTTv5: clean_start no connect, nao no construtor
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
                self.client.loop(timeout=0.01)
                await sleep(0.01)
        except Exception:
            await self.shutdown('Exception in receive loop')

    async def mqtt_subscribe(self, app_id, msg):
        raw_topic = msg['mqtt']['topic']  # $share/workers/status/#
        topic = self._strip_shared(raw_topic)  # status/#  <- usado internamente
        qos = msg['mqtt']['qos']

        if topic not in self.topics_subscription:
            self.topics_subscription[topic] = {'qos': -1, 'apps': set()}
        status = self.topics_subscription[topic]
        qos_diff = qos - status['qos']

        self.application_data[app_id]['subscriptions'][topic] = qos

        if qos_diff > 0 and len(status['apps']) > 0:
            self.client.unsubscribe(raw_topic)
            self.client.subscribe(raw_topic, qos)  # paho recebe o original
            status['qos'] = qos
        elif len(status['apps']) == 0:
            # callback registrado com o tópico real — é o que o paho entrega
            self.client.message_callback_add(
                topic,
                lambda client, userdata, message: self._mqtt_receive(
                    topic, message.topic, message.payload, message.qos
                )
            )
            self.client.subscribe(raw_topic, qos)  # paho recebe o original
            status['qos'] = qos

        status['apps'].add(app_id)
        self.topics_subscription[topic] = status

        # flush de mensagens enfileiradas antes da subscription
        flushed_topics = []
        for msg_topic in self.topic_queues:
            if mqtt.topic_matches_sub(topic, msg_topic):
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

    def _strip_shared(self, topic: str) -> str:
        if topic.startswith('$share/'):
            parts = topic.split('/', 2)
            if len(parts) == 3:
                stripped = parts[2]
                #print(f'[STRIP] {topic} -> {stripped}')
                return stripped
        return topic