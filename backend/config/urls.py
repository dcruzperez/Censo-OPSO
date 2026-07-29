"""Enrutador principal (URLconf raíz) del proyecto OPSO.

Django recibe una URL, la compara contra esta lista de arriba hacia abajo y
entrega el control a la primera vista que coincida. Aquí solo delegamos:
cada app define sus propias rutas, lo que mantiene el proyecto ordenado.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Panel de administración de Django (gestión de usuarios y roles).
    path("admin/", admin.site.urls),
    # Paneles por rol: /dashboard/, /dashboard/admin/, /dashboard/supervisor/...
    path("dashboard/", include("dashboards.urls")),
    # Autenticación y raíz del sitio: /login/, /logout/, /
    # Se incluye al final porque contiene la ruta "" (la más genérica).
    path("", include("usuarios.urls")),
]
