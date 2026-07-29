"""Formularios de la administración de usuarios (HU-03).

Se separan de forms.py por responsabilidad: forms.py resuelve la AUTENTICACIÓN
(entrar al sistema, recuperar la contraseña) y este módulo resuelve la
ADMINISTRACIÓN (crear, editar y deshabilitar cuentas). Son dos historias de
usuario distintas y mezclarlas en un archivo de 600 líneas dificultaría el
mantenimiento.

¿Por qué ModelForm y no Form?
Un Form obliga a declarar cada campo, sus validaciones y luego copiar los datos
al objeto a mano. Un ModelForm LEE el modelo y deriva de él:
  - los campos y sus tipos,
  - las etiquetas y textos de ayuda (verbose_name / help_text),
  - las validaciones (max_length, EmailField, validators=[validar_rut]),
  - las restricciones de unicidad,
  - y el método save() que escribe en PostgreSQL.
Resultado: la regla se define UNA vez, en el modelo, y no puede quedar
desincronizada entre la base de datos y el formulario.
"""

from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import Rol, RolCodigo, Usuario
from .seguridad import generar_clave_aleatoria
from .validators import limpiar_nombre_usuario, limpiar_rut

# Clases de Bootstrap reutilizadas en todos los campos.
CLASE_TEXTO = "form-control"
CLASE_SELECT = "form-select"


class CampoRol(forms.ModelChoiceField):
    """Selector de rol que avisa cuando un rol está desactivado.

    ModelChoiceField muestra str(objeto) en cada opción. Al redefinir
    label_from_instance el administrador ve "Censista (rol desactivado)" y
    entiende por qué esa persona no podría iniciar sesión, en vez de
    preguntárselo.
    """

    def label_from_instance(self, obj):
        return obj.nombre if obj.activo else f"{obj.nombre} (rol desactivado)"


