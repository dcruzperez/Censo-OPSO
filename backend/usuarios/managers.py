"""Manager (gestor) del modelo Usuario.

¿Por qué necesitamos uno propio?
El manager que trae Django (UserManager) obliga a entregar un "username".
Como en OPSO el identificador de acceso es el correo electrónico, hay que
reescribir la forma de crear usuarios; si no, el comando
`python manage.py createsuperuser` fallaría.
"""

from django.contrib.auth.base_user import BaseUserManager
from django.db.models import Q

from .validators import limpiar_nombre_usuario


class UsuarioManager(BaseUserManager):
    """Sabe crear usuarios normales y superusuarios usando el correo."""

    # Permite que las migraciones de datos usen este manager.
    use_in_migrations = True

    def _crear_usuario(self, email, password, **campos_extra):
        if not email:
            raise ValueError("El correo electrónico es obligatorio.")

        # normalize_email pasa el dominio a minúsculas (Gmail.COM -> gmail.com).
        email = self.normalize_email(email).lower()
        usuario = self.model(email=email, **campos_extra)

        # set_password NO guarda la contraseña: guarda su hash.
        # Aquí es donde el texto plano desaparece para siempre.
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **campos_extra):
        """Crea un usuario común (censista, supervisor)."""
        campos_extra.setdefault("is_staff", False)
        campos_extra.setdefault("is_superuser", False)
        return self._crear_usuario(email, password, **campos_extra)

    def create_superuser(self, email, password=None, **campos_extra):
        """Crea el superusuario técnico (acceso total, incluido /admin/)."""
        campos_extra.setdefault("is_staff", True)
        campos_extra.setdefault("is_superuser", True)
        campos_extra.setdefault("is_active", True)

        if campos_extra.get("is_staff") is not True:
            raise ValueError("Un superusuario debe tener is_staff=True.")
        if campos_extra.get("is_superuser") is not True:
            raise ValueError("Un superusuario debe tener is_superuser=True.")

        return self._crear_usuario(email, password, **campos_extra)

    def get_by_natural_key(self, username):
        """Búsqueda del usuario al iniciar sesión, insensible a mayúsculas.

        Así "Daniel@opso.cl" y "daniel@opso.cl" son la misma cuenta.
        """
        return self.get(**{f"{self.model.USERNAME_FIELD}__iexact": username})

    def activos_con_rol(self):
        """Consulta reutilizable: usuarios habilitados, con su rol precargado.

        select_related("rol") trae el usuario y su rol en UNA sola consulta SQL
        (JOIN) en vez de una consulta extra por cada usuario (problema N+1).
        """
        return self.filter(is_active=True).select_related("rol")

    # ------------------------------------------------------------------
    # Consultas de la HU-03 (Administración de usuarios)
    # ------------------------------------------------------------------
    # ¿Por qué viven en el manager y no en la vista?
    # Porque una consulta escrita en el manager se puede reutilizar desde una
    # vista, un comando de gestión, una prueba o el admin, y se prueba de forma
    # aislada. Es el principio "fat model, thin view" aplicado a las consultas.

    def administradores_activos(self):
        """Cuentas que hoy pueden administrar el sistema.

        Incluye el superusuario técnico aunque no tenga fila de rol: es la
        misma regla que aplica la propiedad Usuario.es_administrador, y ambas
        deben coincidir o el sistema podría quedarse sin nadie que administre.
        """
        from .models import RolCodigo

        return self.filter(is_active=True).filter(
            Q(rol__codigo=RolCodigo.ADMINISTRADOR) | Q(is_superuser=True)
        )

    def buscar(self, termino):
        """Búsqueda por nombre, apellido, correo, nombre de usuario o RUT.

        Q() permite combinar condiciones con OR y se traduce a una sola
        sentencia SQL con paréntesis. icontains -> ILIKE '%termino%' en
        PostgreSQL: insensible a mayúsculas y a la posición del texto.
        """
        termino = (termino or "").strip()
        if not termino:
            return self.all()

        # Para el RUT se quitan puntos y guion: así "12.345.678-5", "12345678-5"
        # y "123456785" encuentran la misma persona.
        rut = termino.replace(".", "").replace("-", "").replace(" ", "")

        return self.filter(
            Q(first_name__icontains=termino)
            | Q(last_name__icontains=termino)
            | Q(email__icontains=termino)
            | Q(nombre_usuario__icontains=termino)
            | Q(rut__startswith=rut)
        )

    def generar_nombre_usuario(self, first_name="", last_name="", email=""):
        """Propone un nombre de usuario libre a partir de los datos personales.

        Regla: primera letra del nombre + apellido (Marta Soto -> msoto). Si ya
        está ocupado, agrega un número (msoto2, msoto3...). Si no hay nombre ni
        apellido, usa la parte local del correo.

        ¿Por qué proponerlo en vez de exigirlo?
        Porque el administrador crea decenas de cuentas y no debería inventar
        identificadores a mano. El campo queda editable: la propuesta es una
        comodidad, no una imposición.
        """
        nombre = limpiar_nombre_usuario(first_name) or ""
        apellido = limpiar_nombre_usuario(last_name) or ""

        if nombre and apellido:
            base = f"{nombre[0]}{apellido}"
        elif apellido or nombre:
            base = apellido or nombre
        else:
            base = limpiar_nombre_usuario((email or "").split("@")[0]) or "usuario"

        # Se conservan solo los caracteres permitidos por el validador y se
        # exige que empiece por letra o número (lo pide NOMBRE_USUARIO_PERMITIDO).
        base = "".join(c for c in base if c.isascii() and (c.isalnum() or c in "._-"))
        base = base.lstrip("._-")[:25]

        # El validador exige un mínimo de 3 caracteres: si el nombre es muy
        # corto (ej.: "Ana Li" -> "ali" está bien, pero "A" -> "a" no), se
        # completa con un sufijo fijo en vez de generar un valor inválido.
        if len(base) < 3:
            base = f"{base}opso"[:25]

        candidato = base
        contador = 2
        while self.filter(nombre_usuario__iexact=candidato).exists():
            candidato = f"{base}{contador}"
            contador += 1

        return candidato
