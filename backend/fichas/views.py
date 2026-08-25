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

import json
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Case, Count, F, IntegerField, Q, Value, When
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
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
    GrupoFamiliar,
    Integrante,
    MaterialidadMuros,
    NivelEducacional,
    OrigenAgua,
    Parentesco,
    PuebloOriginario,
    Sexo,
    SistemaSanitario,
    SituacionOcupacional,
    TenenciaVivienda,
    TipoVivienda,
    Vivienda,
)
from .reportes import (
    construir_base_csv,
    construir_base_excel,
    construir_reporte_excel,
    construir_reporte_pdf,
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


# ==========================================================================
# HU-08 — REGISTRAR LA VIVIENDA Y SU GRUPO FAMILIAR
# ==========================================================================


class RegistroEnTerrenoMixin(PermisoRequeridoMixin):
    """Puerta de las pantallas que ESCRIBEN información del censo.

    `fichas.crear` y `fichas.editar` los sembró la HU-04 y el reparto inicial se
    los dio al rol Censista y a nadie más —ni siquiera al Supervisor, que valida
    pero no levanta—. Esa separación de funciones venía de la HU-03 y aquí se
    cumple sola: el supervisor no puede registrar fichas porque no tiene el
    permiso, no porque una vista lo compruebe a mano.

    Basta con uno de los dos: quien puede crear una ficha puede corregir lo que
    acaba de escribir, y exigir los dos obligaría a conceder siempre ambos.
    """

    permisos_requeridos = ("fichas.crear", "fichas.editar")
    mensaje_sin_permiso = (
        "No tienes permiso para registrar información de terreno en OPSO."
    )


def _catalogos_offline():
    """Los TextChoices que usan los formularios de captura, listos para JSON.

    Se leen de los mismos enums que ya usan `ViviendaForm`/`GrupoFamiliarForm`/
    `IntegranteForm` — no se copian a mano — para que un valor agregado a un
    catálogo aparezca aquí solo, sin necesidad de acordarse de actualizar esta
    función.
    """
    return {
        "tipo": list(TipoVivienda.choices),
        "tenencia": list(TenenciaVivienda.choices),
        "materialidad_muros": list(MaterialidadMuros.choices),
        "origen_agua": list(OrigenAgua.choices),
        "sistema_sanitario": list(SistemaSanitario.choices),
        "parentesco": list(Parentesco.choices),
        "sexo": list(Sexo.choices),
        "nivel_educacional": list(NivelEducacional.choices),
        "situacion_ocupacional": list(SituacionOcupacional.choices),
        "pueblo_originario": list(PuebloOriginario.choices),
    }


def _zonas_offline(censista):
    """Las zonas asignadas a esta persona, con la misma etiqueta que CampoZona."""
    return [
        {
            "id": zona.pk,
            "etiqueta": f"{zona.nombre} · {zona.sector.nombre} · {zona.sector.comuna.nombre}",
        }
        for zona in zonas_disponibles(censista)
    ]


class EncuestaOfflineView(RegistroEnTerrenoMixin, View):
    """El asistente de captura de una encuesta nueva, pensado para funcionar sin
    conexión (HU-24): vivienda, hogar, integrantes y ubicación en una sola
    pantalla, sin recargar y sin tocar el servidor hasta que se sincroniza.

    URL: /encuestas/nueva/

    ----------------------------------------------------------------------
    POR QUÉ REEMPLAZA A LO QUE ANTES ERA RegistrarViviendaView
    ----------------------------------------------------------------------
    Hasta la HU-23, registrar una vivienda nueva era un POST real que devolvía un
    `pk` real, y la pantalla del hogar necesitaba ese `pk` para poder existir. Sin
    conexión eso es, literalmente, imposible: no hay servidor que devuelva nada.

    Esta vista ya no procesa un formulario: SIRVE el asistente (plantilla + JS de
    `static/js/encuesta_offline.js`) que hace vivienda, hogar, integrantes y
    ubicación enteros en el navegador, guardando cada paso en IndexedDB. El único
    contacto con el servidor ocurre al pulsar «Sincronizar», que es
    `SincronizarEncuestaOfflineView`. Es la única forma de crear una encuesta
    nueva, con o sin conexión: no se mantienen dos pantallas para lo mismo.

    Sigue exigiendo el mismo permiso que antes (`RegistroEnTerrenoMixin`): quien
    puede registrar una vivienda es exactamente la misma persona, tenga o no
    señal en ese momento.
    """

    template_name = "fichas/encuesta_offline.html"

    def hay_donde_registrar(self):
        """¿Tiene esta persona alguna zona donde registrar? Si no, no hay pantalla.

        Un asistente cuyo primer paso no tiene ninguna zona que ofrecer no sirve
        ni siquiera offline, así que se comprueba aquí, con conexión, antes de
        entregarlo.
        """
        return zonas_disponibles(self.request.user).exists()

    def get(self, request, *args, **kwargs):
        if not self.hay_donde_registrar():
            return render(
                request,
                "fichas/sin_territorio.html",
                {"titulo_pagina": "Registrar una vivienda"},
            )

        return render(request, self.template_name, self.contexto())

    def contexto(self):
        return {
            "titulo_pagina": "Nueva encuesta",
            "datos_iniciales": {
                "zonas": _zonas_offline(self.request.user),
                "catalogos": _catalogos_offline(),
                "limites": {
                    "latitud_minima": str(Vivienda.LATITUD_MINIMA),
                    "latitud_maxima": str(Vivienda.LATITUD_MAXIMA),
                    "longitud_minima": str(Vivienda.LONGITUD_MINIMA),
                    "longitud_maxima": str(Vivienda.LONGITUD_MAXIMA),
                    "edad_escolaridad": Integrante.EDAD_ESCOLARIDAD,
                    "edad_ocupacion": Integrante.EDAD_OCUPACION,
                    "ingreso_maximo": GrupoFamiliarForm.INGRESO_MAXIMO,
                    "motivo_cierre_minimo": CerrarSinDatosForm.MOTIVO_MINIMO,
                    "precision_aceptable": Vivienda.PRECISION_ACEPTABLE,
                },
                "urls": {
                    "sincronizar": reverse("fichas:sincronizar_encuesta_offline"),
                    "mis_encuestas": reverse("fichas:mis_encuestas"),
                },
            },
        }


def _a_texto_de_formulario(datos, campos_booleanos_select=(), campos_casilla=()):
    """Traduce un dict JSON (bool/número/texto nativos) al formato de cadenas que
    esperan los widgets de Django, sin obligar al JavaScript del asistente a
    conocer esa diferencia.

    Django distingue dos convenciones de cadena para "verdadero"/"falso" según el
    widget, y son distintas a propósito de Django, no un capricho de este
    proyecto:

      - Un `<select>` con opciones `(True, "Sí"), (False, "No")` (como
        `tiene_electricidad`) renderiza y espera literalmente "True"/"False".
      - Un `CheckboxInput` (como `confirmar_duplicado` o `tiene_discapacidad`)
        espera "true"/"false" en minúscula, o directamente la ausencia de la
        clave para "no marcado".

    Centralizar la traducción aquí, en Python, es lo que evita reescribir a mano
    en JavaScript estas dos convenciones —y sus mayúsculas— y arriesgarse a que
    una de las dos copias se equivoque.
    """
    normalizado = dict(datos)

    for campo in campos_booleanos_select:
        if normalizado.get(campo) is not None:
            normalizado[campo] = str(bool(normalizado[campo]))

    for campo in campos_casilla:
        normalizado[campo] = "true" if normalizado.get(campo) else "false"

    return normalizado


class SincronizacionOfflineInvalida(Exception):
    """Se levanta dentro de la transacción de sincronización para revertirla.

    `transaction.atomic()` deshace todo lo escrito en cuanto una excepción
    escapa de su bloque; esta lleva además el detalle de qué falló, para que la
    vista lo traduzca a la respuesta JSON sin tener que adivinarlo de nuevo.
    """

    def __init__(self, errores):
        super().__init__(errores)
        self.errores = errores


class SincronizarEncuestaOfflineView(RegistroEnTerrenoMixin, View):
    """Recibe UNA encuesta capturada offline y la crea, reutilizando los mismos
    formularios que usaría el flujo online (HU-24).

    URL: /encuestas/sincronizar/  (POST, JSON)

    ----------------------------------------------------------------------
    POR QUÉ REUTILIZA LOS FORMS EN VEZ DE VALIDAR "A MANO"
    ----------------------------------------------------------------------
    `ViviendaForm`, `GrupoFamiliarForm`, `IntegranteForm`, `UbicacionForm`,
    `BorradorForm` y `CerrarSinDatosForm` ya conocen cada regla de negocio de
    estas cuatro tablas: dirección duplicada, zona vigente, RUT único en el
    hogar, cercanía al resto de la zona, edad mínima para exigir escolaridad…
    Repetir esas reglas aquí sería mantenerlas en dos sitios, con la certeza de
    que algún día se desincronizarían. La única validación que SÍ es propia de
    esta vista es la del punto 2 de abajo.

    ----------------------------------------------------------------------
    LA SEGURIDAD FRENTE A UN CLIENTE QUE MIENTE
    ----------------------------------------------------------------------
    El JavaScript del asistente no valida nada que dependa del servidor —zona
    todavía asignada, dirección duplicada, RUT repetido— porque offline no puede.
    Esta vista tampoco confía en lo que el celular asegura: `ViviendaForm` vuelve
    a construir el queryset de zonas permitidas con `censista=request.user` en
    este mismo instante, así que una zona que dejó de estar asignada se rechaza
    aquí igual que se rechazaría en el flujo online, aunque el payload la incluya.

    ----------------------------------------------------------------------
    SINCRONIZAR DOS VECES LA MISMA ENCUESTA ES SEGURO
    ----------------------------------------------------------------------
    Ver `Encuesta.origen_offline_id`. Si el `cliente_id` ya existe, se devuelve la
    encuesta ya creada en vez de duplicarla — necesario porque una conexión débil
    puede cortar la RESPUESTA de un envío que en realidad sí se guardó, y el
    asistente no tiene forma de distinguir eso de un fallo real.

    ----------------------------------------------------------------------
    "COMPLETAR" SIN TODO LO NECESARIO NO DESCARTA LA ENCUESTA
    ----------------------------------------------------------------------
    Si faltan piezas para completar (el jefe de hogar, algún integrante
    declarado), la vivienda, el hogar y lo que sí se capturó se guardan de
    todas formas, como BORRADOR — no se revierte la transacción entera. El
    asistente offline no tiene pantalla de edición, así que descartarlo todo
    dejaría a la persona sin ningún lugar donde corregir lo que falta. Ver el
    detalle en `_crear_encuesta`.
    """

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse(
                {"exito": False, "error": "El cuerpo de la petición no es JSON válido."},
                status=400,
            )

        try:
            cliente_id = uuid.UUID(str(payload.get("cliente_id")))
        except (TypeError, ValueError):
            return JsonResponse(
                {"exito": False, "error": "Falta un cliente_id válido."}, status=400
            )

        existente = Encuesta.objects.filter(origen_offline_id=cliente_id).first()

        if existente is not None:
            return JsonResponse(
                {
                    "exito": True,
                    "ya_existia": True,
                    "encuesta_id": existente.pk,
                    "vivienda_id": existente.vivienda_id,
                }
            )

        try:
            with transaction.atomic():
                encuesta, advertencia = self._crear_encuesta(request, payload, cliente_id)
        except SincronizacionOfflineInvalida as error:
            return JsonResponse({"exito": False, "errores": error.errores}, status=422)

        return JsonResponse(
            {
                "exito": True,
                "ya_existia": False,
                "encuesta_id": encuesta.pk,
                "vivienda_id": encuesta.vivienda_id,
                "advertencia": advertencia,
            }
        )

    def _crear_encuesta(self, request, payload, cliente_id):
        """Todo lo que ocurre DENTRO de la transacción. Devuelve `(encuesta,
        advertencia)`: `advertencia` es `None` salvo cuando se pidió
        "completar" y faltaba algo, caso en el que la encuesta SÍ se crea
        —como borrador— y se explica qué falta en vez de descartar todo.

        Para cualquier otro problema (un formulario inválido de verdad: un
        RUT mal escrito, una zona que ya no está asignada), si algo falla a
        mitad de camino nada de lo anterior queda a medias — ni la vivienda,
        ni el hogar, ni los integrantes ya guardados de esta misma encuesta.
        """
        datos_vivienda = _a_texto_de_formulario(
            payload.get("vivienda") or {},
            campos_booleanos_select=("tiene_electricidad",),
            campos_casilla=("confirmar_duplicado",),
        )
        vivienda_form = ViviendaForm(datos_vivienda, censista=request.user)

        if not vivienda_form.is_valid():
            raise SincronizacionOfflineInvalida(
                {"vivienda": vivienda_form.errors.get_json_data()}
            )

        vivienda = vivienda_form.save()

        encuesta = Encuesta.objects.create(
            vivienda=vivienda, censista=request.user, origen_offline_id=cliente_id
        )
        encuesta.cambiar_estado(EstadoEncuesta.BORRADOR)

        datos_hogar = payload.get("hogar")

        if datos_hogar:
            hogar_form = GrupoFamiliarForm(datos_hogar)

            if not hogar_form.is_valid():
                raise SincronizacionOfflineInvalida(
                    {"hogar": hogar_form.errors.get_json_data()}
                )

            hogar = hogar_form.save(commit=False)
            hogar.encuesta = encuesta
            hogar.save()

            errores_integrantes = []

            for indice, datos_integrante in enumerate(payload.get("integrantes") or []):
                integrante_form = IntegranteForm(
                    _a_texto_de_formulario(
                        datos_integrante, campos_casilla=("tiene_discapacidad",)
                    ),
                    grupo_familiar=hogar,
                )

                if not integrante_form.is_valid():
                    errores_integrantes.append(
                        {
                            "indice": indice,
                            "errores": integrante_form.errors.get_json_data(),
                        }
                    )
                    continue

                # Se guarda de inmediato, no al final: la validación de RUT único
                # del SIGUIENTE integrante consulta `grupo_familiar.integrantes`
                # en la base de datos, y solo ve a este si ya está guardado — es
                # lo mismo que ocurre online, donde cada persona es un POST
                # aparte que se confirma antes de que llegue la siguiente.
                integrante_form.save()

            if errores_integrantes:
                raise SincronizacionOfflineInvalida({"integrantes": errores_integrantes})

        datos_ubicacion = payload.get("ubicacion")

        if datos_ubicacion:
            datos_ubicacion = dict(datos_ubicacion)
            # UbicacionForm.save() no mira cleaned_data para esto: mira
            # self.data.get("capturada") == "1", igual que hace la plantilla
            # online cuando el navegador entregó el punto solo.
            if datos_ubicacion.pop("capturada_por_gps", False):
                datos_ubicacion["capturada"] = "1"

            ubicacion_form = UbicacionForm(
                _a_texto_de_formulario(
                    datos_ubicacion, campos_casilla=("confirmar_lejania",)
                ),
                instance=vivienda,
            )

            if not ubicacion_form.is_valid():
                raise SincronizacionOfflineInvalida(
                    {"ubicacion": ubicacion_form.errors.get_json_data()}
                )

            ubicacion_form.save()

        # Se vuelve a leer desde la base para que `pasos_pendientes()` vea el
        # hogar y los integrantes recién guardados: el objeto `encuesta` en
        # memoria todavía tiene en caché el estado de ANTES de guardarlos.
        encuesta = Encuesta.objects.select_related(
            "vivienda", "grupo_familiar"
        ).get(pk=encuesta.pk)

        resultado = payload.get("resultado")
        advertencia = None

        if resultado == "completar":
            pendientes = encuesta.pasos_pendientes()

            # A propósito, esto NO levanta SincronizacionOfflineInvalida.
            #
            # Si lo hiciera, la transacción completa se revertiría — vivienda,
            # hogar y los integrantes que sí se alcanzaron a capturar— y la
            # encuesta desaparecería sin dejar rastro en el servidor. Eso deja
            # a la persona sin ningún lugar donde corregir lo que falta: el
            # asistente offline no tiene pantalla de edición, así que "se
            # perdió todo, vuelve a capturarla entera" sería la única salida.
            #
            # En el flujo ONLINE esto no pasa porque crear la encuesta y
            # completarla son dos POST distintos: si falta el jefe de hogar,
            # CompletarEncuestaView avisa pero la vivienda y el hogar ya están
            # guardados desde antes, y se completan por las pantallas
            # normales. Aquí se imita ese mismo resultado sin necesitar dos
            # peticiones: se deja la encuesta en BORRADOR —que es el estado en
            # el que ya está, ver más arriba— y se avisa qué falta, para que
            # la persona la termine desde "Mis encuestas" con conexión.
            if pendientes:
                advertencia = (
                    "Se guardó como borrador: no se pudo completar porque "
                    f"falta {pendientes[0]['texto'].rstrip('.').lower()}. "
                    "Complétala desde «Mis encuestas»."
                )
            else:
                encuesta.cambiar_estado(EstadoEncuesta.COMPLETADA)
        elif resultado == "cerrar_sin_datos":
            cierre_form = CerrarSinDatosForm(payload.get("cierre") or {})

            if not cierre_form.is_valid():
                raise SincronizacionOfflineInvalida(
                    {"cierre": cierre_form.errors.get_json_data()}
                )

            encuesta.motivo_cierre = cierre_form.cleaned_data["motivo_cierre"]
            # La próxima visita se borra: la encuesta ya no espera a nadie, igual
            # que en CerrarSinDatosView.
            encuesta.proxima_visita = None
            encuesta.save(update_fields=["motivo_cierre", "proxima_visita"])
            encuesta.cambiar_estado(cierre_form.cleaned_data["estado"])
        else:
            borrador_form = BorradorForm(payload.get("borrador") or {}, instance=encuesta)

            if not borrador_form.is_valid():
                raise SincronizacionOfflineInvalida(
                    {"borrador": borrador_form.errors.get_json_data()}
                )

            borrador_form.save()

        return encuesta, advertencia


class ServirServiceWorkerView(View):
    """Entrega el service worker del asistente offline desde la raíz del sitio.

    URL: /sw.js (declarada en config/urls.py, no aquí — ver el comentario ahí)

    Un service worker solo puede controlar el subárbol de URLs igual o superior a
    la ruta desde la que el navegador lo obtuvo: servirlo bajo `/static/js/...` lo
    dejaría atrapado en `/static/`, que no sirve para vigilar `/encuestas/`. Se
    lee el archivo directamente del disco —no pasa por `collectstatic` ni por
    `ManifestStaticFilesStorage`— para que la URL sea siempre la misma y no un
    nombre con hash que cambia en cada despliegue: un service worker registrado
    con una URL que dejó de existir simplemente deja de poder actualizarse. Mismo
    principio que `ServirFotografiaView`: no todo archivo se sirve como se
    guarda.

    No exige ningún permiso de `fichas`, solo sesión iniciada (la exige el
    middleware de la HU-01 por defecto): es un script genérico, no un dato del
    censo, y el navegador solo necesita descargarlo una vez —estando conectado—
    para instalarlo.
    """

    RUTA_ARCHIVO = Path(settings.BASE_DIR) / "static" / "js" / "encuesta_offline_sw.js"

    def get(self, request, *args, **kwargs):
        contenido = self.RUTA_ARCHIVO.read_bytes()

        respuesta = HttpResponse(contenido, content_type="application/javascript")
        # Sin esto, el navegador puede tardar hasta 24 horas en notar que el
        # service worker cambió: el propio estándar recomienda no cachearlo.
        respuesta["Cache-Control"] = "no-cache"
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta


class EditarViviendaView(RegistroEnTerrenoMixin, View):
    """Corrige o completa los datos de una vivienda ya registrada.

    URL: /encuestas/viviendas/<pk>/editar/

    Existe por dos motivos distintos, y el segundo no es un caso raro:

      - Corregir un error: se puso «casa» y era una pieza en un conventillo.
      - COMPLETAR una vivienda del padrón antiguo. Las encuestas que la HU-07
        cargó se convirtieron en viviendas sin describir (ver la migración 0002), y
        esta es la pantalla donde se les llenan las características al llegar.
    """

    template_name = "fichas/vivienda_form.html"

    @cached_property
    def vivienda(self):
        """La vivienda, y solo si la persona tiene algo que ver con ella.

        Se restringe por las zonas asignadas y NO por «tener una encuesta aquí»,
        porque el segundo caso de uso —completar una vivienda que registró un
        compañero de sector— es legítimo: el sector puede estar repartido entre
        varias personas y la casa es la misma para todas.

        404 y no 403 cuando no corresponde, por lo mismo que en la ficha de una
        encuesta ajena: un 403 confirmaría que esa vivienda existe.
        """
        return get_object_or_404(
            Vivienda.objects.filter(
                zona__in=zonas_disponibles(self.request.user)
            ).select_related("zona", "zona__sector", "zona__sector__comuna"),
            pk=self.kwargs["pk"],
        )

    def formulario(self, datos=None):
        return ViviendaForm(datos, censista=self.request.user, instance=self.vivienda)

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.contexto(self.formulario()))

    def post(self, request, *args, **kwargs):
        formulario = self.formulario(request.POST)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        vivienda = formulario.save()

        messages.success(
            request, f"Datos de «{vivienda.direccion}» actualizados."
        )
        return redirect("fichas:vivienda_detalle", pk=vivienda.pk)

    def contexto(self, formulario):
        return {
            "titulo_pagina": f"Editar {self.vivienda.direccion}",
            "form": formulario,
            "vivienda": self.vivienda,
            "duplicadas": getattr(formulario, "duplicadas", None),
            "es_alta": False,
        }


