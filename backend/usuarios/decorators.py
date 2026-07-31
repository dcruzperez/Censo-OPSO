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
from django.core.exceptions import ImproperlyConfigured, PermissionDenied


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


def permiso_requerido(*codigos, exigir_todos=False):
    """Permite el paso solo si el rol del usuario tiene los permisos indicados.

    Es el equivalente en decorador de PermisoRequeridoMixin, para vistas escritas
    como función:

        @permiso_requerido("fichas.validar")
        def validar_ficha(request, pk): ...

        @permiso_requerido("fichas.editar", "fichas.validar", exigir_todos=True)
        def reabrir_ficha(request, pk): ...

    Por defecto basta con UNO de los permisos indicados; exigir_todos=True los
    pide todos. Misma regla y mismo valor por defecto que el mixin, para que las
    dos formas de escribir una vista se comporten igual y no haya que recordar
    dos criterios distintos.
    """
    if not codigos:
        # Mismo razonamiento que en el mixin: un decorador sin permisos dejaría
        # la vista abierta y es casi seguro un olvido. Falla al importar el
        # módulo, que es el momento más temprano posible.
        raise ImproperlyConfigured(
            "permiso_requerido() necesita al menos un código de permiso."
        )

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            usuario = request.user

            if exigir_todos:
                autorizado = all(usuario.tiene_permiso(c) for c in codigos)
            else:
                autorizado = usuario.tiene_algun_permiso(*codigos)

            if autorizado:
                return vista(request, *args, **kwargs)

            raise PermissionDenied("No tienes permiso para realizar esa acción.")

        return login_required(envoltura)

    return decorador
