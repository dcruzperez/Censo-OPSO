"""Comando de gestión: crea un usuario de prueba por cada rol.

Sirve para la demostración en la defensa: en un solo paso quedan las tres
cuentas necesarias para mostrar la redirección diferenciada por rol.

Uso:
    python manage.py crear_usuarios_demo
    python manage.py crear_usuarios_demo --clave "MiClaveSegura2026#"

Un "management command" es la forma correcta de escribir scripts en Django:
recibe la configuración y la conexión a la base de datos ya inicializadas.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from usuarios.models import Rol, RolCodigo

Usuario = get_user_model()

CLAVE_POR_DEFECTO = "Censo2026#Opso"

CUENTAS = [
    ("admin@opso.cl", "Ana", "Rojas", RolCodigo.ADMINISTRADOR, "12345678-5", "arojas"),
    ("supervisor@opso.cl", "Luis", "Pérez", RolCodigo.SUPERVISOR, "11111111-1", "lperez"),
    ("censista@opso.cl", "Marta", "Soto", RolCodigo.CENSISTA, "22222222-2", "msoto"),
]


class Command(BaseCommand):
    help = "Crea (o actualiza) un usuario de demostración por cada rol."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clave",
            default=CLAVE_POR_DEFECTO,
            help="Contraseña asignada a las tres cuentas.",
        )

    # transaction.atomic: si algo falla a mitad de camino, no queda la base
    # de datos a medio poblar (todo o nada).
    @transaction.atomic
    def handle(self, *args, **opciones):
        clave = opciones["clave"]

        if not Rol.objects.exists():
            raise CommandError(
                "No hay roles en la base de datos. Ejecuta primero: "
                "python manage.py migrate"
            )

        for email, nombre, apellido, codigo_rol, rut, nombre_usuario in CUENTAS:
            rol = Rol.objects.get(codigo=codigo_rol)

            usuario, creado = Usuario.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": nombre,
                    "last_name": apellido,
                    "rol": rol,
                    "rut": rut,
                    "nombre_usuario": nombre_usuario,
                    "is_staff": codigo_rol == RolCodigo.ADMINISTRADOR,
                },
            )

            # set_password siempre: así el comando también sirve para
            # restablecer la clave de las cuentas de demostración.
            usuario.set_password(clave)
            usuario.rol = rol
            usuario.is_active = True
            usuario.save()

            etiqueta = "creado" if creado else "actualizado"
            self.stdout.write(
                self.style.SUCCESS(f"  {rol.nombre:<15} {email:<22} ({etiqueta})")
            )

        self.stdout.write("")
        self.stdout.write(self.style.WARNING(f"  Contraseña de las 3 cuentas: {clave}"))
        self.stdout.write(
            self.style.WARNING(
                "  Son cuentas de DEMOSTRACIÓN: no usar en un entorno real."
            )
        )