class RegistrarHogarView(RegistroEnTerrenoMixin, View):
    """Registra o corrige el grupo familiar de una encuesta.

    URL: /encuestas/<pk>/hogar/

    Es el segundo paso del registro y la pantalla que de verdad «almacena la
    información del censo». Sirve para crear el hogar y para corregirlo: el mismo
    formulario con `instance` cuando ya existe, que es lo que hace que volver a
    entrar muestre lo que se escribió antes en vez de una pantalla en blanco.

    ----------------------------------------------------------------------
    GUARDAR DEJA LA ENCUESTA EN BORRADOR, NO EN COMPLETADA
    ----------------------------------------------------------------------
    Y es a propósito. Al hogar todavía le faltan sus integrantes uno por uno, que
    es la historia siguiente; darla por COMPLETADA aquí haría que el supervisor
    recibiera para validar fichas a las que les falta la mitad.

    La transición a COMPLETADA es de la historia de borradores, que es la que
    define cuándo una encuesta está terminada. Aquí solo se garantiza que una
    encuesta con datos nunca se quede en PENDIENTE, porque «pendiente» significa
    «sin visitar» y esta ya se visitó.
    """

    template_name = "fichas/hogar_form.html"

    @cached_property
    def encuesta(self):
        """Solo las encuestas PROPIAS. Aquí no vale `fichas.ver_todas`.

        Ver la ficha de otra persona es supervisión; ESCRIBIR en ella sería
        levantar información en su nombre, y el dato quedaría atribuido a quien no
        estuvo en la puerta. La ficha del censo tiene que poder responder quién la
        levantó, y esa respuesta es `encuesta.censista`.
        """
        return get_object_or_404(
            Encuesta.objects.select_related(
                "vivienda", "vivienda__zona", "vivienda__zona__sector"
            ),
            pk=self.kwargs["pk"],
            censista=self.request.user,
        )

    def comprobar_abierta(self):
        """None si se puede escribir, o una redirección con el motivo si no.

        Se comprueba en el GET y en el POST, no solo al dibujar la pantalla: la
        URL del POST se puede enviar a mano. Es la misma lección que la HU-06
        documentó al comprobar el reparto en los dos verbos.
        """
        permitido, motivo = self.encuesta.puede_registrarse()

        if permitido:
            return None

        messages.error(self.request, motivo)
        return redirect("fichas:encuesta_detalle", pk=self.encuesta.pk)

    def formulario(self, datos=None):
        return GrupoFamiliarForm(
            datos,
            instance=getattr(self.encuesta, "grupo_familiar", None),
        )

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        return render(request, self.template_name, self.contexto(self.formulario()))

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        formulario = self.formulario(request.POST)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        ya_existia = self.encuesta.tiene_grupo_familiar

        with transaction.atomic():
            hogar = formulario.save(commit=False)
            hogar.encuesta = self.encuesta
            hogar.save()

            # Una encuesta con datos no puede seguir diciendo «sin visitar».
            if self.encuesta.estado == EstadoEncuesta.PENDIENTE:
                self.encuesta.cambiar_estado(EstadoEncuesta.BORRADOR)

        messages.success(
            request,
            (
                f"Datos del hogar de {hogar.jefe_hogar_nombre} "
                f"{'actualizados' if ya_existia else 'registrados'}. "
                "La encuesta queda como borrador hasta que registres a sus "
                "integrantes."
            ),
        )
        return redirect("fichas:encuesta_detalle", pk=self.encuesta.pk)

    def contexto(self, formulario):
        return {
            "titulo_pagina": f"Hogar de {self.encuesta.direccion}",
            "form": formulario,
            "encuesta": self.encuesta,
            "vivienda": self.encuesta.vivienda,
            "ya_existia": self.encuesta.tiene_grupo_familiar,
        }


