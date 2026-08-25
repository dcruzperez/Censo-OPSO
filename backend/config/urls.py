"""Enrutador principal (URLconf raíz) del proyecto OPSO.

Django recibe una URL, la compara contra esta lista de arriba hacia abajo y
entrega el control a la primera vista que coincida. Aquí solo delegamos:
cada app define sus propias rutas, lo que mantiene el proyecto ordenado.
"""

from django.contrib import admin
from django.urls import include, path

from fichas.views import ServirServiceWorkerView

urlpatterns = [
    # Panel de administración de Django (gestión de usuarios y roles).
    path("admin/", admin.site.urls),
    # Paneles por rol: /dashboard/, /dashboard/admin/, /dashboard/supervisor/...
    path("dashboard/", include("dashboards.urls")),
    # Organización territorial: /operativos/, /operativos/comunas/, ... (HU-05)
    path("operativos/", include("operativos.urls")),
    # Encuestas del encuestador: /encuestas/, /encuestas/<pk>/ (HU-07)
    path("encuestas/", include("fichas.urls")),
    # HU-24: el service worker del asistente offline va en la RAÍZ del
    # dominio y no bajo /static/js/..., porque su "scope" —qué URLs puede
    # vigilar— nunca puede ser más amplio que la ruta desde la que el
    # navegador lo obtuvo. Servido bajo /static/ solo controlaría /static/,
    # que es inútil para vigilar /encuestas/nueva/. Ver ServirServiceWorkerView.
    path("sw.js", ServirServiceWorkerView.as_view()),
    # Autenticación y raíz del sitio: /login/, /logout/, /
    # Se incluye al final porque contiene la ruta "" (la más genérica).
    path("", include("usuarios.urls")),
]
