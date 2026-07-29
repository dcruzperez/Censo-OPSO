"""Decoradores de control de acceso para vistas basadas en funciones.

Se incluyen para cubrir el caso de vistas simples escritas como función.
Hacen exactamente lo mismo que RolRequeridoMixin, pero con la sintaxis:

    @rol_requerido(RolCodigo.SUPERVISOR)
    def asignar_sector(request): ...

Un decorador es una función que envuelve otra función: se ejecuta ANTES de la
vista, decide si corresponde continuar y, si no, corta la petición.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def rol_requerido(*codigos, permitir_administrador=True):
    """Permite el paso solo si el usuario tiene alguno de los roles indicados."""

    def decorador(vista):
        @wraps(vista)  # conserva el nombre y docstring de la vista original
        def envoltura(request, *args, **kwargs):
            usuario = request.user

            if permitir_administrador and usuario.es_administrador:
                return vista(request, *args, **kwargs)

            if usuario.tiene_rol(*codigos):
                return vista(request, *args, **kwargs)

            # PermissionDenied -> Django responde HTTP 403 (Prohibido).
            raise PermissionDenied("No tienes permisos para acceder a esa sección.")

        # login_required se aplica por fuera: primero se comprueba que haya
        # sesión y solo entonces se evalúa el rol.
        return login_required(envoltura)

    return decorador


def solo_administrador(vista):
    """Atajo legible para vistas exclusivas del administrador."""
    from .models import RolCodigo

    return rol_requerido(RolCodigo.ADMINISTRADOR)(vista)
