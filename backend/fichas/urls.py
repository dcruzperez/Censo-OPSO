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
    # VIVIENDAS (HU-08) — rutas fijas antes de las que llevan <int:pk>
    #
    # /encuestas/viviendas/nueva/ tiene que declararse antes de
    # /encuestas/<int:pk>/, por la misma razón que la HU-05 puso /comunas/ antes
    # de /<int:pk>/: Django recorre la lista en orden y se queda con la primera
    # que coincide. El conversor «int» nunca haría coincidir la palabra
    # «viviendas», así que hoy funcionaría igual, pero el orden explícito deja
    # claro cuál manda si mañana el conversor cambiara.
    # ------------------------------------------------------------------
    path(
        "viviendas/nueva/",
        views.RegistrarViviendaView.as_view(),
        name="vivienda_registrar",
    ),
    path(
        "viviendas/<int:pk>/",
        views.ViviendaDetalleView.as_view(),
        name="vivienda_detalle",
    ),
    path(
        "viviendas/<int:pk>/editar/",
        views.EditarViviendaView.as_view(),
        name="vivienda_editar",
    ),
    # Agregar un segundo hogar a una vivienda existente. Solo POST (ver la vista).
    path(
        "viviendas/<int:pk>/hogar/nuevo/",
        views.AgregarHogarView.as_view(),
        name="hogar_agregar",
    ),
    # ------------------------------------------------------------------
    # ENCUESTAS — <int:pk> al final, porque es la más genérica
    # ------------------------------------------------------------------
    path(
        "<int:pk>/",
        views.EncuestaDetailView.as_view(),
        name="encuesta_detalle",
    ),
    # El hogar va ANIDADO en su encuesta y no en /hogares/<pk>/, porque una
    # relación uno a uno no necesita identificador propio en la dirección: la
    # encuesta ya identifica sin ambigüedad de qué hogar se habla, y una URL con
    # dos identificadores para el mismo objeto es un dato más que verificar. Es el
    # mismo criterio con que la HU-05 anidó «crear» y no «editar».
    path(
        "<int:pk>/hogar/",
        views.RegistrarHogarView.as_view(),
        name="registrar_hogar",
    ),
    # ------------------------------------------------------------------
    # LAS PERSONAS DEL HOGAR (HU-09)
    #
    # Van anidadas bajo su encuesta, incluso las que actúan sobre UNA persona
    # concreta. Es lo contrario de lo que hizo la HU-05 —donde «editar» no se
    # anidaba porque el sector ya sabía a qué operativo pertenecía— y el motivo
    # es que aquí la encuesta no es un dato redundante: es la que decide si la
    # persona que pide la página tiene derecho a tocar esa fila.
    #
    # Con /integrantes/<id>/editar/ suelto, la vista tendría que remontar la
    # cadena entera (integrante -> hogar -> encuesta -> censista) para comprobar
    # el permiso, y esa comprobación se puede olvidar. Con la encuesta en la URL,
    # el filtro por dueño se aplica ANTES de buscar a la persona y no hay forma de
    # llegar a una fila ajena.
    # ------------------------------------------------------------------
    path(
        "<int:encuesta_pk>/integrantes/",
        views.IntegrantesView.as_view(),
        name="integrantes",
    ),
    path(
        "<int:encuesta_pk>/integrantes/nuevo/",
        views.RegistrarIntegranteView.as_view(),
        name="integrante_nuevo",
    ),
    path(
        "<int:encuesta_pk>/integrantes/<int:pk>/editar/",
        views.EditarIntegranteView.as_view(),
        name="integrante_editar",
    ),
    path(
        "<int:encuesta_pk>/integrantes/<int:pk>/quitar/",
        views.QuitarIntegranteView.as_view(),
        name="integrante_quitar",
    ),
    # ------------------------------------------------------------------
    # EL BORRADOR Y EL CIERRE (HU-10)
    #
    # Las tres son verbos sobre UNA encuesta, así que van bajo su <pk> con un
    # sufijo que dice qué hacen. Mismo criterio que /operativos/<pk>/estado/ en la
    # HU-05: la acción se nombra en la dirección, y el objeto sobre el que actúa la
    # identifica el <pk> que ya está delante.
    # ------------------------------------------------------------------
        name="guardar_borrador",
    ),
    path(
        "<int:pk>/completar/",
        views.CompletarEncuestaView.as_view(),
        name="completar_encuesta",
    ),
    path(
        "<int:pk>/cerrar/",
        views.CerrarSinDatosView.as_view(),
        name="cerrar_encuesta",
    ),
]
