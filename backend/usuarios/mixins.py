"""Mixins de control de acceso para vistas basadas en clases.

Un "mixin" es una clase pequeña que aporta una capacidad y se combina con
otras por herencia múltiple. La ventaja frente a repetir código es que la
regla de autorización se escribe UNA vez y se declara en cada vista con una
sola línea: roles_permitidos = (...).
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


class RolRequeridoMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Exige sesión iniciada Y un rol autorizado.

    El orden de herencia importa: LoginRequiredMixin va primero para que a un
    visitante anónimo se le pida iniciar sesión (en lugar de responderle 403,
    lo que sería confuso).
    """

    #: Códigos de rol que pueden entrar (ver RolCodigo).
    roles_permitidos = ()

    #: Los administradores acceden a todo por definición del negocio.
    permitir_administrador = True

    #: Mensaje mostrado cuando el rol no alcanza.
    mensaje_sin_permiso = "No tienes permisos para acceder a esa sección."

    def test_func(self):
        """UserPassesTestMixin llama a este método: True = pasa, False = no."""
        usuario = self.request.user

        if self.permitir_administrador and usuario.es_administrador:
            return True

        return usuario.tiene_rol(*self.roles_permitidos)

    def handle_no_permission(self):
        """Qué hacer cuando test_func devuelve False.

        - Visitante anónimo -> comportamiento estándar: ir al login con ?next=.
        - Usuario autenticado con rol insuficiente -> aviso claro y redirección
          a SU propio panel. Es mejor experiencia que un 403 seco.
        """
        usuario = self.request.user

        if not usuario.is_authenticated:
            return super().handle_no_permission()

        destino = usuario.get_dashboard_url()

        # Salvaguarda contra un bucle infinito de redirecciones: si su propio
        # panel es justamente el que no puede ver, respondemos 403.
        if destino == self.request.path:
            raise PermissionDenied(self.mensaje_sin_permiso)

        messages.error(self.request, self.mensaje_sin_permiso)
        return redirect(destino)
