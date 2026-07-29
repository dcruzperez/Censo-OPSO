"""Configuración de la app "usuarios"."""

from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "usuarios"
    verbose_name = "Usuarios y control de acceso"

    def ready(self):
        """Se ejecuta una sola vez, cuando Django termina de cargar las apps.

        Es el lugar correcto para conectar las señales: si las conectáramos
        en models.py podrían registrarse dos veces o fallar por importaciones
        circulares.
        """
        from . import signals  # noqa: F401  (importar ya registra las señales)
