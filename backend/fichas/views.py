"""Vistas del módulo de encuestas (HU-07 a HU-10).

Catorce pantallas. Las tres primeras CONSULTAN y las demás ESCRIBEN:

    /encuestas/                              mis encuestas y su estado   (HU-07)
    /encuestas/<pk>/                         la ficha de una encuesta    (HU-07)
    /encuestas/viviendas/<pk>/               la vivienda y sus hogares   (HU-08)

    /encuestas/viviendas/nueva/              registrar una vivienda      (HU-08)
    /encuestas/viviendas/<pk>/editar/        corregir o completar        (HU-08)
    /encuestas/<pk>/hogar/                   registrar el grupo familiar (HU-08)
    /encuestas/viviendas/<pk>/hogar/nuevo/   agregar un segundo hogar    (HU-08)

    /encuestas/<pk>/integrantes/                    las personas del hogar (HU-09)
    /encuestas/<pk>/integrantes/nuevo/              agregar una persona    (HU-09)
    /encuestas/<pk>/integrantes/<id>/editar/        corregir sus datos     (HU-09)
    /encuestas/<pk>/integrantes/<id>/quitar/        quitarla del hogar     (HU-09)

    /encuestas/<pk>/borrador/                 guardar por dónde iba        (HU-10)
    /encuestas/<pk>/completar/                darla por terminada          (HU-10)
    /encuestas/<pk>/cerrar/                   cerrarla sin poder levantar  (HU-10)

CONTROL DE ACCESO — SÉPTIMA HISTORIA SEGUIDA SIN AGREGAR PERMISOS

    fichas.ver_propias -> ver las encuestas de las que uno es responsable
    fichas.ver_todas   -> ver también las de otras personas
    fichas.crear       -> registrar viviendas, hogares y personas  (HU-08, HU-09)
    fichas.editar      -> corregir lo registrado, cerrar y terminar (HU-08 a HU-10)

Los cuatro los sembró la migración 0005 de la HU-04. El reparto inicial le dio al
rol Censista `ver_propias`, `crear` y `editar`, y al Supervisor `ver_propias`,
`ver_todas` y `validar` —pero NI `crear` NI `editar`—. Es decir: la separación
entre quien levanta la información y quien la valida, que la HU-03 estableció como
principio, la aplica hoy el catálogo de permisos sin que ninguna vista tenga que
comprobarla a mano. Estas cuatro historias no conceden nada nuevo a nadie.

--------------------------------------------------------------------------
EL CICLO DE VIDA, YA COMPLETO (HU-10)
--------------------------------------------------------------------------
La HU-07 definió los siete estados y ninguna pantalla producía más que BORRADOR.
Con la HU-10 el camino del encuestador está entero:

    PENDIENTE ──registra algo──> BORRADOR ──completar──> COMPLETADA ──> (supervisor)
        │                            │
        └────── cerrar ──────────────┴──> NO_UBICADA / RECHAZADA

Lo que sigue faltando es la parte del SUPERVISOR: VALIDADA y OBSERVADA, que
produce el permiso `fichas.validar` en su propia historia. El encuestador no puede
reabrir lo que ya envió, y eso es deliberado: ver CompletarEncuestaView.

--------------------------------------------------------------------------
ESTA PANTALLA SÍ EXIGE PERMISO, Y «MIS SECTORES» NO. ¿NO ES CONTRADICTORIO?
--------------------------------------------------------------------------
No, y la diferencia ya está escrita en el proyecto. MisSectoresView (HU-06)
argumentó por qué no exigía permiso, y en esa misma explicación dejó dicho cuál
sería el caso contrario:

    «Se evaluó agregar un permiso "operativos.ver_propios" por simetría con
    "fichas.ver_propias", que sí existe. La diferencia es que aquel gobierna una
    FUNCIONALIDAD (el módulo de fichas, que un rol puede no tener en absoluto),
    mientras que esto es la pantalla que le dice a una persona cuál es su trabajo.»

Esta es justamente esa funcionalidad. Un rol puede no tener nada que ver con el
levantamiento de información —un coordinador, un digitador, un perfil de consulta
para la municipalidad— y para esos roles el módulo de fichas no debe existir. Ver
el territorio que a uno le asignaron, en cambio, no se le puede quitar a nadie sin
inutilizarle la cuenta.

Dicho de otro modo: `operativos.ver_propios` no existe porque no habría ningún
motivo operativo para revocarlo; `fichas.ver_propias` existe porque sí lo hay.
"""

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Case, Count, F, IntegerField, Q, Value, When
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import DetailView, ListView

