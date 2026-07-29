"""Rutas de los paneles. Prefijo /dashboard/ (definido en config/urls.py)."""

from django.urls import path

from . import views

app_name = "dashboards"

urlpatterns = [
    # /dashboard/            -> despachador: mira el rol y reenvía
    path("", views.RedirigirSegunRolView.as_view(), name="redirigir"),
    # /dashboard/admin/      -> panel del Administrador
    path("admin/", views.DashboardAdministradorView.as_view(), name="administrador"),
    # /dashboard/supervisor/ -> panel del Supervisor
    path("supervisor/", views.DashboardSupervisorView.as_view(), name="supervisor"),
    # /dashboard/censista/   -> panel del Censista
    path("censista/", views.DashboardCensistaView.as_view(), name="censista"),
]
