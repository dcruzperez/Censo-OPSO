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


class RegistrarViviendaView(RegistroEnTerrenoMixin, View):
    """Alta de una vivienda nueva y de su primera encuesta. GET muestra, POST guarda.

    URL: /encuestas/viviendas/nueva/

    ----------------------------------------------------------------------
    UNA VIVIENDA NUEVA NACE SIEMPRE CON UNA ENCUESTA
    ----------------------------------------------------------------------
    Guardar la vivienda crea además la encuesta de quien la registró, en estado
    BORRADOR. Las dos cosas ocurren en la misma transacción y no hay pantalla para
    hacer solo una.

    Es deliberado: nadie registra una vivienda en terreno «por si acaso». Se
    registra porque se está ahí, tocando esa puerta, y por lo tanto el trabajo
    empezó. Dejar la vivienda sin encuesta produciría casas que no le aparecen a
    nadie en «Mis encuestas» y que nadie va a levantar; dejar la encuesta en
    PENDIENTE diría que todavía no se visita, y la visita es justamente lo que
    acaba de pasar.

    ----------------------------------------------------------------------
    POR QUÉ View Y NO CreateView
    ----------------------------------------------------------------------
    Mismo motivo que AsignarSectorView en la HU-06: aquí no se guarda UN objeto.
    Se guardan dos, en una transacción, y el destino depende del segundo. Con
    CreateView habría que sobrescribir `form_valid`, `get_form_kwargs` y
    `get_success_url` hasta no dejar nada del comportamiento original.
    """

    template_name = "fichas/vivienda_form.html"

    def formulario(self, datos=None):
        return ViviendaForm(datos, censista=self.request.user)

    def hay_donde_registrar(self):
        """¿Tiene esta persona alguna zona donde registrar? Si no, no hay pantalla.

        Se comprueba antes de dibujar el formulario porque un formulario cuyo
        primer desplegable está vacío no se puede completar, y dejar que la persona
        lo descubra rellenando los otros nueve campos es maltratarla.
        """
        return zonas_disponibles(self.request.user).exists()

    def get(self, request, *args, **kwargs):
        if not self.hay_donde_registrar():
            return render(request, "fichas/sin_territorio.html", self.contexto_vacio())

        return render(request, self.template_name, self.contexto(self.formulario()))

    def post(self, request, *args, **kwargs):
        if not self.hay_donde_registrar():
            return render(request, "fichas/sin_territorio.html", self.contexto_vacio())

        formulario = self.formulario(request.POST)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        # Las dos escrituras en una sola transacción: una vivienda sin su encuesta
        # sería una casa que no le aparece a nadie, y es peor que no haber
        # guardado nada.
        with transaction.atomic():
            vivienda = formulario.save()
            encuesta = Encuesta.objects.create(
                vivienda=vivienda, censista=request.user
            )
            encuesta.cambiar_estado(EstadoEncuesta.BORRADOR)

        messages.success(
            request,
            f"Vivienda «{vivienda.direccion}» registrada. Ahora completa los datos "
            "del hogar.",
        )
        return redirect("fichas:registrar_hogar", pk=encuesta.pk)

    def contexto(self, formulario):
        return {
            "titulo_pagina": "Registrar una vivienda",
            "form": formulario,
            "duplicadas": getattr(formulario, "duplicadas", None),
            "es_alta": True,
        }

    def contexto_vacio(self):
        return {"titulo_pagina": "Registrar una vivienda"}


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