class AgregarHogarView(RegistroEnTerrenoMixin, View):
    """Crea una encuesta más sobre una vivienda que ya existe. Solo POST.

    URL: /encuestas/viviendas/<pk>/hogar/nuevo/

    Es la respuesta operativa al caso que dio origen al modelo de la HU-08: se
    llega a una casa ya registrada y resulta que vive una segunda familia. Sin
    esta pantalla habría que registrar la vivienda otra vez, que es exactamente el
    duplicado que el sistema pide confirmar.

    Solo POST, y con token CSRF, porque CREA una fila. Si un GET pudiera hacerlo,
    bastaría con que alguien incrustara la dirección en un <img src="..."> para
    llenar la base de encuestas vacías con la sesión de quien mirara la página. Es
    la misma razón por la que retirar una asignación en la HU-06 son dos pasos.
    """

    @cached_property
    def vivienda(self):
        return get_object_or_404(
            Vivienda.objects.filter(
                zona__in=zonas_disponibles(self.request.user)
            ).select_related("zona", "zona__sector"),
            pk=self.kwargs["pk"],
        )

    def post(self, request, *args, **kwargs):
        permitido, motivo = self.vivienda.puede_registrarse_trabajo()

        if not permitido:
            messages.error(request, motivo)
            return redirect("fichas:vivienda_detalle", pk=self.vivienda.pk)

        with transaction.atomic():
            encuesta = Encuesta.objects.create(
                vivienda=self.vivienda, censista=request.user
            )
            encuesta.cambiar_estado(EstadoEncuesta.BORRADOR)

        messages.success(
            request,
            f"Se agregó un hogar más en «{self.vivienda.direccion}». Completa sus "
            "datos.",
        )
        return redirect("fichas:registrar_hogar", pk=encuesta.pk)


class ViviendaDetalleView(PermisoRequeridoMixin, DetailView):
    """La vivienda y los hogares que la habitan.

    URL: /encuestas/viviendas/<pk>/

    Es donde se ve el caso que la HU-08 vino a modelar bien: una casa, dos
    hogares, una sola descripción del inmueble. Y es el sitio desde el que se
    agrega el segundo hogar.
    """

    permisos_requeridos = ("fichas.ver_propias", "fichas.ver_todas")
    mensaje_sin_permiso = "No tienes permiso para consultar el módulo de encuestas."

    model = Vivienda
    template_name = "fichas/vivienda_detalle.html"
    context_object_name = "vivienda"

    def get_queryset(self):
        consulta = Vivienda.objects.select_related(
            "zona",
            "zona__sector",
            "zona__sector__comuna",
            "zona__sector__comuna__region",
            "zona__sector__operativo",
            "registrada_por",
        )

        if self.request.user.tiene_permiso("fichas.ver_todas"):
            return consulta

        # Sin `ver_todas`, se ve una vivienda si se tiene trabajo en ella o si
        # está en el territorio asignado. Lo segundo es lo que permite completar
        # los datos de una casa que registró un compañero del mismo sector.
        return consulta.filter(
            Q(encuestas__censista=self.request.user)
            | Q(zona__in=zonas_disponibles(self.request.user))
        ).distinct()

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        vivienda = self.object

        contexto["titulo_pagina"] = vivienda.direccion
        contexto["hogares"] = (
            vivienda.encuestas.select_related("censista")
            .prefetch_related("grupo_familiar")
            .order_by("id")
        )
        permitido, motivo = vivienda.puede_registrarse_trabajo()
        contexto["puede_registrar"] = permitido and self.request.user.tiene_algun_permiso(
            "fichas.crear", "fichas.editar"
        )
        contexto["motivo_bloqueo"] = motivo
        return contexto


# ==========================================================================
# HU-09 — LAS PERSONAS DEL HOGAR
# ==========================================================================


class HogarDeLaEncuestaMixin(RegistroEnTerrenoMixin):
    """Base de las cuatro pantallas de integrantes.

    Todas trabajan sobre el hogar de UNA encuesta propia y abierta, así que las
    tres comprobaciones —es mía, tiene hogar registrado, admite cambios— se
    escriben aquí una vez. Repetirlas en cuatro vistas sería garantizar que alguna
    se quedara sin una de las tres, y la que faltara no daría ningún error: solo
    dejaría escribir donde no se debe.
    """

    @cached_property
    def encuesta(self):
        """Solo encuestas PROPIAS, igual que al registrar el hogar.

        Ni siquiera `fichas.ver_todas` abre esta puerta: escribir una persona en la
        ficha de otro encuestador dejaría el dato atribuido a quien no estuvo en la
        vivienda.
        """
        return get_object_or_404(
            Encuesta.objects.select_related(
                "vivienda", "vivienda__zona", "vivienda__zona__sector", "grupo_familiar"
            ),
            pk=self.kwargs["encuesta_pk"],
            censista=self.request.user,
        )

    @cached_property
    def grupo_familiar(self):
        return getattr(self.encuesta, "grupo_familiar", None)

    def comprobar_hogar_registrado(self):
        """No se pueden registrar personas de un hogar que todavía no existe.

        Es un orden real, no un capricho del sistema: el parentesco de cada persona
        se declara respecto al jefe de hogar, y el jefe de hogar se identifica al
        registrar el hogar. Sin ese paso, la primera pregunta del formulario no
        tendría respuesta posible.
        """
        if self.grupo_familiar is not None:
            return None

        messages.info(
            self.request,
            "Primero registra los datos del hogar y después a sus integrantes.",
        )
        return redirect("fichas:registrar_hogar", pk=self.encuesta.pk)

    def comprobar_abierta(self):
        permitido, motivo = self.encuesta.puede_registrarse()

        if permitido:
            return None

        messages.error(self.request, motivo)
        return redirect("fichas:encuesta_detalle", pk=self.encuesta.pk)

    def comprobar_todo(self):
        """Las dos comprobaciones, en el orden en que hay que hacerlas."""
        return self.comprobar_hogar_registrado() or self.comprobar_abierta()


class IntegrantesView(HogarDeLaEncuestaMixin, View):
    """Las personas del hogar: cuántas van, cuántas faltan y quiénes son.

    URL: /encuestas/<encuesta_pk>/integrantes/

    Es la pantalla donde se ve para qué servía `integrantes_declarados`. La HU-08
    lo guardó argumentando que «son dos datos distintos y su diferencia es
    información»; aquí esa diferencia es la barra de avance y el aviso de que
    faltan tres personas por registrar.

    Se comprueba en el GET, y no solo se ocultan botones, porque la lista también
    la puede abrir alguien con la encuesta ya cerrada.
    """

    template_name = "fichas/integrantes.html"

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_hogar_registrado()) is not None:
            return respuesta

        permitido, motivo = self.encuesta.puede_registrarse()

        return render(
            request,
            self.template_name,
            {
                "titulo_pagina": f"Integrantes de {self.encuesta.direccion}",
                "encuesta": self.encuesta,
                "hogar": self.grupo_familiar,
                "integrantes": self.grupo_familiar.integrantes_ordenados(),
                "puede_registrar": permitido,
                "motivo_bloqueo": motivo,
            },
        )


