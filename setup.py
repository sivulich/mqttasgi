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
    description_content_type='text/text', 
    description="MQTT ASGI Protocol Server",
    long_description_content_type="text/markdown",
    long_description=open("README.md").read(),
    license="MIT",
    packages=["mqttasgi"],
    include_package_data=True,
    install_requires=[
        "paho-mqtt",
        "django",
        "channels",
        "python-dotenv"
    ],
    entry_points={
        "console_scripts": [
            "mqttasgi=mqttasgi.cli:main",
        ]
    },
    classifiers=[
        'Environment :: Web Environment',
        'License :: OSI Approved :: MIT License',
        'Framework :: Django',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Scientific/Engineering :: Interface Engine/Protocol Translator',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Server',
        'Topic :: Home Automation'
    ]
)
