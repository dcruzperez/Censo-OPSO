"""Mixins de control de acceso para vistas basadas en clases.

Un "mixin" es una clase pequeña que aporta una capacidad y se combina con
otras por herencia múltiple. La ventaja frente a repetir código es que la
regla de autorización se escribe UNA vez y se declara en cada vista con una
sola línea.

Hay dos mixins de autorización porque hay dos preguntas distintas:

    RolRequeridoMixin     -> "¿QUIÉN eres?"          roles_permitidos = (...)
    PermisoRequeridoMixin -> "¿QUÉ puedes hacer?"    permisos_requeridos = (...)

Cuándo usar cada uno está explicado en la docstring de PermisoRequeridoMixin.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.shortcuts import redirect


class RechazoAmableMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Base común: define QUÉ HACER cuando la autorización falla.

    Se extrajo para que los dos mixins de autorización compartan exactamente el
    mismo comportamiento de rechazo. Si estuviera escrito dos veces, alguien
    podría mejorar el mensaje en uno y dejar el otro atrás, y la experiencia
    sería incoherente según qué regla bloqueó el paso.

    Las subclases solo tienen que implementar test_func().

    El orden de herencia importa: LoginRequiredMixin va primero para que a un
    visitante anónimo se le pida iniciar sesión en lugar de responderle 403, lo
    que sería confuso.
    """

    #: Mensaje mostrado cuando la autorización no alcanza.
    mensaje_sin_permiso = "No tienes permisos para acceder a esa sección."

    def handle_no_permission(self):
        """Qué hacer cuando test_func devuelve False.

        - Visitante anónimo -> comportamiento estándar: ir al login con ?next=.
        - Usuario autenticado sin autorización -> aviso claro y redirección a SU
          propio panel. Es mejor experiencia que un 403 seco.
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


class RolRequeridoMixin(RechazoAmableMixin):
    """Exige sesión iniciada Y un rol autorizado.

    Es la regla escrita en la HU-01 y usada por los paneles y por todo el módulo
    de administración de usuarios. No cambia con la HU-04: sigue siendo la
    protección correcta para lo que no debe poder reconfigurarse desde una
    pantalla (ver PermisoRequeridoMixin).
    """

    #: Códigos de rol que pueden entrar (ver RolCodigo).
    roles_permitidos = ()

    #: Los administradores acceden a todo por definición del negocio.
    permitir_administrador = True

    def test_func(self):
        """UserPassesTestMixin llama a este método: True = pasa, False = no."""
        usuario = self.request.user

        if self.permitir_administrador and usuario.es_administrador:
            return True

        return usuario.tiene_rol(*self.roles_permitidos)


class PermisoRequeridoMixin(RechazoAmableMixin):
    """Exige sesión iniciada Y un permiso concedido al rol del usuario (HU-04).

    ¿Por qué agregar esta forma si RolRequeridoMixin ya protege las vistas?

    Porque la pregunta que responde es la correcta para una regla de negocio, y
    la ventaja es concreta: cuando el administrador concede "fichas.validar" al
    rol Censista desde la matriz, la autorización cambia SIN TOCAR NI DESPLEGAR
    CÓDIGO. Con roles_permitidos habría que editar la vista, volver a probar y
    subir el sistema de nuevo para un cambio que es puramente operativo.

    LOS DOS MIXINS CONVIVEN A PROPÓSITO. No es una transición a medias:

      - La MATRIZ DE PERMISOS sigue protegida por ROL (MatrizPermisosView usa
        RolRequeridoMixin). Si la pantalla que gobierna los permisos se gobernara
        a sí misma por permisos, un administrador podría revocarse el acceso con
        un clic y dejar el sistema sin nadie capaz de repararlo desde la
        aplicación. Es el mismo bloqueo total que ya previene
        es_ultimo_administrador_activo(), y la defensa es la misma: la llave
        maestra no se guarda dentro de la caja que abre.

      - La ADMINISTRACIÓN DE USUARIOS va por PERMISO (ModuloUsuariosMixin), y
        también las funcionalidades del negocio (fichas, operativos, reportes),
        porque su reparto entre administradores y supervisores es una decisión
        operativa que puede cambiar de un operativo al siguiente. Delegar el
        listado de usuarios no entrega la llave maestra: quien lo recibe sigue
        sin poder repartir permisos.

    Que la administración de usuarios se proteja por permiso no la deja sin
    defensas por objeto: las reglas que impiden tocar un superusuario,
    autodeshabilitarse o dejar el sistema sin administradores se evalúan DENTRO
    de cada vista y ningún permiso de la matriz las desactiva.

    Uso:

        class ValidarFichaView(PermisoRequeridoMixin, UpdateView):
            permisos_requeridos = ("fichas.validar",)
    """

    #: Códigos de permiso exigidos (ver el catálogo del modelo Permiso).
    permisos_requeridos = ()

    #: Con varios permisos declarados, ¿hacen falta todos o basta con uno?
    #: Por defecto basta uno, que es el caso habitual ("puede entrar quien pueda
    #: ver sus propias fichas O todas las fichas"). Exigir todos se marca a
    #: propósito, para que la regla más restrictiva sea siempre la explícita.
    exigir_todos = False

    mensaje_sin_permiso = "No tienes permiso para realizar esa acción."

    def test_func(self):
        usuario = self.request.user

        if not self.permisos_requeridos:
            # Una vista que hereda de este mixin sin declarar permisos quedaría
            # abierta a cualquier usuario autenticado, y eso es casi con certeza
            # un olvido del programador y no una decisión. Se rompe en vez de
            # dejar pasar: "seguro por defecto" también aplica al descuido.
            #
            # ImproperlyConfigured es la excepción que Django usa justamente para
            # esto: no es un error del visitante (no sería un 4xx), es un error
            # de configuración del proyecto y debe verse en desarrollo.
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} hereda de PermisoRequeridoMixin "
                "pero no declara permisos_requeridos."
            )

        if self.exigir_todos:
            return all(
                usuario.tiene_permiso(codigo) for codigo in self.permisos_requeridos
            )

        # Una sola consulta con __in en vez de una por permiso.
        return usuario.tiene_algun_permiso(*self.permisos_requeridos)
