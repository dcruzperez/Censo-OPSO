"""HU-15: devolver con observaciones.

Agrega el contador `veces_devuelta` y extiende a OBSERVADA la restricción que exige
un comentario al resolver. Las explicaciones están junto a cada campo en
fichas/models.py; aquí interesan dos cosas.

--------------------------------------------------------------------------
POR QUÉ LA RESTRICCIÓN CAMBIA DE NOMBRE
--------------------------------------------------------------------------
La HU-14 creó `encuesta_anulacion_con_motivo`, que cubría solo ANULADA. Esta
migración la borra y crea `encuesta_resolucion_con_motivo`, que cubre ANULADA y
OBSERVADA.

Se podría haber conservado el nombre anterior y ampliar su condición. Se prefirió
renombrarla porque una restricción llamada «anulacion» que además gobierna las
devoluciones MIENTE sobre lo que comprueba, y el nombre de una restricción es lo
único que se ve cuando la base de datos rechaza una fila: el mensaje de error dice
el nombre y nada más.

--------------------------------------------------------------------------
POR QUÉ HACE FALTA UN PASO DE DATOS
--------------------------------------------------------------------------
Hasta ahora, OBSERVADA solo se podía alcanzar por el admin o por el comando de
demostración, y ninguno de los dos escribía `comentario_revision`: la HU-07 definió
el estado tres historias antes de que existiera el campo. Esas filas contradicen la
restricción nueva, así que crearla sin más las rechazaría y la migración fallaría —
como ya pasó, a propósito, en la HU-10.

`rellenar_observaciones` resuelve el conflicto con el mismo criterio de entonces:

  - Si hay algo en `observaciones`, se copia. En esas filas es el único sitio donde
    pudo quedar escrito el motivo de la devolución, porque el campo específico no
    existía.
  - Si no hay nada, se escribe la constancia de que no se anotó. NO es una
    observación inventada: es la información verdadera, y un dato inventado es peor
    que un dato ausente porque nadie puede distinguirlo después.

Se copia y no se mueve: `observaciones` conserva su contenido, porque vaciarla
supondría que todo lo que había ahí era la devolución, y no se puede saber.
"""

from django.conf import settings
from django.db import migrations, models


#: Texto para las filas que ya estaban OBSERVADAS sin ninguna observación escrita.
SIN_OBSERVACION_REGISTRADA = (
    "Observación no registrada: la encuesta se devolvió antes de que el sistema "
    "exigiera anotarla."
)


def rellenar_observaciones(apps, schema_editor):
    """Le da un comentario a las encuestas ya devueltas que no lo tienen."""
    Encuesta = apps.get_model("fichas", "Encuesta")

    for encuesta in Encuesta.objects.filter(
        estado="OBSERVADA", comentario_revision=""
    ).iterator():
        encuesta.comentario_revision = (
            encuesta.observaciones.strip() or SIN_OBSERVACION_REGISTRADA
        )
        # Si estaba observada, alguien la devolvió al menos una vez. Dejar el
        # contador en cero diría que nunca se devolvió, que es falso.
        encuesta.veces_devuelta = max(encuesta.veces_devuelta, 1)
        encuesta.save(update_fields=["comentario_revision", "veces_devuelta"])


def vaciar_observaciones(apps, schema_editor):
    """Reverso: borra solo lo que escribió la función de arriba.

    Se compara con lo que se copió para no borrar una observación que alguien haya
    escrito de verdad después de aplicar la migración.
    """
    Encuesta = apps.get_model("fichas", "Encuesta")

    for encuesta in Encuesta.objects.filter(estado="OBSERVADA").iterator():
        if encuesta.comentario_revision in (
            SIN_OBSERVACION_REGISTRADA,
            encuesta.observaciones.strip(),
        ):
            encuesta.comentario_revision = ""
            encuesta.save(update_fields=["comentario_revision"])


class Migration(migrations.Migration):

    dependencies = [
        ('fichas', '0007_resolucion_del_supervisor'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='encuesta',
            name='encuesta_anulacion_con_motivo',
        ),
        migrations.AddField(
            model_name='encuesta',
            name='veces_devuelta',
            field=models.PositiveSmallIntegerField(default=0, help_text='Cuántas veces el supervisor la ha devuelto con observaciones. Una ficha devuelta tres veces señala un problema de formación, no de esa ficha.', verbose_name='veces devuelta'),
        ),
        migrations.AlterField(
            model_name='encuesta',
            name='comentario_revision',
            field=models.TextField(blank=True, help_text='Lo que el supervisor deja escrito al resolver. Obligatorio al anular y al devolver: una ficha descartada o devuelta sin explicación no sirve de nada.', verbose_name='comentario de la revisión'),
        ),
        # El paso de datos va entre la columna y la restricción: sin él, las filas
        # que ya estaban OBSERVADAS sin comentario harían fallar la creación.
        migrations.RunPython(rellenar_observaciones, vaciar_observaciones),
        migrations.AddConstraint(
            model_name='encuesta',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('estado__in', ['ANULADA', 'OBSERVADA']), _negated=True), models.Q(('comentario_revision', ''), _negated=True), _connector='OR'), name='encuesta_resolucion_con_motivo'),
        ),
    ]
