"""HU-07: la tabla de las encuestas, la unidad de trabajo del encuestador.

Crea fichas_encuesta con sus tres restricciones y sus dos índices. Las
explicaciones de cada decisión están junto al campo que describen, en
fichas/models.py.

Las tres restricciones son lo que la base de datos garantiza aunque un script no
pase por los formularios:

  encuesta_estado_valido    -> el estado solo puede ser uno de los siete del
                               catálogo, aunque alguien inserte con SQL directo.

  encuesta_inicio_coherente -> iniciada_en está vacía SI Y SOLO SI la encuesta
                               sigue pendiente. Una encuesta empezada sin fecha de
                               inicio haría imposible distinguir un borrador de
                               ayer de uno de hace tres semanas.

  encuesta_cierre_coherente -> cerrada_en está vacía SI Y SOLO SI la encuesta
                               sigue siendo trabajo del encuestador. Es lo que
                               impide que una ficha devuelta por el supervisor
                               conserve su fecha de cierre y siga contando como
                               terminada.

Los dos índices responden a las dos consultas del módulo: «mis encuestas»
(censista + estado), que se ejecuta muchas veces al día desde un teléfono, y «cómo
va esta zona» (zona + estado), que usarán la supervisión y los reportes.

No hay datos que migrar: la tabla nace vacía. Para la demostración, el comando
`python manage.py crear_encuestas_demo` siembra un operativo con encuestas en
todos los estados.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('operativos', '0003_asignaciones'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Encuesta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('direccion', models.CharField(help_text='Calle y número de la vivienda. Ej.: Pasaje Los Robles 1425.', max_length=200, verbose_name='dirección')),
                ('referencia', models.CharField(blank=True, help_text='Cómo reconocerla desde la calle. Ej.: casa verde, portón negro, frente al almacén.', max_length=200, verbose_name='referencia')),
                ('estado', models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('BORRADOR', 'Borrador'), ('COMPLETADA', 'Completada'), ('OBSERVADA', 'Observada'), ('VALIDADA', 'Validada'), ('NO_UBICADA', 'No ubicada'), ('RECHAZADA', 'Rechazada')], db_index=True, default='PENDIENTE', help_text='En qué etapa está el levantamiento de esta vivienda.', max_length=20, verbose_name='estado')),
                ('observaciones', models.TextField(blank=True, help_text='Indicaciones del supervisor o notas del propio encuestador. Ej.: «pasar después de las 19:00, trabajan todo el día».', verbose_name='observaciones')),
                ('creada_en', models.DateTimeField(auto_now_add=True, verbose_name='creada en')),
                ('actualizada_en', models.DateTimeField(auto_now=True, verbose_name='actualizada en')),
                ('iniciada_en', models.DateTimeField(blank=True, help_text='Primera visita a la vivienda. Vacío mientras la encuesta sigue pendiente.', null=True, verbose_name='iniciada en')),
                ('cerrada_en', models.DateTimeField(blank=True, help_text='Cuándo dejó de depender del encuestador. Vacío mientras siga siendo trabajo suyo.', null=True, verbose_name='cerrada en')),
                ('asignada_por', models.ForeignKey(blank=True, help_text='Quién encargó esta encuesta. Vacío si la creó el encuestador.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='encuestas_asignadas', to=settings.AUTH_USER_MODEL, verbose_name='asignada por')),
                ('censista', models.ForeignKey(help_text='Persona que debe levantar esta encuesta.', on_delete=django.db.models.deletion.PROTECT, related_name='encuestas', to=settings.AUTH_USER_MODEL, verbose_name='encuestador')),
                ('zona', models.ForeignKey(help_text='Zona del sector en la que se ubica la vivienda.', on_delete=django.db.models.deletion.PROTECT, related_name='encuestas', to='operativos.zona', verbose_name='zona')),
            ],
            options={
                'verbose_name': 'encuesta',
                'verbose_name_plural': 'encuestas',
                'db_table': 'fichas_encuesta',
                'ordering': ['zona__sector__nombre', 'zona__nombre', 'direccion'],
                'indexes': [models.Index(fields=['censista', 'estado'], name='idx_encuesta_censista'), models.Index(fields=['zona', 'estado'], name='idx_encuesta_zona')],
                'constraints': [models.CheckConstraint(condition=models.Q(('estado__in', ['PENDIENTE', 'BORRADOR', 'COMPLETADA', 'OBSERVADA', 'VALIDADA', 'NO_UBICADA', 'RECHAZADA'])), name='encuesta_estado_valido'), models.CheckConstraint(condition=models.Q(models.Q(('estado', 'PENDIENTE'), ('iniciada_en__isnull', True)), models.Q(models.Q(('estado', 'PENDIENTE'), _negated=True), ('iniciada_en__isnull', False)), _connector='OR'), name='encuesta_inicio_coherente'), models.CheckConstraint(condition=models.Q(models.Q(('cerrada_en__isnull', True), ('estado__in', ['PENDIENTE', 'BORRADOR', 'OBSERVADA'])), models.Q(('cerrada_en__isnull', False), ('estado__in', ['COMPLETADA', 'VALIDADA', 'NO_UBICADA', 'RECHAZADA'])), _connector='OR'), name='encuesta_cierre_coherente')],
            },
        ),
    ]
