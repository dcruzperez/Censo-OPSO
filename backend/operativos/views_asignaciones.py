"""Vistas del reparto de sectores (HU-06).

Cuatro pantallas, y por primera vez en el proyecto el protagonista NO es el
administrador:

    /operativos/<pk>/asignaciones/          panel de reparto del operativo
    /operativos/sectores/<pk>/asignar/      quiénes cubren un sector
    /operativos/asignaciones/<pk>/retirar/  retirar a una persona
    /operativos/mis-sectores/               lo que ve el censista

CONTROL DE ACCESO — TERCERA HISTORIA SEGUIDA SIN AGREGAR PERMISOS

    operativos.ver            -> consultar el panel de reparto
    operativos.asignar_sector -> repartir el trabajo

Los dos los sembró la migración 0005 de la HU-04, y el reparto inicial ya le daba
AMBOS al rol Supervisor. Es decir: el supervisor puede usar esta historia sin que
nadie le conceda nada, porque la HU-04 modeló su trabajo antes de que existieran
las pantallas. La descripción sembrada entonces era literalmente "Asignar
censistas a un sector — Distribuir el trabajo de terreno entre el personal
disponible".

POR QUÉ ASIGNAR ES UN PERMISO DISTINTO DE GESTIONAR

Son dos trabajos distintos y los hace gente distinta. El administrador DIBUJA el
territorio (operativos.gestionar): decide que la comuna se parte en cinco
sectores. El supervisor REPARTE ese territorio (operativos.asignar_sector): decide
quién cubre cada uno. Con un solo permiso, dejar que un supervisor reparta el
trabajo obligaría a dejarlo también redibujar el mapa, que no es su función.

Y el supervisor, en efecto, NO tiene operativos.gestionar en el reparto inicial:
puede repartir el terreno pero no alterar su división. Hay pruebas de las dos
cosas.
"""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import ListView, TemplateView

from usuarios.auditoria import describir_cambio_asignaciones, registrar_accion
from usuarios.mixins import PermisoRequeridoMixin
from usuarios.models import AccionAuditoria

from .forms_asignaciones import AsignarSectorForm, FiltroAsignacionesForm
from .models import AsignacionSector, Operativo, Sector


# ==========================================================================
# PUERTA DE ACCESO
# ==========================================================================


class RepartoTerritorialMixin(PermisoRequeridoMixin):
    """Puerta de las pantallas que REPARTEN el trabajo."""

    permisos_requeridos = ("operativos.asignar_sector",)
    mensaje_sin_permiso = (
        "No tienes permiso para asignar sectores a los encuestadores."
    )


# ==========================================================================
# 1. PANEL DE REPARTO DEL OPERATIVO
# ==========================================================================


