"""Rutas de autenticación.

app_name crea un "espacio de nombres": las URLs se referencian como
"usuarios:login". Así, si otra app también tuviera una ruta llamada "login",
no habría ambigüedad. Y si mañana cambia la dirección /login/ por /acceso/,
las plantillas y vistas no se tocan, porque referencian el NOMBRE.
"""

from django.urls import path
from django.views.generic import RedirectView

from . import views, views_gestion, views_permisos

app_name = "usuarios"

urlpatterns = [
    # /login/  -> formulario de inicio de sesión
    path("login/", views.LoginOPSOView.as_view(), name="login"),
    # /logout/ -> cierre de sesión (solo acepta POST, ver views.py)
    path("logout/", views.LogoutOPSOView.as_view(), name="logout"),
    # /sin-rol/ -> aviso para cuentas sin rol asignado
    path("sin-rol/", views.SinRolView.as_view(), name="sin_rol"),
    # ------------------------------------------------------------------
    # RECUPERACIÓN DE CONTRASEÑA — cuatro pasos, cuatro URLs
    # ------------------------------------------------------------------
    # Los NOMBRES (password_reset, password_reset_done, ...) son los que usa
    # Django internamente. Se conservan a propósito: así cualquier código
    # nativo o de terceros que espere esos nombres sigue funcionando.
    #
    # PASO 1: formulario donde se escribe el correo.
    path(
        "recuperar-contrasena/",
        views.RecuperarContrasenaView.as_view(),
        name="password_reset",
    ),
    # PASO 2: confirmación neutra ("revisa tu correo").
    path(
        "recuperar-contrasena/enviado/",
        views.RecuperarContrasenaEnviadoView.as_view(),
        name="password_reset_done",
    ),
    # PASO 3: el enlace del correo. Lleva dos datos en la propia dirección:
    #   uidb64 -> el id del usuario codificado en base64 (NO cifrado: solo
    #             es una forma segura de poner un número en una URL)
    #   token  -> la firma temporal que prueba que el enlace es legítimo
    #
    # Esta misma ruta atiende dos casos: cuando el token viene en la URL
    # (primera visita) y cuando vale "set-password" (después de que Django lo
    # movió a la sesión para que no quede expuesto en la barra del navegador).
    path(
        "restablecer/<uidb64>/<token>/",
        views.RestablecerContrasenaView.as_view(),
        name="password_reset_confirm",
    ),
    # PASO 4: aviso de éxito con el enlace para iniciar sesión.
    path(
        "restablecer/completado/",
        views.RestablecerContrasenaCompletadoView.as_view(),
        name="password_reset_complete",
    ),
    # ------------------------------------------------------------------
    # ADMINISTRACIÓN DE USUARIOS (HU-03) — por permiso desde la HU-04
    # ------------------------------------------------------------------
    # Cada vista declara el permiso que exige (ver ModuloUsuariosMixin en
    # views_gestion.py). Con el reparto inicial solo entra el administrador,
    # igual que antes, pero ahora eso se puede cambiar desde /roles/permisos/.
    # Todas comparten el prefijo /usuarios/. Agrupar las rutas de un módulo
    # bajo un prefijo común no es solo orden: permite proteger el módulo
    # completo de una sola vez en el servidor web o en un firewall de
    # aplicación, sin enumerar cada dirección.
    #
    # La ruta de auditoría se declara ANTES de las que llevan <int:pk>. Aunque
    # el conversor "int" nunca haría coincidir la palabra "auditoria", el orden
    # explícito deja claro cuál manda si mañana el conversor cambiara a <str>.
    #
    # /usuarios/            -> listado con búsqueda, filtros y paginación
    path("usuarios/", views_gestion.UsuarioListView.as_view(), name="lista"),
    # /usuarios/nuevo/      -> formulario de creación
    path("usuarios/nuevo/", views_gestion.UsuarioCreateView.as_view(), name="crear"),
    # /usuarios/auditoria/  -> bitácora completa de acciones administrativas
    path(
        "usuarios/auditoria/",
        views_gestion.AuditoriaListView.as_view(),
        name="auditoria",
    ),
    # ------------------------------------------------------------------
    # ROLES Y PERMISOS (HU-04) — solo rol Administrador, a propósito
    # ------------------------------------------------------------------
    # Esta ruta NO se protege por permiso: es la única del sistema que conserva
    # el control por rol, para que nadie pueda revocarse el acceso a la pantalla
    # que reparte los accesos (ver la docstring de MatrizPermisosView).
    # Prefijo /roles/ y no /usuarios/roles/: los permisos se conceden a ROLES,
    # no a personas, y la dirección debe reflejar sobre qué entidad se trabaja.
    # Que además solo pueda entrar el administrador es una regla de acceso, no
    # una razón para colgar la ruta bajo /usuarios/.
    #
    # /roles/permisos/ -> matriz rol × permiso (GET consulta, POST guarda)
    path(
        "roles/permisos/",
        views_permisos.MatrizPermisosView.as_view(),
        name="permisos",
    ),
    # /usuarios/5/          -> ficha del usuario 5 con su historial
    path(
        "usuarios/<int:pk>/", views_gestion.UsuarioDetailView.as_view(), name="detalle"
    ),
    # /usuarios/5/editar/   -> formulario de edición del usuario 5
    path(
        "usuarios/<int:pk>/editar/",
        views_gestion.UsuarioUpdateView.as_view(),
        name="editar",
    ),
    # /usuarios/5/deshabilitar/ -> confirmación (GET) y baja lógica (POST)
    #
    # as_view(activar=False) fija el atributo de la clase para esta ruta. Es la
    # forma de que UNA clase atienda las dos operaciones opuestas sin duplicar
    # su lógica de validación y auditoría.
    path(
        "usuarios/<int:pk>/deshabilitar/",
        views_gestion.CambiarEstadoUsuarioView.as_view(activar=False),
        name="deshabilitar",
    ),
    # /usuarios/5/habilitar/ -> confirmación (GET) y reactivación (POST)
    path(
        "usuarios/<int:pk>/habilitar/",
        views_gestion.CambiarEstadoUsuarioView.as_view(activar=True),
        name="habilitar",
    ),
    # /usuarios/5/enviar-enlace/ -> reenvío del enlace de contraseña (solo POST)
    path(
        "usuarios/<int:pk>/enviar-enlace/",
        views_gestion.EnviarEnlaceContrasenaView.as_view(),
        name="enviar_enlace",
    ),
    # /  -> la raíz reenvía al despachador de paneles.
    path(
        "",
        RedirectView.as_view(pattern_name="dashboards:redirigir", permanent=False),
        name="inicio",
    ),
]
