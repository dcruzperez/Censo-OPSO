"""Paneles diferenciados por rol.

Los tres paneles son, por ahora, pantallas de bienvenida con los accesos que
tendrá cada rol. Lo importante para esta historia de usuario es que el
CONTROL DE ACCESO ya está aplicado y probado: un censista no puede abrir
/dashboard/admin/ ni escribiendo la URL a mano.
"""

from django.views.generic import RedirectView, TemplateView

from usuarios.mixins import RolRequeridoMixin
from usuarios.models import RolCodigo


class RedirigirSegunRolView(RolRequeridoMixin, RedirectView):
    """Despachador central: /dashboard/ -> panel del rol del usuario.

    ¿Por qué existe esta vista intermedia?
    Porque LOGIN_REDIRECT_URL solo admite UNA dirección fija, y OPSO necesita
    tres destinos distintos. Esta vista es esa única dirección fija y ella
    resuelve el destino real en tiempo de ejecución. Beneficios:
      - LOGIN_REDIRECT_URL no queda amarrada a un rol.
      - Cualquier parte del sistema puede enviar a "dashboards:redirigir" sin
        saber el rol de quien navega.
      - Si mañana hay un cuarto rol, esta vista no cambia.
    """

    permanent = False  # HTTP 302: la redirección depende de quién consulta

    # Aquí no se exige un rol específico: basta con tener sesión iniciada.
    # roles_permitidos vacío + permitir_administrador basta para el admin;
    # para el resto, test_func se resuelve abajo.
    def test_func(self):
        return self.request.user.is_authenticated

    def get_redirect_url(self, *args, **kwargs):
        # get_dashboard_url() consulta el rol en PostgreSQL y devuelve la URL
        # registrada para ese rol (o /sin-rol/ si no tiene).
        return self.request.user.get_dashboard_url()


class DashboardAdministradorView(RolRequeridoMixin, TemplateView):
    """Panel del Administrador: gestión de usuarios, roles y configuración."""

    template_name = "dashboards/administrador.html"
    roles_permitidos = (RolCodigo.ADMINISTRADOR,)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Panel del Administrador"

        # Datos reales para que el panel no sea una pantalla vacía.
        from usuarios.models import IntentoAcceso, RegistroAuditoria, Rol, Usuario

        contexto["total_usuarios"] = Usuario.objects.filter(is_active=True).count()
        contexto["total_inactivos"] = Usuario.objects.filter(is_active=False).count()
        contexto["total_roles"] = Rol.objects.filter(activo=True).count()
        contexto["accesos_recientes"] = (
            IntentoAcceso.objects.select_related("usuario").all()[:10]
        )
        # Últimas acciones administrativas (HU-03): el panel muestra de un
        # vistazo qué se ha hecho con las cuentas del sistema.
        contexto["auditoria_reciente"] = RegistroAuditoria.objects.select_related(
            "administrador", "usuario_afectado"
        )[:5]
        return contexto