class RegistrarIntegranteView(HogarDeLaEncuestaMixin, View):
    """Agrega una persona al hogar. GET muestra, POST guarda.

    URL: /encuestas/<encuesta_pk>/integrantes/nuevo/

    ----------------------------------------------------------------------
    LA PRIMERA PERSONA VIENE PRERRELLENADA
    ----------------------------------------------------------------------
    Si el hogar todavía no tiene jefe registrado, el formulario llega con el
    parentesco en «jefe de hogar» y con el nombre y el RUT que se tomaron al
    registrar el hogar (HU-08).

    No es un adorno: es lo que mantiene coherentes los dos sitios donde vive el
    nombre del jefe de hogar. Sin el prellenado, el encuestador escribiría el
    nombre otra vez y en la mitad de los casos quedaría distinto —«Rosa Millán» y
    «Rosa Elena Millán Soto»— y el hogar diría dos cosas sobre la misma persona.

    Se prerrellena y no se crea automáticamente porque el formulario pide datos que
    el registro del hogar no tomó: sexo, fecha de nacimiento, escolaridad. Crear la
    fila sola exigiría inventarlos.

    ----------------------------------------------------------------------
    «GUARDAR Y AGREGAR OTRA»
    ----------------------------------------------------------------------
    Registrar seis personas seguidas es la operación real de esta pantalla. Con un
    solo botón, cada una costaría tres toques: guardar, volver a la lista, pulsar
    «agregar». El segundo botón devuelve un formulario vacío en el mismo sitio, que
    es lo que convierte seis personas en seis formularios y no en dieciocho toques.
    """

    template_name = "fichas/integrante_form.html"

    def formulario(self, datos=None, instancia=None):
        return IntegranteForm(
            datos,
            grupo_familiar=self.grupo_familiar,
            instance=instancia,
            initial=None if datos else self.valores_iniciales(),
        )

    def valores_iniciales(self):
        """Prerrellena a la primera persona con lo que ya se sabe del jefe de hogar."""
        if self.grupo_familiar.jefe_hogar_registrado is not None:
            return {}

        nombre = self.grupo_familiar.jefe_hogar_nombre.split()

        return {
            "parentesco": Parentesco.JEFE_HOGAR,
            # Partir el nombre por la mitad es una heurística y se sabe: en Chile
            # lo habitual son dos nombres y dos apellidos. Se ofrece como borrador
            # editable, no como dato definitivo, y por eso va en `initial`.
            "nombres": " ".join(nombre[: max(1, len(nombre) // 2)]),
            "apellidos": " ".join(nombre[max(1, len(nombre) // 2) :]),
            "rut": self.grupo_familiar.jefe_hogar_rut,
        }

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_todo()) is not None:
            return respuesta

        return render(request, self.template_name, self.contexto(self.formulario()))

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_todo()) is not None:
            return respuesta

        formulario = self.formulario(request.POST)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        integrante = formulario.save()

        messages.success(
            request,
            f"{integrante.nombre_completo} agregado al hogar. "
            f"{self.resumen_avance()}",
        )

        # El botón «guardar y agregar otra» vuelve a este mismo formulario, vacío.
        if "guardar_y_seguir" in request.POST:
            return redirect(
                "fichas:integrante_nuevo", encuesta_pk=self.encuesta.pk
            )

        return redirect("fichas:integrantes", encuesta_pk=self.encuesta.pk)

    def resumen_avance(self):
        """Frase que dice cómo va el hogar, no solo que se guardó.

        Mismo criterio que `resumen_equipo()` en la HU-06: un mensaje que dice
        «guardado» obliga a mirar la lista para saber qué falta.
        """
        hogar = self.grupo_familiar
        hogar.refresh_from_db()

        if hogar.hay_discrepancia:
            return (
                f"Van {hogar.total_integrantes()} y la familia declaró "
                f"{hogar.integrantes_declarados}: revisa el número declarado."
            )

        pendientes = hogar.integrantes_pendientes

        if pendientes:
            return f"Faltan {pendientes} persona{'s' if pendientes != 1 else ''}."

        return "El hogar quedó completo."

    def contexto(self, formulario):
        return {
            "titulo_pagina": "Agregar una persona",
            "form": formulario,
            "encuesta": self.encuesta,
            "hogar": self.grupo_familiar,
            "es_alta": True,
        }


class EditarIntegranteView(HogarDeLaEncuestaMixin, View):
    """Corrige los datos de una persona ya registrada.

    URL: /encuestas/<encuesta_pk>/integrantes/<pk>/editar/

    La persona se busca DENTRO del hogar de la encuesta y no por su identificador
    suelto. Es lo que hace imposible editar a alguien de otro hogar cambiando un
    número en la dirección: el filtro por `grupo_familiar` va siempre, y la
    encuesta ya está filtrada por `censista=request.user`.
    """

    template_name = "fichas/integrante_form.html"

    @cached_property
    def integrante(self):
        return get_object_or_404(
            Integrante, pk=self.kwargs["pk"], grupo_familiar=self.grupo_familiar
        )

    def formulario(self, datos=None):
        return IntegranteForm(
            datos, grupo_familiar=self.grupo_familiar, instance=self.integrante
        )

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_todo()) is not None:
            return respuesta

        return render(request, self.template_name, self.contexto(self.formulario()))

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_todo()) is not None:
            return respuesta

        formulario = self.formulario(request.POST)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        integrante = formulario.save()

        messages.success(request, f"Datos de {integrante.nombre_completo} actualizados.")
        return redirect("fichas:integrantes", encuesta_pk=self.encuesta.pk)

    def contexto(self, formulario):
        return {
            "titulo_pagina": f"Editar a {self.integrante.nombre_completo}",
            "form": formulario,
            "encuesta": self.encuesta,
            "hogar": self.grupo_familiar,
            "integrante": self.integrante,
            "es_alta": False,
        }


class QuitarIntegranteView(HogarDeLaEncuestaMixin, View):
    """Quita a una persona del hogar. GET confirma, POST ejecuta.

    URL: /encuestas/<encuesta_pk>/integrantes/<pk>/quitar/

    ----------------------------------------------------------------------
    AQUÍ SÍ SE BORRA, Y ES LA EXCEPCIÓN DEL PROYECTO
    ----------------------------------------------------------------------
    OPSO desactiva en vez de borrar en todas partes: cuentas (HU-03), comunas y
    sectores (HU-05), asignaciones (HU-06). Esta vista borra la fila de verdad, y
    conviene poder explicar por qué no es una incoherencia.

    Lo que se desactiva en vez de borrarse es aquello cuyo PASADO significa algo:
    una asignación retirada explica por qué esa persona levantó esas fichas; una
    comuna desactivada explica de dónde salieron los datos de 2026.

    Una persona agregada por error a un hogar no tiene pasado que explicar. Es un
    dato que se está capturando, todavía en borrador, que ningún supervisor ha
    validado y que no sostiene ninguna otra fila. Conservarla desactivada
    obligaría a filtrar «los integrantes que sí cuentan» en cada recuento del
    censo, y la primera consulta que se olvidara del filtro daría un hogar con una
    persona de más.

    Y hay un motivo más fuerte: son DATOS PERSONALES DE TERCEROS. Guardar
    indefinidamente a una persona que no debía estar en la base, marcada como
    «inactiva», es exactamente lo que la minimización de datos pide no hacer
    (Ley N° 21.719).

    Dos pasos —confirmar y ejecutar— por lo mismo que retirar una asignación en la
    HU-06: si un GET pudiera borrar, un <img src="..."> incrustado en cualquier
    página lo ejecutaría con la sesión de quien la mirara.
    """

    template_name = "fichas/integrante_quitar.html"

    @cached_property
    def integrante(self):
        return get_object_or_404(
            Integrante, pk=self.kwargs["pk"], grupo_familiar=self.grupo_familiar
        )

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_todo()) is not None:
            return respuesta

        return render(
            request,
            self.template_name,
            {
                "titulo_pagina": f"Quitar a {self.integrante.nombre_completo}",
                "encuesta": self.encuesta,
                "hogar": self.grupo_familiar,
                "integrante": self.integrante,
            },
        )

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_todo()) is not None:
            return respuesta

        nombre = self.integrante.nombre_completo
        era_jefe = self.integrante.es_jefe_hogar

        self.integrante.delete()

        aviso = (
            " El hogar quedó sin jefe de hogar registrado: marca a alguien como tal."
            if era_jefe
            else ""
        )
        messages.success(request, f"{nombre} ya no figura en este hogar.{aviso}")
        return redirect("fichas:integrantes", encuesta_pk=self.encuesta.pk)


# ==========================================================================
# HU-10 — EL BORRADOR Y EL CIERRE DE LA ENCUESTA
# ==========================================================================


class EncuestaPropiaMixin(RegistroEnTerrenoMixin):
    """Base de las tres pantallas del borrador.

    Igual que HogarDeLaEncuestaMixin en la HU-09, pero sin exigir que el hogar
    exista: se puede guardar una nota de avance —o cerrar por no ubicada— en una
    encuesta a la que todavía no se le ha registrado nada. De hecho es el caso más
    frecuente de «no ubicada»: se llega, no hay nadie, se cierra.
    """

    @cached_property
    def encuesta(self):
        return get_object_or_404(
            Encuesta.objects.select_related(
                "vivienda", "vivienda__zona", "vivienda__zona__sector", "grupo_familiar"
            ),
            pk=self.kwargs["pk"],
            censista=self.request.user,
        )

    def comprobar_abierta(self):
        permitido, motivo = self.encuesta.puede_registrarse()

        if permitido:
            return None

        messages.error(self.request, motivo)
        return redirect("fichas:encuesta_detalle", pk=self.encuesta.pk)


class GuardarBorradorView(EncuestaPropiaMixin, View):
    """Deja anotado por dónde iba la encuesta y cuándo volver.

    URL: /encuestas/<pk>/borrador/

    ----------------------------------------------------------------------
    ¿QUÉ GUARDA, SI TODO SE GUARDABA YA?
    ----------------------------------------------------------------------
    Los datos del censo se guardan desde la HU-08 en cuanto se pulsa cada botón: no
    hay nada que se pierda al salir de la aplicación. Lo que esta pantalla guarda es
    lo que NO es un campo del formulario: por dónde iba la conversación y cuándo
    conviene volver.

    Eso hoy vive en la cabeza del encuestador y se pierde al día siguiente. Una
    encuesta a medias sin nota hay que reconstruirla de memoria, y cuando pasan
    cuatro días se vuelve a empezar —con la familia respondiendo dos veces las
    mismas preguntas—.

    Es la diferencia entre «los datos están guardados» y «puedo continuar», y la
    historia pide lo segundo.

    ----------------------------------------------------------------------
    GUARDAR LA NOTA NO CAMBIA EL ESTADO… CON UNA EXCEPCIÓN
    ----------------------------------------------------------------------
    Una encuesta PENDIENTE a la que se le deja una nota pasa a BORRADOR, porque
    dejar una nota implica haber estado ahí: «pendiente» significa «sin visitar» y
    ya no es verdad. Es la misma regla que aplicó la HU-08 al registrar el hogar, y
    la única transición que esta pantalla provoca.

    Una encuesta OBSERVADA que recibe una nota SIGUE observada: bajarla a BORRADOR
    haría desaparecer de la pantalla el hecho de que el supervisor la devolvió, que
    es el aviso más urgente que tiene el encuestador.
    """

    template_name = "fichas/borrador_form.html"

    def formulario(self, datos=None):
        return BorradorForm(datos, instance=self.encuesta)

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        return render(request, self.template_name, self.contexto(self.formulario()))

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        formulario = self.formulario(request.POST)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        with transaction.atomic():
            encuesta = formulario.save()

            if encuesta.estado == EstadoEncuesta.PENDIENTE:
                encuesta.cambiar_estado(EstadoEncuesta.BORRADOR)

        messages.success(request, self.confirmacion(encuesta))
        return redirect("fichas:encuesta_detalle", pk=encuesta.pk)

    def confirmacion(self, encuesta):
        """Dice qué queda anotado, no solo que se guardó.

        Mismo criterio que `resumen_equipo()` en la HU-06 y `resumen_avance()` en la
        HU-09: un «guardado» obliga a volver a mirar la pantalla para saber qué
        quedó.
        """
        if encuesta.proxima_visita:
            return (
                "Borrador guardado. Anotado para volver el "
                f"{encuesta.proxima_visita:%d-%m-%Y}."
            )

        return "Borrador guardado. Podrás continuar donde lo dejaste."

    def contexto(self, formulario):
        return {
            "titulo_pagina": f"Borrador de {self.encuesta.direccion}",
            "form": formulario,
            "encuesta": self.encuesta,
            "pendientes": self.encuesta.pasos_pendientes(),
        }


