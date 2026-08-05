"""HU-10: el borrador y el cierre de una encuesta.

Tres columnas y una restricción. Las explicaciones están junto a cada campo en
fichas/models.py; aquí interesan dos cosas.

--------------------------------------------------------------------------
POR QUÉ SE PARTE `observaciones` EN DOS
--------------------------------------------------------------------------
La HU-07 declaró `observaciones` como «indicaciones del supervisor O notas del
propio encuestador». Esa «o» era una ambigüedad, y se paga en cuanto los dos
escriben en el mismo campo: la nota que el encuestador se deja a sí mismo pisaría
las instrucciones que recibió, o al revés.

Esta migración NO mueve datos: `observaciones` conserva lo que tenga y solo se
reescribe su texto de ayuda para que signifique una sola cosa —las indicaciones
que se reciben—, y `nota_avance` nace vacía para lo que uno se deja anotado. Dos
autores, dos propósitos, dos columnas.

Se prefiere agregar una columna antes que repartir a mano el contenido de la
existente, porque nadie puede saber hoy cuál de las dos cosas escribió cada quien
en las filas que ya están: adivinarlo sería inventar autoría.

--------------------------------------------------------------------------
LA RESTRICCIÓN: CERRAR SIN LEVANTAR EXIGE DECIR POR QUÉ
--------------------------------------------------------------------------
  encuesta_cierre_con_motivo -> si el estado es NO_UBICADA o RECHAZADA, entonces
                                motivo_cierre no puede estar vacío.

«No ubicada» y «rechazada» son resultados legítimos —la HU-07 lo argumentó al
definir los siete estados— pero solo son INFORMACIÓN si consta el motivo. Sin
esta restricción, una zona podría acumular veinte encuestas cerradas sin que
nadie distinga «la dirección no existe» de «pasé y no había nadie», que exigen
decisiones opuestas del supervisor.

NO se puede crear sobre los datos existentes sin trabajo previo, y eso se
comprobó a la primera: la migración falló con
`CHECK constraint failed: encuesta_cierre_con_motivo`. El motivo es que la HU-07
permitía cerrar una encuesta como no ubicada o rechazada SIN NINGÚN CAMPO donde
escribir por qué, así que el motivo —cuando se escribió— acabó en
`observaciones`.

Por eso hay un paso de datos (`rellenar_motivos`) ANTES de crear la restricción.
Copia lo que haya en `observaciones` y, cuando no hay nada, escribe la constancia
de que no se anotó. No inventa motivos: ver la explicación en esa función.

Que la restricción se cree al final tiene además una consecuencia buena: en
cualquier base con filas que contradigan la regla, la migración FALLA en vez de
aceptarlas. Fallar ruidosamente obliga a mirar esas filas en vez de heredar el
problema, que es exactamente lo que ocurrió aquí.
"""

from django.conf import settings
from django.db import migrations, models

#: Texto que se escribe cuando una encuesta ya cerrada NO tiene motivo anotado en
#: ninguna parte. No es un motivo inventado: es la constancia de que no se anotó.
SIN_MOTIVO_REGISTRADO = (
    "Motivo no registrado: la encuesta se cerró antes de que el sistema exigiera "
    "anotarlo."
)


def rellenar_motivos(apps, schema_editor):
    """Le da un motivo a las encuestas ya cerradas sin levantar.

    Hace falta porque la restricción que se crea justo después las rechazaría, y
    porque esas filas existen: la HU-07 permitía cerrar una encuesta como no
    ubicada o rechazada sin ningún campo donde escribir por qué, así que el motivo
    —cuando se escribió— acabó en `observaciones`.

    Dos casos y ninguno inventa nada:

      - Si hay algo en `observaciones`, se copia. Es el motivo real, guardado en el
        único sitio que había.
      - Si no hay nada, se escribe SIN_MOTIVO_REGISTRADO. Eso NO es un motivo
        inventado: es la constancia explícita de que no se anotó, que es la
        información verdadera. Es el mismo criterio con que la migración 0002 dejó
        «sin describir» las viviendas heredadas en vez de rellenarlas con «lo más
        común»: un dato inventado es peor que un dato ausente, porque nadie puede
        distinguirlo después.

    Se copia y no se mueve: `observaciones` conserva su contenido. Vaciarla
    supondría que todo lo que hay ahí era el motivo del cierre, y no se puede saber.
    """
    Encuesta = apps.get_model("fichas", "Encuesta")

    for encuesta in Encuesta.objects.filter(
        estado__in=["NO_UBICADA", "RECHAZADA"], motivo_cierre=""
    ).iterator():
        encuesta.motivo_cierre = encuesta.observaciones.strip() or SIN_MOTIVO_REGISTRADO
        encuesta.save(update_fields=["motivo_cierre"])


def vaciar_motivos(apps, schema_editor):
    """Reverso: borra lo que escribió `rellenar_motivos`.

    Solo vacía las filas cuyo motivo COINCIDE con lo que se copió, para no borrar
    un motivo que alguien haya escrito de verdad después de aplicar la migración.
    """
    Encuesta = apps.get_model("fichas", "Encuesta")

    for encuesta in Encuesta.objects.exclude(motivo_cierre="").iterator():
        if encuesta.motivo_cierre in (
            SIN_MOTIVO_REGISTRADO,
            encuesta.observaciones.strip(),
        ):
            encuesta.motivo_cierre = ""
            encuesta.save(update_fields=["motivo_cierre"])


class Migration(migrations.Migration):

    dependencies = [
        ('fichas', '0003_integrantes_del_hogar'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='encuesta',
            name='motivo_cierre',
            field=models.TextField(blank=True, help_text='Por qué no se pudo levantar. Obligatorio al cerrar una encuesta como no ubicada o rechazada.', verbose_name='motivo del cierre'),
        ),
        migrations.AddField(
            model_name='encuesta',
            name='nota_avance',
            field=models.TextField(blank=True, help_text='Recordatorio para uno mismo al retomar la encuesta. Ej.: «falta el módulo de ingresos y los datos del hijo mayor».', verbose_name='nota de avance'),
        ),
        migrations.AddField(
            model_name='encuesta',
            name='proxima_visita',
            field=models.DateField(blank=True, help_text='Cuándo conviene volver. Vacío si no hace falta una segunda visita.', null=True, verbose_name='próxima visita'),
        ),
        migrations.AlterField(
            model_name='encuesta',
            name='observaciones',
            field=models.TextField(blank=True, help_text='Indicaciones para quien va a levantar esta encuesta. Ej.: «pasar después de las 19:00, trabajan todo el día».', verbose_name='observaciones'),
        ),
        # El paso de datos va ANTES de la restricción, y no es opcional: las
        # encuestas que la HU-07 cerró sin levantar no tenían dónde guardar el
        # motivo, así que sin este paso la creación de la restricción falla.
        migrations.RunPython(rellenar_motivos, vaciar_motivos),
        migrations.AddConstraint(
            model_name='encuesta',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('estado__in', ['NO_UBICADA', 'RECHAZADA']), _negated=True), models.Q(('motivo_cierre', ''), _negated=True), _connector='OR'), name='encuesta_cierre_con_motivo'),
        ),
    ]
