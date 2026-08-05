"""HU-09: las personas que viven en cada hogar.

Crea fichas_integrante con sus cuatro restricciones y su índice. Las
explicaciones de cada decisión están junto al campo que describen, en
fichas/models.py.

Las dos restricciones que conviene señalar son índices únicos PARCIALES, la misma
técnica que la HU-06 estrenó con `asignacion_activa_unica`:

  un_solo_jefe_por_hogar -> único ENTRE LOS QUE SON JEFE DE HOGAR
                            (WHERE parentesco = 'JEFE_HOGAR'). Hace única una
                            opción concreta de la columna sin hacer única la
                            columna entera, que impediría tener dos hijos.
                            Importa porque el parentesco de todas las demás
                            personas se mide respecto al jefe de hogar: con dos,
                            esa columna dejaría de significar algo.

  rut_unico_en_el_hogar  -> único ENTRE LOS QUE TIENEN RUT (WHERE rut <> ''). Sin
                            la condición, dos personas sin RUT chocarían por
                            compartir la cadena vacía y no se podría registrar a
                            una familia que no lleva los carnets encima.

Lo que NO está aquí y podría parecer que falta: que la fecha de nacimiento no sea
futura. Una restricción de la base de datos no puede depender de la fecha de hoy
sin volverse falsa mañana, así que esa comprobación vive en Integrante.clean() y
en el formulario, que es donde puede ser cierta.

No hay datos que migrar: la tabla nace vacía.
"""

import django.db.models.deletion
import usuarios.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fichas', '0002_vivienda_y_grupo_familiar'),
    ]

    operations = [
        migrations.CreateModel(
            name='Integrante',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('parentesco', models.CharField(choices=[('JEFE_HOGAR', 'Jefe o jefa de hogar'), ('CONYUGE', 'Cónyuge o conviviente'), ('HIJO', 'Hijo o hija'), ('PADRE_MADRE', 'Padre o madre'), ('HERMANO', 'Hermano o hermana'), ('NIETO', 'Nieto o nieta'), ('OTRO_PARIENTE', 'Otro pariente'), ('NO_PARIENTE', 'Sin parentesco')], help_text='Relación con el jefe o jefa de hogar.', max_length=20, verbose_name='parentesco')),
                ('nombres', models.CharField(help_text='Nombre o nombres de pila.', max_length=100, verbose_name='nombres')),
                ('apellidos', models.CharField(help_text='Apellidos de la persona.', max_length=100, verbose_name='apellidos')),
                ('rut', models.CharField(blank=True, help_text='Formato 12345678-9. Opcional, igual que el del jefe de hogar.', max_length=12, validators=[usuarios.validators.validar_rut], verbose_name='RUT')),
                ('sexo', models.CharField(choices=[('FEMENINO', 'Femenino'), ('MASCULINO', 'Masculino'), ('OTRO', 'Otro'), ('NO_RESPONDE', 'Prefiere no responder')], help_text='Tal como la persona lo declara.', max_length=20, verbose_name='sexo')),
                ('fecha_nacimiento', models.DateField(help_text='Se guarda la fecha y no la edad: la edad caduca y la fecha no.', verbose_name='fecha de nacimiento')),
                ('nivel_educacional', models.CharField(blank=True, choices=[('SIN_ESTUDIOS', 'Sin estudios formales'), ('BASICA_INCOMPLETA', 'Básica incompleta'), ('BASICA_COMPLETA', 'Básica completa'), ('MEDIA_INCOMPLETA', 'Media incompleta'), ('MEDIA_COMPLETA', 'Media completa'), ('TECNICA', 'Técnica de nivel superior'), ('UNIVERSITARIA', 'Universitaria'), ('POSTGRADO', 'Postgrado')], help_text='Se pregunta desde los 5 años.', max_length=20, verbose_name='nivel educacional')),
                ('situacion_ocupacional', models.CharField(blank=True, choices=[('TRABAJA', 'Trabaja'), ('BUSCA_TRABAJO', 'Busca trabajo'), ('ESTUDIA', 'Estudia'), ('LABORES_HOGAR', 'Labores del hogar'), ('JUBILADO', 'Jubilado o pensionado'), ('NO_TRABAJA', 'No trabaja ni busca trabajo')], help_text='Se pregunta desde los 15 años.', max_length=20, verbose_name='situación ocupacional')),
                ('pueblo_originario', models.CharField(choices=[('NINGUNO', 'No pertenece a ninguno'), ('MAPUCHE', 'Mapuche'), ('AYMARA', 'Aymara'), ('RAPANUI', 'Rapa Nui'), ('LICKANANTAY', 'Lickanantay (atacameño)'), ('QUECHUA', 'Quechua'), ('COLLA', 'Colla'), ('DIAGUITA', 'Diaguita'), ('KAWESQAR', 'Kawésqar'), ('YAGAN', 'Yagán'), ('CHANGO', 'Chango'), ('NO_RESPONDE', 'Prefiere no responder')], default='NINGUNO', help_text='Dato autodeclarado por la persona.', max_length=20, verbose_name='pueblo originario')),
                ('tiene_discapacidad', models.BooleanField(default=False, help_text='Alguna condición de discapacidad permanente declarada.', verbose_name='presenta discapacidad')),
                ('observaciones', models.TextField(blank=True, help_text='Situaciones de esta persona que conviene dejar por escrito.', verbose_name='observaciones')),
                ('registrado_en', models.DateTimeField(auto_now_add=True, verbose_name='registrado en')),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='actualizado en')),
                ('grupo_familiar', models.ForeignKey(help_text='Hogar al que pertenece esta persona.', on_delete=django.db.models.deletion.CASCADE, related_name='integrantes', to='fichas.grupofamiliar', verbose_name='grupo familiar')),
            ],
            options={
                'verbose_name': 'integrante',
                'verbose_name_plural': 'integrantes',
                'db_table': 'fichas_integrante',
                'ordering': ['fecha_nacimiento'],
                'indexes': [models.Index(fields=['grupo_familiar', 'parentesco'], name='idx_integrante_hogar')],
                'constraints': [models.CheckConstraint(condition=models.Q(('parentesco__in', ['JEFE_HOGAR', 'CONYUGE', 'HIJO', 'PADRE_MADRE', 'HERMANO', 'NIETO', 'OTRO_PARIENTE', 'NO_PARIENTE'])), name='integrante_parentesco_valido'), models.CheckConstraint(condition=models.Q(('sexo__in', ['FEMENINO', 'MASCULINO', 'OTRO', 'NO_RESPONDE'])), name='integrante_sexo_valido'), models.UniqueConstraint(condition=models.Q(('parentesco', 'JEFE_HOGAR')), fields=('grupo_familiar',), name='un_solo_jefe_por_hogar'), models.UniqueConstraint(condition=models.Q(('rut', ''), _negated=True), fields=('grupo_familiar', 'rut'), name='rut_unico_en_el_hogar')],
            },
        ),
    ]