class PanelAsignacionesView(PermisoRequeridoMixin, ListView):
    """Todos los sectores del operativo con su equipo y su carga de trabajo.

    URL: /operativos/<pk>/asignaciones/

    Es la pantalla central de la historia. Responde de un vistazo las tres
    preguntas del supervisor:

        ¿Qué sectores no tiene nadie?   -> los marcados en rojo
        ¿Quién cubre cada uno?          -> la columna del equipo
        ¿Está bien repartida la carga?  -> la columna de viviendas estimadas

    La tercera es la que convierte "asignar" en "DISTRIBUIR", que es lo que pide la
    historia. Sin la carga a la vista, repartir cinco sectores entre dos personas
    es una decisión a ciegas: podrían quedar 400 viviendas para una y 60 para la
    otra sin que nadie lo note hasta que sea tarde.

    Solo exige operativos.ver: consultar el reparto no es modificarlo. Un
    administrador que quiera revisar cómo quedó distribuido el trabajo entra aquí
    sin necesitar el permiso de asignar.
    """

    permisos_requeridos = ("operativos.ver",)
    mensaje_sin_permiso = "No tienes permiso para consultar el reparto del trabajo."

    model = Sector
    template_name = "operativos/asignaciones_panel.html"
    context_object_name = "sectores"
    paginate_by = 20

    @cached_property
    def operativo(self):
        return get_object_or_404(Operativo, pk=self.kwargs["pk"])

    def get_queryset(self):
        """Los sectores del operativo, con su equipo y su carga ya resueltos.

        Tres técnicas contra el problema N+1, cada una para lo suyo:

          select_related  -> la comuna y su región, que van en cada fila.
          Prefetch        -> las asignaciones ACTIVAS con su censista. Se usa
                             Prefetch y no prefetch_related a secas porque hay que
                             filtrar: sin el filtro se traerían también las
                             históricas y la plantilla mostraría gente que ya no
                             cubre el sector.
          annotate(Sum)   -> la carga de trabajo, sumada por PostgreSQL.

        El annotate de viviendas evita llamar a Sector.viviendas_estimadas() en la
        plantilla, que lanzaría una consulta por fila.
        """
        from django.db.models import Sum

        consulta = (
            Sector.objects.filter(operativo=self.operativo)
            .select_related("comuna", "comuna__region")
            .prefetch_related(
                Prefetch(
                    "asignaciones",
                    queryset=AsignacionSector.objects.filter(activa=True)
                    .select_related("censista")
                    .order_by("censista__first_name", "censista__last_name"),
                    to_attr="equipo",
                )
            )
            .annotate(
                n_asignados=Count(
                    "asignaciones", filter=Q(asignaciones__activa=True), distinct=True
                ),
                carga=Sum("zonas__viviendas_estimadas", filter=Q(zonas__activa=True)),
            )
            # Sin orden explícito la paginación es inconsistente: annotate genera
            # un GROUP BY y Django descarta el Meta.ordering. Es la misma trampa
            # que apareció en los listados de la HU-05.
            .order_by("comuna__region__orden", "comuna__nombre", "nombre")
        )

        self.filtro = FiltroAsignacionesForm(
            self.request.GET or None, operativo=self.operativo
        )

        if self.filtro.is_valid():
            texto = self.filtro.cleaned_data.get("q")
            cobertura = self.filtro.cleaned_data.get("cobertura")
            censista = self.filtro.cleaned_data.get("censista")

            if texto:
                consulta = consulta.filter(
                    Q(nombre__icontains=texto) | Q(comuna__nombre__icontains=texto)
                )
            if cobertura == "sin_asignar":
                consulta = consulta.filter(n_asignados=0)
            elif cobertura == "asignados":
                consulta = consulta.filter(n_asignados__gt=0)
            if censista:
                consulta = consulta.filter(
                    asignaciones__censista=censista, asignaciones__activa=True
                )

        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        operativo = self.operativo

        contexto["titulo_pagina"] = f"Reparto de {operativo.nombre}"
        contexto["operativo"] = operativo
        contexto["filtro"] = self.filtro

        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        contexto["parametros"] = parametros.urlencode()

        # Contadores GLOBALES del operativo, no de la página: responden "¿cómo va
        # el reparto?" y no deben cambiar al pasar de página.
        contexto["total_sectores"] = operativo.sectores.filter(activo=True).count()
        contexto["total_asignados"] = operativo.total_sectores_asignados()
        contexto["total_sin_asignar"] = operativo.total_sectores_sin_asignar()
        contexto["censistas_desplegados"] = operativo.censistas_desplegados()

        # La carga por persona: el dato que hace visible un reparto desequilibrado.
        contexto["carga_por_censista"] = self.carga_por_censista(operativo)

        contexto["puede_asignar"] = self.request.user.tiene_permiso(
            "operativos.asignar_sector"
        )
        contexto["reparto_abierto"] = operativo.admite_cambios_de_territorio
        return contexto

    def carga_por_censista(self, operativo):
        """Cuántos sectores y cuántas viviendas tiene cada persona en este operativo.

        Se resuelve con UNA consulta agregada sobre Usuario en vez de recorrer las
        asignaciones en Python. Es lo que permite mostrar la tabla de equilibrio
        sin que su coste crezca con el número de censistas.

        Resultado: lista de Usuario con los atributos anotados n_sectores y
        viviendas.
        """
        from django.db.models import Sum

        from usuarios.models import Usuario

        return list(
            Usuario.objects.filter(
                asignaciones_sector__sector__operativo=operativo,
                asignaciones_sector__activa=True,
            )
            .annotate(
                n_sectores=Count("asignaciones_sector__sector", distinct=True),
                viviendas=Sum(
                    "asignaciones_sector__sector__zonas__viviendas_estimadas",
                    filter=Q(asignaciones_sector__sector__zonas__activa=True),
                ),
            )
            .order_by("-n_sectores", "first_name", "last_name")
        )