class CompletarEncuestaView(EncuestaPropiaMixin, View):
    """Da la encuesta por terminada y la manda a revisión. GET confirma, POST ejecuta.

    URL: /encuestas/<pk>/completar/

    ----------------------------------------------------------------------
    ES LA ÚNICA SALIDA DEL BORRADOR, Y HASTA AHORA NO EXISTÍA
    ----------------------------------------------------------------------
    Desde la HU-07 el estado COMPLETADA estaba definido y ninguna pantalla lo
    producía: todo lo que el encuestador tocaba quedaba en BORRADOR para siempre y
    el supervisor no recibía nada. Esta vista cierra ese hueco, y con ella el
    ciclo de vida completo tiene por fin un camino de ida entero:

        PENDIENTE -> BORRADOR -> COMPLETADA -> (el supervisor valida u observa)

    ----------------------------------------------------------------------
    NO SE PUEDE COMPLETAR UNA ENCUESTA INCOMPLETA
    ----------------------------------------------------------------------
    Se comprueba `Encuesta.puede_completarse`, que exige la vivienda descrita, el
    hogar registrado, su jefe identificado y todas las personas declaradas
    presentes. Y se comprueba en el GET **y** en el POST: ocultar el botón no es una
    validación.

    La pantalla no dice «no puedes»: muestra LA LISTA de lo que falta con un enlace
    a cada paso. Es la razón por la que `pasos_pendientes()` devuelve rutas y no
    textos —ver su docstring—: «falta describir la vivienda → [ir]» se resuelve en
    un toque, y «no puedes completar la encuesta» obliga a buscar el problema
    pantalla por pantalla.

    ----------------------------------------------------------------------
    UNA VEZ COMPLETADA, EL ENCUESTADOR NO PUEDE REABRIRLA
    ----------------------------------------------------------------------
    Y es a propósito. Reabrir lo que ya se envió a revisión permitiría cambiar los
    datos que el supervisor está mirando en ese momento, o los que ya aprobó. El
    camino de vuelta existe y es del supervisor: devolverla como OBSERVADA, que la
    convierte otra vez en trabajo abierto. `puede_registrarse()` ya lo impide, así
    que esta vista no necesita añadir ninguna regla nueva.
    """

    template_name = "fichas/encuesta_completar.html"

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        return render(request, self.template_name, self.contexto())

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        pendientes = self.encuesta.pasos_pendientes()

        if pendientes:
            messages.error(
                request,
                "No se puede dar por terminada: falta "
                f"{pendientes[0]['texto'].rstrip('.').lower()}.",
            )
            return render(request, self.template_name, self.contexto())

        self.encuesta.cambiar_estado(EstadoEncuesta.COMPLETADA)

        messages.success(
            request,
            f"Encuesta de {self.encuesta.direccion} terminada y enviada a revisión. "
            "Tu supervisor la validará o te la devolverá con observaciones.",
        )
        return redirect("fichas:mis_encuestas")

    def contexto(self):
        hogar = getattr(self.encuesta, "grupo_familiar", None)

        return {
            "titulo_pagina": f"Terminar {self.encuesta.direccion}",
            "encuesta": self.encuesta,
            "hogar": hogar,
            "pendientes": self.encuesta.pasos_pendientes(),
            "integrantes": (
                hogar.integrantes_ordenados() if hogar is not None else []
            ),
        }


class CerrarSinDatosView(EncuestaPropiaMixin, View):
    """Cierra una encuesta que no se pudo levantar. GET muestra, POST ejecuta.

    URL: /encuestas/<pk>/cerrar/

    Produce NO_UBICADA o RECHAZADA, los dos estados que la HU-07 definió como
    RESULTADOS y no como fracasos: sin ellos, una dirección que no existe quedaría
    pendiente para siempre y el avance del operativo mentiría hacia abajo.

    Lo que esta historia agrega es el motivo. La HU-07 dejó los estados sin ningún
    campo donde escribir por qué, y una encuesta cerrada sin explicación no es
    información: el supervisor no puede decidir si manda a otra persona a esa
    dirección. `motivo_cierre` y su restricción lo resuelven, y el formulario exige
    además que sea legible.

    Se puede cerrar una encuesta EN CUALQUIER PUNTO del borrador, incluso sin haber
    registrado nada: es el caso más frecuente —se llega, no hay nadie, se cierra— y
    exigir el hogar registrado obligaría a inventar una familia para poder decir que
    no se encontró a ninguna.
    """

    template_name = "fichas/encuesta_cerrar.html"

    def formulario(self, datos=None):
        return CerrarSinDatosForm(datos)

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        return render(request, self.template_name, self.contexto(self.formulario()))

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        formulario = self.formulario(request.POST)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        # El estado se aplica con cambiar_estado() y no con el save() del
        # formulario, porque hay que mover también las dos fechas. El formulario
        # solo aporta el motivo y cuál de los dos estados es.
        nuevo_estado = formulario.cleaned_data["estado"]

        with transaction.atomic():
            self.encuesta.motivo_cierre = formulario.cleaned_data["motivo_cierre"]
            # La próxima visita se borra: la encuesta ya no espera a nadie, y
            # dejarla haría que el listado siguiera avisando de una visita que no
            # hay que hacer.
            self.encuesta.proxima_visita = None
            self.encuesta.save(update_fields=["motivo_cierre", "proxima_visita"])
            self.encuesta.cambiar_estado(nuevo_estado)

        messages.success(
            request,
            f"Encuesta de {self.encuesta.direccion} cerrada como "
            f"«{self.encuesta.get_estado_display()}». El motivo quedó registrado.",
        )
        return redirect("fichas:mis_encuestas")

    def contexto(self, formulario):
        return {
            "titulo_pagina": f"Cerrar {self.encuesta.direccion}",
            "form": formulario,
            "encuesta": self.encuesta,
        }


# ==========================================================================
# HU-11 — LA UBICACIÓN GEOGRÁFICA
# ==========================================================================


class CapturarUbicacionView(RegistroEnTerrenoMixin, View):
    """Captura o corrige el punto GPS de una vivienda. GET muestra, POST guarda.

    URL: /encuestas/viviendas/<pk>/ubicacion/

    ----------------------------------------------------------------------
    POR QUÉ ES UNA PANTALLA APARTE Y NO UN CAMPO DEL FORMULARIO DE VIVIENDA
    ----------------------------------------------------------------------
    Porque la ubicación se toma EN OTRO MOMENTO y a veces EN OTRO SITIO. El
    formulario de la vivienda se llena conversando con la familia, muchas veces
    dentro de la casa —donde el GPS es peor— o después de la visita. El punto se
    toma en la puerta, de pie en la calle, y son diez segundos.

    Mezclarlos obligaría a capturar el GPS en el instante exacto en que se registra
    la casa, y en la práctica se acabaría guardando el punto de donde estuviera el
    teléfono en ese momento.

    Hay además un caso que solo esta pantalla resuelve: las viviendas que ya
    existían antes de la HU-11 no tienen punto, y hay que poder capturárselo al
    volver a pasar sin editar todo lo demás.

    ----------------------------------------------------------------------
    QUIÉN PUEDE
    ----------------------------------------------------------------------
    Las mismas reglas que editar la vivienda: la zona tiene que estar entre las
    asignadas (`zonas_disponibles`) y el territorio tiene que admitir trabajo. No se
    exige que la encuesta sea propia, por lo mismo que en EditarViviendaView: el
    sector puede estar repartido entre varias personas y la casa es la misma para
    todas. La ubicación describe el inmueble, no el trabajo de nadie.
    """

    template_name = "fichas/ubicacion_form.html"

    @cached_property
    def vivienda(self):
        return get_object_or_404(
            Vivienda.objects.filter(
                zona__in=zonas_disponibles(self.request.user)
            ).select_related("zona", "zona__sector", "zona__sector__comuna"),
            pk=self.kwargs["pk"],
        )

    def comprobar_abierta(self):
        permitido, motivo = self.vivienda.puede_registrarse_trabajo()

        if permitido:
            return None

        messages.error(self.request, motivo)
        return redirect("fichas:vivienda_detalle", pk=self.vivienda.pk)

    def formulario(self, datos=None):
        return UbicacionForm(datos, instance=self.vivienda)

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        return render(request, self.template_name, self.contexto(self.formulario()))

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        formulario = self.formulario(request.POST)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        vivienda = formulario.save()

        messages.success(request, self.confirmacion(vivienda))
        return redirect("fichas:vivienda_detalle", pk=vivienda.pk)

    def confirmacion(self, vivienda):
        """Confirma el punto Y su calidad, no solo que se guardó.

        Decir «ubicación guardada» esconde el caso que importa: un punto con 300
        metros de error se guardó igual y no sirve para distinguir una casa de la
        de enfrente. Si la precisión es mala, el mensaje lo dice y sugiere repetir
        la captura afuera.
        """
        base = f"Ubicación de «{vivienda.direccion}» guardada."

        if vivienda.precision_metros is None:
            return f"{base} No quedó registrada la precisión del aparato."

        if not vivienda.precision_aceptable:
            return (
                f"{base} La precisión es de {vivienda.precision_metros} m, que es "
                "mucho: si puedes, repite la captura en la calle y con el cielo "
                "despejado."
            )

        return f"{base} Precisión: {vivienda.precision_metros} m."

    def contexto(self, formulario):
        return {
            "titulo_pagina": f"Ubicación de {self.vivienda.direccion}",
            "form": formulario,
            "vivienda": self.vivienda,
            "distancia_al_resto": getattr(formulario, "distancia_al_resto", None),
            "hay_referencia": Vivienda.centro_de_la_zona(
                self.vivienda.zona, excluir=self.vivienda.pk
            )
            is not None,
        }


# ==========================================================================
# HU-12 — LAS FOTOGRAFÍAS
# ==========================================================================


class ViviendaDelTerritorioMixin(RegistroEnTerrenoMixin):
    """Base de las pantallas que trabajan sobre una vivienda del territorio propio.

    Repite el criterio de EditarViviendaView y CapturarUbicacionView: la vivienda
    tiene que estar en una zona asignada, y el territorio tiene que admitir trabajo.
    No se exige que la encuesta sea propia porque una fotografía documenta el
    INMUEBLE, y el sector puede estar repartido entre varias personas.
    """

    @cached_property
    def vivienda(self):
        return get_object_or_404(
            Vivienda.objects.filter(
                zona__in=zonas_disponibles(self.request.user)
            ).select_related("zona", "zona__sector"),
            pk=self.kwargs["pk"],
        )

    def comprobar_abierta(self):
        permitido, motivo = self.vivienda.puede_registrarse_trabajo()

        if permitido:
            return None

        messages.error(self.request, motivo)
        return redirect("fichas:vivienda_detalle", pk=self.vivienda.pk)


class SubirFotografiaView(ViviendaDelTerritorioMixin, View):
    """Adjunta una fotografía a la vivienda. GET muestra, POST guarda.

    URL: /encuestas/viviendas/<pk>/fotografias/nueva/

    ----------------------------------------------------------------------
    «CUANDO SEA NECESARIO» ESTÁ EN EL TÍTULO DE LA HISTORIA, Y SE TOMA EN SERIO
    ----------------------------------------------------------------------
    Esta pantalla NO empuja a fotografiar. Al contrario: pide elegir qué se está
    documentando, obliga a explicar por qué hizo falta y limita a cinco fotos por
    vivienda. Un formulario que solo dijera «sube una imagen» produciría álbumes de
    casas ajenas, que es exactamente lo que un censo no debe acumular.

    La advertencia de no fotografiar personas va ANTES del campo de archivo, no
    después: leerla cuando la foto ya está seleccionada no sirve de nada.
    """

    template_name = "fichas/fotografia_form.html"

    def formulario(self, datos=None, archivos=None):
        return FotografiaForm(datos, archivos, vivienda=self.vivienda)

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        return render(request, self.template_name, self.contexto(self.formulario()))

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        # request.FILES va aparte de request.POST: sin pasarlo, el campo de imagen
        # llega vacío y el formulario dice que falta el archivo aunque se haya
        # subido. Es el error clásico de la primera subida de archivos.
        formulario = self.formulario(request.POST, request.FILES)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        fotografia = formulario.save(commit=False)
        fotografia.tomada_por = request.user
        fotografia.save()

        messages.success(
            request,
            f"Fotografía adjuntada a «{self.vivienda.direccion}»: "
            f"{fotografia.get_tipo_display().lower()}.",
        )
        return redirect("fichas:vivienda_detalle", pk=self.vivienda.pk)

    def contexto(self, formulario):
        tope = settings.OPSO_MAXIMO_FOTOS_POR_VIVIENDA

        return {
            "titulo_pagina": f"Fotografía de {self.vivienda.direccion}",
            "form": formulario,
            "vivienda": self.vivienda,
            "fotografias": self.vivienda.fotografias.all(),
            "tope": tope,
            "quedan": max(0, tope - self.vivienda.fotografias.count()),
            "tamano_maximo_mb": settings.OPSO_TAMANO_MAXIMO_FOTO // (1024 * 1024),
        }


