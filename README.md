# mqttasgi - MQTT ASGI Protocol Server
mqttasgi is an ASGI protocol server that implements an interface for MQTT.

# Usage
    mqttasgi -H localhost -p 1883 my_application.asgi:application
In your routing

    application = ProtocolTypeRouter({
      'websocket': AllowedHostsOriginValidator(URLRouter([
          url('.*', WebsocketConsumer)
      ])),
      'mqtt': MqttConsumer,
      ....
    })
    
Your consumer should inherit from MqttConsumer in mqttasgi.consumers. It implements helper functions such as publish and subscribe.