class UsuarioFormBase(forms.ModelForm):
    """Parte común de los formularios de crear y editar.

    Evita duplicar la definición de campos, los widgets y —sobre todo— las
    validaciones de duplicados: si estuvieran escritas dos veces, una podría
    corregirse y la otra no.
    """

    # Se declara explícitamente para poder usar CampoRol y controlar el orden
    # de las opciones. queryset se ajusta en __init__.
    rol = CampoRol(
        queryset=Rol.objects.all(),
        label="Rol",
        required=False,
        empty_label="— Sin rol asignado —",
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
        help_text="Determina qué puede ver y hacer la persona en OPSO.",
    )

    # El estado se modela como lista desplegable en vez de casilla de
    # verificación. Motivo: una casilla marcada/desmarcada es ambigua a la
    # vista ("¿desmarcada significa inactivo o significa que no la toqué?");
    # un desplegable con dos opciones explícitas no deja dudas.
    is_active = forms.TypedChoiceField(
        label="Estado",
        choices=((True, "Activo"), (False, "Inactivo")),
        coerce=lambda valor: valor in (True, "True", "true", "1"),
        initial=True,
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
        help_text="Un usuario inactivo conserva todos sus datos pero no puede iniciar sesión.",
    )

    class Meta:
        model = Usuario
        fields = (
            "first_name",
            "last_name",
            "email",
            "nombre_usuario",
            "rut",
            "telefono",
            "rol",
            "is_active",
        )
        # Se sobrescriben las etiquetas heredadas de AbstractUser, que están en
        # inglés ("first name", "last name").
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Correo electrónico",
            "nombre_usuario": "Nombre de usuario",
            "rut": "RUT",
            "telefono": "Teléfono",
        }
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": CLASE_TEXTO, "placeholder": "Marta", "autofocus": True}
            ),
            "last_name": forms.TextInput(
                attrs={"class": CLASE_TEXTO, "placeholder": "Soto"}
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": "persona@opso.cl",
                    "autocomplete": "off",
                    "inputmode": "email",
                }
            ),
            "nombre_usuario": forms.TextInput(
                attrs={"class": CLASE_TEXTO, "placeholder": "msoto", "autocomplete": "off"}
            ),
            "rut": forms.TextInput(
                attrs={"class": CLASE_TEXTO, "placeholder": "12345678-5"}
            ),
            "telefono": forms.TextInput(
                attrs={"class": CLASE_TEXTO, "placeholder": "+56 9 1234 5678"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Nombre y apellido son opcionales en AbstractUser (blank=True), pero
        # en OPSO son obligatorios: identifican a la persona en el listado y en
        # la ficha del censo. Se exige en el formulario y no en el modelo para
        # no invalidar las cuentas técnicas ya creadas con createsuperuser.
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True

        # El rol se ofrece solo entre los roles activos... salvo el que ya
        # tiene asignado esta persona. Si no se incluyera, editar el teléfono
        # de alguien con un rol desactivado fallaría con "elija una opción
        # válida", un error incomprensible para el administrador.
        disponibles = Q(activo=True)
        if self.instance.pk and self.instance.rol_id:
            disponibles |= Q(pk=self.instance.rol_id)
        self.fields["rol"].queryset = Rol.objects.filter(disponibles).order_by("nombre")

    # ------------------------------------------------------------------
    # VALIDACIONES POR CAMPO
    # ------------------------------------------------------------------
    # Django llama automáticamente a clean_<nombre_del_campo>() después de
    # convertir el dato al tipo de Python correspondiente. Lo que devuelve el
    # método es el valor que queda en cleaned_data y el que se guardará.

    def clean_first_name(self):
        return (self.cleaned_data.get("first_name") or "").strip()

    def clean_last_name(self):
        return (self.cleaned_data.get("last_name") or "").strip()

    def clean_email(self):
        """Normaliza el correo y comprueba que no esté repetido.

        ¿Por qué revisar el duplicado a mano si el modelo ya declara unique=True?
        Porque PostgreSQL compara texto respetando mayúsculas: para la base de
        datos "Ana@opso.cl" y "ana@opso.cl" son DISTINTOS y ambos pasarían la
        restricción UNIQUE. Pero Usuario.save() guarda el correo en minúsculas,
        así que al grabar el segundo se produciría un IntegrityError: una página
        de error 500 en vez de un mensaje claro.

        Con __iexact la comparación es insensible a mayúsculas y el
        administrador recibe un error entendible junto al campo.
        """
        email = (self.cleaned_data.get("email") or "").strip().lower()

        duplicados = Usuario.objects.filter(email__iexact=email)
        # Al EDITAR hay que excluirse a sí mismo: si no, el usuario chocaría
        # con su propio correo y nunca podría guardar.
        if self.instance.pk:
            duplicados = duplicados.exclude(pk=self.instance.pk)

        if duplicados.exists():
            raise ValidationError(
                "Ya existe una cuenta registrada con este correo electrónico.",
                code="email_duplicado",
            )

        return email

    def clean_nombre_usuario(self):
        """Normaliza y verifica que el nombre de usuario sea único."""
        nombre_usuario = limpiar_nombre_usuario(self.cleaned_data.get("nombre_usuario"))

        if nombre_usuario is None:
            # Campo opcional: si viene vacío se propone uno automáticamente a
            # partir del nombre y el apellido (ver save()).
            return None

        duplicados = Usuario.objects.filter(nombre_usuario__iexact=nombre_usuario)
        if self.instance.pk:
            duplicados = duplicados.exclude(pk=self.instance.pk)

        if duplicados.exists():
            raise ValidationError(
                "Este nombre de usuario ya está en uso. Elige otro.",
                code="nombre_usuario_duplicado",
            )

        return nombre_usuario

    def clean_rut(self):
        """Normaliza el RUT al formato canónico y verifica que sea único.

        El validador de formato y dígito verificador (validar_rut) lo aplica el
        propio modelo: el ModelForm lo hereda y no hay que repetirlo aquí.
        """
        rut = self.cleaned_data.get("rut")
        if not rut:
            return None

        rut = limpiar_rut(rut)

        duplicados = Usuario.objects.filter(rut=rut)
        if self.instance.pk:
            duplicados = duplicados.exclude(pk=self.instance.pk)

        if duplicados.exists():
            raise ValidationError(
                "Ya existe una cuenta registrada con este RUT.",
                code="rut_duplicado",
            )

        return rut


class CrearUsuarioForm(UsuarioFormBase):
    """Formulario de creación de cuentas.

    Aquí se resuelve la pregunta central de la historia de usuario: ¿cómo
    obtiene su primera contraseña la persona? Se ofrecen las dos alternativas y
    la recomendada viene seleccionada por defecto.
    """

    ENLACE = "enlace"
    MANUAL = "manual"

    metodo_clave = forms.ChoiceField(
        label="¿Cómo definirá su contraseña?",
        choices=(
            (
                ENLACE,
                "Enviar un enlace al correo para que la persona la cree "
                "(recomendado)",
            ),
            (MANUAL, "Definir yo una contraseña inicial"),
        ),
        initial=ENLACE,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )

    password1 = forms.CharField(
        label="Contraseña inicial",
        required=False,  # solo obligatoria si se eligió el método manual
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": CLASE_TEXTO, "autocomplete": "new-password"}
        ),
        help_text=password_validation.password_validators_help_text_html,
    )
    password2 = forms.CharField(
        label="Repetir la contraseña",
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": CLASE_TEXTO, "autocomplete": "new-password"}
        ),
        help_text="Escríbela otra vez para descartar un error de tipeo.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #: La vista lee este atributo después de save() para saber si debe
        #: enviar el correo. El envío NO se hace en el formulario porque
        #: requiere el objeto request (dominio y protocolo del enlace).
        self.requiere_enlace = False

    def clean(self):
        """Validación global: coherencia entre el método elegido y las claves.

        clean() se ejecuta DESPUÉS de todos los clean_<campo>() y es el lugar
        correcto para las reglas que involucran a más de un campo.
        """
        datos = super().clean()

        if datos.get("metodo_clave") == self.MANUAL:
            password1 = datos.get("password1")
            password2 = datos.get("password2")

            if not password1:
                self.add_error(
                    "password1",
                    ValidationError(
                        "Escribe la contraseña inicial o elige la opción de "
                        "enviar el enlace por correo.",
                        code="clave_requerida",
                    ),
                )
            elif password1 != password2:
                # add_error asocia el mensaje a un campo concreto: aparece
                # justo debajo de él, no en un bloque genérico arriba.
                self.add_error(
                    "password2",
                    ValidationError(
                        "Las dos contraseñas no coinciden.", code="clave_distinta"
                    ),
                )

        return datos

    def _post_clean(self):
        """Aquí se valida la ROBUSTEZ de la contraseña.

        ¿Por qué en _post_clean() y no en clean()?
        Porque AUTH_PASSWORD_VALIDATORS incluye
        UserAttributeSimilarityValidator, que rechaza contraseñas parecidas al
        correo o al nombre de la persona. Para poder comparar necesita el objeto
        Usuario ya poblado, y eso solo ocurre en _post_clean(), cuando el
        ModelForm ha copiado cleaned_data a self.instance.

        Es exactamente la misma estrategia que usa BaseUserCreationForm de
        Django: se reutiliza el patrón en vez de improvisar otro.
        """
        super()._post_clean()

        password = self.cleaned_data.get("password1")
        if password and self.cleaned_data.get("metodo_clave") == self.MANUAL:
            try:
                password_validation.validate_password(password, self.instance)
            except ValidationError as error:
                self.add_error("password1", error)

    def save(self, commit=True):
        """Crea el usuario con su contraseña ya convertida en hash.

        NUNCA se asigna usuario.password = "texto". set_password() aplica
        Argon2id (configurado en PASSWORD_HASHERS) y guarda
        "argon2$argon2id$v=19$m=...$sal$hash". El texto plano no se almacena en
        ningún momento ni en ningún lugar.
        """
        usuario = super().save(commit=False)

        # Si el administrador no escribió un nombre de usuario, se propone uno.
        if not usuario.nombre_usuario:
            usuario.nombre_usuario = Usuario.objects.generar_nombre_usuario(
                first_name=usuario.first_name,
                last_name=usuario.last_name,
                email=usuario.email,
            )

        if self.cleaned_data.get("metodo_clave") == self.MANUAL:
            usuario.set_password(self.cleaned_data["password1"])
            self.requiere_enlace = False
        else:
            # Contraseña aleatoria que nadie conoce: la cuenta existe pero es
            # inaccesible hasta que la persona use el enlace del correo.
            usuario.set_password(generar_clave_aleatoria())
            self.requiere_enlace = True

        if commit:
            usuario.save()

        return usuario


class EditarUsuarioForm(UsuarioFormBase):
    """Formulario de edición de cuentas.

    Campos que NO se pueden modificar aquí, y por qué:

      password        -> es un hash irreversible: no hay nada que "editar".
                         Cambiarla tiene su propio flujo (enlace al correo),
                         que además avisa al titular por correo.
      last_login,
      date_joined,
      creado_en,
      actualizado_en  -> son HECHOS registrados por el sistema, no datos
                         editables. Si un administrador pudiera cambiarlos, la
                         auditoría dejaría de ser confiable.
      is_staff,
      is_superuser    -> son permisos técnicos sobre /admin/, no roles del
                         negocio. Se administran solo desde /admin/ y solo un
                         superusuario puede otorgarlos (evita la escalada de
                         privilegios desde la interfaz común).

    Y una regla especial: el administrador NO puede cambiar su propio rol ni su
    propio estado. Ver __init__.
    """

    def __init__(self, *args, usuario_actual=None, **kwargs):
        """usuario_actual es quien está usando el formulario (request.user)."""
        super().__init__(*args, **kwargs)
        self.usuario_actual = usuario_actual

        editando_su_propia_cuenta = (
            usuario_actual is not None
            and self.instance.pk
            and usuario_actual.pk == self.instance.pk
        )

        if editando_su_propia_cuenta:
            # disabled=True hace dos cosas a la vez:
            #   1. en el HTML, el campo aparece bloqueado;
            #   2. y —esto es lo importante— Django IGNORA el valor que llegue
            #      del navegador y usa el valor inicial de la base de datos.
            # Por eso la protección no se puede burlar enviando el formulario
            # con curl o modificando el HTML con las herramientas del
            # navegador: no es una defensa visual, es una defensa real.
            for nombre in ("rol", "is_active"):
                self.fields[nombre].disabled = True
                self.fields[nombre].help_text = (
                    "No puedes modificar tu propio rol ni tu propio estado. "
                    "Debe hacerlo otro administrador."
                )

    def clean(self):
        """Regla de negocio: el sistema nunca puede quedar sin administradores."""
        datos = super().clean()

        # ¿Esta edición dejaría al sistema sin ningún administrador activo?
        if self.instance.pk and self.instance.es_ultimo_administrador_activo():
            queda_activo = datos.get("is_active", self.instance.is_active)
            rol_nuevo = datos.get("rol", self.instance.rol)
            sigue_siendo_admin = self.instance.is_superuser or (
                rol_nuevo is not None and rol_nuevo.codigo == RolCodigo.ADMINISTRADOR
            )

            if not queda_activo:
                self.add_error(
                    "is_active",
                    ValidationError(
                        "Es el único administrador activo del sistema. Si se "
                        "desactiva, nadie podría volver a administrar cuentas. "
                        "Crea o habilita otro administrador antes.",
                        code="ultimo_administrador",
                    ),
                )
            elif not sigue_siendo_admin:
                self.add_error(
                    "rol",
                    ValidationError(
                        "Es el único administrador activo del sistema. Asigna "
                        "el rol Administrador a otra persona antes de cambiar "
                        "este.",
                        code="ultimo_administrador",
                    ),
                )

        return datos


class FiltroUsuariosForm(forms.Form):
    """Formulario de búsqueda y filtros del listado.

    Es un Form normal (no ModelForm) porque no crea ni modifica nada: solo
    limpia los parámetros que llegan por la URL.

    ¿Por qué pasar los filtros por un formulario en vez de leer request.GET
    directamente? Porque el formulario valida y convierte: si alguien escribe
    ?rol=abc a mano, el ModelChoiceField lo rechaza y el listado simplemente no
    filtra por rol, en lugar de lanzar una excepción al consultar la base de
    datos con un id inválido.
    """

    ESTADOS = (
        ("", "Todos los estados"),
        ("activos", "Solo activos"),
        ("inactivos", "Solo inactivos"),
    )

    q = forms.CharField(
        label="Buscar",
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": CLASE_TEXTO,
                "placeholder": "Nombre, apellido, correo, usuario o RUT",
                "autocomplete": "off",
            }
        ),
    )
    rol = forms.ModelChoiceField(
        label="Rol",
        required=False,
        queryset=Rol.objects.all().order_by("nombre"),
        empty_label="Todos los roles",
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
    )
    estado = forms.ChoiceField(
        label="Estado",
        required=False,
        choices=ESTADOS,
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
    )

    def clean_q(self):
        return (self.cleaned_data.get("q") or "").strip()
