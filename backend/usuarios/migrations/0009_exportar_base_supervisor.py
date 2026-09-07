"""HU-20: amplía el alcance de `reportes.exportar_base` al rol SUPERVISOR.

La 0008 original lo concedió solo al Administrador porque en ese momento la
historia decía "Como administrador". El alcance de HU-20 se actualizó
después para incluir al Supervisor —ver `docs/HU-20_base_consolidada.md`—,
así que esta migración hace por el Supervisor exactamente lo que la 0008 ya
hizo por el Administrador: un `.add()` explícito, aditivo e idempotente, en
vez de reescribir 0008 (una migración ya aplicada en otros entornos no se
edita: se corrige hacia adelante).

`Usuario.tiene_permiso()` no tiene ningún bypass para el Supervisor —a
diferencia del Administrador—, así que sin este `.add()` ningún supervisor
podría exportar la base, sin importar lo que diga la documentación.
"""

from django.db import migrations

CODIGO = "reportes.exportar_base"


def conceder_a_supervisor(apps, schema_editor):
    Permiso = apps.get_model("usuarios", "Permiso")
    Rol = apps.get_model("usuarios", "Rol")

    permiso = Permiso.objects.filter(codigo=CODIGO).first()
    supervisor = Rol.objects.filter(codigo="SUPERVISOR").first()
    if permiso is not None and supervisor is not None:
        supervisor.permisos.add(permiso)


def retirar_a_supervisor(apps, schema_editor):
    """Solo desvincula el permiso del rol Supervisor: la fila del `Permiso`
    y su concesión al Administrador siguen a cargo de la 0008.
    """
    Permiso = apps.get_model("usuarios", "Permiso")
    Rol = apps.get_model("usuarios", "Rol")

    permiso = Permiso.objects.filter(codigo=CODIGO).first()
    supervisor = Rol.objects.filter(codigo="SUPERVISOR").first()
    if permiso is not None and supervisor is not None:
        supervisor.permisos.remove(permiso)


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0008_permiso_exportar_base"),
    ]

    operations = [
        migrations.RunPython(conceder_a_supervisor, retirar_a_supervisor),
    ]
