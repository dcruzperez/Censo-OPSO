"""HU-12: las fotografías de la vivienda.

Crea fichas_fotografia con sus dos restricciones y su índice. Las explicaciones de
cada decisión están junto al campo que describen, en fichas/models.py.

Es la primera tabla del proyecto que guarda ARCHIVOS, y eso tiene dos consecuencias
que conviene tener presentes al aplicarla o revertirla:

  1. LA COLUMNA GUARDA UNA RUTA, NO LA IMAGEN. El archivo vive en MEDIA_ROOT. Borrar
     la fila NO borra el archivo —Django dejó de hacerlo a propósito hace muchas
     versiones—, así que revertir esta migración deja los archivos huérfanos en el
     disco. Para datos personales eso no es basura acumulada: es información que ya
     no debería existir. El borrado en el día a día lo hace
     `Fotografia.borrar_archivo()`; al revertir hay que vaciar la carpeta a mano.

  2. LOS ARCHIVOS NO SE SIRVEN COMO ESTÁTICOS. Ver el comentario de MEDIA_URL en
     settings.py: se entregan por una vista que comprueba quién pregunta.

Las dos restricciones:

  fotografia_tipo_valido      -> el tipo es uno del catálogo.
  fotografia_con_descripcion  -> la descripción no puede estar vacía. Una foto sin
                                 explicación no es evidencia de nada, y dentro de
                                 seis meses nadie sabrá qué se estaba mirando.

No hay datos que migrar: la tabla nace vacía.
"""

import django.db.models.deletion
import fichas.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fichas', '0005_ubicacion_gps'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Fotografia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imagen', models.ImageField(help_text='JPEG, PNG o WEBP. El nombre original del archivo no se conserva.', upload_to=fichas.models.ruta_de_la_fotografia, verbose_name='imagen')),
                ('tipo', models.CharField(choices=[('FACHADA', 'Fachada de la vivienda'), ('ACCESO', 'Cómo se llega o se reconoce'), ('MATERIALIDAD', 'Estado o materialidad de la construcción'), ('SERVICIOS', 'Servicios básicos (medidor, conexión, pozo)'), ('CROQUIS', 'Croquis o anotación en papel'), ('OTRA', 'Otra evidencia')], help_text='Qué se está documentando.', max_length=20, verbose_name='tipo de evidencia')),
                ('descripcion', models.CharField(help_text='Por qué hizo falta esta foto. Ej.: «el número de la casa está borrado; es la tercera del pasaje».', max_length=200, verbose_name='descripción')),
                ('tomada_en', models.DateTimeField(auto_now_add=True, verbose_name='subida en')),
                ('tomada_por', models.ForeignKey(blank=True, help_text='Quién la subió.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fotografias_tomadas', to=settings.AUTH_USER_MODEL, verbose_name='tomada por')),
                ('vivienda', models.ForeignKey(help_text='Vivienda que la fotografía documenta.', on_delete=django.db.models.deletion.CASCADE, related_name='fotografias', to='fichas.vivienda', verbose_name='vivienda')),
            ],
            options={
                'verbose_name': 'fotografía',
                'verbose_name_plural': 'fotografías',
                'db_table': 'fichas_fotografia',
                'ordering': ['-tomada_en'],
                'indexes': [models.Index(fields=['vivienda', 'tipo'], name='idx_foto_vivienda')],
                'constraints': [models.CheckConstraint(condition=models.Q(('tipo__in', ['FACHADA', 'ACCESO', 'MATERIALIDAD', 'SERVICIOS', 'CROQUIS', 'OTRA'])), name='fotografia_tipo_valido'), models.CheckConstraint(condition=models.Q(('descripcion', ''), _negated=True), name='fotografia_con_descripcion')],
            },
        ),
    ]
