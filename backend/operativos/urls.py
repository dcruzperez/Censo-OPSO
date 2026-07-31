"""Rutas de la organización territorial (HU-05).

app_name crea el espacio de nombres "operativos": las URLs se referencian como
"operativos:operativo_detalle". Así, si mañana cambia /operativos/ por
/despliegues/, las plantillas y las vistas no se tocan, porque referencian el
NOMBRE y no la dirección.

--------------------------------------------------------------------------
CÓMO ESTÁN ORGANIZADAS LAS DIRECCIONES
--------------------------------------------------------------------------
La URL refleja la JERARQUÍA de los datos, no la de las pantallas:

    /operativos/                              listado
    /operativos/nuevo/                        alta
    /operativos/comunas/                      catálogo de comunas
    /operativos/comunas/nueva/
    /operativos/comunas/5/editar/
    /operativos/5/                            ficha con su territorio
    /operativos/5/editar/
    /operativos/5/estado/                     confirmar cambio de estado
    /operativos/5/sectores/nuevo/             crear sector EN el operativo 5
    /operativos/sectores/9/editar/
    /operativos/sectores/9/zonas/nueva/       crear zona EN el sector 9
    /operativos/zonas/12/editar/

Dos decisiones que conviene poder explicar:

1. CREAR va anidado; EDITAR no. Para crear un sector hace falta saber en qué
   operativo, y ese dato viaja en la dirección: /operativos/5/sectores/nuevo/.
   Para editar el sector 9 no hace falta repetir el operativo, porque el propio
   sector ya sabe a cuál pertenece. Anidarlo igualmente
   (/operativos/5/sectores/9/editar/) permitiría que alguien escribiera un
   operativo que no corresponde y obligaría a validar la coherencia en cada
   vista. Menos datos en la URL es menos que verificar.

2. Las rutas fijas van ANTES de las que llevan <int:pk>. /operativos/comunas/ se
   declara antes de /operativos/<int:pk>/ porque Django recorre la lista en orden
   y se queda con la primera que coincide. El conversor "int" nunca haría
   coincidir la palabra "comunas", así que hoy funcionaría igual, pero el orden
   explícito deja claro cuál manda si mañana el conversor cambiara a <str>.
"""

from django.urls import path

from . import views

app_name = "operativos"

urlpatterns = [
    # ------------------------------------------------------------------
    # OPERATIVOS
    # ------------------------------------------------------------------
    path("", views.OperativoListView.as_view(), name="operativo_lista"),
    path("nuevo/", views.OperativoCreateView.as_view(), name="operativo_crear"),
    # ------------------------------------------------------------------
    # COMUNAS — antes de <int:pk> (ver la nota 2 de la cabecera)
    # ------------------------------------------------------------------
    path("comunas/", views.ComunaListView.as_view(), name="comuna_lista"),
    path("comunas/nueva/", views.ComunaCreateView.as_view(), name="comuna_crear"),
    path(
        "comunas/<int:pk>/editar/",
        views.ComunaUpdateView.as_view(),
        name="comuna_editar",
    ),
    # Una sola clase atiende activar y desactivar; el atributo `activar` fijado
    # aquí decide el sentido. Es la forma de que la validación y la auditoría se
    # escriban una vez para dos operaciones opuestas.
    path(
        "comunas/<int:pk>/desactivar/",
        views.ComunaCambiarEstadoView.as_view(activar=False),
        name="comuna_desactivar",
    ),
    path(
        "comunas/<int:pk>/activar/",
        views.ComunaCambiarEstadoView.as_view(activar=True),
        name="comuna_activar",
    ),
    # ------------------------------------------------------------------
    # SECTORES
    # ------------------------------------------------------------------
    path(
        "sectores/<int:pk>/editar/",
        views.SectorUpdateView.as_view(),
        name="sector_editar",
    ),
    path(
        "sectores/<int:pk>/desactivar/",
        views.SectorCambiarEstadoView.as_view(activar=False),
        name="sector_desactivar",
    ),
    path(
        "sectores/<int:pk>/activar/",
        views.SectorCambiarEstadoView.as_view(activar=True),
        name="sector_activar",
    ),
    path(
        "sectores/<int:sector_pk>/zonas/nueva/",
        views.ZonaCreateView.as_view(),
        name="zona_crear",
    ),
    # ------------------------------------------------------------------
    # ZONAS
    # ------------------------------------------------------------------
    path("zonas/<int:pk>/editar/", views.ZonaUpdateView.as_view(), name="zona_editar"),
    path(
        "zonas/<int:pk>/desactivar/",
        views.ZonaCambiarEstadoView.as_view(activar=False),
        name="zona_desactivar",
    ),
    path(
        "zonas/<int:pk>/activar/",
        views.ZonaCambiarEstadoView.as_view(activar=True),
        name="zona_activar",
    ),
    # ------------------------------------------------------------------
    # FICHA DEL OPERATIVO — al final, porque <int:pk> es la más genérica
    # ------------------------------------------------------------------
    path("<int:pk>/", views.OperativoDetailView.as_view(), name="operativo_detalle"),
    path(
        "<int:pk>/editar/",
        views.OperativoUpdateView.as_view(),
        name="operativo_editar",
    ),
    path(
        "<int:pk>/estado/",
        views.OperativoCambiarEstadoView.as_view(),
        name="operativo_estado",
    ),
    path(
        "<int:operativo_pk>/sectores/nuevo/",
        views.SectorCreateView.as_view(),
        name="sector_crear",
    ),
]
