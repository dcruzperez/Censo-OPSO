"""HU-05: esquema de la organización territorial.

Crea las cinco tablas de la app (región, comuna, operativo, sector, zona) con
sus claves foráneas, restricciones e índices. Las explicaciones de cada decisión
están en operativos/models.py, que es donde se leen junto al campo que
describen; repetirlas aquí las dejaría desactualizadas.

Vale la pena señalar qué queda garantizado por la BASE DE DATOS y no solo por
los formularios, porque es lo que sobrevive a un script mal escrito o a una
carga masiva:

  - operativo_fechas_coherentes    -> ningún operativo termina antes de empezar
  - operativo_estado_valido        -> el estado siempre es uno de los tres
  - comuna_unica_por_region        -> no hay dos comunas homónimas en una región
  - sector_unico_por_operativo_y_comuna
  - zona_unica_por_sector

Y tres índices para las consultas que la interfaz hace en cada pantalla
(comunas activas, sectores de un operativo, zonas de un sector).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Region',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(help_text='Código oficial de la región según el Instituto Nacional de Estadísticas (ej.: 08 para el Biobío).', max_length=5, unique=True, verbose_name='código')),
                ('nombre', models.CharField(help_text='Nombre oficial de la región.', max_length=80, unique=True, verbose_name='nombre')),
                ('orden', models.PositiveSmallIntegerField(default=100, help_text='Posición en el listado. Se usa el orden geográfico de norte a sur, que es como se nombran las regiones en Chile, en vez del alfabético.', verbose_name='orden')),
            ],
            options={
                'verbose_name': 'región',
                'verbose_name_plural': 'regiones',
                'db_table': 'operativos_region',
                'ordering': ['orden', 'nombre'],
            },
        ),
        migrations.CreateModel(
            name='Operativo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(help_text='Cómo se identifica el operativo. Ej.: Censo Social 2026.', max_length=120, unique=True, verbose_name='nombre')),
                ('descripcion', models.TextField(blank=True, help_text='Objetivo del operativo y cualquier antecedente útil.', verbose_name='descripción')),
                ('fecha_inicio', models.DateField(help_text='Primer día de trabajo en terreno.', verbose_name='fecha de inicio')),
                ('fecha_termino', models.DateField(help_text='Último día previsto de trabajo en terreno.', verbose_name='fecha de término')),
                ('estado', models.CharField(choices=[('PLANIFICACION', 'En planificación'), ('EN_CURSO', 'En curso'), ('CERRADO', 'Cerrado')], db_index=True, default='PLANIFICACION', help_text='En qué etapa está el operativo.', max_length=20, verbose_name='estado')),
                ('creado_en', models.DateTimeField(auto_now_add=True, verbose_name='creado en')),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='actualizado en')),
                ('creado_por', models.ForeignKey(blank=True, help_text='Quién dio de alta el operativo.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='operativos_creados', to=settings.AUTH_USER_MODEL, verbose_name='creado por')),
            ],
            options={
                'verbose_name': 'operativo',
                'verbose_name_plural': 'operativos',
                'db_table': 'operativos_operativo',
                'ordering': ['-fecha_inicio', 'nombre'],
            },
        ),
        migrations.CreateModel(
            name='Comuna',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(help_text='Nombre de la comuna, tal como se escribe oficialmente.', max_length=100, verbose_name='nombre')),
                ('activa', models.BooleanField(default=True, help_text='Si se desactiva, deja de ofrecerse al crear sectores nuevos. Los sectores que ya existen no se modifican.', verbose_name='activa')),
                ('creado_en', models.DateTimeField(auto_now_add=True, verbose_name='creado en')),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='actualizado en')),
                ('region', models.ForeignKey(help_text='Región a la que pertenece la comuna.', on_delete=django.db.models.deletion.PROTECT, related_name='comunas', to='operativos.region', verbose_name='región')),
            ],
            options={
                'verbose_name': 'comuna',
                'verbose_name_plural': 'comunas',
                'db_table': 'operativos_comuna',
                'ordering': ['region__orden', 'nombre'],
            },
        ),
        migrations.CreateModel(
            name='Sector',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(help_text='Cómo se conoce el sector en terreno. Ej.: Los Boldos.', max_length=120, verbose_name='nombre')),
                ('descripcion', models.TextField(blank=True, help_text='Límites o referencias que ayuden a reconocerlo en terreno.', verbose_name='descripción')),
                ('activo', models.BooleanField(default=True, help_text='Si se desactiva, deja de considerarse parte del operativo sin borrar sus zonas ni su historial.', verbose_name='activo')),
                ('creado_en', models.DateTimeField(auto_now_add=True, verbose_name='creado en')),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='actualizado en')),
                ('comuna', models.ForeignKey(help_text='Comuna en la que se ubica el sector.', on_delete=django.db.models.deletion.PROTECT, related_name='sectores', to='operativos.comuna', verbose_name='comuna')),
                ('operativo', models.ForeignKey(help_text='Operativo al que pertenece este sector.', on_delete=django.db.models.deletion.CASCADE, related_name='sectores', to='operativos.operativo', verbose_name='operativo')),
            ],
            options={
                'verbose_name': 'sector',
                'verbose_name_plural': 'sectores',
                'db_table': 'operativos_sector',
                'ordering': ['comuna__nombre', 'nombre'],
            },
        ),
        migrations.CreateModel(
            name='Zona',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(help_text='Identificación de la zona. Ej.: Zona 1 o Manzanas 1-8.', max_length=120, verbose_name='nombre')),
                ('descripcion', models.TextField(blank=True, help_text='Calles, manzanas o límites que definen la zona.', verbose_name='descripción')),
                ('viviendas_estimadas', models.PositiveIntegerField(blank=True, help_text='Cuántas viviendas se espera encontrar. Sirve para repartir la carga de trabajo de forma parecida entre censistas. Opcional: muchas veces no se sabe hasta llegar.', null=True, verbose_name='viviendas estimadas')),
                ('activa', models.BooleanField(default=True, help_text='Si se desactiva, deja de contarse en el avance del sector.', verbose_name='activa')),
                ('creado_en', models.DateTimeField(auto_now_add=True, verbose_name='creado en')),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='actualizado en')),
                ('sector', models.ForeignKey(help_text='Sector que esta zona subdivide.', on_delete=django.db.models.deletion.CASCADE, related_name='zonas', to='operativos.sector', verbose_name='sector')),
            ],
            options={
                'verbose_name': 'zona',
                'verbose_name_plural': 'zonas',
                'db_table': 'operativos_zona',
                'ordering': ['sector__nombre', 'nombre'],
            },
        ),
        migrations.AddConstraint(
            model_name='operativo',
            constraint=models.CheckConstraint(condition=models.Q(('fecha_termino__gte', models.F('fecha_inicio'))), name='operativo_fechas_coherentes'),
        ),
        migrations.AddConstraint(
            model_name='operativo',
            constraint=models.CheckConstraint(condition=models.Q(('estado__in', ['PLANIFICACION', 'EN_CURSO', 'CERRADO'])), name='operativo_estado_valido'),
        ),
        migrations.AddIndex(
            model_name='comuna',
            index=models.Index(fields=['activa', 'nombre'], name='idx_comuna_activa'),
        ),
        migrations.AddConstraint(
            model_name='comuna',
            constraint=models.UniqueConstraint(fields=('region', 'nombre'), name='comuna_unica_por_region'),
        ),
        migrations.AddIndex(
            model_name='sector',
            index=models.Index(fields=['operativo', 'activo'], name='idx_sector_operativo'),
        ),
        migrations.AddConstraint(
            model_name='sector',
            constraint=models.UniqueConstraint(fields=('operativo', 'comuna', 'nombre'), name='sector_unico_por_operativo_y_comuna'),
        ),
        migrations.AddIndex(
            model_name='zona',
            index=models.Index(fields=['sector', 'activa'], name='idx_zona_sector'),
        ),
        migrations.AddConstraint(
            model_name='zona',
            constraint=models.UniqueConstraint(fields=('sector', 'nombre'), name='zona_unica_por_sector'),
        ),
    ]
