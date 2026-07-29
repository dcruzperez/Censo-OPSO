"""Modelos de la app "usuarios".

Cuatro tablas:
  1. usuarios_rol                 -> catálogo de roles (Administrador/Supervisor/Censista)
  2. usuarios_usuario             -> personas que acceden al sistema
  3. usuarios_intento_acceso      -> bitácora de intentos de inicio de sesión
  4. usuarios_registro_auditoria  -> bitácora de acciones administrativas (HU-03)

Las dos últimas son bitácoras y cumplen funciones distintas:
  - IntentoAcceso responde "¿quién entró al sistema?" (autenticación).
  - RegistroAuditoria responde "¿quién modificó a quién?" (administración).
"""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .managers import UsuarioManager
from .validators import (
    limpiar_nombre_usuario,
    limpiar_rut,
    validar_nombre_usuario,
    validar_rut,
)


class RolCodigo(models.TextChoices):
    """Códigos de rol definidos como constantes.

    ¿Por qué una clase de opciones y no texto libre?
    Porque así el código nunca escribe "adminstrador" mal: se usa
    RolCodigo.ADMINISTRADOR y el editor autocompleta. Además Django puede
    validar el valor y mostrar la etiqueta legible en los formularios.
    """

    ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
    SUPERVISOR = "SUPERVISOR", "Supervisor"
    CENSISTA = "CENSISTA", "Censista"