from usuarios.mixins import PermisoRequeridoMixin

from .forms import (
    AnularEncuestaForm,
    BorradorForm,
    CerrarSinDatosForm,
    DevolverEncuestaForm,
    FiltroMisEncuestasForm,
    FiltroRevisionForm,
    FotografiaForm,
    GrupoFamiliarForm,
    IntegranteForm,
    UbicacionForm,
    ValidarEncuestaForm,
    ViviendaForm,
    zonas_disponibles,
)
from .models import (
    ESTADOS_ABIERTOS,
    ESTADOS_CERRADOS,
    ESTADOS_RESUELTOS,
    ESTADOS_SIN_LEVANTAR,
    Encuesta,
    EstadoEncuesta,
    Fotografia,
    Integrante,
    Parentesco,
    Vivienda,
)

# --------------------------------------------------------------------------
# EL ORDEN DE LA JORNADA
#
# La pantalla NO se ordena por fecha ni alfabéticamente: se ordena por URGENCIA,
# porque su propósito —«para organizar mi trabajo»— es responder qué hago primero.
#
# El criterio, de arriba abajo:
#
#   1. OBSERVADA   el supervisor la devolvió: hay trabajo rehecho y alguien
#                  esperando. Es lo único que bloquea a otra persona.
#   2. BORRADOR    está a medias. Terminar lo empezado cuesta menos que empezar
#                  algo nuevo, y una visita ya gastada que no se cierra se pierde.
#   3. PENDIENTE   el trabajo normal del día.
#   4. COMPLETADA  enviada, esperando revisión. Se muestra para saber qué se hizo,
#                  pero ya no hay nada que hacer con ella.
#   5. el resto    cerradas: validadas, no ubicadas y rechazadas.
#
# Se resuelve con un CASE de SQL y no ordenando en Python porque el listado está
# PAGINADO: ordenar en memoria solo ordenaría la página que ya trajo la base de
# datos, y la primera página dejaría de ser la más urgente para pasar a ser «las 20
# primeras por casualidad, ordenadas entre sí».
# --------------------------------------------------------------------------
ORDEN_POR_URGENCIA = Case(
    When(estado=EstadoEncuesta.OBSERVADA, then=Value(0)),
    When(estado=EstadoEncuesta.BORRADOR, then=Value(1)),
    When(estado=EstadoEncuesta.PENDIENTE, then=Value(2)),
    When(estado=EstadoEncuesta.COMPLETADA, then=Value(3)),
    default=Value(4),
    output_field=IntegerField(),
)


