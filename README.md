# mqttasgi - MQTT ASGI Protocol Server for Django
mqttasgi is an ASGI protocol server that implements a complete interface for MQTT for the Django development framework.

# Features
- Publish / Subscribe to any topic
- Multiple workers to handle different topics / subscriptions.
- Full Django ORM support within consumers.
- Full testing consumer to enable TDD.
- Lightweight.

# Instalation
To install mqttasgi
```bash
    pip install mqttasgi
```

# Usage
Mqttasgi provides a cli interface to run the protocol server. 
```bash
    mqttasgi -H localhost -p 1883 my_application.asgi:application
```
Parameters:
| Parameter   | Explanaation      |
|-------------|:-----------------:|
| -H / --host | MQTT broker host |
| -p / --port | MQTT broker port |
| -v / --verbosity | Logging verbosity |
| -U / --username | MQTT Username |
| -P / --password | MQTT Password |
| -i / --id | MQTT Client ID |
| Last argument | ASGI Apllication |

To add your consumer to the routing in your django application:
```python
    application = ProtocolTypeRouter({
      'websocket': AllowedHostsOriginValidator(URLRouter([
          url('.*', WebsocketConsumer)
      ])),
      'mqtt': MqttConsumer,
      ....
    })
```    
Your consumer should inherit from MqttConsumer in mqttasgi.consumers. It implements helper functions such as publish and subscribe. A simple example:
```python
from mqttasgi.consumers import MqttConsumer
class MyMqttConsumer(MqttConsumer):

    async def connect(self):
        await self.subscribe('my/testing/topic', 2)

    async def receive(self, mqtt_message):
        print('Received a message at topic:', mqtt_mesage['topic'])
        print('With payload', mqtt_message['payload'])
        print('And QOS:', mqtt_message['qos'])
        pass

    async def disconnect(self):
        await self.unsubscribe('my/testing/topic')
    
```
