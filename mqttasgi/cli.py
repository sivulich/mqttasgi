import sys
import importlib
import argparse
import logging

from .server import Server

logger = logging.getLogger(__name__)


def get_application(application_name):
    sys.path.insert(0, ".")
    module_path, object_path = application_name.split(":", 1)
    application = importlib.import_module(module_path)
    for bit in object_path.split("."):
        application = getattr(application, bit)

    return application


def main():
    parser = argparse.ArgumentParser(description="MQTT ASGI Protocol Server")
    parser.add_argument("-H", "--host", help="MQTT broker host",
                        default="localhost")
    parser.add_argument("-p", "--port", help="MQTT broker port", type=int,
                        default=1883)
    parser.add_argument("-v", "--verbosity", type=int, default=0,
                        help="Set verbosity")
    parser.add_argument("-U", "--username", help="MQTT username to authorised connection")
    parser.add_argument("-P", "--password", help="MQTT password to authorised connection")
    parser.add_argument("-i", "--id", dest="client_id", help="MQTT Client ID")

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
        logger=logger
    )

    server.run()
