import sys
import importlib


def get_application(application_name):
    sys.path.insert(0, ".")
    module_path, object_path = application_name.split(":", 1)
    application = importlib.import_module(module_path)
    for bit in object_path.split("."):
        application = getattr(application, bit)

    if hasattr(application, "as_asgi"):
        return application.as_asgi()
    return application