# ==========================================================================
# 2. ASIGNAR: QUIÉNES CUBREN UN SECTOR
# ==========================================================================


class AsignarSectorView(RepartoTerritorialMixin, View):
    """Define el equipo de un sector. GET muestra, POST guarda.

    URL: /operativos/sectores/<pk>/asignar/

    Se escribe como View "cruda" y no heredando de FormView por lo mismo que
    MatrizPermisosView en la HU-04: aquí no se está editando UN objeto (el
    formulario no es un ModelForm de AsignacionSector, sino un conjunto de
    personas), así que FormView obligaría a sobrescribir get_form, get_form_kwargs,
    get_context_data, form_valid y form_invalid hasta no dejar nada del
    comportamiento original. Con View se escriben get() y post() y se lee de
    corrido.
    """

    template_name = "operativos/sector_asignar.html"

    @cached_property
    def sector(self):
        return get_object_or_404(
            Sector.objects.select_related("operativo", "comuna", "comuna__region"),
            pk=self.kwargs["pk"],
        )

    def comprobar_reparto_abierto(self):
        """None si se puede repartir, o una redirección con el motivo si no.

        La regla vive en Sector.puede_recibir_asignaciones() y se comprueba tanto
        en el GET como en el POST. Comprobarla solo en el GET —o solo ocultando el
        botón en la plantilla— no serviría: la URL del POST se puede enviar a mano.
        Es la misma lección que la HU-03 documentó con "no autodeshabilitarse".
        """
        permitido, motivo = self.sector.puede_recibir_asignaciones()

        if permitido:
            return None

        messages.error(self.request, motivo)
        return redirect("operativos:asignaciones_panel", pk=self.sector.operativo_id)

    def construir_formulario(self, datos=None):
        return AsignarSectorForm(
            datos, sector=self.sector, asignado_por=self.request.user
        )

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_reparto_abierto()) is not None:
            return respuesta

        return render(
            request, self.template_name, self.contexto(self.construir_formulario())
        )

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_reparto_abierto()) is not None:
            return respuesta

        formulario = self.construir_formulario(request.POST)

        if not formulario.is_valid():
            # Solo puede ser inválido si llegó el identificador de alguien que no
            # está en la lista de disponibles, lo que no ocurre usando la pantalla:
            # implica una petición manipulada. Se rechaza el POST completo en vez
            # de aplicar la parte válida, porque un reparto a medias deja sectores
            # en un estado que nadie decidió.
            messages.error(
                request,
                "No se pudo guardar: la solicitud incluía a alguien que no está "
                "disponible para este sector. No se aplicó ningún cambio.",
            )
            return render(request, self.template_name, self.contexto(formulario))

        # Una sola transacción para todo el reparto del sector, y la fila de
        # auditoría dentro. Si algo falla a mitad no queda un equipo a medio
        # armar ni un cambio sin registrar.
        with transaction.atomic():
            antes, despues = formulario.guardar()
            detalle = describir_cambio_asignaciones(antes, despues)

            if detalle:
                registrar_accion(
                    administrador=request.user,
                    accion=AccionAuditoria.CAMBIAR_ASIGNACIONES,
                    objeto_territorial=self.sector,
                    detalle=detalle,
                    request=request,
                )

        if detalle:
            messages.success(
                request,
                f"Reparto de «{self.sector.nombre}» actualizado. "
                f"{self.resumen_equipo(despues)}",
            )
        else:
            messages.info(request, "No hiciste ningún cambio en el reparto.")

        return redirect(
            "operativos:asignaciones_panel", pk=self.sector.operativo_id
        )

    def resumen_equipo(self, censistas):
        """Frase que confirma el resultado, no solo que se guardó.

        Un mensaje de éxito que dice "guardado" obliga a volver a mirar la tabla
        para saber qué quedó. Decir "lo cubren 2 personas" —o avisar de que no
        quedó nadie— cierra la operación sin que haya que verificarla.
        """
        if not censistas:
            return "Ahora no lo cubre nadie: quedó sin personal asignado."

        if len(censistas) == 1:
            nombre = censistas[0].get_full_name() or censistas[0].email
            return f"Queda a cargo de {nombre}."

        return f"Lo cubren {len(censistas)} personas."

    def contexto(self, formulario):
        return {
            "titulo_pagina": f"Asignar {self.sector.nombre}",
            "sector": self.sector,
            "operativo": self.sector.operativo,
            "form": formulario,
            "seleccionados": formulario.censistas_seleccionados(),
            # El historial del sector: quién lo cubrió antes. Da contexto para
            # decidir ("Juan ya trabajó aquí en el operativo anterior").
            "historial": self.sector.asignaciones.filter(activa=False)
            .select_related("censista")
            .order_by("-desasignado_en"),
            "carga": self.sector.viviendas_estimadas(),
            "hay_censistas": formulario.fields["censistas"].queryset.exists(),
        }


