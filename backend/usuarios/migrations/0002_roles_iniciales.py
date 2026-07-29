"""Migración de DATOS: carga los tres roles base de OPSO.

Diferencia clave con la migración 0001:
  - 0001 es una migración de ESQUEMA: crea tablas y columnas (DDL).
  - 0002 es una migración de DATOS: inserta filas (DML).

¿Por qué sembrar los roles con una migración y no a mano en pgAdmin?
  1. REPRODUCIBILIDAD: cualquier persona clona el repositorio, ejecuta
     `python manage.py migrate` y obtiene exactamente la misma base de datos.
     No hay pasos manuales que alguien pueda olvidar.
  2. VERSIONADO: los roles son parte del código, quedan en el historial de Git.
  3. PRUEBAS: Django crea la base de datos de prueba aplicando las migraciones,
     así que los roles también existen al ejecutar los test automáticos.
"""

from django.db import migrations

# Se definen aquí como texto y no importando RolCodigo desde models.py.
# Motivo: una migración debe seguir funcionando dentro de cinco años, aunque el
# código del modelo haya cambiado. Una migración es una foto de un momento.
ROLES_INICIALES = [
    {
        "codigo": "ADMINISTRADOR",
        "nombre": "Administrador",
        "descripcion": (
            "Responsable técnico del sistema. Gestiona usuarios y roles, "
            "configura el operativo y accede a la auditoría y a todos los "
            "reportes."
        ),
        "dashboard_url_name": "dashboards:administrador",
    },
    {
        "codigo": "SUPERVISOR",
        "nombre": "Supervisor",
        "descripcion": (
            "Coordina el trabajo en terreno. Valida las fichas levantadas por "
            "los censistas, asigna sectores y controla el avance del operativo."
        ),
        "dashboard_url_name": "dashboards:supervisor",
    },
    {
        "codigo": "CENSISTA",
        "nombre": "Censista",
        "descripcion": (
            "Personal de terreno. Registra la información de las familias en "
            "las fichas del censo. Solo accede a lo que él mismo levanta."
        ),
        "dashboard_url_name": "dashboards:censista",
    },
]


def crear_roles(apps, schema_editor):
    """Inserta los roles si no existen todavía.

    apps.get_model() entrega una versión "histórica" del modelo, tal como
    estaba en esta migración. Nunca se importa el modelo real (from ..models
    import Rol): si mañana el modelo cambia, esta migración seguiría funcionando.
    """
    Rol = apps.get_model("usuarios", "Rol")

    for datos in ROLES_INICIALES:
        # update_or_create hace la migración IDEMPOTENTE: se puede volver a
        # aplicar sin duplicar filas ni fallar por la restricción UNIQUE.
        Rol.objects.update_or_create(codigo=datos["codigo"], defaults=datos)


def eliminar_roles(apps, schema_editor):
    """Operación inversa, para poder revertir con `migrate usuarios 0001`.

    Solo borra los roles que no tengan usuarios asignados: la clave foránea es
    PROTECT y el borrado fallaría si alguien ya los está usando.
    """
    Rol = apps.get_model("usuarios", "Rol")
    codigos = [datos["codigo"] for datos in ROLES_INICIALES]
    Rol.objects.filter(codigo__in=codigos, usuarios__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        # Debe existir la tabla antes de insertar datos en ella.
        ("usuarios", "0001_initial"),
    ]

    operations = [
        # RunPython recibe la función de avance y la de reversa.
        migrations.RunPython(crear_roles, eliminar_roles),
    ]
