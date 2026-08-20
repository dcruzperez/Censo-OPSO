"""HU-20: agrega el permiso `reportes.exportar_base` al catálogo.

Es un permiso NUEVO y no una reutilización de `reportes.exportar` (HU-19) a
propósito: `reportes.exportar` descarga AGREGADOS —conteos por estado, por
sector, por censista, sin un solo dato de una familia—, y esta historia
descarga la BASE CONSOLIDADA, una fila por persona con nombre, RUT, teléfono e
ingreso del hogar incluidos. Son capacidades de gravedad muy distinta y
mezclarlas en un mismo permiso le daría a cualquiera con `reportes.exportar`
—hoy, el rol Supervisor completo— acceso a datos personales que la historia
solo le pide al administrador.

Por eso, y a diferencia del reparto general de `sembrar_permisos` en la
migración 0005, este permiso se concede EXPLÍCITAMENTE solo al rol
ADMINISTRADOR y a ningún otro. Es el mismo criterio que 0005 ya aplicó para
el administrador en general —"sembrarlos hace que la matriz muestre la
verdad en vez de una fila vacía engañosa"—, llevado a un permiso que llega
después: sin este `.add()`, `Usuario.tiene_permiso()` seguiría dejando pasar
al administrador igual (concede todos de forma implícita, sin consultar la
tabla), pero la matriz de permisos mostraría su celda sin marcar, que sería
mentir sobre quién puede hacer qué.
"""

from django.db import migrations

CODIGO = "reportes.exportar_base"
NOMBRE = "Exportar la base consolidada"
MODULO = "REPORTES"
ORDEN = 30  # después de reportes.ver (10) y reportes.exportar (20)
DESCRIPCION = (
    "Descargar la base de datos consolidada del censo —una fila por persona, "
    "con nombre, RUT, teléfono e ingreso del hogar— para análisis externos."
)


def sembrar_permiso(apps, schema_editor):
    Permiso = apps.get_model("usuarios", "Permiso")
    Rol = apps.get_model("usuarios", "Rol")

    permiso, _ = Permiso.objects.update_or_create(
        codigo=CODIGO,
        defaults={
            "nombre": NOMBRE,
            "modulo": MODULO,
            "orden": ORDEN,
            "descripcion": DESCRIPCION,
            "activo": True,
        },
    )

    # Solo el Administrador (ver docstring del módulo). add() es aditivo e
    # idempotente: no toca los demás permisos del rol ni duplica si la
    # migración se vuelve a aplicar.
    administrador = Rol.objects.filter(codigo="ADMINISTRADOR").first()
    if administrador is not None:
        administrador.permisos.add(permiso)


def borrar_permiso(apps, schema_editor):
    """Basta con borrar el Permiso: PostgreSQL limpia la fila de la tabla
    intermedia `usuarios_rol_permisos` en cascada, igual que en 0005.
    """
    Permiso = apps.get_model("usuarios", "Permiso")
    Permiso.objects.filter(codigo=CODIGO).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0007_accion_asignaciones"),
    ]

    operations = [
        migrations.RunPython(sembrar_permiso, borrar_permiso),
    ]
