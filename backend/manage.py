#!/usr/bin/env python
"""Utilidad de línea de comandos de Django para tareas administrativas.

Este archivo es el "control remoto" del proyecto: todo lo que hacemos
(migrar, crear usuarios, levantar el servidor, correr pruebas) pasa por aquí.
"""

import os
import sys


def main():
    # Le decimos a Django dónde están las configuraciones del proyecto.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. ¿Está instalado y el entorno "
            "virtual activado? (pip install -r requirements.txt)"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
