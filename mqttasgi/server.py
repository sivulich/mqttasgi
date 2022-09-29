import os
import asyncio
import functools
import logging
import time
import signal
import json
import paho.mqtt.client as mqtt
from .utils import get_application
import sys

_logger = logging.getLogger(__name__)


class Server(object):
    def __init__(self, application, host, port, username=None, password=None,
                 client_id=2407, mqtt_type_pub=None, mqtt_type_usub=None, mqtt_type_sub=None,
                 mqtt_type_msg=None, connect_max_retries=3, logger=None, clean_session=True, cert=None, key=None, ca_cert=None):

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
        }, clean_session=clean_session)
        # self.client.enable_logger(self.log)
        self.username = username
        self.password = password
        # certificates
        self.cert = cert
        self.key = key
        self.ca_cert = ca_cert
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.connect_max_retries = connect_max_retries
        self.client.on_message = lambda client, userdata, message: \
            self._mqtt_receive(-1, message.topic, message.payload, message.qos)

        self.topics_subscription = {}
        self.topic_queues = {}

        self.mqtt_type_pub = mqtt_type_pub or "mqtt.pub"
        self.mqtt_type_sub = mqtt_type_sub or "mqtt.sub"
        self.mqtt_type_usub = mqtt_type_usub or "mqtt.usub"
        self.mqtt_type_msg = mqtt_type_msg or "mqtt.msg"

    def _on_connect(self, client, userdata, flags, rc):
        self.log.info("[mqttasgi][connection][connected] - Connected to {}:{}".format(self.host, self.port))
        for app_id in self.application_data:
            try:
                self.application_data[app_id]['receive'].put_nowait({
                    'type': 'mqtt.connect',
                    'mqtt': {

                    }
                })
            except Exception as e:
                self.log.error("[mqttasgi][mqtt][connect] - Cant add to queue"
                               "of {}".format(app_id))
                self.log.exception(e)

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
                           " to topic:{} adding to queue".format(topic))
            if topic not in self.topic_queues:
                self.topic_queues[topic] = []

            self.topic_queues[topic] += [{
                        'topic': topic,
                        'payload': payload,
                        'qos': qos
                    }]
            return

        for app_id in self.topics_subscription[subscription]['apps']:
            try:
                self.application_data[app_id]['receive'].put_nowait({
                    'type': 'mqtt.msg',
                    'mqtt': {
                        'topic': topic,
                        'payload': payload,
                        'qos': qos
                    }
                })
            except Exception as e:
                self.log.error("[mqttasgi][mqtt][receive] - Cant add to queue"
                               "of {}".format(app_id))
                self.log.exception(e)
        self.log.debug("[mqttasgi][mqtt][receive] - Added message to queue app_ids:{} topic:{}".format(self.topics_subscription[subscription]['apps'], topic))


    async def mqtt_receive_loop(self):

        if self.username:
            self.client.username_pw_set(username=self.username, password=self.password)

        if all([self.cert, self.key, self.ca_cert]):
            self.client.tls_set(
                ca_certs=self.ca_cert,
                certfile=self.cert,
                keyfile=self.key,
            )


        self.client.connect(self.host, self.port)

        self.log.info(f"MQTT loop start")

        while True:
            self.client.loop(0.01)
            await asyncio.sleep(0.01)

    async def mqtt_publish(self, app_id, msg):
        mqqt_publication = msg['mqtt']
        self.log.debug("[mqttasgi][app][publish] - Application {} publishing at {}:{}"
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
                "[mqttasgi][app][subscribe] - Subscription of {} to {}:{} already exists".format(app_id, topic,
                                                                                                      qos))
        self.application_data[app_id]['subscriptions'][topic] = qos

        if qos_diff > 0 and len(status['apps']) > 0:
            self.log.debug(
                "[mqttasgi][app][subscribe] - Subscription to {} must be updated to QOS: {}".format(topic, qos))
            self.client.unsubscribe(topic)
            self.client.subscribe(topic, qos)
            status = (qos, status[1])
        elif len(status['apps']) == 0:
            self.log.debug("[mqttasgi][app][subscribe] - Subscription to {}:{}".format(topic, qos))
            self.client.message_callback_add(topic, lambda client, userdata,
                                                           message: self._mqtt_receive(topic, message.topic,
                                                                                       message.payload,
                                                                                       message.qos))
            self.client.subscribe(topic, qos)
            status['qos'] = qos
        else:
            self.log.debug(
                "[mqttasgi][app][subscribe] - Subscription to {}:{} has {} listeners".format(topic, status['qos'],
                                                                                                  len(status['apps']) + 1))
        status['apps'].add(app_id)
        self.topics_subscription[topic] = status
        flushed_topics = []
        for msg_topic in self.topic_queues:
            if mqtt.topic_matches_sub(topic, msg_topic):
                self.log.info(
                    "[mqttasgi][app][subscribe] - Flushing {} with {} messages"
                        .format(msg_topic, len(self.topic_queues[msg_topic])))
                while len(self.topic_queues[msg_topic]) > 0:
                    msg = self.topic_queues[msg_topic].pop(0)
                    try:
                        self.application_data[app_id]['receive'].put_nowait({
                            'type': 'mqtt.msg',
                            'mqtt': msg
                        })
                    except Exception as e:
                        self.log.error("[mqttasgi][mqtt][receive] - Cant add to queue"
                                       "of {}".format(app_id))
                        self.log.exception(e)
                flushed_topics += [msg_topic]

        for msg_topic in flushed_topics:
            del self.topic_queues[msg_topic]


    async def mqtt_unsubscribe(self, app_id, msg, soft=False):
        mqqt_unsubscritpion = msg['mqtt']
        topic = mqqt_unsubscritpion['topic']
        if topic not in self.topics_subscription:
            self.log.error("[mqttasgi][app][unsubscribe] - Tried to unsubscribe from non existing topic {}".format(topic))
            return
        status = self.topics_subscription[topic]

        if app_id not in self.topics_subscription[topic]['apps']:
            self.log.error(
                "[mqttasgi][app][unsubscribe] - App {} tried to unsubscribe from a topic it's not subsribed to {}"
                    .format(app_id, topic))
            return

        if topic in self.application_data[app_id]['subscriptions']:
            del self.application_data[app_id]['subscriptions'][topic]


        if len(status['apps']) == 1:
            if not soft:
                self.client.unsubscribe(topic)
            self.client.message_callback_remove(topic)
            self.topics_subscription[topic] = {'qos': 0, 'apps': set()}
            self.log.debug("[mqttasgi][app][unsubscribe] - {} Unsubscribed from {}".format('Soft' if soft else '',
                                                                                           topic))
        elif len(status['apps']) > 1:
            self.log.debug(
                "[mqttasgi][app][unsubscribe] - Subscription to {}:{} has {} listeners"
                    .format(topic, status['qos'], len(status['apps']) - 1))

            self.topics_subscription[topic]['apps'].remove(app_id)

    async def mqttasgi_worker_spawn(self, app_id, msg):
        if app_id != 0:
            self.log.error("[mqttasgi][app][worker.spawn] - Application {} tried to create a worker, not allowed!"
                           .format(app_id))
            return
        new_app_id = msg['command']['app_id']
        new_consumer_path = msg['command']['consumer_path']
        new_consumer_params = msg['command']['consumer_params']
        self.create_application(new_app_id, consumer_path=new_consumer_path,
                                      consumer_parameters=new_consumer_params)

        self.application_data[new_app_id]['receive'].put_nowait({
            'type': 'mqtt.connect',
            'mqtt': {

            }
        })
        pass

    async def mqttasgi_worker_kill(self, app_id, msg):
        if app_id != 0:
            self.log.error("[mqttasgi][app][worker.kill] - Application {} tried to kill a worker, not allowed!"
                           .format(app_id))
            return
        new_app_id = msg['command']['app_id']
        await self.delete_application(new_app_id)
        pass

    async def _application_send(self, app_id, msg):
        action_map = {
            self.mqtt_type_pub: self.mqtt_publish,
            self.mqtt_type_sub: self.mqtt_subscribe,
            self.mqtt_type_usub: self.mqtt_unsubscribe,
            'mqttasgi.worker.spawn': self.mqttasgi_worker_spawn,
            'mqttasgi.worker.kill': self.mqttasgi_worker_kill,
        }
        try:
            if app_id not in self.application_data:
                self.log.warning("[mqttasgi][app][send] - Application {} does not exist!"
                               .format(app_id))
            else:
                await action_map[msg['type']](app_id, msg)
        except Exception as e:
            self.log.error("[mqttasgi][app][send] - Exception "
                           "of {}".format(app_id))
            self.log.exception(e)

    async def shutdown(self, signum):
        """Cleanup tasks tied to the service's shutdown."""
        self.log.warning(f"MQTTASGI Received signal {signum}, terminating")
        self.stop=True
        for app_id in self.application_data:
            self.application_data[app_id]["receive"].put_nowait(
                {"type": "mqtt.disconnect"}
            )
        self.log.warning("MQTTASGI Waiting for all applications to close")
        await asyncio.gather(*[self.application_data[app_id]["task"] for app_id in self.application_data])
        all_tasks = asyncio.Task.all_tasks if sys.version_info[1] < 7 else asyncio.all_tasks
        tasks = [t for t in all_tasks() if t is not asyncio.current_task()]
        self.log.info(f"Cancelling {len(tasks)} outstanding tasks")
        [task.cancel() for task in tasks]
        self.loop.stop()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.log.info("Shutdown complete")

    def create_application(self, app_id, instance_type='worker', consumer_path=None, consumer_parameters=None):
        scope = {}
        if consumer_parameters is not None:
            scope = {**consumer_parameters}
        scope = {**scope, **self.base_scope, 'app_id': app_id, 'instance_type': instance_type}
        if app_id in self.application_data:
            self.log.error('[mqttasgi][app][worker.spawn] - Tried to create a fork with same ID,'
                         ' ignoring! Verify your code!')
            return
        if consumer_path is None:
            application = self.application_type
        else:
            application = get_application(consumer_path)
        self.application_data[app_id] = {}
        self.application_data[app_id]['receive'] = asyncio.Queue()
        self.application_data[app_id]['instance'] = application(scope,
                                                                receive=self.application_data[app_id]['receive'].get,
                                                                send=lambda message: self._application_send(app_id, message))
        task = asyncio.ensure_future(
            self.application_data[app_id]['instance'],
            loop=asyncio.get_event_loop()
        )
        self.application_data[app_id]['task'] = task
        self.application_data[app_id]['subscriptions'] = {}

    async def delete_application(self, app_id):
        if app_id not in self.application_data:
            self.log.error('[mqttasgi][app][worker.kill] - Tried to kill an instance that doesnt exist, ignoring! '
                         'Verify your code!')
            return

        self.application_data[app_id]['receive'].put_nowait({
            'type': 'mqtt.disconnect',
            'mqtt': {

            }
        })
        # Apps can decide whether to unsubscribe or not, to mantain a queue of messages in the broker
        for topic in [*self.application_data[app_id]['subscriptions']]:
            await self.mqtt_unsubscribe(app_id, {'mqtt': {'topic': topic}}, soft=True)

        del self.application_data[app_id]
        if len(self.application_data.keys()) == 0:
            self.log.error(
                "[mqttasgi][unsubscribe][kill] - All applications where killed, exiting!"
            )
            await self.shutdown("no-apps")

    def handle_exception(self, loop, context):
        # context["message"] will always be there; but context["exception"] may not
        msg = context.get("exception", context["message"])
        self.log.info(f"Caught exception: {msg}")

    def run(self):
        self.stop = False
        loop = asyncio.get_event_loop()
        self.loop = loop

        try:
            for signame in ('SIGINT', 'SIGTERM'):
                loop.add_signal_handler(
                    getattr(signal, signame),
                    lambda signame=signame: asyncio.create_task(self.shutdown(signame)),
                )
        except NotImplementedError:
            # Running on windows
            pass
        # loop.set_exception_handler(self.handle_exception)
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