# ==========================================================================
# 3. RETIRAR UNA ASIGNACIÓN
# ==========================================================================


class RetirarAsignacionView(RepartoTerritorialMixin, View):
    """Retira a una persona de un sector. GET confirma, POST ejecuta.

    URL: /operativos/asignaciones/<pk>/retirar/

    Existe además del formulario de conjunto porque son dos gestos distintos:
    rearmar el equipo de un sector es una decisión de planificación, y sacar a una
    persona concreta —se enfermó, renunció, se va a otro sector— es una corrección
    puntual. Obligar a pasar por la pantalla completa para eso invita a desmarcar
    la casilla equivocada.

    Dos pasos por la misma razón que en toda la aplicación: un GET debe ser seguro,
    y si retirar se pudiera hacer con un GET, un <img src="..."> incrustado en
    cualquier página lo ejecutaría con la sesión del supervisor (ataque CSRF).
    """

    template_name = "operativos/asignacion_retirar.html"

    @cached_property
    def asignacion(self):
        return get_object_or_404(
            AsignacionSector.objects.select_related(
                "censista", "sector", "sector__operativo", "sector__comuna"
            ),
            pk=self.kwargs["pk"],
        )

    def comprobar_reparto_abierto(self):
        permitido, motivo = self.asignacion.sector.puede_recibir_asignaciones()

        if permitido:
            return None

        messages.error(self.request, motivo)
        return redirect(
            "operativos:asignaciones_panel",
            pk=self.asignacion.sector.operativo_id,
        )

    def get(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_reparto_abierto()) is not None:
            return respuesta

        return render(request, self.template_name, self.contexto())

    def post(self, request, *args, **kwargs):
        if (respuesta := self.comprobar_reparto_abierto()) is not None:
            return respuesta

        asignacion = self.asignacion
        sector = asignacion.sector

        if not asignacion.activa:
            # Ya estaba retirada: probablemente se recargó la página o se abrió el
            # enlace dos veces. No se escribe en la bitácora un hecho que no
            # ocurrió ni se avisa de un éxito falso.
            messages.info(
                request,
                f"{asignacion.censista.get_full_name() or asignacion.censista.email} "
                f"ya no tenía «{sector.nombre}» a cargo.",
            )
            return redirect("operativos:asignaciones_panel", pk=sector.operativo_id)

        with transaction.atomic():
            asignacion.desactivar()

            registrar_accion(
                administrador=request.user,
                accion=AccionAuditoria.CAMBIAR_ASIGNACIONES,
                objeto_territorial=sector,
                detalle=describir_cambio_asignaciones([asignacion.censista], []),
                request=request,
            )

        restantes = sector.asignaciones.filter(activa=True).count()
        aviso = (
            "El sector quedó sin personal asignado."
            if restantes == 0
            else f"El sector sigue cubierto por {restantes} persona(s)."
        )

        messages.success(
            request,
            f"{asignacion.censista.get_full_name() or asignacion.censista.email} "
            f"ya no tiene «{sector.nombre}» a cargo. {aviso}",
        )
        return redirect("operativos:asignaciones_panel", pk=sector.operativo_id)

    def contexto(self):
        sector = self.asignacion.sector
        return {
            "titulo_pagina": f"Retirar de {sector.nombre}",
            "asignacion": self.asignacion,
            "sector": sector,
            "operativo": sector.operativo,
            "otros": sector.asignaciones.filter(activa=True)
            .exclude(pk=self.asignacion.pk)
            .select_related("censista"),
        }