class MisEncuestasView(PermisoRequeridoMixin, ListView):
    """Las encuestas de quien entró, ordenadas por lo que hay que hacer primero.

    URL: /encuestas/

    ----------------------------------------------------------------------
    QUÉ PROTEGE ESTA VISTA
    ----------------------------------------------------------------------
    El permiso es la puerta del módulo; el filtro por `self.request.user` es lo que
    hace que la pantalla sea propia. Ese filtro NO es parametrizable: no hay ningún
    <pk> en la URL ni ningún campo del formulario que apunte a otra persona, así
    que no existe forma de pedir «las encuestas de fulano».

    Es la misma construcción de MisSectoresView y por la misma razón: el control de
    acceso más fiable no es el que comprueba bien la petición, es el que hace que
    la petición peligrosa no se pueda ni formular.

    Nótese que un supervisor con `fichas.ver_todas` que entre aquí verá SUS
    encuestas —probablemente ninguna—, no las de todos. Esta pantalla es «lo mío»
    por definición, y el listado general del operativo es otra historia con otra
    pantalla. Confundirlas haría que el mismo botón mostrara cosas distintas según
    quién lo pulsa, que es la clase de sorpresa que un sistema no debe dar.
    """

    permisos_requeridos = ("fichas.ver_propias",)
    mensaje_sin_permiso = "No tienes permiso para consultar el módulo de encuestas."

    model = Encuesta
    template_name = "fichas/mis_encuestas.html"
    context_object_name = "encuestas"
    paginate_by = 20

    def encuestas_propias(self):
        """Todas las encuestas de la persona que entró, sin filtros de pantalla.

        Es el punto de partida único de la vista: de aquí salen tanto el listado
        como los contadores. Tenerlo en un solo método es lo que garantiza que el
        filtro por usuario se aplique siempre, incluso si mañana se agrega otra
        consulta a la pantalla.
        """
        return Encuesta.objects.filter(censista=self.request.user)

    def get_queryset(self):
        """El listado: encuestas propias, filtradas, ordenadas por urgencia.

        select_related sube los cuatro niveles de la jerarquía territorial de una
        sola vez (zona -> sector -> comuna y sector -> operativo). Sin él, cada una
        de las 20 filas de la página pediría su zona, su sector, su comuna y su
        operativo por separado: 80 consultas para dibujar una tabla. Es el mismo
        problema N+1 que la HU-06 documentó en su panel, y la misma solución.
        """
        consulta = self.encuestas_propias().select_related(
            "vivienda",
            "vivienda__zona",
            "vivienda__zona__sector",
            "vivienda__zona__sector__comuna",
            "vivienda__zona__sector__operativo",
        )

        self.filtro = FiltroMisEncuestasForm(
            self.request.GET or None, censista=self.request.user
        )

        # Un formulario de filtros inválido no es un error del que haya que
        # informar: significa que llegó una URL manipulada o antigua. Se ignora lo
        # que no se entiende y se muestra la lista completa, que es la respuesta
        # menos sorprendente.
        if self.filtro.is_valid():
            texto = self.filtro.cleaned_data.get("q")
            estado = self.filtro.cleaned_data.get("estado")
            sector = self.filtro.cleaned_data.get("sector")
            historicas = self.filtro.cleaned_data.get("historicas")

            if texto:
                consulta = consulta.filter(
                    Q(vivienda__direccion__icontains=texto)
                    | Q(vivienda__referencia__icontains=texto)
                )

            if estado == FiltroMisEncuestasForm.GRUPO_ABIERTAS:
                consulta = consulta.filter(estado__in=ESTADOS_ABIERTOS)
            elif estado == FiltroMisEncuestasForm.GRUPO_CERRADAS:
                consulta = consulta.filter(estado__in=ESTADOS_CERRADOS)
            elif estado:
                consulta = consulta.filter(estado=estado)

            if sector:
                consulta = consulta.filter(vivienda__zona__sector=sector)

            if not historicas:
                consulta = self.solo_trabajo_vivo(consulta)
        else:
            consulta = self.solo_trabajo_vivo(consulta)

        return consulta.annotate(urgencia=ORDEN_POR_URGENCIA).order_by(
            "urgencia",
            "vivienda__zona__sector__nombre",
            "vivienda__zona__nombre",
            "vivienda__direccion",
        )

    @staticmethod
    def solo_trabajo_vivo(consulta):
        """Descarta las encuestas de operativos ya cerrados.

        Es el comportamiento POR DEFECTO, y la casilla «incluir operativos
        cerrados» del filtro es lo que lo desactiva. Se decide así, y no mostrando
        todo desde el principio, porque un operativo cerrado no es trabajo: es
        historia. Mezclarlo obligaría al encuestador a distinguir a ojo, leyendo
        fechas, qué de lo que ve le toca hacer hoy.

        Es la misma separación que hace MisSectoresView entre sectores vigentes e
        históricos, resuelta aquí con un filtro en vez de con dos listas porque
        este listado está paginado y una segunda lista completa al pie no cabría.
        """
        from operativos.models import EstadoOperativo

        return consulta.exclude(
            vivienda__zona__sector__operativo__estado=EstadoOperativo.CERRADO
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Mis encuestas"
        contexto["filtro"] = self.filtro

        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        contexto["parametros"] = parametros.urlencode()

        vivas = self.solo_trabajo_vivo(self.encuestas_propias())

        contexto["resumen"] = self.resumen(vivas)
        contexto["avance_por_zona"] = self.avance_por_zona(vivas)
        contexto["hay_encuestas"] = self.encuestas_propias().exists()
        return contexto

    def resumen(self, consulta):
        """Los contadores del encabezado, en UNA sola consulta.

        Dos decisiones que conviene poder explicar:

        1. SE CUENTAN LAS ENCUESTAS DEL TRABAJO VIVO, NO LAS DE LA PÁGINA NI LAS
           DEL FILTRO. Un contador que cambia al filtrar no responde «¿cuánto me
           queda?», responde «¿cuánto me queda de lo que estoy mirando?», que ya se
           ve en la lista. Es el mismo criterio con que el panel de la HU-06
           mantiene sus contadores globales al pasar de página.

        2. SON SIETE RECUENTOS Y UNA SOLA CONSULTA, gracias al argumento `filter`
           de Count, que PostgreSQL resuelve con FILTER (WHERE ...) en la misma
           pasada. Siete llamadas a .count() serían siete viajes a la base de datos
           para dibujar una fila de tarjetas.
        """
        resumen = consulta.aggregate(
            total=Count("id"),
            por_trabajar=Count("id", filter=Q(estado__in=ESTADOS_ABIERTOS)),
            pendientes=Count("id", filter=Q(estado=EstadoEncuesta.PENDIENTE)),
            borradores=Count("id", filter=Q(estado=EstadoEncuesta.BORRADOR)),
            observadas=Count("id", filter=Q(estado=EstadoEncuesta.OBSERVADA)),
            completadas=Count("id", filter=Q(estado=EstadoEncuesta.COMPLETADA)),
            validadas=Count("id", filter=Q(estado=EstadoEncuesta.VALIDADA)),
            cerradas=Count("id", filter=Q(estado__in=ESTADOS_CERRADOS)),
            # HU-10: visitas anotadas cuya fecha ya llegó o pasó. Es el contador que
            # evita el olvido silencioso de un borrador con «volver el jueves».
            #
            # Se calcula en la misma consulta agregada y no recorriendo las
            # encuestas con `visita_pendiente_vencida`, que haría una comprobación
            # por fila en Python. La propiedad del modelo sigue existiendo para una
            # encuesta suelta; aquí interesa el recuento.
            visitas_vencidas=Count(
                "id",
                filter=Q(
                    estado__in=ESTADOS_ABIERTOS,
                    proxima_visita__lte=timezone.localdate(),
                ),
            ),
        )

        # El avance en porcentaje, calculado en Python porque es aritmética sobre
        # dos números que ya están en memoria: pedírselo a la base de datos sería
        # un viaje más para dividir.
        total = resumen["total"]
        resumen["avance"] = round(resumen["cerradas"] * 100 / total) if total else 0
        return resumen

    def avance_por_zona(self, consulta):
        """Cuántas encuestas quedan por zona, para decidir dónde ir hoy.

        Es la traducción al terreno del contador general: saber que quedan 37 no
        dice a qué calle ir; saber que la zona 1 está terminada y la zona 3 tiene 22
        pendientes, sí.

        Se resuelve con UNA consulta agrupada (values + annotate) en vez de recorrer
        las zonas en Python, por la misma razón que `carga_por_censista` en la
        HU-06: agrupar es trabajo de PostgreSQL y su coste no crece con el número de
        zonas que tenga la persona.
        """
        return list(
            consulta.values(
                "vivienda__zona__id",
                "vivienda__zona__nombre",
                "vivienda__zona__sector__nombre",
                "vivienda__zona__sector__comuna__nombre",
            )
            .annotate(
                total=Count("id"),
                por_trabajar=Count("id", filter=Q(estado__in=ESTADOS_ABIERTOS)),
            )
            .order_by(
                "-por_trabajar",
                "vivienda__zona__sector__nombre",
                "vivienda__zona__nombre",
            )
        )


class EncuestaDetailView(PermisoRequeridoMixin, DetailView):
    """La ficha de una encuesta: dónde es, en qué estado está y qué se sabe de ella.

    URL: /encuestas/<pk>/

    ----------------------------------------------------------------------
    DOS PERMISOS, Y BASTA CON UNO
    ----------------------------------------------------------------------
    `exigir_todos` queda en False (el valor por defecto), así que entra quien tenga
    `fichas.ver_propias` O `fichas.ver_todas`. El permiso decide si puede usar el
    módulo; QUÉ encuesta puede abrir se decide abajo, fila por fila.

    ----------------------------------------------------------------------
    LA SEGURIDAD POR OBJETO: POR QUÉ 404 Y NO 403
    ----------------------------------------------------------------------
    Un encuestador que pida la encuesta de otra persona recibe un 404, no un «no
    tienes permiso». No es un descuido: un 403 CONFIRMA QUE ESA FICHA EXISTE. Con
    un identificador que se puede probar en secuencia (/encuestas/1/, /2/, /3/),
    esa diferencia permite averiguar cuántas encuestas tiene el operativo y en qué
    rango de identificadores están, sin ver ni una.

    Se implementa restringiendo el QUERYSET y no comprobando después del
    get_object(), que es la diferencia entre que la regla se aplique siempre y que
    se aplique mientras nadie olvide llamarla. Si mañana esta vista gana un método
    POST, seguirá operando solo sobre filas que el usuario puede ver.
    """

    permisos_requeridos = ("fichas.ver_propias", "fichas.ver_todas")
    mensaje_sin_permiso = "No tienes permiso para consultar el módulo de encuestas."

    model = Encuesta
    template_name = "fichas/encuesta_detalle.html"
    context_object_name = "encuesta"

    def get_queryset(self):
        consulta = Encuesta.objects.select_related(
            "vivienda",
            "vivienda__zona",
            "vivienda__zona__sector",
            "vivienda__zona__sector__comuna",
            "vivienda__zona__sector__comuna__region",
            "vivienda__zona__sector__operativo",
            "censista",
            "asignada_por",
        )

        # Quien puede ver las fichas de todos —el supervisor, el administrador—
        # abre cualquiera. El resto, solo las suyas.
        if self.request.user.tiene_permiso("fichas.ver_todas"):
            return consulta

        return consulta.filter(censista=self.request.user)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        encuesta = self.object

        contexto["titulo_pagina"] = encuesta.direccion
        contexto["es_propia"] = encuesta.censista_id == self.request.user.pk

        # Los otros hogares de la MISMA vivienda.
        #
        # En la HU-07 esto se buscaba comparando direcciones, porque la dirección
        # vivía en la encuesta. Desde la HU-08 la pregunta es directa —los hermanos
        # de la misma clave foránea— y además significa lo correcto: son hogares de
        # la misma casa, no filas que casualmente escribieron la misma calle.
        contexto["otros_hogares"] = (
            encuesta.vivienda.encuestas.exclude(pk=encuesta.pk)
            .select_related("censista")
            .order_by("id")
        )

        # Si la vivienda viene del padrón de la HU-07, sus características están en
        # blanco. Se avisa con el enlace para completarlas, en vez de mostrar cinco
        # guiones sin explicación.
        contexto["puede_registrar"], contexto["motivo_bloqueo"] = (
            encuesta.puede_registrarse()
        )
        contexto["puede_editar_datos"] = (
            contexto["es_propia"]
            and contexto["puede_registrar"]
            and self.request.user.tiene_algun_permiso("fichas.crear", "fichas.editar")
        )
        return contexto


