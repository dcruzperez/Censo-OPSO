"""HU-06: agrega la acción CAMBIAR_ASIGNACIONES al catálogo de la bitácora.

Es una AlterField sobre el campo `accion` y no toca ni una fila de datos: las
opciones (`choices`) de un CharField son validación de Django, no una restricción
de PostgreSQL, así que ampliar la lista no reescribe la tabla ni invalida los
valores ya guardados.

La columna ya medía 30 caracteres desde la migración 0006 y
"CAMBIAR_ASIGNACIONES" mide 20, así que tampoco hace falta ampliarla.

No se agregó ningún TipoObjetoAuditoria: el reparto del trabajo recae sobre un
SECTOR, que ya estaba en el catálogo desde la HU-05.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0006_auditoria_territorial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='registroauditoria',
            name='accion',
            field=models.CharField(choices=[('CREAR', 'Creó la cuenta'), ('EDITAR', 'Editó los datos'), ('CAMBIAR_ROL', 'Cambió el rol'), ('DESHABILITAR', 'Deshabilitó la cuenta'), ('HABILITAR', 'Habilitó la cuenta'), ('ENVIAR_ENLACE', 'Envió enlace de contraseña'), ('CAMBIAR_PERMISOS', 'Cambió los permisos del rol'), ('CREAR_TERRITORIO', 'Creó el registro territorial'), ('EDITAR_TERRITORIO', 'Editó el registro territorial'), ('ACTIVAR_TERRITORIO', 'Activó el registro territorial'), ('DESACTIVAR_TERRITORIO', 'Desactivó el registro territorial'), ('CAMBIAR_ESTADO_OPERATIVO', 'Cambió el estado del operativo'), ('CAMBIAR_ASIGNACIONES', 'Cambió las asignaciones del sector')], db_index=True, max_length=30, verbose_name='acción'),
        ),
    ]
