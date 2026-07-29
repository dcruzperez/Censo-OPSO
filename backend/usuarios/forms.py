"""Formularios de la app usuarios.

Un formulario de Django cumple tres tareas:
  1. DIBUJAR los campos en HTML.
  2. LIMPIAR y VALIDAR lo que llega del navegador (nunca se confía en el
     cliente: los datos pueden venir de curl, Postman o un bot).
  3. REPORTAR errores de forma ordenada para mostrarlos en la plantilla.
"""

from django import forms
from django.conf import settings
from django.contrib.auth.forms import (
    AuthenticationForm,
    BaseUserCreationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserChangeForm,
)
from django.core.exceptions import ValidationError

from .models import Usuario
from .seguridad import esta_bloqueado


class LoginForm(AuthenticationForm):
    """Formulario de inicio de sesión de OPSO.

    Hereda de AuthenticationForm, el formulario de Django que ya sabe:
      - llamar a authenticate() para comparar el hash de la contraseña,
      - rechazar cuentas con is_active=False,
      - dejar el usuario validado disponible en get_user().

    Nosotros solo agregamos: etiquetas en español, clases de Bootstrap, la
    casilla "recordarme" y el control de intentos fallidos.
    """

    # AuthenticationForm llama "username" a su primer campo aunque el
    # identificador real sea el correo. Lo redefinimos como EmailField para
    # que el navegador muestre el teclado de correo y valide el formato.
    username = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "usuario@opso.cl",
                "autocomplete": "email",  # ayuda al gestor de contraseñas
                "autofocus": True,  # el cursor parte aquí
                "inputmode": "email",
            }
        ),
    )

    password = forms.CharField(
        label="Contraseña",
        # strip=False: NO se recortan los espacios. Un espacio puede ser parte
        # legítima de la contraseña y quitarlo impediría el ingreso.
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "••••••••",
                "autocomplete": "current-password",
            }
        ),
    )

    recordarme = forms.BooleanField(
        label="Recordarme en este equipo",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    # Mensajes de error propios. El de credenciales inválidas es DELIBERADAMENTE
    # genérico: si dijera "ese correo no existe", un atacante podría averiguar
    # qué correos están registrados (enumeración de usuarios).
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": (
            "El correo electrónico o la contraseña son incorrectos. "
            "Verifica tus datos e inténtalo nuevamente."
        ),
        "inactive": (
            "Tu cuenta se encuentra desactivada. Comunícate con el "
            "administrador del sistema."
        ),
        "rol_inactivo": (
            "El rol asignado a tu cuenta está desactivado. Comunícate con el "
            "administrador del sistema."
        ),
        "bloqueado": (
            "Se superó el número de intentos permitidos. Por seguridad, la "
            "cuenta quedó bloqueada temporalmente durante %(minutos)s minutos."
        ),
    }

    def clean_username(self):
        """Normaliza el correo a minúsculas y sin espacios."""
        return (self.cleaned_data.get("username") or "").strip().lower()

    def clean(self):
        """Validación global del formulario.

        Se ejecuta después de limpiar cada campo. Primero revisamos el bloqueo
        por fuerza bruta y solo después verificamos la contraseña: así el
        atacante bloqueado no consume tiempo de CPU calculando hashes.
        """
        email = self.cleaned_data.get("username")

        if email and esta_bloqueado(email):
            raise ValidationError(
                self.error_messages["bloqueado"],
                code="bloqueado",
                params={"minutos": settings.OPSO_BLOQUEO_LOGIN_MINUTOS},
            )

        # super().clean() es quien realmente llama a authenticate().
        return super().clean()

    def confirm_login_allowed(self, user):
        """Último filtro una vez que la contraseña YA fue verificada.

        Django, por defecto, solo revisa is_active. Aquí añadimos la regla de
        negocio de OPSO: si el rol de la persona fue desactivado, no entra.
        """
        super().confirm_login_allowed(user)  # revisa is_active

        if user.rol_id and not user.rol.activo and not user.is_superuser:
            raise ValidationError(
                self.error_messages["rol_inactivo"], code="rol_inactivo"
            )