class Rol(models.Model):
    """Catálogo de roles del sistema (tabla independiente).

    DECISIÓN DE DISEÑO: el rol es una TABLA y no un simple campo de texto en
    Usuario. Ventajas:
      - Un rol es una entidad con datos propios (nombre visible, descripción,
        panel de destino, si está activo). Eso no cabe en un CharField.
      - Se puede desactivar un rol completo sin tocar el código.
      - La integridad la garantiza la base de datos con una clave foránea:
        es imposible que exista un usuario con un rol que no existe.
      - Permite crecer: si mañana OPSO necesita el rol "Digitador" o
        "Coordinador Regional", se agrega una fila, no se modifica el modelo
        ni se generan migraciones.
    """

    codigo = models.CharField(
        "código",
        max_length=20,
        choices=RolCodigo.choices,
        unique=True,  # no puede haber dos roles "SUPERVISOR"
        help_text="Identificador interno e inmutable del rol.",
    )
    nombre = models.CharField(
        "nombre visible",
        max_length=60,
        help_text="Nombre que se muestra en la interfaz.",
    )
    descripcion = models.TextField(
        "descripción",
        blank=True,
        help_text="Qué puede hacer este rol dentro de OPSO.",
    )
    dashboard_url_name = models.CharField(
        "panel de destino",
        max_length=100,
        help_text=(
            "Nombre de la URL de Django a la que se redirige tras iniciar "
            "sesión. Ej.: dashboards:supervisor"
        ),
    )
    activo = models.BooleanField(
        "activo",
        default=True,
        help_text="Si se desactiva, sus usuarios no podrán iniciar sesión.",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        db_table = "usuarios_rol"
        verbose_name = "rol"
        verbose_name_plural = "roles"
        ordering = ["nombre"]
        constraints = [
            # Restricción a nivel de BASE DE DATOS: aunque alguien inserte una
            # fila con SQL directo, PostgreSQL rechazará un código inválido.
            models.CheckConstraint(
                condition=models.Q(codigo__in=RolCodigo.values),
                name="rol_codigo_valido",
            ),
        ]

    def __str__(self):
        return self.nombre


class Usuario(AbstractUser):
    """Usuario del sistema OPSO.

    DECISIÓN DE DISEÑO: hereda de AbstractUser (no de AbstractBaseUser ni usa
    el User por defecto). Explicación completa en la documentación, resumen:
      - Reaprovecha todo lo que ya funciona y está auditado: hash de
        contraseñas, permisos, grupos, integración con el admin y con
        login_required.
      - Permite agregar los campos que OPSO necesita (rol, RUT, teléfono).
      - Permite cambiar el identificador de acceso de "username" a "email".
    """

    # Eliminamos el campo username: en OPSO se entra con el correo.
    username = None

    email = models.EmailField(
        "correo electrónico",
        unique=True,  # es la credencial de acceso: debe ser único
        help_text="Correo institucional con el que inicia sesión.",
    )
    nombre_usuario = models.CharField(
        "nombre de usuario",
        max_length=30,
        unique=True,
        null=True,  # NULL en la base de datos (varios NULL no chocan en SQL)
        blank=True,  # opcional en los formularios
        validators=[validar_nombre_usuario],
        help_text=(
            "Identificador corto para listados y planillas (ej.: msoto). "
            "NO se usa para iniciar sesión: la credencial es el correo."
        ),
    )
    rut = models.CharField(
        "RUT",
        max_length=12,
        unique=True,
        null=True,  # NULL en la base de datos
        blank=True,  # opcional en los formularios
        validators=[validar_rut],
        help_text="Formato 12345678-9. Identifica a la persona en terreno.",
    )
    telefono = models.CharField(
        "teléfono",
        max_length=20,
        blank=True,
        help_text="Contacto para coordinación del operativo.",
    )
    rol = models.ForeignKey(
        Rol,
        on_delete=models.PROTECT,  # no se puede borrar un rol con usuarios
        related_name="usuarios",  # rol.usuarios.all()
        null=True,
        blank=True,
        verbose_name="rol",
        help_text="Determina qué puede ver y hacer en el sistema.",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    # --- Configuración del sistema de autenticación ---
    # Campo que actúa como nombre de usuario al iniciar sesión.
    USERNAME_FIELD = "email"
    # Campo usado para enviar correos (recuperación de contraseña).
    EMAIL_FIELD = "email"
    # Campos que pedirá createsuperuser además de email y contraseña.
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UsuarioManager()

    class Meta:
        db_table = "usuarios_usuario"
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["first_name", "last_name"]
        indexes = [
            # Índice para acelerar los listados filtrados por rol.
            models.Index(fields=["rol", "is_active"], name="idx_usuario_rol_activo"),
            # Índice del listado de administración: se pagina y ordena por
            # nombre, y casi siempre se filtra por estado.
            models.Index(
                fields=["is_active", "first_name", "last_name"],
                name="idx_usuario_estado_nombre",
            ),
        ]

    def __str__(self):
        return f"{self.get_full_name() or self.email}"

    def save(self, *args, **kwargs):
        """Normaliza los datos antes de escribir en PostgreSQL."""
        self.email = self.email.strip().lower()
        self.rut = limpiar_rut(self.rut) if self.rut else None
        self.nombre_usuario = limpiar_nombre_usuario(self.nombre_usuario)
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Ayudantes de rol. La lógica de permisos vive AQUÍ, en el modelo, no
    # repartida en las vistas y plantillas ("fat model, thin view").
    # ------------------------------------------------------------------

    @property
    def codigo_rol(self):
        """Código del rol o None si aún no tiene rol asignado."""
        return self.rol.codigo if self.rol_id else None

    @property
    def es_administrador(self):
        # El superusuario técnico se considera administrador aunque no tenga
        # una fila de rol asignada (así nunca se queda fuera del sistema).
        return self.is_superuser or self.codigo_rol == RolCodigo.ADMINISTRADOR

    @property
    def es_supervisor(self):
        return self.codigo_rol == RolCodigo.SUPERVISOR

    @property
    def es_censista(self):
        return self.codigo_rol == RolCodigo.CENSISTA

    def tiene_rol(self, *codigos):
        """True si el usuario tiene alguno de los roles indicados y está activo."""
        if not self.rol_id or not self.rol.activo:
            return False
        return self.rol.codigo in codigos

    # ------------------------------------------------------------------
    # Ayudantes de la HU-03 (Administración de usuarios)
    # ------------------------------------------------------------------

    @property
    def etiqueta_estado(self):
        """Texto legible del estado, para plantillas y auditoría."""
        return "Activo" if self.is_active else "Inactivo"

    @property
    def usuario_visible(self):
        """Nombre de usuario o, si no tiene, la parte local del correo.

        Evita celdas vacías en el listado sin obligar a que el campo sea
        obligatorio: si nadie definió un alias, se muestra algo útil igual.
        """
        return self.nombre_usuario or self.email.split("@")[0]

    def es_ultimo_administrador_activo(self):
        """True si deshabilitar o degradar esta cuenta dejaría al sistema sin administradores.

        ¿Por qué es importante? Porque un sistema sin ningún administrador
        activo queda "cerrado por dentro": nadie podría volver a crear usuarios
        ni reactivar cuentas desde la aplicación, y habría que intervenir la
        base de datos a mano. Es un caso de bloqueo total ("lockout") y se
        previene con una consulta de una línea.
        """
        if not self.es_administrador or not self.is_active:
            return False

        otros = self.__class__.objects.administradores_activos().exclude(pk=self.pk)
        return not otros.exists()

    def get_dashboard_url(self):
        """Devuelve la URL del panel que corresponde a este usuario.

        Es el corazón del punto 9 (redirección por rol). La relación
        rol -> panel está GUARDADA EN LA BASE DE DATOS, no escrita a mano en
        un if/elif dentro de la vista. Si se agrega un rol nuevo, basta con
        registrar su panel en la tabla usuarios_rol.
        """
        if self.rol_id and self.rol.activo and self.rol.dashboard_url_name:
            try:
                return reverse(self.rol.dashboard_url_name)
            except NoReverseMatch:
                # El nombre guardado no existe en las URLs: no rompemos el
                # inicio de sesión, caemos al respaldo de abajo.
                pass

        if self.is_superuser:
            return reverse("dashboards:administrador")

        # Usuario válido pero sin rol útil: pantalla informativa.
        return reverse("usuarios:sin_rol")


class IntentoAcceso(models.Model):
    """Bitácora de intentos de inicio de sesión (auditoría y seguridad).

    Cumple dos funciones:
      1. TRAZABILIDAD: permite responder "quién entró, cuándo y desde dónde",
         exigencia razonable al manejar datos personales de familias
         (Ley N° 19.628 y Ley N° 21.719 sobre protección de datos).
      2. DEFENSA ACTIVA: contando los fallos recientes se bloquea
         temporalmente la cuenta ante un ataque de fuerza bruta.

    NUNCA se guarda la contraseña probada, ni siquiera cifrada.
    """

    email_ingresado = models.CharField(
        "correo ingresado",
        max_length=254,
        db_index=True,
        help_text="Lo que escribió la persona (puede no existir como cuenta).",
    )
    usuario = models.ForeignKey(
        "usuarios.Usuario",
        on_delete=models.SET_NULL,  # si se borra el usuario, la bitácora queda
        null=True,
        blank=True,
        related_name="intentos_acceso",
        verbose_name="usuario",
    )
    exitoso = models.BooleanField("¿fue exitoso?", default=False)
    ip = models.GenericIPAddressField("dirección IP", null=True, blank=True)
    user_agent = models.CharField("navegador", max_length=300, blank=True)
    ocurrido_en = models.DateTimeField("fecha y hora", default=timezone.now, db_index=True)

    class Meta:
        db_table = "usuarios_intento_acceso"
        verbose_name = "intento de acceso"
        verbose_name_plural = "intentos de acceso"
        ordering = ["-ocurrido_en"]
        indexes = [
            # Índice compuesto: es exactamente la consulta que hace el
            # bloqueo por fuerza bruta (mismo correo + fallidos + recientes).
            models.Index(
                fields=["email_ingresado", "exitoso", "ocurrido_en"],
                name="idx_intento_email_exito",
            ),
        ]

    def __str__(self):
        estado = "OK" if self.exitoso else "FALLIDO"
        return f"{self.email_ingresado} [{estado}] {self.ocurrido_en:%d-%m-%Y %H:%M}"


# ==========================================================================
# AUDITORÍA DE LA ADMINISTRACIÓN DE USUARIOS (HU-03)
# ==========================================================================


class AccionAuditoria(models.TextChoices):
    """Catálogo cerrado de acciones administrativas registrables.

    Se usa TextChoices y no texto libre por la misma razón que en RolCodigo:
    el valor guardado es estable y consultable ("dame todas las
    deshabilitaciones del mes"), mientras la etiqueta legible puede cambiar
    sin migrar datos.
    """

    CREAR = "CREAR", "Creó la cuenta"
    EDITAR = "EDITAR", "Editó los datos"
    CAMBIAR_ROL = "CAMBIAR_ROL", "Cambió el rol"
    DESHABILITAR = "DESHABILITAR", "Deshabilitó la cuenta"
    HABILITAR = "HABILITAR", "Habilitó la cuenta"
    ENVIAR_ENLACE = "ENVIAR_ENLACE", "Envió enlace de contraseña"


class RegistroAuditoria(models.Model):
    """Bitácora de las acciones del administrador sobre las cuentas.

    Responde las cuatro preguntas de toda auditoría:
        ¿QUIÉN?    -> administrador (+ administrador_email como copia fija)
        ¿CUÁNDO?   -> ocurrido_en
        ¿QUÉ hizo? -> accion + detalle
        ¿A QUIÉN?  -> usuario_afectado (+ usuario_afectado_email)

    DECISIÓN DE DISEÑO 1 — tabla propia y no reutilizar django_admin_log.
    El log del admin de Django solo registra lo que ocurre DENTRO de /admin/.
    OPSO administra usuarios desde su propia interfaz, así que necesita su
    propia bitácora; además aquí se guarda la IP, que el log del admin no tiene.

    DECISIÓN DE DISEÑO 2 — se duplican los correos en columnas de texto.
    Es una desnormalización DELIBERADA. Las claves foráneas usan SET_NULL: si
    algún día se borrara físicamente una cuenta (por ejemplo, por una solicitud
    de eliminación de datos personales), la fila de auditoría sobreviviría pero
    perdería la referencia. La copia del correo mantiene legible el registro
    histórico. En una bitácora, la trazabilidad vale más que la normalización
    perfecta.

    DECISIÓN DE DISEÑO 3 — la bitácora es de solo escritura.
    No hay vistas de edición ni de borrado, y en el admin está bloqueada. Una
    bitácora que se puede alterar no sirve como evidencia.
    """

    administrador = models.ForeignKey(
        "usuarios.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acciones_realizadas",
        verbose_name="administrador",
        help_text="Quién ejecutó la acción.",
    )
    administrador_email = models.CharField(
        "correo del administrador",
        max_length=254,
        blank=True,
        help_text="Copia fija: sobrevive aunque la cuenta se elimine.",
    )
    accion = models.CharField(
        "acción",
        max_length=20,
        choices=AccionAuditoria.choices,
        db_index=True,
    )
    usuario_afectado = models.ForeignKey(
        "usuarios.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acciones_recibidas",
        verbose_name="usuario afectado",
        help_text="Sobre qué cuenta se ejecutó la acción.",
    )
    usuario_afectado_email = models.CharField(
        "correo del usuario afectado",
        max_length=254,
        blank=True,
    )
    detalle = models.TextField(
        "detalle",
        blank=True,
        help_text="Qué cambió exactamente, campo por campo.",
    )
    ip = models.GenericIPAddressField("dirección IP", null=True, blank=True)
    user_agent = models.CharField("navegador", max_length=300, blank=True)
    ocurrido_en = models.DateTimeField(
        "fecha y hora", default=timezone.now, db_index=True
    )

    class Meta:
        db_table = "usuarios_registro_auditoria"
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"
        ordering = ["-ocurrido_en", "-id"]
        indexes = [
            # Consulta típica de la ficha de un usuario: "historial de esta
            # cuenta, del más nuevo al más antiguo".
            models.Index(
                fields=["usuario_afectado", "-ocurrido_en"],
                name="idx_auditoria_afectado",
            ),
        ]

    def __str__(self):
        return (
            f"{self.ocurrido_en:%d-%m-%Y %H:%M} · {self.administrador_email} "
            f"· {self.get_accion_display()} · {self.usuario_afectado_email}"
        )
