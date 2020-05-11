import os
import asyncio
import functools
import logging
import time
import signal
import json
import paho.mqtt.client as mqtt
from asgiref.sync import async_to_sync

_logger = logging.getLogger(__name__)


class Server(object):
    def __init__(self, application, host, port, username=None, password=None,
                 client_id=None, mqtt_type_pub=None, mqtt_type_usub=None, mqtt_type_sub=None,
                 mqtt_type_msg=None, connect_max_retries=3, logger=None):

        self.application_type = application
        self.application_data = {}
        self.base_scope = {
            'type': 'mqtt',
            'version': '2.4',
            'spec_version': '0.1'
        }
        if logger is None:
            self.log = _logger
        else:
            self.log = logger

        self.host = host
        self.port = port
        self.client_id = client_id
        self.client = mqtt.Client(client_id=self.client_id, userdata={
            "server": self,
            "host": self.host,
            "port": self.port,
        })
        self.username = username
        self.password = password
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.connect_max_retries = connect_max_retries
        self.client.on_message = lambda client, userdata, message: \
            self._mqtt_receive(-1, message.topic, message.payload, message.qos)

        self.topics_subscription = {}

        self.mqtt_type_pub = mqtt_type_pub or "mqtt.pub"
        self.mqtt_type_sub = mqtt_type_sub or "mqtt.sub"
        self.mqtt_type_usub = mqtt_type_usub or "mqtt.usub"
        self.mqtt_type_msg = mqtt_type_msg or "mqtt.msg"

    def _on_connect(self, client, userdata, flags, rc):
        self.log.info("[mqttasgi][connection][connected] - Connected to {}:{}".format(self.host, self.port))
        for app_id in self.application_data:
            self.application_data[app_id]['receive'].put_nowait({
                'type': 'mqtt.connect',
                'mqtt': {

                }
            })
        pass

    def _on_disconnect(self, client, userdata, rc):
        self.log.warning("[mqttasgi][connection][disconnected] - Disconnected from {}:{}".format(self.host,self.port))
        if not self.stop:
            if self.connect_max_retries != 0:
                for i in range(self.connect_max_retries):
                    self.log.info("[mqttasgi][connection][reconnect] - Attempting {} reconnect".format(i+1))
                    try:
                        client.reconnect()
                        self.log.warning("[mqttasgi][connection][reconnect] - Reconnected after {} attempts".format(i+1))
                        break
                    except Exception as e:
                        if i < self.connect_max_retries:
                            self.log.info("[mqttasgi][connection][reconnect] - Failed {} sleeping for {} seconds".format(i+1, i+1))
                            time.sleep(i+1)
                            continue
                        else:
                            for app_id in self.application_data:

                                self.application_data[app_id]['receive'].put_nowait({
                                    'type': 'mqtt.disconnect',
                                    'mqtt': {

                                    }
                                })
                            raise
            else:
                exit = False
                tries = 0
                while not exit:
                    try:
                        client.reconnect()
                        self.log.warning("[mqttasgi][connection][reconnect] - Reconnected after {} attempts".format(tries+1))
                        exit = True
                        break
                    except Exception as e:
                        tries += 1
                        time.sleep(tries + 1 if tries<10 else 10)

    def _mqtt_receive(self, subscription, topic, payload, qos):
        if subscription == -1:
            self.log.warning("[mqttasgi][mqtt][receive] - Received message that no app is subscribed"
                           " to topic:{}".format(topic))
            return
        try:
            for app_id in self.topics_subscription[subscription]['apps']:
                self.application_data[app_id]['receive'].put_nowait({
                    'type': 'mqtt.msg',
                    'mqtt': {
                        'topic': topic,
                        'payload': payload,
                        'qos': qos
                    }
                })
            self.log.debug("[mqttasgi][mqtt][receive] - Added message to queue app_ids:{} topic:{}".format(self.topics_subscription[subscription]['apps'], topic))
        except Exception as e:
            self.log.error("[mqttasgi][mqtt][receive] - Cant add to queue"
                         "of {}".format(app_id))
            self.log.exception(e)

    async def mqtt_receive_loop(self):

        if self.username:
            self.client.username_pw_set(username=self.username, password=self.password)

        self.client.connect(self.host, self.port)

        self.log.info(f"MQTT loop start")

        while True:
            self.client.loop(0.01)
            await asyncio.sleep(0.01)

    async def mqtt_publish(self, app_id, msg):
        mqqt_publication = msg['mqtt']
        self.log.debug("[mqttasgi][channels][publish] - Application {} publishing at {}:{}"
                     .format(app_id, mqqt_publication['topic'], mqqt_publication.get('qos', 1)))
        self.client.publish(
            mqqt_publication['topic'],
            mqqt_publication['payload'],
            qos=mqqt_publication.get('qos', 1),
            retain=mqqt_publication.get('retain', False))

    async def mqtt_subscribe(self, app_id, msg):
        mqqt_subscritpion = msg['mqtt']
        topic = mqqt_subscritpion['topic']
        qos = mqqt_subscritpion['qos']
        if topic not in self.topics_subscription:
            self.topics_subscription[topic] = {'qos': -1, 'apps': set()}
        status = self.topics_subscription[topic]
        qos_diff = qos - status['qos']

        if topic in self.application_data[app_id]['subscriptions'] and \
                qos == self.application_data[app_id]['subscriptions'][topic]:

            self.log.warning(
                "[mqttasgi][channels][subscribe] - Subscription of {} to {}:{} already exists".format(app_id, topic,
                                                                                                      qos))
        self.application_data[app_id]['subscriptions'][topic] = qos

        if qos_diff > 0 and len(status['apps']) > 0:
            self.log.debug(
                "[mqttasgi][channels][subscribe] - Subscription to {} must be updated to QOS: {}".format(topic, qos))
            self.client.unsubscribe(topic)
            self.client.subscribe(topic, qos)
            status = (qos, status[1])
        elif len(status['apps']) == 0:
            self.log.debug("[mqttasgi][channels][subscribe] - Subscription to {}:{}".format(topic, qos))
            self.client.message_callback_add(topic, lambda client, userdata,
                                                           message: self._mqtt_receive(topic, message.topic,
                                                                                       message.payload,
                                                                                       message.qos))
            self.client.subscribe(topic, qos)
            status['qos'] = qos
        else:
            self.log.debug(
                "[mqttasgi][channels][subscribe] - Subscription to {}:{} has {} listeners".format(topic, status['qos'],
                                                                                                  len(status['apps']) + 1))
        status['apps'].add(app_id)
        self.topics_subscription[topic] = status

    async def mqtt_unsubscribe(self, app_id, msg):
        mqqt_unsubscritpion = msg['mqtt']
        topic = mqqt_unsubscritpion['topic']
        if topic not in self.topics_subscription:
            self.log.error("[mqttasgi][channels][unsubscribe] - Tried to unsubscribe from non existing topic {}".format(topic))
            return
        status = self.topics_subscription[topic]

        if app_id not in self.topics_subscription[topic]['apps']:
            self.log.error(
                "[mqttasgi][channels][unsubscribe] - App {} tried to unsubscribe from a topic it's not subsribed to {}"
                    .format(app_id, topic))
            return

        if topic in self.application_data[app_id]['subscriptions']:
            del self.application_data[app_id]['subscriptions'][topic]
            if len(self.application_data[app_id]['subscriptions'].keys()) == 0:
                await self.delete_application(app_id)

        if len(status['apps']) == 1:
            self.client.unsubscribe(topic)
            self.client.message_callback_remove(topic)
            self.topics_subscription[topic] = {'qos': 0, 'apps': set()}
            self.log.debug("[mqttasgi][channels][unsubscribe] - Unsubscribed from {}".format(topic))
        elif len(status['apps']) > 1:
            self.log.debug(
                "[mqttasgi][channels][unsubscribe] - Subscription to {}:{} has {} listeners"
                    .format(topic, status['qos'], len(status['apps']) - 1))

            self.topics_subscription[topic]['apps'].remove(app_id)

    async def _application_send(self, app_id, msg):
        action_map = {
            self.mqtt_type_pub: self.mqtt_publish,
            self.mqtt_type_sub: self.mqtt_subscribe,
            self.mqtt_type_usub: self.mqtt_unsubscribe,
        }
        try:
            await action_map[msg['type']](app_id, msg)
        except Exception as e:
            self.log.exception(e)

    def stop_server(self, signum):
        self.log.warning("MQTTASGI Received signal {}, terminating".format(signum))
        # self.log.warning("Leaving consumers a second to exit gracefully")
        for app_id in self.application_data:
            self.application_data[app_id]['receive'].put_nowait({
                'type': 'mqtt.disconnect',
                'mqtt': {

                }
            })
        self.stop = True
        for task in asyncio.Task.all_tasks():
            task.cancel()
        self.loop.stop()

    def create_application(self, app_id, instance_type='worker'):
        scope = {'app_id': app_id, 'instance_type': instance_type, **self.base_scope}
        if app_id in self.application_data:
            self.log.error('[mqttasgi][subscribe][spawn] - Tried to create a fork with same ID,'
                         ' ignoring! Verify your code!')
            return
        self.application_data[app_id] = {}
        self.application_data[app_id]['instance'] = self.application_type(scope)
        self.application_data[app_id]['receive'] = asyncio.Queue()
        task = asyncio.ensure_future(
            self.application_data[app_id]['instance'](receive=self.application_data[app_id]['receive'].get,
                                               send=lambda message: self._application_send(app_id, message)),

        )
        self.application_data[app_id]['task'] = task
        self.application_data[app_id]['subscriptions'] = {}

    async def delete_application(self, app_id):
        if app_id not in self.application_data:
            self.log.error('[mqttasgi][unsubscribe][kill] - Tried to kill an instance that doesnt exist, ignoring! '
                         'Verify your code!')
            return
        self.application_data[app_id]['receive'].put_nowait({
            'type': 'mqtt.disconnect',
            'mqtt': {

            }
        })
        task = self.application_data[app_id]['task']
        task.cancel()
        del self.application_data[app_id]
        if len(self.application_data.keys()) == 0:
            self.log.error('[mqttasgi][unsubscribe][kill] - All applications where killed, exiting!')
            self.stop_server('no-apps')

    def run(self):
        self.stop = False
        loop = asyncio.get_event_loop()
        self.loop = loop

        for signame in ('SIGINT', 'SIGTERM'):
            loop.add_signal_handler(
                getattr(signal, signame),
                functools.partial(self.stop_server, signame)
            )

        self.log.info("MQTTASGI initialized. The complete MQTT ASGI protocol server.")
        self.log.info("MQTTASGI Event loops running forever, press Ctrl+C to interrupt.")
        self.log.info("pid %s: send SIGINT or SIGTERM to exit." % os.getpid())

        self.create_application(0, instance_type='master')

        asyncio.ensure_future(self.mqtt_receive_loop())

        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

        self.client.disconnect()