class QuitarFotografiaView(RegistroEnTerrenoMixin, View):
    """Borra una fotografía. GET confirma, POST ejecuta.

    URL: /encuestas/fotografias/<pk>/quitar/

    ----------------------------------------------------------------------
    BORRA EL ARCHIVO, NO SOLO LA FILA
    ----------------------------------------------------------------------
    Django no borra el archivo al borrar la fila —dejó de hacerlo a propósito hace
    muchas versiones—, así que hay que hacerlo explícitamente. Si no, el disco
    acumula fotografías de casas de familias que ya nadie puede ver ni saber que
    están ahí.

    Para datos personales eso no es un descuido de limpieza: es conservar
    información que ya no debería existir, que es justo lo contrario de lo que pide
    la minimización de datos (Ley N° 21.719). Por eso el borrado vive en
    `Fotografia.borrar_archivo()` y no repartido por las vistas.

    Es la segunda pantalla del proyecto que borra de verdad, después de quitar a un
    integrante en la HU-09, y por el mismo motivo: lo que se elimina es un dato
    capturado por error, no un registro histórico que explique algo.

    Dos pasos, como siempre: con un GET capaz de borrar, un `<img src="...">`
    incrustado en cualquier página lo ejecutaría con la sesión de quien la mirara.
    """

    template_name = "fichas/fotografia_quitar.html"

    @cached_property
    def fotografia(self):
        return get_object_or_404(
            Fotografia.objects.filter(
                vivienda__zona__in=zonas_disponibles(self.request.user)
            ).select_related("vivienda", "vivienda__zona", "tomada_por"),
            pk=self.kwargs["pk"],
        )

    def comprobar_abierta(self):
        permitido, motivo = self.fotografia.vivienda.puede_registrarse_trabajo()

        if permitido:
            return None

        messages.error(self.request, motivo)
        return redirect(
            "fichas:vivienda_detalle", pk=self.fotografia.vivienda_id
        )

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        return render(
            request,
            self.template_name,
            {
                "titulo_pagina": "Quitar la fotografía",
                "fotografia": self.fotografia,
                "vivienda": self.fotografia.vivienda,
            },
        )

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_abierta()) is not None:
            return respuesta

        vivienda_pk = self.fotografia.vivienda_id
        etiqueta = self.fotografia.get_tipo_display().lower()

        self.fotografia.borrar_archivo()

        messages.success(
            request, f"La fotografía ({etiqueta}) se borró junto con su archivo."
        )
        return redirect("fichas:vivienda_detalle", pk=vivienda_pk)


class ServirFotografiaView(PermisoRequeridoMixin, View):
    """Entrega el archivo de una fotografía, comprobando antes quién lo pide.

    URL: /encuestas/fotografias/<pk>/ver/

    ----------------------------------------------------------------------
    POR QUÉ EXISTE ESTA VISTA EN LUGAR DE SERVIR LA CARPETA MEDIA
    ----------------------------------------------------------------------
    Es la decisión más importante de la HU-12, y la más fácil de hacer mal.

    Lo habitual en un proyecto Django es añadir en urls.py:

        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    …y en producción un `location /media/` en Nginx. Con eso, **cualquiera que
    conozca o adivine la dirección de un archivo lo descarga: sin sesión, sin rol y
    sin dejar rastro**. Para un logotipo da igual. Para la fotografía de la casa de
    una familia censada, es publicar datos personales en internet.

    OPSO no sirve MEDIA_ROOT en ningún entorno. Los archivos se entregan por aquí, y
    aquí se comprueba:

      - que haya sesión iniciada y permiso del módulo (el mixin),
      - y que quien pregunta tenga algo que ver con esa vivienda (get_queryset).

    El nombre del archivo en disco es un UUID, así que aunque un día alguien
    configure mal el servidor web, la dirección no se encuentra probando. Eso es una
    segunda línea de defensa, no un sustituto de esta vista.

    ----------------------------------------------------------------------
    FileResponse, Y LO QUE APORTAN SUS DOS CABECERAS
    ----------------------------------------------------------------------
    FileResponse envía el archivo por trozos en vez de cargarlo entero en memoria:
    con varias personas mirando fotos a la vez, la diferencia es el servidor.

    `Content-Disposition: inline` hace que el navegador la muestre en vez de
    descargarla, y `X-Content-Type-Options: nosniff` le prohíbe adivinar el tipo:
    si por lo que fuera llegara a haber un archivo que no es una imagen, el
    navegador no lo interpretará como otra cosa.

    ----------------------------------------------------------------------
    EN PRODUCCIÓN
    ----------------------------------------------------------------------
    Servir archivos desde Python es más lento que hacerlo desde el servidor web. La
    forma correcta de recuperar ese rendimiento SIN perder el control de acceso es
    la cabecera `X-Accel-Redirect` (Nginx) o `X-Sendfile` (Apache): Django decide si
    la persona puede, y el servidor web entrega el archivo. Se deja anotado aquí
    porque es un cambio de una línea y conviene no improvisarlo.
    """

    permisos_requeridos = ("fichas.ver_propias", "fichas.ver_todas")
    mensaje_sin_permiso = "No tienes permiso para consultar el módulo de encuestas."

    def get_queryset(self):
        """Quién puede ver la foto de qué vivienda.

        Mismo criterio que ViviendaDetalleView: con `fichas.ver_todas` se ven todas
        —es lo que necesita el supervisor para revisar—; sin ese permiso, solo las
        de viviendas donde se tiene trabajo o territorio asignado.
        """
        consulta = Fotografia.objects.select_related("vivienda", "vivienda__zona")

        if self.request.user.tiene_permiso("fichas.ver_todas"):
            return consulta

        return consulta.filter(
            Q(vivienda__encuestas__censista=self.request.user)
            | Q(vivienda__zona__in=zonas_disponibles(self.request.user))
        ).distinct()

    def get(self, request, *args, **kwargs):
        fotografia = get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])

        try:
            archivo = fotografia.imagen.open("rb")
        except FileNotFoundError:
            # La fila existe y el archivo no: un respaldo restaurado a medias, o un
            # borrado a mano en el disco. Se responde 404 y no 500 porque, desde
            # fuera, «esta foto no está» es exactamente lo que ocurre.
            raise Http404("El archivo de esta fotografía ya no está disponible.")

        respuesta = FileResponse(archivo, as_attachment=False)
        respuesta["X-Content-Type-Options"] = "nosniff"
        # Las fotos son datos personales: que no queden en cachés compartidas.
        respuesta["Cache-Control"] = "private, max-age=0, no-store"

        return respuesta


# ==========================================================================
# HU-13 — LA REVISIÓN DEL SUPERVISOR
# ==========================================================================

# --------------------------------------------------------------------------
# EL ORDEN DE LA BANDEJA: LA QUE LLEVA MÁS ESPERANDO, PRIMERO
#
# Es el criterio OPUESTO al de «Mis encuestas» (HU-07), donde manda la urgencia. No
# es una incoherencia: son dos colas distintas.
#
# El encuestador elige a qué puerta va y le conviene atacar primero lo que bloquea a
# otros. El supervisor no elige: recibe una cola, y la única política justa para una
# cola es atenderla en orden de llegada. Ordenarla por «lo más fácil» o «lo más
# nuevo» produce fichas antiguas que no se revisan nunca, y una ficha revisada tres
# semanas tarde ya no se puede corregir: el encuestador no recuerda esa casa y
# probablemente ya no trabaja esa zona.
# --------------------------------------------------------------------------


class RevisionMixin(PermisoRequeridoMixin):
    """Puerta de las pantallas de supervisión.

    `fichas.ver_todas` es el permiso correcto y no `fichas.validar`: estas dos
    pantallas solo LEEN. Quien puede ver el trabajo de todos puede revisarlo; poder
    aprobarlo o devolverlo es otra cosa y llega con las historias siguientes, que
    sí exigirán `fichas.validar`.

    Separarlos permite algo real: un coordinador que necesita mirar cómo va el
    operativo puede recibir `ver_todas` sin quedar habilitado para validar fichas.
    """

    permisos_requeridos = ("fichas.ver_todas",)
    mensaje_sin_permiso = (
        "No tienes permiso para revisar las encuestas de otras personas."
    )

    @staticmethod
    def encuestas_revisables():
        """Todas las encuestas ya levantadas, con lo necesario para juzgarlas.

        Se excluyen las PENDIENTES: una puerta que nadie ha tocado no es trabajo
        recibido y llenaría la bandeja de ruido. Las cerradas sin levantar
        —no ubicada, rechazada— SÍ entran: el supervisor tiene que poder leer el
        motivo y decidir si manda a otra persona.

        Es estático (no usa `self`) a propósito: así lo reutilizan también las
        exportaciones de reportes (HU-19), que exigen `reportes.exportar` y no
        `fichas.ver_todas`, sin tener que heredar de este mixin.
        """
        return (
            Encuesta.objects.exclude(estado=EstadoEncuesta.PENDIENTE)
            .select_related(
                "vivienda",
                "vivienda__zona",
                "vivienda__zona__sector",
                "vivienda__zona__sector__comuna",
                "vivienda__zona__sector__operativo",
                "censista",
                "grupo_familiar",
            )
        )