class DashboardSupervisorView(RolRequeridoMixin, TemplateView):
    """Panel del Supervisor: seguimiento de censistas y validación de fichas."""

    template_name = "dashboards/supervisor.html"
    roles_permitidos = (RolCodigo.SUPERVISOR,)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Panel del Supervisor"

        from usuarios.models import Usuario

        contexto["total_censistas"] = Usuario.objects.filter(
            is_active=True, rol__codigo=RolCodigo.CENSISTA
        ).count()

        # HU-06: el reparto del trabajo. El panel tenía estos contadores como
        # marcadores de posición ("—") desde la HU-01; ahora hay datos que ponerles.
        from operativos.models import AsignacionSector, EstadoOperativo, Operativo, Sector

        operativos_vigentes = Operativo.objects.filter(
            estado__in=(EstadoOperativo.PLANIFICACION, EstadoOperativo.EN_CURSO)
        )

        # distinct() porque un sector con tres censistas debe contar UNA vez.
        contexto["sectores_asignados"] = (
            Sector.objects.filter(
                operativo__in=operativos_vigentes, activo=True, asignaciones__activa=True
            )
            .distinct()
            .count()
        )

        # El número que de verdad le sirve al supervisor: territorio que nadie va a
        # visitar. Se muestra destacado en el panel por eso.
        contexto["sectores_sin_asignar"] = (
            Sector.objects.filter(operativo__in=operativos_vigentes, activo=True)
            .exclude(asignaciones__activa=True)
            .distinct()
            .count()
        )

        contexto["censistas_desplegados"] = (
            AsignacionSector.objects.filter(
                activa=True, sector__operativo__in=operativos_vigentes
            )
            .values("censista")
            .distinct()
            .count()
        )

        # El operativo al que llevan los enlaces del panel: el más próximo en curso
        # o en planificación. Sin esto el supervisor tendría que pasar por el
        # listado de operativos para llegar a su trabajo del día.
        contexto["operativo_actual"] = operativos_vigentes.order_by(
            "-fecha_inicio"
        ).first()

        # HU-13: la cola de revisión. Es lo primero que el supervisor necesita al
        # entrar, igual que al censista le importan sus encuestas por trabajar.
        from django.db.models import Count, Q

        from fichas.models import ESTADOS_SIN_LEVANTAR, Encuesta, EstadoEncuesta

        revisables = Encuesta.objects.exclude(estado=EstadoEncuesta.PENDIENTE)

        contexto["resumen_revision"] = revisables.aggregate(
            recibidas=Count("id", filter=Q(estado=EstadoEncuesta.COMPLETADA)),
            validadas=Count("id", filter=Q(estado=EstadoEncuesta.VALIDADA)),
            observadas=Count("id", filter=Q(estado=EstadoEncuesta.OBSERVADA)),
            anuladas=Count("id", filter=Q(estado=EstadoEncuesta.ANULADA)),
            sin_levantar=Count("id", filter=Q(estado__in=ESTADOS_SIN_LEVANTAR)),
        )

        # Las cinco que llevan más esperando: la cola se atiende por antigüedad, así
        # que el panel muestra justamente su cabeza.
        contexto["cola_revision"] = (
            revisables.filter(
                estado=EstadoEncuesta.COMPLETADA, cerrada_en__isnull=False
            )
            .select_related("vivienda", "censista")
            .order_by("cerrada_en")[:5]
        )

        # HU-16: alertas de calidad de datos. Mismo universo que resumen_revision
        # de arriba —revisables, sin las PENDIENTE— para que los números de un
        # mismo panel no respondan a criterios distintos sin que nada lo avise.
        contexto["alertas_calidad"] = Encuesta.resumen_alertas_calidad(revisables)
        # Se pasa el umbral en vez de escribir «7» en la plantilla: si el modelo
        # cambia la constante, el texto del panel no se queda desactualizado.
        contexto["dias_espera_prolongada"] = Encuesta.DIAS_ESPERA_PROLONGADA
        return contexto


class DashboardCensistaView(RolRequeridoMixin, TemplateView):
    """Panel del Censista: levantamiento de información de familias."""

    template_name = "dashboards/censista.html"
    roles_permitidos = (RolCodigo.CENSISTA,)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Panel del Censista"

        # HU-06: sus sectores a cargo. Es lo primero que necesita ver al entrar:
        # dónde le toca trabajar hoy.
        #
        # Se filtra por self.request.user y se excluyen los operativos cerrados: un
        # sector de un operativo terminado no es trabajo pendiente, y mezclarlos
        # obligaría a distinguirlos leyendo las fechas.
        from operativos.models import AsignacionSector, EstadoOperativo

        contexto["mis_asignaciones"] = (
            AsignacionSector.objects.filter(activa=True, censista=self.request.user)
            .exclude(sector__operativo__estado=EstadoOperativo.CERRADO)
            .select_related("sector", "sector__comuna", "sector__operativo")
            .order_by("sector__nombre")
        )

        # HU-07: sus encuestas. El panel tenía estos dos contadores como marcadores
        # de posición ("—") desde la HU-01, igual que le pasó al del supervisor
        # hasta la HU-06; ahora hay datos que ponerles.
        #
        # Se cuentan solo las de operativos NO cerrados, por lo mismo que los
        # sectores de arriba: un padrón de un operativo terminado no es trabajo
        # pendiente, y sumarlo haría que el panel mostrara una carga que no existe.
        from django.db.models import Count, Q

        from fichas.models import ESTADOS_ABIERTOS, Encuesta, EstadoEncuesta

        mis_encuestas = Encuesta.objects.filter(
            censista=self.request.user
        ).exclude(vivienda__zona__sector__operativo__estado=EstadoOperativo.CERRADO)

        # Un solo viaje a la base de datos para los tres recuentos, con el
        # argumento `filter` de Count. Es el mismo recurso que usa MisEncuestasView.
        contexto["resumen_encuestas"] = mis_encuestas.aggregate(
            total=Count("id"),
            por_trabajar=Count("id", filter=Q(estado__in=ESTADOS_ABIERTOS)),
            observadas=Count("id", filter=Q(estado=EstadoEncuesta.OBSERVADA)),
        )

        # Las tres primeras de la jornada, con el mismo criterio de urgencia que
        # «Mis encuestas»: primero lo devuelto, después lo empezado a medias.
        from fichas.views import ORDEN_POR_URGENCIA

        contexto["proximas_encuestas"] = (
            mis_encuestas.filter(estado__in=ESTADOS_ABIERTOS)
            .select_related("vivienda", "vivienda__zona", "vivienda__zona__sector")
            .annotate(urgencia=ORDEN_POR_URGENCIA)
            .order_by(
                "urgencia",
                "vivienda__zona__sector__nombre",
                "vivienda__zona__nombre",
                "vivienda__direccion",
            )[:5]
        )
        return contexto
