import os.path
import re
from setuptools import setup


def get_version(package):
    init_py = open(os.path.join(package, '__init__.py')).read()
    return re.search("^__version__ = ['\"]([^'\"]+)['\"]", init_py).group(1)


setup(
    name="mqttasgi",
    version=get_version("mqttasgi"),
    author="Santiago Ivulich",
    author_email="sivulich@itba.edu.ar",
    url="https://github.com/sivulich/mqttasgi",
    description="MQTT ASGI Protocol Server",
    long_description=open("README.md").read(),
    license="MIT",
    packages=["mqttasgi"],
    install_requires=[
        "paho-mqtt",
    ],
    entry_points={
        "console_scripts": [
            "mqttasgi=mqttasgi.cli",
        ]
    },
    classifiers=[
        'Development Status :: 1 - Beta',
        'Environment :: Web Environment',
        'License :: MIT',
        'Framework :: Django',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: MQTT',
    ]
)