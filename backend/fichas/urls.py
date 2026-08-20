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
    # SUPERVISIÓN (HU-13) — ruta fija, antes de las que llevan <int:pk>
    #
    # Es «la excepción» que esta misma cabecera dejó anunciada en la HU-07: el
    # listado propio del encuestador es la raíz porque el módulo nace para él, y el
    # listado de TODAS las encuestas —el de quien supervisa— va en su subruta.
    # ------------------------------------------------------------------
    path(
        "revision/",
        views.BandejaRevisionView.as_view(),
        name="bandeja_revision",
    ),
    # HU-19: exportar lo que la bandeja está mostrando. Rutas fijas dentro de
    # revision/, por lo mismo que revision/ está antes de <int:pk>/: son
    # excepciones y van antes de lo genérico.
    path(
        "revision/reporte.xlsx",
        views.ExportarReporteExcelView.as_view(),
        name="reporte_excel",
    ),
    path(
        "revision/reporte.pdf",
        views.ExportarReportePDFView.as_view(),
        name="reporte_pdf",
    ),
    # HU-20: la base consolidada completa (una fila por persona), sin
    # filtros. No cuelga de revision/ porque no es "lo que la bandeja está
    # mostrando": es para el administrador, no para quien revisa.
    path(
        "base-consolidada.xlsx",
        views.ExportarBaseExcelView.as_view(),
        name="base_consolidada_excel",
    ),
    path(
        "base-consolidada.csv",
        views.ExportarBaseCSVView.as_view(),
        name="base_consolidada_csv",
    ),
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
    # La ubicación va bajo la VIVIENDA y no bajo la encuesta (HU-11): describe el
    # inmueble, no el trabajo. Dos hogares de la misma casa comparten el punto.
    path(
        "viviendas/<int:pk>/ubicacion/",
        views.CapturarUbicacionView.as_view(),
        name="capturar_ubicacion",
    ),
    # ------------------------------------------------------------------
    # FOTOGRAFÍAS (HU-12)
    #
    # Subir va bajo la VIVIENDA, porque hace falta saber a cuál se adjunta. Ver y
    # quitar van bajo /fotografias/<pk>/ porque la foto ya sabe de qué vivienda es,
    # y repetirlo en la dirección sería un dato más que verificar. Es el mismo
    # criterio con el que la HU-05 anidó «crear» y no «editar».
    #
    # OJO con «ver»: NO es la ruta del archivo, es una vista que comprueba quién
    # pregunta antes de entregarlo. OPSO no sirve MEDIA_ROOT como estáticos en
    # ningún entorno; ver ServirFotografiaView y el comentario de MEDIA_URL.
    # ------------------------------------------------------------------
    path(
        "viviendas/<int:pk>/fotografias/nueva/",
        views.SubirFotografiaView.as_view(),
        name="subir_fotografia",
    ),
    path(
        "fotografias/<int:pk>/ver/",
        views.ServirFotografiaView.as_view(),
        name="ver_fotografia",
    ),
    path(
        "fotografias/<int:pk>/quitar/",
        views.QuitarFotografiaView.as_view(),
        name="quitar_fotografia",
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
    # La revisión de UNA encuesta (HU-13). Va con sufijo bajo su <pk>, como las
    # tres acciones de la HU-10: la pantalla es otra lectura del mismo objeto.
    path(
        "<int:pk>/revisar/",
        views.RevisarEncuestaView.as_view(),
        name="revisar_encuesta",
    ),
    # ------------------------------------------------------------------
    # RESOLVER: APROBAR, ANULAR (HU-14) O DEVOLVER (HU-15)
    #
    # Verbos sobre UNA encuesta, con el mismo patrón que las tres acciones de la
    # HU-10. Exigen `fichas.validar`, no `fichas.ver_todas`: leer el trabajo de
    # todos y firmarlo son capacidades distintas.
    #
    # Las tres salidas de una revisión, y las tres direcciones se leen como lo que
    # hacen: validar cierra bien, anular cierra mal, devolver reabre.
    # ------------------------------------------------------------------
    path(
        "<int:pk>/validar/",
        views.ValidarEncuestaView.as_view(),
        name="validar_encuesta",
    ),
    path(
        "<int:pk>/anular/",
        views.AnularEncuestaView.as_view(),
        name="anular_encuesta",
    ),
    path(
        "<int:pk>/devolver/",
        views.DevolverEncuestaView.as_view(),
        name="devolver_encuesta",
    ),
    path(
        "<int:pk>/borrador/",
        views.GuardarBorradorView.as_view(),
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
