from asgiref.testing import ApplicationCommunicator


class MqttComunicator(ApplicationCommunicator):

    def __init__(self, application, app_id, instance_type='worker', consumer_parameters=None):

        self.scope = {
            **(consumer_parameters if consumer_parameters is not None else {}),
            "type": "mqtt",
            "app_id": app_id,
            "instance_type": instance_type,
        }
        super().__init__(application, self.scope)

    async def connect(self, timeout=1):
        """
        Trigger the connection code.

        """
        await self.send_input({"type": "mqtt.connect"})
        response = await self.receive_output(timeout)
        return response

    async def publish(self, topic, payload, qos):
        """
        Sends a Mqtt message to the application.
        """
        # Send the right kind of event

        await self.send_input({"type": "mqtt.msg",
                               'mqtt': {
                                    'topic': topic,
                                    'payload': payload,
                                    'qos': qos
                                }})

    async def receive_from(self, timeout=1):
        """
        Receives a data frame from the view. Will fail if the connection
        closes instead. Returns either a bytestring or a unicode string
        depending on what sort of frame you got.
        """
        response = await self.receive_output(timeout)
        return response

    async def disconnect(self, code=1000, timeout=1):
        """
        Closes the socket
        """
        await self.send_input({"type": "mqtt.disconnect"})
        await self.wait(timeout)
    pass