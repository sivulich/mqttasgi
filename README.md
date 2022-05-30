# mqttasgi - MQTT ASGI Protocol Server for Django
mqttasgi is an ASGI protocol server that implements a complete interface for MQTT for the Django development framework. Built following [daphne](https://github.com/django/daphne) protocol server.

# Features
- Publish / Subscribe to any topic
- Multiple workers to handle different topics / subscriptions.
- Full Django ORM support within consumers.
- Full testing consumer to enable TDD.
- Lightweight.
- Django 3.x, 4.x / Channels 3.x support

# Instalation
To install mqttasgi for Django 3.x, 4.x
```bash
pip install mqttasgi
```

**IMPORTANT NOTE:** If legacy support for Django 2.x is required install latest 0.x mqttasgi.

# Usage
Mqttasgi provides a cli interface to run the protocol server. 
```bash
mqttasgi -H localhost -p 1883 my_application.asgi:application
```
Parameters:
| Parameter   | Explanation      |
|-------------|:-----------------:|
| -H / --host | MQTT broker host |
| -p / --port | MQTT broker port |
| -c / --cleansession | MQTT Clean Session |
| -v / --verbosity | Logging verbosity |
| -U / --username | MQTT Username |
| -P / --password | MQTT Password |
| -i / --id | MQTT Client ID |
| Last argument | ASGI Apllication |

To add your consumer to the `asgi.py` file in your django application:
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
Your consumer should inherit from MqttConsumer in mqttasgi.consumers. It implements helper functions such as publish and subscribe. A simple example:
```python
from mqttasgi.consumers import MqttConsumer
class MyMqttConsumer(MqttConsumer):

    async def connect(self):
        await self.subscribe('my/testing/topic', 2)

    async def receive(self, mqtt_message):
        print('Received a message at topic:', mqtt_message['topic'])
        print('With payload', mqtt_message['payload'])
        print('And QOS:', mqtt_message['qos'])
        pass

    async def disconnect(self):
        await self.unsubscribe('my/testing/topic')
    
```

# Supporters

## MAPER - IIOT Asset Monitoring - [Webpage](https://home.mapertech.com/en/)

![Maper Logo](https://media-exp1.licdn.com/dms/image/C4D0BAQEi2zH7bSXq8A/company-logo_200_200/0/1529507408740?e=2147483647&v=beta&t=XVIxvlp41JE8_YnwwDNcGlnu7VVanxPGICNoGboHyTY)

Predict failures before they happen.

Real time health monitoring to avoid unexpected downtimes and organize maintenance in industrial plants.

Combining IoT Technology and Artificial Intelligence, we deliver a complete view of your assets like never before. 

With real time health diagnostics you will increase the reliability of the whole production process, benefitting both the company and it's staff.