class BandejaRevisionView(RevisionMixin, ListView):
    """Las encuestas recibidas, en orden de llegada.

    URL: /encuestas/revision/

    ----------------------------------------------------------------------
    ESTA ES «LA EXCEPCIÓN» QUE LA HU-07 DEJÓ ANUNCIADA
    ----------------------------------------------------------------------
    Cuando se escribieron las URL del módulo, la HU-07 justificó que el listado
    propio del encuestador fuera la raíz `/encuestas/` con esta frase:

        «Cuando la historia de supervisión agregue el listado de TODAS las
        encuestas del operativo, esa irá en su propia subruta, porque será la
        excepción.»

    Esta es esa pantalla y esa subruta.

    ----------------------------------------------------------------------
    LO QUE MUESTRA CADA FILA, Y POR QUÉ
    ----------------------------------------------------------------------
    Revisar no es leer una ficha entera: es decidir CUÁL abrir. Por eso la fila
    lleva los cuatro números que permiten sospechar antes de entrar —personas
    registradas contra declaradas, si la vivienda está descrita, si tiene ubicación
    y cuántas fotos— más los días que lleva esperando.

    Con eso, una bandeja de cuarenta fichas se recorre en un minuto y se entra solo
    a las que lo piden.
    """

    permisos_requeridos = ("fichas.ver_todas",)
    model = Encuesta
    template_name = "fichas/revision_bandeja.html"
    context_object_name = "encuestas"
    paginate_by = 25

    def get_queryset(self):
        consulta = self.encuestas_revisables().prefetch_related(
            "grupo_familiar__integrantes", "vivienda__fotografias"
        )

        self.filtro = FiltroRevisionForm(self.request.GET or None)

        if self.filtro.is_valid():
            consulta = self.aplicar_filtros(consulta, self.filtro.cleaned_data)
        else:
            # Sin filtros válidos se muestra lo que espera revisión, que es la
            # razón por la que alguien abre esta pantalla.
            consulta = consulta.filter(estado=EstadoEncuesta.COMPLETADA)

        # Orden de llegada: nulls al final, para que una fila sin fecha —que no
        # debería existir— no encabece la cola.
        return consulta.order_by(F("cerrada_en").asc(nulls_last=True), "id")

    @staticmethod
    def aplicar_filtros(consulta, datos):
        """Aplica sobre `consulta` los filtros ya limpios de un `FiltroRevisionForm`.

        Estático porque no depende de la petición: es estático también para que
        las exportaciones de reportes (HU-19) apliquen exactamente el mismo
        criterio de filtrado que esta pantalla sin heredar de `BandejaRevisionView`
        ni duplicar esta lógica.
        """
        estado = datos.get("estado")

        if estado == FiltroRevisionForm.GRUPO_RECIBIDAS:
            consulta = consulta.filter(estado=EstadoEncuesta.COMPLETADA)
        elif estado == FiltroRevisionForm.GRUPO_REVISADAS:
            # El grupo «ya revisadas» se arma con ESTADOS_RESUELTOS y no a mano,
            # para que una cuarta resolución futura aparezca aquí sola.
            consulta = consulta.filter(estado__in=ESTADOS_RESUELTOS)
        elif estado != FiltroRevisionForm.GRUPO_TODAS:
            consulta = consulta.filter(estado=estado)

        if texto := datos.get("q"):
            consulta = consulta.filter(
                Q(vivienda__direccion__icontains=texto)
                | Q(grupo_familiar__jefe_hogar_nombre__icontains=texto)
            )

        if operativo := datos.get("operativo"):
            consulta = consulta.filter(vivienda__zona__sector__operativo=operativo)

        if sector := datos.get("sector"):
            consulta = consulta.filter(vivienda__zona__sector=sector)

        if censista := datos.get("censista"):
            consulta = consulta.filter(censista=censista)

        # HU-18: rango de fechas sobre `cerrada_en`. `__date` compara en la zona
        # horaria local (TIME_ZONE), igual que `dias_esperando` en el modelo, para
        # que un cierre de las 23:50 no caiga en el día siguiente por estar en UTC.
        if fecha_desde := datos.get("fecha_desde"):
            consulta = consulta.filter(cerrada_en__date__gte=fecha_desde)

        if fecha_hasta := datos.get("fecha_hasta"):
            consulta = consulta.filter(cerrada_en__date__lte=fecha_hasta)

        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)

        contexto["titulo_pagina"] = "Revisión de encuestas"
        contexto["filtro"] = self.filtro

        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        contexto["parametros"] = parametros.urlencode()

        contexto["resumen"] = self.resumen()
        contexto["mas_antigua"] = self.mas_antigua()
        return contexto

    def resumen(self):
        """Los contadores de la cola, en una sola consulta.

        Se calculan sobre TODAS las encuestas revisables y no sobre lo filtrado, por
        lo mismo que en la HU-07: un contador que cambia al filtrar responde «cuánto
        hay de lo que estoy mirando», que ya se ve en la lista.
        """
        return self.encuestas_revisables().aggregate(
            recibidas=Count("id", filter=Q(estado=EstadoEncuesta.COMPLETADA)),
            validadas=Count("id", filter=Q(estado=EstadoEncuesta.VALIDADA)),
            observadas=Count("id", filter=Q(estado=EstadoEncuesta.OBSERVADA)),
            anuladas=Count("id", filter=Q(estado=EstadoEncuesta.ANULADA)),
            sin_levantar=Count("id", filter=Q(estado__in=ESTADOS_SIN_LEVANTAR)),
        )

    def mas_antigua(self):
        """La encuesta que lleva más tiempo esperando, o None si no hay ninguna.

        Se muestra aparte de la lista porque es el indicador de salud de la cola: si
        la más antigua lleva tres semanas, el problema no es esa ficha, es el ritmo
        de revisión. Y es lo que hace visible que devolver una encuesta tarde ya no
        sirve de nada.
        """
        return (
            self.encuestas_revisables()
            .filter(estado=EstadoEncuesta.COMPLETADA, cerrada_en__isnull=False)
            .order_by("cerrada_en")
            .first()
        )


def _encuestas_filtradas_para_reporte(get_params):
    """Las mismas encuestas que vería la bandeja con estos parámetros de URL.

    Comparte el criterio exacto de `BandejaRevisionView.get_queryset()`
    (`encuestas_revisables()` + `aplicar_filtros()`, ambos `@staticmethod` por
    esto mismo) porque el reporte responde «¿cómo va lo que estoy mirando
    ahora mismo?»: si exportar aplicara el filtro de otro modo, un supervisor
    podría descargar un PDF que no coincide con la pantalla desde la que lo pidió.
    """
    consulta = RevisionMixin.encuestas_revisables()
    filtro = FiltroRevisionForm(get_params or None)

    if filtro.is_valid():
        consulta = BandejaRevisionView.aplicar_filtros(consulta, filtro.cleaned_data)
    else:
        consulta = consulta.filter(estado=EstadoEncuesta.COMPLETADA)

    return consulta


class ReporteMixin(PermisoRequeridoMixin):
    """Puerta de las exportaciones de reportes (HU-19).

    `reportes.exportar`, no `fichas.ver_todas`. El reporte solo lleva conteos
    —ningún dato de una familia— así que puede vivir separado del permiso que
    abre la ficha de otra persona: es la misma separación de responsabilidades
    que `RevisionMixin` ya hizo entre `ver_todas` y `validar` en la HU-13.
    """

    permisos_requeridos = ("reportes.exportar",)
    mensaje_sin_permiso = "No tienes permiso para exportar reportes."


class ExportarReporteExcelView(ReporteMixin, View):
    """El resumen de resultados filtrado, como archivo .xlsx.

    URL: /encuestas/revision/reporte.xlsx

    Acepta los mismos parámetros de query que la bandeja de revisión
    (`?estado=&sector=&censista=&fecha_desde=&fecha_hasta=`, HU-13 y HU-18):
    exportar es "descargar lo que estoy viendo", no una pantalla aparte.
    """

    def get(self, request, *args, **kwargs):
        consulta = _encuestas_filtradas_para_reporte(request.GET)
        resumen = Encuesta.resumen_para_reporte(consulta)
        libro = construir_reporte_excel(resumen)

        respuesta = HttpResponse(
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            )
        )
        nombre = f"reporte_operativo_{timezone.localdate().isoformat()}.xlsx"
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
        libro.save(respuesta)
        return respuesta


class ExportarReportePDFView(ReporteMixin, View):
    """El resumen de resultados filtrado, como archivo .pdf.

    URL: /encuestas/revision/reporte.pdf

    Mismos parámetros de query que `ExportarReporteExcelView`, por la misma razón.
    """

    def get(self, request, *args, **kwargs):
        consulta = _encuestas_filtradas_para_reporte(request.GET)
        resumen = Encuesta.resumen_para_reporte(consulta)

        respuesta = HttpResponse(content_type="application/pdf")
        nombre = f"reporte_operativo_{timezone.localdate().isoformat()}.pdf"
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
        construir_reporte_pdf(respuesta, resumen)
        return respuesta


class BaseConsolidadaMixin(PermisoRequeridoMixin):
    """Puerta de la base consolidada (HU-20).

    `reportes.exportar_base`, un permiso DISTINTO de `reportes.exportar`
    (HU-19) y a propósito: aquel descarga agregados —conteos, sin un solo dato
    de una familia—, y este descarga nombre, RUT, teléfono e ingreso del hogar
    de cada persona. Que compartieran permiso le habría dado a cualquiera con
    `reportes.exportar` —hoy, el rol Supervisor completo— acceso a datos
    personales que esta historia solo le pide al administrador. La migración
    `0008_permiso_exportar_base` se lo concede explícitamente solo al rol
    ADMINISTRADOR —a nadie más—, igual que 0005 hizo con el reparto inicial.
    """

    permisos_requeridos = ("reportes.exportar_base",)
    mensaje_sin_permiso = "No tienes permiso para exportar la base consolidada."


class ExportarBaseExcelView(BaseConsolidadaMixin, View):
    """La base consolidada completa, como archivo .xlsx.

    URL: /encuestas/base-consolidada.xlsx

    Sin filtros: a diferencia de la HU-19, esta historia pidió exportar «la
    base consolidada», no un recorte —ver `docs/HU-20_*.md` para la decisión—.
    """

    def get(self, request, *args, **kwargs):
        libro = construir_base_excel(Integrante.base_consolidada())

        respuesta = HttpResponse(
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            )
        )
        nombre = f"base_consolidada_{timezone.localdate().isoformat()}.xlsx"
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
        libro.save(respuesta)
        return respuesta


class ExportarBaseCSVView(BaseConsolidadaMixin, View):
    """La base consolidada completa, como archivo .csv.

    URL: /encuestas/base-consolidada.csv
    """

    def get(self, request, *args, **kwargs):
        respuesta = HttpResponse(content_type="text/csv")
        nombre = f"base_consolidada_{timezone.localdate().isoformat()}.csv"
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
        construir_base_csv(respuesta, Integrante.base_consolidada())
        return respuesta


