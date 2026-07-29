"""Punto de entrada ASGI: se usa si más adelante OPSO necesita websockets."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
