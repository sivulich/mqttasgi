import django
from django.conf import settings


def pytest_configure(config):
    """Bootstrap Django before any tests run."""
    if not settings.configured:
        settings.configure(
            SECRET_KEY='test-secret-key-not-for-production',
            INSTALLED_APPS=['channels'],
            DATABASES={},
            CHANNEL_LAYERS={
                'default': {
                    'BACKEND': 'channels.layers.InMemoryChannelLayer',
                }
            },
        )
        django.setup()