class RevisarEncuestaView(RevisionMixin, DetailView):
    """La encuesta completa en una sola pantalla, para poder juzgarla.

    URL: /encuestas/<pk>/revisar/

    ----------------------------------------------------------------------
    POR QUÉ NO SIRVE LA FICHA QUE YA EXISTÍA
    ----------------------------------------------------------------------
    `EncuestaDetailView` (HU-07) está pensada para el encuestador: le dice dónde
    queda la casa y qué le falta por hacer. Para revisar hace falta lo contrario:
    ver TODO lo levantado junto —la vivienda con sus seis características, el hogar,
    las personas una por una, la ubicación y las fotografías— sin abrir cinco
    pantallas.

    Reutilizar aquella habría significado llenarla de bloques que al encuestador no
    le sirven, y aun así obligar al supervisor a navegar. Son dos lecturas distintas
    del mismo dato, y cada una merece su pantalla.

    ----------------------------------------------------------------------
    SOLO LEE
    ----------------------------------------------------------------------
    No hay ningún botón que cambie el estado. Aprobar, rechazar y devolver con
    observaciones son las historias siguientes del sprint y exigirán
    `fichas.validar`, que esta vista no pide.
    """

    permisos_requeridos = ("fichas.ver_todas",)
    model = Encuesta
    template_name = "fichas/revision_encuesta.html"
    context_object_name = "encuesta"

    def get_queryset(self):
        return self.encuestas_revisables().select_related(
            "vivienda__zona__sector__comuna__region", "asignada_por"
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        encuesta = self.object
        hogar = getattr(encuesta, "grupo_familiar", None)

        contexto["titulo_pagina"] = f"Revisar {encuesta.direccion}"
        contexto["hogar"] = hogar
        contexto["integrantes"] = (
            hogar.integrantes_ordenados() if hogar is not None else []
        )
        contexto["fotografias"] = encuesta.vivienda.fotografias.all()
        contexto["resumen"] = encuesta.resumen_para_revision()

        # Los otros hogares de la misma vivienda: al revisar importa saber si esa
        # casa tiene una segunda familia, porque explica un ingreso por persona
        # extraño o una cantidad de gente que no cuadra con la fachada.
        contexto["otros_hogares"] = (
            encuesta.vivienda.encuestas.exclude(pk=encuesta.pk)
            .select_related("censista", "grupo_familiar")
            .order_by("id")
        )

        # HU-14: los botones de resolver. Se dibujan con `fichas.validar` y la
        # pantalla se abre con `fichas.ver_todas`, así que quien solo puede mirar
        # ve la ficha completa sin acciones. Cuando no se puede resolver se explica
        # el motivo en vez de esconder los botones en silencio: un supervisor
        # mirando su propia ficha necesita saber que es la separación de funciones y
        # no un fallo.
        puede, motivo = encuesta.puede_resolverla(self.request.user)

        contexto["puede_validar"] = puede and self.request.user.tiene_permiso(
            "fichas.validar"
        )
        contexto["motivo_no_resoluble"] = (
            motivo
            if not puede and self.request.user.tiene_permiso("fichas.validar")
            else ""
        )
        return contexto


# ==========================================================================
# HU-14 — APROBAR O ANULAR
# ==========================================================================


class ResolverEncuestaMixin(PermisoRequeridoMixin):
    """Puerta de las pantallas que RESUELVEN una encuesta.

    Aquí sí se exige `fichas.validar`, y no `fichas.ver_todas` como en la HU-13. Es
    el corte que aquella historia dejó preparado: leer el trabajo de todos y
    firmarlo son dos capacidades distintas, y separarlas permite que un coordinador
    mire el operativo sin quedar habilitado para aprobar fichas.

    El permiso lo sembró la HU-04 con esta descripción, escrita cuando no existía
    ninguna pantalla de fichas: «Revisar el trabajo de un censista y aprobarlo o
    devolverlo con observaciones. Es el control de calidad del censo.» Dos historias
    después, es exactamente lo que hace.
    """

    permisos_requeridos = ("fichas.validar",)
    mensaje_sin_permiso = "No tienes permiso para aprobar ni anular encuestas."

    @cached_property
    def encuesta(self):
        """Cualquier encuesta ya levantada: quien resuelve no necesita ser su dueño.

        Es lo contrario de las pantallas del encuestador, que filtran por
        `censista=request.user`. Aquí el filtro sería absurdo —resolver es
        precisamente actuar sobre el trabajo de otra persona— y la regla que
        importa es la inversa: no resolver el PROPIO. Eso lo comprueba
        `puede_resolverla()`.
        """
        return get_object_or_404(
            Encuesta.objects.exclude(estado=EstadoEncuesta.PENDIENTE).select_related(
                "vivienda",
                "vivienda__zona",
                "vivienda__zona__sector",
                "censista",
                "grupo_familiar",
            ),
            pk=self.kwargs["pk"],
        )

    def comprobar_resoluble(self):
        """None si se puede resolver, o una redirección con el motivo si no.

        Se comprueba en el GET y en el POST. No es paranoia: la dirección del POST
        se puede enviar a mano, y dos supervisores mirando la misma bandeja pueden
        pulsar el botón de la misma ficha con segundos de diferencia. El segundo
        tiene que encontrarse con «ya está resuelta» y no sobrescribir la decisión
        del primero.
        """
        permitido, motivo = self.encuesta.puede_resolverla(self.request.user)

        if permitido:
            return None

        messages.error(self.request, motivo)
        return redirect("fichas:revisar_encuesta", pk=self.encuesta.pk)

    def contexto_base(self):
        """Lo que las dos pantallas muestran de la encuesta que se va a resolver.

        Las dos enseñan un resumen antes de pedir la confirmación, porque las dos
        decisiones son difíciles de revertir: una encuesta validada ya no la puede
        tocar el encuestador, y una anulada descarta su trabajo. Confirmar a ciegas
        es exactamente lo que no debe pasar.
        """
        hogar = getattr(self.encuesta, "grupo_familiar", None)

        return {
            "encuesta": self.encuesta,
            "hogar": hogar,
            "resumen": self.encuesta.resumen_para_revision(),
            "integrantes": hogar.integrantes_ordenados() if hogar else [],
        }


class ValidarEncuestaView(ResolverEncuestaMixin, View):
    """Aprueba una encuesta. GET confirma, POST ejecuta.

    URL: /encuestas/<pk>/validar/

    ----------------------------------------------------------------------
    LO QUE SIGNIFICA VALIDAR
    ----------------------------------------------------------------------
    La ficha pasa a VALIDADA y sale definitivamente del circuito: el encuestador ya
    no puede modificarla —`puede_registrarse()` lo impide desde la HU-08— y deja de
    aparecer en la cola de revisión. Es el final feliz del recorrido que empezó en
    la HU-07.

    Dos pasos y no un botón directo desde la bandeja, por lo mismo que en toda la
    aplicación: un GET debe ser seguro, y si validar se pudiera hacer con un GET, un
    `<img src="...">` incrustado en cualquier página aprobaría fichas con la sesión
    del supervisor. Además, la pantalla intermedia es la última oportunidad de mirar
    el resumen antes de firmar.
    """

    template_name = "fichas/encuesta_validar.html"

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_resoluble()) is not None:
            return respuesta

        return render(request, self.template_name, self.contexto(ValidarEncuestaForm()))

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_resoluble()) is not None:
            return respuesta

        formulario = ValidarEncuestaForm(request.POST)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        with transaction.atomic():
            self.encuesta.resolver(
                EstadoEncuesta.VALIDADA,
                usuario=request.user,
                comentario=formulario.cleaned_data["comentario"],
            )

        messages.success(
            request,
            f"Encuesta de {self.encuesta.direccion} validada. El encuestador ya no "
            "puede modificarla.",
        )
        return redirect("fichas:bandeja_revision")

    def contexto(self, formulario):
        return {
            **self.contexto_base(),
            "titulo_pagina": f"Validar {self.encuesta.direccion}",
            "form": formulario,
        }


class AnularEncuestaView(ResolverEncuestaMixin, View):
    """Descarta una encuesta que no sirve. GET muestra el formulario, POST ejecuta.

    URL: /encuestas/<pk>/anular/

    ----------------------------------------------------------------------
    ANULAR ES LA DECISIÓN MÁS GRAVE DE ESTA PANTALLA
    ----------------------------------------------------------------------
    Tira el trabajo de otra persona y deja esa vivienda sin datos en el censo. No es
    lo mismo que devolverla con observaciones —la historia siguiente—, que la reabre
    para que se corrija: anular cierra sin corregir, porque no hay nada que arreglar
    o porque arreglarlo exigiría levantarla de cero.

    De ahí las tres cosas que pide el formulario: una causa de una lista cerrada,
    una explicación de al menos una frase y una casilla de confirmación que dice en
    voz alta la consecuencia. Ninguna de las tres es burocracia: la ficha anulada la
    va a leer el encuestador cuyo trabajo se descarta.

    ----------------------------------------------------------------------
    LO QUE NO HACE, Y ES A PROPÓSITO
    ----------------------------------------------------------------------
    No borra nada. La encuesta, su hogar, sus integrantes y sus fotografías siguen
    ahí, marcados como anulados. Borrarlos sería tentador —«no sirven»— y sería un
    error: el registro de que ALGUIEN levantó esa ficha y de que otra persona la
    descartó, con su motivo, es justamente lo que permite auditar el operativo y
    detectar si un encuestador está inventando datos.

    Es la misma distinción que la HU-09 razonó al permitir borrar un integrante: allí
    se borraba un dato capturado por error, sin pasado que explicar. Aquí hay pasado
    y explica algo.
    """

    template_name = "fichas/encuesta_anular.html"

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_resoluble()) is not None:
            return respuesta

        return render(request, self.template_name, self.contexto(AnularEncuestaForm()))

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_resoluble()) is not None:
            return respuesta

        formulario = AnularEncuestaForm(request.POST)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        with transaction.atomic():
            self.encuesta.resolver(
                EstadoEncuesta.ANULADA,
                usuario=request.user,
                comentario=formulario.comentario_completo(),
            )

        messages.warning(
            request,
            f"Encuesta de {self.encuesta.direccion} anulada. Esa vivienda quedó sin "
            "datos: si hay que volver a levantarla, cárgala de nuevo.",
        )
        return redirect("fichas:bandeja_revision")

    def contexto(self, formulario):
        return {
            **self.contexto_base(),
            "titulo_pagina": f"Anular {self.encuesta.direccion}",
            "form": formulario,
        }


# ==========================================================================
# HU-15 — DEVOLVER CON OBSERVACIONES
# ==========================================================================


class DevolverEncuestaView(ResolverEncuestaMixin, View):
    """Devuelve una encuesta al encuestador para que la corrija.

    URL: /encuestas/<pk>/devolver/

    ----------------------------------------------------------------------
    LA TERCERA SALIDA DE LA REVISIÓN
    ----------------------------------------------------------------------
    La HU-14 dejó dos: validar cierra bien y anular cierra mal. Faltaba la del medio,
    que es la más frecuente en un censo real: la ficha se puede salvar, pero le falta
    algo. Devolverla la pasa a OBSERVADA y la REABRE.

    «Reabrir» no es una metáfora: OBSERVADA pertenece a ESTADOS_ABIERTOS desde la
    HU-07, así que `cambiar_estado()` borra `cerrada_en` y la ficha vuelve a la lista
    de trabajo pendiente del encuestador —arriba, porque `ORDEN_POR_URGENCIA` la pone
    primera—, editable otra vez porque `puede_registrarse()` mira si está abierta. No
    hubo que tocar nada de eso: la HU-07 modeló el estado, la HU-10 modeló las
    transiciones y esta historia solo añade quién lo dispara y con qué texto.

    ----------------------------------------------------------------------
    POR QUÉ NO ES UN BOTÓN DIRECTO
    ----------------------------------------------------------------------
    Por lo mismo que validar y anular: un GET no debe cambiar nada, y aquí además hay
    algo que escribir. Pero la pantalla intermedia gana un segundo propósito propio,
    que es la razón de que exista `problemas_detectados()`: llega con las
    observaciones ya redactadas a partir de lo que el sistema sabe contar. El
    supervisor corrige y añade en vez de escribir de cero, y así la devolución no se
    queda en «revisar» por pereza.
    """

    template_name = "fichas/encuesta_devolver.html"

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_resoluble()) is not None:
            return respuesta

        return render(
            request,
            self.template_name,
            self.contexto(DevolverEncuestaForm(encuesta=self.encuesta)),
        )

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_resoluble()) is not None:
            return respuesta

        formulario = DevolverEncuestaForm(request.POST, encuesta=self.encuesta)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        with transaction.atomic():
            self.encuesta.devolver(
                usuario=request.user,
                observaciones=formulario.comentario_completo(),
            )

        messages.success(
            request,
            f"Encuesta de {self.encuesta.direccion} devuelta a "
            f"{self.encuesta.censista.get_full_name() or self.encuesta.censista.email}. "
            "Volverá a la cola de revisión cuando la corrija y la envíe otra vez.",
        )
        return redirect("fichas:bandeja_revision")

    def contexto(self, formulario):
        return {
            **self.contexto_base(),
            "titulo_pagina": f"Devolver {self.encuesta.direccion}",
            "form": formulario,
            # Se pasa aparte de `form` porque la plantilla lo enseña como lista, no
            # como campo: el supervisor tiene que poder ver lo que el sistema detectó
            # incluso si borra el texto prerrellenado.
            "problemas": self.encuesta.problemas_detectados(),
        }
