"""HU-14: el octavo estado y la resolución del supervisor.

Agrega el estado ANULADA y las tres columnas que registran quién resolvió una
encuesta, cuándo y con qué comentario. Las explicaciones están junto a cada campo
en fichas/models.py; aquí interesan dos cosas.

--------------------------------------------------------------------------
POR QUÉ SE BORRAN Y SE VUELVEN A CREAR DOS RESTRICCIONES
--------------------------------------------------------------------------
`encuesta_estado_valido` y `encuesta_cierre_coherente` enumeran los estados como
TEXTO LITERAL, por la razón que la HU-07 dejó escrita: una restricción viaja a la
migración y tiene que seguir significando lo mismo dentro de diez versiones del
modelo.

La contrapartida de esa decisión es esta migración: agregar un estado obliga a
reescribir las dos, porque ANULADA tiene que entrar en la lista de valores válidos
y en el grupo de los estados cerrados (una encuesta anulada ya no depende del
encuestador, así que exige fecha de cierre).

Es el precio correcto. La alternativa —restricciones que leen la lista del modelo—
habría dejado migraciones antiguas cuyo significado cambia al editar código, y una
migración que se comporta distinto según el código de hoy no sirve para reconstruir
una base.

--------------------------------------------------------------------------
LA RESTRICCIÓN NUEVA
--------------------------------------------------------------------------
  encuesta_anulacion_con_motivo -> si el estado es ANULADA, `comentario_revision`
                                   no puede estar vacío. Una ficha descartada sin
                                   explicación no se puede defender: ni ante el
                                   encuestador cuyo trabajo se tira, ni ante quien
                                   audite el censo.

Solo cubre ANULADA. Validar no necesita comentario —aprobar es el resultado
esperado y exigir un texto por cada ficha buena produciría cientos de «ok»— y la
HU-15 extenderá la restricción a OBSERVADA, que sí lo necesita.

No hay datos que migrar: las tres columnas nacen vacías y ninguna fila existente
está en ANULADA, así que la restricción se crea sin conflictos.
"""

from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fichas', '0006_fotografias'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='encuesta',
            name='encuesta_estado_valido',
        ),
        migrations.RemoveConstraint(
            model_name='encuesta',
            name='encuesta_cierre_coherente',
        ),
        migrations.AddField(
            model_name='encuesta',
            name='comentario_revision',
            field=models.TextField(blank=True, help_text='Lo que el supervisor deja escrito al resolver. Obligatorio al anular: una ficha descartada sin explicación no se puede defender.', verbose_name='comentario de la revisión'),
        ),
        migrations.AddField(
            model_name='encuesta',
            name='revisada_en',
            field=models.DateTimeField(blank=True, help_text='Cuándo se resolvió. Vacío mientras no se haya revisado.', null=True, verbose_name='revisada en'),
        ),
        migrations.AddField(
            model_name='encuesta',
            name='revisada_por',
            field=models.ForeignKey(blank=True, help_text='Quién la validó, anuló o devolvió.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='encuestas_revisadas', to=settings.AUTH_USER_MODEL, verbose_name='revisada por'),
        ),
        migrations.AlterField(
            model_name='encuesta',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('BORRADOR', 'Borrador'), ('COMPLETADA', 'Completada'), ('OBSERVADA', 'Observada'), ('VALIDADA', 'Validada'), ('NO_UBICADA', 'No ubicada'), ('RECHAZADA', 'Rechazada'), ('ANULADA', 'Anulada')], db_index=True, default='PENDIENTE', help_text='En qué etapa está el levantamiento de esta vivienda.', max_length=20, verbose_name='estado'),
        ),
        migrations.AddConstraint(
            model_name='encuesta',
            constraint=models.CheckConstraint(condition=models.Q(('estado__in', ['PENDIENTE', 'BORRADOR', 'COMPLETADA', 'OBSERVADA', 'VALIDADA', 'NO_UBICADA', 'RECHAZADA', 'ANULADA'])), name='encuesta_estado_valido'),
        ),
        migrations.AddConstraint(
            model_name='encuesta',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('cerrada_en__isnull', True), ('estado__in', ['PENDIENTE', 'BORRADOR', 'OBSERVADA'])), models.Q(('cerrada_en__isnull', False), ('estado__in', ['COMPLETADA', 'VALIDADA', 'NO_UBICADA', 'RECHAZADA', 'ANULADA'])), _connector='OR'), name='encuesta_cierre_coherente'),
        ),
        migrations.AddConstraint(
            model_name='encuesta',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('estado', 'ANULADA'), _negated=True), models.Q(('comentario_revision', ''), _negated=True), _connector='OR'), name='encuesta_anulacion_con_motivo'),
        ),
    ]
