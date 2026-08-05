"""Rutas del módulo de encuestas (HU-07).

app_name crea el espacio de nombres "fichas": las URLs se referencian como
"fichas:mis_encuestas". Mismo criterio que en las apps anteriores — las
plantillas nombran la ruta y no la dirección, así que cambiar /encuestas/ por
otra cosa no obliga a tocar ni una plantilla.

--------------------------------------------------------------------------
POR QUÉ LA DIRECCIÓN ES /encuestas/ Y LA APP SE LLAMA «fichas»
--------------------------------------------------------------------------
Porque nombran cosas distintas y las dos son correctas. La app se llama como el
MÓDULO DE PERMISOS que la gobierna, que la HU-04 bautizó FICHAS (`fichas.crear`,
`fichas.validar`). La dirección se llama como lo que el usuario cree que está
mirando, que son sus encuestas. Forzar que coincidan obligaría a renombrar el
catálogo de permisos —que ya está sembrado por una migración aplicada— o a
enseñarle al encuestador una palabra que no usa.

--------------------------------------------------------------------------
POR QUÉ EL LISTADO PROPIO ES LA RAÍZ Y NO /encuestas/mis-encuestas/
--------------------------------------------------------------------------
La HU-06 puso «mis sectores» en una subruta (/operativos/mis-sectores/) porque en
/operativos/ ya vivía el listado general del administrador: la pantalla propia era
la excepción dentro de un módulo de gestión.

Aquí es al revés. El módulo de encuestas nace para el encuestador, y su listado
propio es la pantalla principal, no un caso particular. Cuando la historia de
supervisión agregue el listado de TODAS las encuestas del operativo, esa irá en su
propia subruta, porque será la excepción.
"""

from django.urls import path

from . import views

app_name = "fichas"

urlpatterns = [
    path("", views.MisEncuestasView.as_view(), name="mis_encuestas"),
    # ------------------------------------------------------------------
    # ENCUESTAS — <int:pk> al final, porque es la más genérica
    # ------------------------------------------------------------------
    path(
        "<int:pk>/",
        views.EncuestaDetailView.as_view(),
        name="encuesta_detalle",
    ),
