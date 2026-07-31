"""HU-05: la bitácora aprende a registrar acciones sobre el territorio.

Tres columnas nuevas (objeto_tipo, objeto_id, objeto_nombre) y una ampliada
(accion pasa de 20 a 30 caracteres, porque "CAMBIAR_ESTADO_OPERATIVO" mide 24).

¿POR QUÉ NO HAY QUE MIGRAR NINGÚN DATO?

Porque las tres columnas admiten vacío y nulo: las filas de auditoría que ya
existen quedan con objeto_tipo="" y objeto_id=NULL, que es exactamente la verdad
(no afectaron a ningún objeto territorial). La propiedad
RegistroAuditoria.objetivo las sigue resolviendo por usuario_afectado_email o
rol_afectado_nombre, igual que antes.

Ampliar accion de 20 a 30 tampoco toca datos: en PostgreSQL agrandar un
varchar(n) es un cambio solo de catálogo, no reescribe la tabla. Los valores
guardados siguen siendo válidos porque todos miden menos de 20.

Es decir: esta migración es reversible y no destructiva. Se puede aplicar sobre
una base en producción con la bitácora llena sin perder una sola fila.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0005_permisos_iniciales'),
    ]

    operations = [
        migrations.AddField(
            model_name='registroauditoria',
            name='objeto_id',
            field=models.PositiveIntegerField(blank=True, help_text='Clave primaria del registro territorial afectado. Sin clave foránea a propósito: ver la explicación en el modelo.', null=True, verbose_name='identificador del objeto'),
        ),
        migrations.AddField(
            model_name='registroauditoria',
            name='objeto_nombre',
            field=models.CharField(blank=True, help_text='Copia fija con el camino completo, ej.: «Zona 1 · Los Boldos · Concepción». Es lo que hace legible la fila años después.', max_length=250, verbose_name='nombre del objeto territorial'),
        ),
        migrations.AddField(
            model_name='registroauditoria',
            name='objeto_tipo',
            field=models.CharField(blank=True, choices=[('OPERATIVO', 'Operativo'), ('COMUNA', 'Comuna'), ('SECTOR', 'Sector'), ('ZONA', 'Zona')], db_index=True, help_text='Qué clase de registro territorial se afectó (HU-05).', max_length=20, verbose_name='tipo de objeto territorial'),
        ),
        migrations.AlterField(
            model_name='registroauditoria',
            name='accion',
            field=models.CharField(choices=[('CREAR', 'Creó la cuenta'), ('EDITAR', 'Editó los datos'), ('CAMBIAR_ROL', 'Cambió el rol'), ('DESHABILITAR', 'Deshabilitó la cuenta'), ('HABILITAR', 'Habilitó la cuenta'), ('ENVIAR_ENLACE', 'Envió enlace de contraseña'), ('CAMBIAR_PERMISOS', 'Cambió los permisos del rol'), ('CREAR_TERRITORIO', 'Creó el registro territorial'), ('EDITAR_TERRITORIO', 'Editó el registro territorial'), ('ACTIVAR_TERRITORIO', 'Activó el registro territorial'), ('DESACTIVAR_TERRITORIO', 'Desactivó el registro territorial'), ('CAMBIAR_ESTADO_OPERATIVO', 'Cambió el estado del operativo')], db_index=True, max_length=30, verbose_name='acción'),
        ),
    ]