# ==========================================================================
# 4. LO QUE VE EL CENSISTA
# ==========================================================================


class MisSectoresView(TemplateView):
    """Los sectores que la persona que entró tiene a cargo.

    URL: /operativos/mis-sectores/

    ----------------------------------------------------------------------
    ¿POR QUÉ ESTA VISTA NO EXIGE NINGÚN PERMISO?
    ----------------------------------------------------------------------
    Es la única del módulo que no lo hace, y es una decisión, no un olvido.

    El sistema de permisos de OPSO gobierna dos cosas: el acceso a los MÓDULOS y el
    acceso a los datos de OTRAS PERSONAS. Ver el trabajo que a uno mismo le
    asignaron no es ninguna de las dos. Es la información mínima sin la cual la
    cuenta no sirve para nada: un censista que no puede ver dónde le toca trabajar
    no puede trabajar, así que un permiso que se pudiera revocar no expresaría una
    decisión operativa, solo la posibilidad de inutilizar una cuenta por error.

    Es el mismo razonamiento con que la HU-04 dejó la matriz de permisos protegida
    por rol: hay accesos que no deben poder desconfigurarse.

    Se evaluó agregar un permiso "operativos.ver_propios" por simetría con
    "fichas.ver_propias", que sí existe. La diferencia es que aquel gobierna una
    FUNCIONALIDAD (el módulo de fichas, que un rol puede no tener en absoluto),
    mientras que esto es la pantalla que le dice a una persona cuál es su trabajo.

    LO QUE SÍ PROTEGE ESTA VISTA. El filtro por request.user no es negociable ni
    parametrizable: no hay ningún <pk> en la URL ni ningún filtro que el usuario
    pueda enviar. No existe forma de pedir "los sectores de otra persona", así que
    no hace falta comprobar que no se esté haciendo. La sesión la exige
    LoginRequiredMiddleware para toda la aplicación.
    """

    template_name = "operativos/mis_sectores.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Mis sectores"

        # El filtro por self.request.user es lo que hace segura esta vista.
        asignaciones = (
            AsignacionSector.objects.filter(censista=self.request.user, activa=True)
            .select_related(
                "sector",
                "sector__comuna",
                "sector__comuna__region",
                "sector__operativo",
                "asignado_por",
            )
            .prefetch_related("sector__zonas")
            .order_by("sector__operativo__fecha_inicio", "sector__nombre")
        )

        # Se separan los operativos vigentes de los cerrados. Mezclarlos haría que
        # el censista viera sectores de un operativo terminado junto a los de hoy y
        # tuviera que distinguirlos leyendo las fechas.
        vigentes, historicas = [], []
        for asignacion in asignaciones:
            destino = (
                historicas if asignacion.sector.operativo.esta_cerrado else vigentes
            )
            destino.append(asignacion)

        contexto["asignaciones"] = vigentes
        contexto["historicas"] = historicas
        contexto["total_sectores"] = len(vigentes)
        contexto["total_viviendas"] = sum(
            zona.viviendas_estimadas or 0
            for asignacion in vigentes
            for zona in asignacion.sector.zonas.all()
            if zona.activa
        )
        return contexto
