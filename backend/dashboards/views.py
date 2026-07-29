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
        return contexto


class DashboardCensistaView(RolRequeridoMixin, TemplateView):
    """Panel del Censista: levantamiento de información de familias."""

    template_name = "dashboards/censista.html"
    roles_permitidos = (RolCodigo.CENSISTA,)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Panel del Censista"
        return contexto
