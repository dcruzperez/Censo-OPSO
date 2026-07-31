"""Modelos de la app "usuarios".

Seis tablas:
  1. usuarios_rol                 -> catálogo de roles (Administrador/Supervisor/Censista)
  2. usuarios_permiso             -> catálogo de acciones autorizables (HU-04)
  3. usuarios_rol_permisos        -> qué permisos tiene cada rol (HU-04)
  4. usuarios_usuario             -> personas que acceden al sistema
  5. usuarios_intento_acceso      -> bitácora de intentos de inicio de sesión
  6. usuarios_registro_auditoria  -> bitácora de acciones administrativas (HU-03/04)

Las dos últimas son bitácoras y cumplen funciones distintas:
  - IntentoAcceso responde "¿quién entró al sistema?" (autenticación).
  - RegistroAuditoria responde "¿quién modificó qué?" (administración).

La cadena de autorización completa queda así:

    Usuario --rol--> Rol --permisos--> Permiso

Un usuario no tiene permisos propios: los hereda de su rol. Esa es la decisión
central de la HU-04 y se explica en el modelo Permiso.
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


class ModuloPermiso(models.TextChoices):
    """Módulos funcionales de OPSO, usados para AGRUPAR los permisos.

    ¿Por qué agrupar? Porque una matriz plana de veinte casillas sin encabezados
    es ilegible: el administrador tiene que poder ver "todo lo relativo a
    fichas" de un vistazo antes de marcar nada. El módulo es una etiqueta de
    presentación, no una entidad con datos propios, así que es un campo de
    opciones y no una tabla (a diferencia del rol, ver más abajo).
    """

    USUARIOS = "USUARIOS", "Usuarios"
    ROLES = "ROLES", "Roles y permisos"
    AUDITORIA = "AUDITORIA", "Auditoría"
    FICHAS = "FICHAS", "Fichas de familias"
    OPERATIVOS = "OPERATIVOS", "Operativos y sectores"
    REPORTES = "REPORTES", "Reportes"


class Permiso(models.Model):
    """Una acción concreta que un rol puede tener autorizada.

    DECISIÓN DE DISEÑO — catálogo propio en vez de django.contrib.auth.Permission.

    Django trae su propio sistema de permisos, y se evaluó usarlo. Se descartó
    por una razón concreta: los permisos de Django se generan automáticamente a
    partir de los modelos y son siempre los cuatro verbos de una tabla
    (add_usuario, change_usuario, delete_usuario, view_usuario). Ese vocabulario
    describe operaciones sobre FILAS, no las acciones del negocio.

    OPSO necesita expresar cosas como "validar una ficha levantada por un
    censista" o "asignar censistas a un sector". Eso no es "change_ficha": es
    una acción funcional que un supervisor puede hacer y un censista no, sobre
    la misma tabla y a veces sobre la misma fila. Forzarlo dentro del esquema de
    Django obligaría a inventar modelos falsos solo para colgarles permisos, o a
    crear permisos "personalizados" en el Meta de cada modelo, que es
    precisamente lo que aquí se hace explícito y consultable.

    Ventaja adicional, la misma que motivó que el rol sea una tabla: agregar el
    permiso "fichas.reabrir" es INSERTAR UNA FILA. No hay que tocar el código,
    ni generar una migración, ni redesplegar.

    Los permisos de Django siguen existiendo y funcionando para /admin/ (los
    usa el propio panel para decidir quién ve qué). Los dos sistemas conviven
    sin estorbarse porque gobiernan cosas distintas: auth.Permission gobierna
    /admin/, usuarios.Permiso gobierna OPSO.
    """

    codigo = models.CharField(
        "código",
        max_length=60,
        unique=True,
        help_text=(
            "Identificador interno con el que el código comprueba el permiso. "
            "Formato módulo.acción, ej.: fichas.validar"
        ),
    )
    nombre = models.CharField(
        "nombre visible",
        max_length=120,
        help_text="Cómo se lee el permiso en la matriz.",
    )
    modulo = models.CharField(
        "módulo",
        max_length=20,
        choices=ModuloPermiso.choices,
        db_index=True,
        help_text="Sección de OPSO a la que pertenece. Solo agrupa la vista.",
    )
    descripcion = models.TextField(
        "descripción",
        blank=True,
        help_text="Qué habilita exactamente. Se muestra como ayuda en la matriz.",
    )
    orden = models.PositiveSmallIntegerField(
        "orden",
        default=100,
        help_text=(
            "Posición dentro de su módulo. Permite listar los permisos de menos "
            "a más poder (ver, crear, editar, borrar) en vez de alfabéticamente."
        ),
    )
    activo = models.BooleanField(
        "activo",
        default=True,
        help_text=(
            "Si se desactiva, deja de concederse aunque siga marcado en la "
            "matriz. Permite retirar un permiso sin borrar las filas que "
            "documentan quién lo tenía."
        ),
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        db_table = "usuarios_permiso"
        verbose_name = "permiso"
        verbose_name_plural = "permisos"
        # El orden de la matriz: primero por módulo, y dentro de cada módulo por
        # el campo "orden". Así la lista es estable y pedagógica.
        ordering = ["modulo", "orden", "nombre"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(modulo__in=ModuloPermiso.values),
                name="permiso_modulo_valido",
            ),
        ]

    def __str__(self):
        return self.nombre

    @property
    def etiqueta_modulo(self):
        """Nombre legible del módulo (para plantillas y auditoría)."""
        return ModuloPermiso(self.modulo).label


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
    # DECISIÓN DE DISEÑO: relación muchos-a-muchos SIN modelo intermedio propio.
    #
    # Se consideró un modelo "RolPermiso" explícito con columnas "concedido_en" y
    # "concedido_por". Se descartó porque esa información ya la responde
    # RegistroAuditoria, que además la conserva incluso después de que el
    # permiso se revoque. Una tabla intermedia solo guarda el estado ACTUAL: si
    # el permiso se quita, la fila desaparece y con ella el dato de quién lo
    # había concedido. La bitácora, en cambio, es un registro histórico que no
    # se borra. Duplicar el dato en la tabla intermedia daría una respuesta peor
    # y obligaría a mantener dos fuentes coherentes.
    permisos = models.ManyToManyField(
        Permiso,
        related_name="roles",
        blank=True,  # un rol puede existir sin ningún permiso concedido
        verbose_name="permisos",
        # Nombre explícito de la tabla intermedia. Django la llamaría igual por
        # convención, pero declararlo deja el esquema escrito en el código.
        db_table="usuarios_rol_permisos",
        help_text="Acciones que este rol tiene autorizadas dentro de OPSO.",
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

    @property
    def concede_todo(self):
        """True si este rol tiene todos los permisos por definición del negocio.

        Es la contraparte en el modelo Rol de la regla 1 de
        Usuario.tiene_permiso(): el rol Administrador concede todo de forma
        implícita. La matriz lo consulta para mostrar su columna marcada y no
        editable, en vez de dejar creer que quitando una casilla se le retira
        algo.
        """
        return self.codigo == RolCodigo.ADMINISTRADOR

    def permisos_activos(self):
        """Permisos concedidos y vigentes, ya ordenados por módulo."""
        return self.permisos.filter(activo=True)


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
    # Ayudantes de la HU-04 (Roles y permisos)
    # ------------------------------------------------------------------

    def tiene_permiso(self, codigo):
        """True si el rol de este usuario tiene concedido el permiso indicado.

        Tres reglas, en este orden:

        1. El ADMINISTRADOR (y el superusuario técnico) tienen todo concedido de
           forma implícita. No es un atajo cómodo: es la MISMA regla que ya
           aplica RolRequeridoMixin con permitir_administrador=True en todo el
           sistema desde la HU-01. Si aquí se decidiera lo contrario, el
           administrador podría quitarse a sí mismo el permiso que gobierna la
           matriz y dejar el sistema sin nadie capaz de repararlo desde la
           aplicación: el mismo bloqueo total que ya se previene con
           es_ultimo_administrador_activo().

        2. Sin rol, o con el rol desactivado, no hay ningún permiso. Desactivar
           un rol tiene que cortar el acceso de golpe, sin recorrer sus filas.

        3. En cualquier otro caso se consulta la matriz. Se exige activo=True
           también en el permiso: un permiso retirado deja de concederse aunque
           siga marcado, sin tener que limpiar la tabla intermedia.
        """
        if self.es_administrador:
            return True

        if not self.rol_id or not self.rol.activo:
            return False

        return self.rol.permisos.filter(codigo=codigo, activo=True).exists()

    def tiene_algun_permiso(self, *codigos):
        """True si tiene al menos uno de los permisos indicados.

        Se resuelve en UNA consulta con __in en vez de llamar N veces a
        tiene_permiso(): la diferencia importa en una vista que comprueba varios
        permisos para decidir qué botones dibujar.
        """
        if self.es_administrador:
            return True

        if not self.rol_id or not self.rol.activo:
            return False

        return self.rol.permisos.filter(codigo__in=codigos, activo=True).exists()

    def codigos_permisos(self):
        """Conjunto de los códigos de permiso concedidos a este usuario.

        Devuelve un set y no un QuerySet a propósito: quien lo llame va a hacer
        varias comprobaciones de pertenencia seguidas (típicamente en una
        plantilla) y un set las resuelve en memoria, con una sola consulta.

        Para el administrador devuelve TODOS los códigos activos, coherente con
        la regla 1 de tiene_permiso(): lo que se muestra tiene que coincidir con
        lo que realmente se autoriza.
        """
        if self.es_administrador:
            return set(
                Permiso.objects.filter(activo=True).values_list("codigo", flat=True)
            )

        if not self.rol_id or not self.rol.activo:
            return set()

        return set(
            self.rol.permisos.filter(activo=True).values_list("codigo", flat=True)
        )

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
    # HU-04: esta acción no recae sobre una cuenta sino sobre un ROL. Por eso la
    # bitácora tiene, además de usuario_afectado, un rol_afectado.
    CAMBIAR_PERMISOS = "CAMBIAR_PERMISOS", "Cambió los permisos del rol"
    # HU-05: acciones sobre la organización territorial (operativos, comunas,
    # sectores y zonas). Son genéricas a propósito: cuál de las cuatro entidades
    # se tocó lo dice objeto_tipo, así que no hacen falta cuatro juegos de
    # acciones ("CREAR_COMUNA", "CREAR_SECTOR", ...) que multiplicarían el
    # catálogo sin agregar información.
    CREAR_TERRITORIO = "CREAR_TERRITORIO", "Creó el registro territorial"
    EDITAR_TERRITORIO = "EDITAR_TERRITORIO", "Editó el registro territorial"
    ACTIVAR_TERRITORIO = "ACTIVAR_TERRITORIO", "Activó el registro territorial"
    DESACTIVAR_TERRITORIO = (
        "DESACTIVAR_TERRITORIO",
        "Desactivó el registro territorial",
    )
    CAMBIAR_ESTADO_OPERATIVO = (
        "CAMBIAR_ESTADO_OPERATIVO",
        "Cambió el estado del operativo",
    )
    # HU-06: el reparto del trabajo de terreno. Recae sobre un SECTOR (quién lo
    # cubre), así que reutiliza TipoObjetoAuditoria.SECTOR sin agregar un tipo
    # nuevo. Una sola acción para asignar y desasignar, igual que
    # CAMBIAR_PERMISOS: el detalle dice qué entró y qué salió, y así una
    # reasignación —que es las dos cosas a la vez— queda en UNA fila y no en dos
    # que habría que correlacionar por su hora.
    CAMBIAR_ASIGNACIONES = (
        "CAMBIAR_ASIGNACIONES",
        "Cambió las asignaciones del sector",
    )


class TipoObjetoAuditoria(models.TextChoices):
    """Qué clase de objeto territorial afectó una acción (HU-05).

    Acompaña a las columnas objeto_id y objeto_nombre de RegistroAuditoria. Ver
    allí la explicación de por qué el territorio se referencia así y no con una
    clave foránea por entidad.
    """

    OPERATIVO = "OPERATIVO", "Operativo"
    COMUNA = "COMUNA", "Comuna"
    SECTOR = "SECTOR", "Sector"
    ZONA = "ZONA", "Zona"


class RegistroAuditoria(models.Model):
    """Bitácora de las acciones del administrador sobre las cuentas.

    Responde las cuatro preguntas de toda auditoría:
        ¿QUIÉN?    -> administrador (+ administrador_email como copia fija)
        ¿CUÁNDO?   -> ocurrido_en
        ¿QUÉ hizo? -> accion + detalle
        ¿SOBRE QUÉ? -> usuario_afectado (+ email) o rol_afectado (+ nombre)

    Desde la HU-04 el objeto afectado puede ser una cuenta o un rol: cambiar los
    permisos de "Supervisor" no modifica a ninguna persona en particular, pero
    altera lo que pueden hacer todas las que tengan ese rol, y por eso es
    justamente lo más importante de auditar. La propiedad "objetivo" resuelve
    cuál de los dos aplica.

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
        # 30 y no 20: la HU-05 agregó "CAMBIAR_ESTADO_OPERATIVO", de 24
        # caracteres. Se amplía la columna en vez de abreviar el código, porque
        # un código legible en la base de datos vale más que cuatro bytes.
        max_length=30,
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
    # ------------------------------------------------------------------
    # HU-04: el objeto afectado también puede ser un ROL.
    #
    # ¿Por qué dos columnas y no una genérica del tipo "objeto_afectado"?
    # Django ofrece claves foráneas genéricas (contenttypes + GenericForeignKey),
    # que permitirían apuntar a cualquier modelo con un solo par de columnas. Se
    # descartó: una clave genérica no la puede verificar la base de datos (no hay
    # restricción de integridad posible cuando el destino es variable), obliga a
    # una consulta extra por fila para resolver el tipo, y complica los filtros
    # del listado. Con dos claves foráneas explícitas y nulas, PostgreSQL sigue
    # garantizando la integridad y las consultas siguen siendo directas. Solo hay
    # dos tipos de objeto auditables y no se prevén muchos más.
    # ------------------------------------------------------------------
    rol_afectado = models.ForeignKey(
        "usuarios.Rol",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acciones_auditoria",
        verbose_name="rol afectado",
        help_text="Sobre qué rol se ejecutó la acción (permisos).",
    )
    rol_afectado_nombre = models.CharField(
        "nombre del rol afectado",
        max_length=60,
        blank=True,
        help_text="Copia fija: sobrevive aunque el rol se elimine.",
    )
    # ------------------------------------------------------------------
    # HU-05: el objeto afectado también puede ser territorial (un operativo,
    # una comuna, un sector o una zona).
    #
    # REVISIÓN EXPLÍCITA DE LA DECISIÓN DE DISEÑO 2 DE LA HU-04.
    #
    # Allí se escribió que dos claves foráneas explícitas eran preferibles a una
    # referencia genérica, con este argumento: "solo hay dos tipos de objeto
    # auditables y no se prevén muchos más". La HU-05 agrega cuatro de golpe, así
    # que la premisa dejó de ser cierta y la decisión se revisa en vez de
    # arrastrarse.
    #
    # Seguir el camino anterior significaría OCHO columnas nuevas (cuatro claves
    # foráneas más cuatro copias de texto) para una tabla que ya tiene cuatro
    # dedicadas a lo mismo, y otras dos por cada entidad que traigan las
    # historias de fichas y reportes. Una bitácora con veinte columnas casi
    # siempre nulas es ilegible, y las consultas tendrían que unir seis tablas
    # para responder "¿qué pasó aquí?".
    #
    # Se usan entonces tres columnas para las cuatro entidades: el tipo, el
    # identificador y el nombre. NO hay clave foránea, y eso es aceptable aquí
    # por una razón concreta que no valía para las cuentas: el territorio NUNCA
    # se borra físicamente. Comuna, sector y zona se desactivan (misma decisión
    # que las cuentas en la HU-03), así que la fila apuntada sigue existiendo y
    # el identificador no queda huérfano. Y si algún día se borrara, objeto_nombre
    # conserva la información legible, que es exactamente el mismo seguro que ya
    # protege a usuario_afectado_email.
    #
    # Lo que se pierde —que PostgreSQL valide la referencia— se compensa donde
    # importa: el valor probatorio de una bitácora está en el texto que una
    # persona puede leer, no en poder navegar la clave foránea.
    # ------------------------------------------------------------------
    objeto_tipo = models.CharField(
        "tipo de objeto territorial",
        max_length=20,
        choices=TipoObjetoAuditoria.choices,
        blank=True,
        db_index=True,
        help_text="Qué clase de registro territorial se afectó (HU-05).",
    )
    objeto_id = models.PositiveIntegerField(
        "identificador del objeto",
        null=True,
        blank=True,
        help_text=(
            "Clave primaria del registro territorial afectado. Sin clave "
            "foránea a propósito: ver la explicación en el modelo."
        ),
    )
    objeto_nombre = models.CharField(
        "nombre del objeto territorial",
        max_length=250,
        blank=True,
        help_text=(
            "Copia fija con el camino completo, ej.: «Zona 1 · Los Boldos · "
            "Concepción». Es lo que hace legible la fila años después."
        ),
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

    @property
    def objetivo(self):
        """Sobre qué se actuó, en una sola cadena legible.

        Existe para que las plantillas y el admin no repitan el mismo
        condicional: una fila de auditoría apunta a una cuenta, a un rol o a un
        registro territorial, nunca a más de uno, y quien la lee solo quiere
        saber "¿a quién o a qué?".

        Se leen las COPIAS DE TEXTO y no las claves foráneas, por la misma razón
        por la que esas copias existen: si el objeto se eliminó, la clave es
        NULL pero el texto sigue ahí y la bitácora no queda ilegible.
        """
        if self.usuario_afectado_email:
            return self.usuario_afectado_email
        if self.rol_afectado_nombre:
            return f"Rol: {self.rol_afectado_nombre}"
        if self.objeto_nombre:
            # El tipo va delante porque "Los Boldos" no dice si es un sector o
            # una comuna, y en una bitácora esa diferencia importa.
            return f"{self.etiqueta_objeto}: {self.objeto_nombre}"
        return "—"

    @property
    def etiqueta_objeto(self):
        """Nombre legible del tipo de objeto territorial («Sector», «Zona»)."""
        if not self.objeto_tipo:
            return ""
        return TipoObjetoAuditoria(self.objeto_tipo).label

    @property
    def es_territorial(self):
        """True si la fila registra una acción sobre la organización territorial.

        La usa la plantilla de la bitácora para elegir la etiqueta de color, y
        evita que tenga que enumerar las cinco acciones de la HU-05 en un `if`
        que habría que actualizar cada vez que se agregue una.
        """
        return bool(self.objeto_tipo)

    def __str__(self):
        return (
            f"{self.ocurrido_en:%d-%m-%Y %H:%M} · {self.administrador_email} "
            f"· {self.get_accion_display()} · {self.objetivo}"
        )
