import argparse
import logging
import os
from .server import Server
from .utils import get_application
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="MQTT ASGI Protocol Server")
    parser.add_argument("-H", "--host", help="MQTT broker host",
                        default=os.environ.get("MQTT_HOSTNAME", "localhost"))
    parser.add_argument("-p", "--port", help="MQTT broker port", type=int,
                        default=int(os.environ.get("MQTT_PORT", 1883)))
    parser.add_argument("-c", "--cleansession", help="MQTT Clean Session", type=bool,
                        default=os.environ.get("MQTT_CLEAN", "True").lower() == "true")
    parser.add_argument("-v", "--verbosity", type=int, help="Set verbosity",
                        default=int(os.environ.get("VERBOSITY", 0)))
    parser.add_argument("-U", "--username", help="MQTT username to authorised connection",
                        default=os.environ.get("MQTT_USERNAME", None))
    parser.add_argument("-P", "--password", help="MQTT password to authorised connection",
                        default=os.environ.get("MQTT_PASSWORD", None))
    parser.add_argument("-i", "--id", dest="client_id", help="MQTT Client ID",
                        default=os.environ.get("MQTT_CLIENT_ID", None))
    # add support for certificate authentication (TLS)
    parser.add_argument("-C", "--cert", help="MQTT TLS certificate",
                        default=os.environ.get("TLS_CERT", None))
    parser.add_argument("-K", "--key", help="MQTT TLS key",
                        default=os.environ.get("TLS_KEY", None))
    parser.add_argument("-S", "--cacert", help="MQTT TLS CA certificate",
                        default=os.environ.get("TLS_CA", None))

    parser.add_argument("application",
                        help=("The ASGI application instance to use as "
                              "path.to.module:application"))

    args = parser.parse_args()

    logging.basicConfig(
        level={
            0: logging.WARN,
            1: logging.INFO,
            2: logging.DEBUG,
        }.get(args.verbosity, logging.DEBUG),
        format="%(asctime)-15s %(levelname)-8s %(message)s",
    )

    application = get_application(args.application)
    server = Server(
        application,
        args.host,
        args.port,
        args.username,
        args.password,
        args.client_id,
        logger=logger,
        clean_session=args.cleansession,
        cert=args.cert,
        key=args.key,
        ca_cert=args.cacert,
    )

    server.run()

if __name__ == '__main__':
    main()