# ==========================================================================
# RECUPERACIÓN DE CONTRASEÑA
# ==========================================================================
# DECISIÓN: se heredan los formularios de Django en lugar de escribirlos de
# cero, y se personaliza SOLO la presentación.
#
# Lo que hace Django y NO se toca (porque es la parte delicada):
#   PasswordResetForm  -> busca al usuario, genera el token firmado, arma el
#                         enlace y envía el correo.
#   SetPasswordForm    -> compara las dos contraseñas, aplica los validadores
#                         de robustez y guarda el hash.
#
# Lo que se personaliza:
#   - etiquetas y textos de ayuda en español,
#   - clases de Bootstrap en los campos,
#   - normalización del correo a minúsculas.
#
# Reescribir la generación o verificación del token sería el error más grave
# posible en esta funcionalidad: es criptografía, y la implementación de
# Django ya está auditada.


class RecuperarContrasenaForm(PasswordResetForm):
    """Paso 1: la persona escribe su correo para pedir el enlace.

    Se hereda de PasswordResetForm, que aporta:
      - get_users(email): devuelve los usuarios que PUEDEN recuperar. Filtra
        cuentas con is_active=False y cuentas sin contraseña utilizable.
      - save(): genera el token, arma el contexto del correo y lo envía.
    """

    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "usuario@opso.cl",
                "autocomplete": "email",
                "autofocus": True,
                "inputmode": "email",
            }
        ),
        help_text="Escribe el correo con el que accedes a OPSO.",
    )

    def clean_email(self):
        """Normaliza el correo.

        No se valida si existe ni se lanza error cuando no existe: eso
        revelaría qué cuentas están registradas (enumeración de usuarios).
        La búsqueda la hace get_users() y, si no encuentra nada, simplemente
        no envía ningún correo. El usuario ve la misma pantalla en ambos casos.
        """
        return (self.cleaned_data.get("email") or "").strip().lower()


class EstablecerContrasenaForm(SetPasswordForm):
    """Paso 2: la persona define su contraseña nueva.

    SetPasswordForm trae dos campos (new_password1 y new_password2) y toda la
    lógica de validación. Solo se ajusta la presentación.

    Los campos se modifican en __init__ en lugar de volver a declararlos:
    así se conservan intactos los textos de ayuda que Django genera a partir
    de AUTH_PASSWORD_VALIDATORS (mínimo 10 caracteres, no común, etc.).
    """

    ETIQUETAS = {
        "new_password1": "Nueva contraseña",
        "new_password2": "Confirma la nueva contraseña",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for nombre, campo in self.fields.items():
            campo.label = self.ETIQUETAS.get(nombre, campo.label)
            campo.widget.attrs.update(
                {
                    "class": "form-control form-control-lg",
                    "placeholder": "••••••••",
                    # "new-password" le indica al gestor de contraseñas del
                    # navegador que ofrezca generar y guardar una clave nueva.
                    "autocomplete": "new-password",
                }
            )

        self.fields["new_password2"].help_text = (
            "Vuelve a escribir la contraseña para confirmar que no hubo un error de tipeo."
        )


# ==========================================================================
# Formularios para el panel de administración (/admin/)
# ==========================================================================
# Los de Django apuntan al modelo User por defecto; hay que redirigirlos a
# nuestro modelo Usuario, o el admin fallaría al crear o editar cuentas.


class UsuarioCreationForm(BaseUserCreationForm):
    """Crear usuario en el admin (pide la contraseña dos veces)."""

    class Meta(BaseUserCreationForm.Meta):
        model = Usuario
        fields = (
            "email",
            "nombre_usuario",
            "first_name",
            "last_name",
            "rut",
            "telefono",
            "rol",
        )


class UsuarioChangeForm(UserChangeForm):
    """Editar usuario en el admin.

    Nunca muestra la contraseña (es un hash irreversible): muestra un enlace
    al formulario de cambio de contraseña.
    """

    class Meta(UserChangeForm.Meta):
        model = Usuario
        fields = "__all__"
