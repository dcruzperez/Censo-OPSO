"""HU-06: la tabla que registra quién cubre cada sector.

Crea operativos_asignacion_sector con sus dos restricciones y sus dos índices.
Las explicaciones de cada decisión están junto al campo que describen, en
operativos/models.py.

Vale la pena señalar las dos restricciones, porque son lo que la base de datos
garantiza aunque un script no pase por los formularios:

  asignacion_activa_unica   -> índice único PARCIAL (solo entre las activas).
                               Permite reasignar a alguien que ya estuvo antes,
                               porque la fila histórica no estorba, e impide
                               duplicar una asignación vigente.

  asignacion_baja_coherente -> activa=True exige desasignado_en vacío, y
                               activa=False exige que tenga fecha. Impide filas
                               que se contradicen consigo mismas y que harían el
                               historial poco fiable.

No hay datos que migrar: la tabla nace vacía. El reparto del trabajo lo hace el
supervisor desde la aplicación, no una migración.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operativos', '0002_regiones_iniciales'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AsignacionSector',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('observaciones', models.TextField(blank=True, help_text='Instrucciones para esta persona en este sector. Ej.: «empezar por el pasaje sur, la subida está en obras».', verbose_name='observaciones')),
                ('activa', models.BooleanField(default=True, help_text='Si se desactiva, la persona deja de tener el sector a cargo, pero la fila se conserva como historial del reparto.', verbose_name='activa')),
                ('asignado_en', models.DateTimeField(auto_now_add=True, verbose_name='asignado en')),
                ('desasignado_en', models.DateTimeField(blank=True, help_text='Cuándo se retiró la asignación. Vacío si sigue vigente.', null=True, verbose_name='desasignado en')),
                ('asignado_por', models.ForeignKey(blank=True, help_text='Supervisor que hizo el reparto.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='asignaciones_realizadas', to=settings.AUTH_USER_MODEL, verbose_name='asignado por')),
                ('censista', models.ForeignKey(help_text='Persona que levantará la información en ese sector.', on_delete=django.db.models.deletion.PROTECT, related_name='asignaciones_sector', to=settings.AUTH_USER_MODEL, verbose_name='censista')),
                ('sector', models.ForeignKey(help_text='Sector que se le encarga a la persona.', on_delete=django.db.models.deletion.CASCADE, related_name='asignaciones', to='operativos.sector', verbose_name='sector')),
            ],
            options={
                'verbose_name': 'asignación de sector',
                'verbose_name_plural': 'asignaciones de sectores',
                'db_table': 'operativos_asignacion_sector',
                'ordering': ['-activa', '-asignado_en'],
                'indexes': [models.Index(fields=['censista', 'activa'], name='idx_asignacion_censista'), models.Index(fields=['sector', 'activa'], name='idx_asignacion_sector')],
                'constraints': [models.UniqueConstraint(condition=models.Q(('activa', True)), fields=('sector', 'censista'), name='asignacion_activa_unica'), models.CheckConstraint(condition=models.Q(models.Q(('activa', True), ('desasignado_en__isnull', True)), models.Q(('activa', False), ('desasignado_en__isnull', False)), _connector='OR'), name='asignacion_baja_coherente')],
            },
        ),
    ]
