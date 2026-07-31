"""Configuración de la app "operativos"."""

from django.apps import AppConfig


class OperativosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "operativos"
    verbose_name = "Operativos y organización territorial"
