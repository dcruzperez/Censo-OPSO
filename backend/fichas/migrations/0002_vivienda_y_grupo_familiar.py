"""HU-08: la vivienda y el grupo familiar, y el traspaso de lo que ya existía.

Es la primera migración del proyecto que MUEVE DATOS DE UNA TABLA A OTRA, y por
eso está escrita a mano en vez de generada con `makemigrations`. El generador
automático sabe crear columnas, pero no sabe qué hacer con las
filas que ya están: al encontrarse una clave foránea obligatoria nueva, pregunta
por un valor por defecto, y aquí no hay ninguno que sea correcto.

--------------------------------------------------------------------------
QUÉ HACE, EN ORDEN
--------------------------------------------------------------------------
 1. Crea `fichas_vivienda` y `fichas_grupo_familiar`.
 2. Agrega `Encuesta.vivienda` como NULA, que es la única forma de agregar una
    clave foránea obligatoria a una tabla con filas.
 3. Traspasa los datos: por cada encuesta existente crea (o reutiliza) la
    vivienda que le corresponde y la apunta.
 4. Recién entonces la vuelve OBLIGATORIA.
 5. Borra de `fichas_encuesta` las tres columnas que se mudaron.

El orden no es negociable: invertir 3 y 4 dejaría la migración a medias en
cualquier base que ya tenga encuestas, que es justamente el caso que esta
migración existe para resolver.

--------------------------------------------------------------------------
POR QUÉ LAS VIVIENDAS MIGRADAS QUEDAN SIN DESCRIBIR
--------------------------------------------------------------------------
Las encuestas de la HU-07 tienen dirección y zona, pero nadie levantó todavía el
tipo de vivienda, la materialidad ni los servicios: esa pantalla la trae esta
misma historia. La migración podría rellenar esos campos con «lo más común» y
dejar la base sin vacíos, y sería lo peor que podría hacer: **un dato inventado es
peor que un dato ausente**, porque nadie puede distinguirlo después y acabaría
sumado en un informe.

Las viviendas migradas quedan, por tanto, con sus características en blanco, y el
sistema lo muestra como «sin describir» con un enlace para completarla. Es el
mismo criterio con el que la HU-03 desnormalizó los correos en la bitácora: entre
un dato que se puede leer y una tabla perfecta, en información que va a defender
decisiones públicas manda la primera.

--------------------------------------------------------------------------
SE PUEDE DESHACER, Y ESO OBLIGA A ORDENAR CON CUIDADO
--------------------------------------------------------------------------
Una migración de datos sin vuelta atrás obliga a restaurar un respaldo si algo
sale mal en producción, así que esta se puede revertir con
`migrate fichas 0001`.

Conseguirlo tiene un truco que conviene poder explicar. Django deshace las
operaciones EN ORDEN INVERSO, así que al revertir, lo primero que ocurre es que
reaparecen las tres columnas que se habían borrado… vacías. Si se hubieran
declarado obligatorias, la base de datos rechazaría ahí mismo la vuelta atrás:
no se puede agregar una columna NOT NULL a una tabla que ya tiene filas.

Por eso las columnas se vuelven NULAS (pasos 7 a 9) ANTES de borrarlas, aunque
en el sentido de ida eso no sirva para nada. En el sentido de vuelta es lo que
hace posible la secuencia correcta:

    reaparecen nulas -> `revertir()` las rellena -> vuelven a ser obligatorias

El mismo motivo por el que `Encuesta.vivienda` se agrega nula y se endurece
después, solo que en el otro sentido.
"""

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import usuarios.validators


def traspasar(apps, schema_editor):
    """Convierte cada encuesta existente en una vivienda con su encuesta.

    Dos encuestas con la misma zona, dirección y referencia se consideran DOS
    HOGARES DE LA MISMA VIVIENDA y comparten una sola fila: es exactamente el caso
    que la HU-07 dejó anotado como punto débil y que esta historia resuelve.

    Si la referencia difiere se crean dos viviendas, porque en terreno «la casa del
    fondo» y «la de adelante» en la misma dirección son dos viviendas distintas y
    no dos hogares de una.
    """
    Encuesta = apps.get_model("fichas", "Encuesta")
    Vivienda = apps.get_model("fichas", "Vivienda")

    viviendas = {}

    for encuesta in Encuesta.objects.all().iterator():
        clave = (encuesta.zona_id, encuesta.direccion, encuesta.referencia)

        if clave not in viviendas:
            viviendas[clave] = Vivienda.objects.create(
                zona_id=encuesta.zona_id,
                direccion=encuesta.direccion,
                referencia=encuesta.referencia,
                # Sin describir a propósito: ver la cabecera.
                observaciones=(
                    "Vivienda creada al migrar el padrón de la HU-07. Sus "
                    "características todavía no se han levantado en terreno."
                ),
                registrada_por_id=encuesta.asignada_por_id,
            )

        encuesta.vivienda = viviendas[clave]
        encuesta.save(update_fields=["vivienda"])


def sin_vuelta_atras(apps, schema_editor):
    """Reverso vacío de `traspasar`.

    No hay nada que deshacer aquí: las viviendas creadas desaparecen solas cuando
    la vuelta atrás borra la tabla, unos pasos más adelante. La restauración de
    los datos en la encuesta la hace `revertir`, que está colocada donde debe
    estar (ver la cabecera).
    """


def sin_ida(apps, schema_editor):
    """Ida vacía: esta operación solo existe por su reverso."""


def revertir(apps, schema_editor):
    """Devuelve la dirección, la referencia y la zona a cada encuesta.

    Se ejecuta solo al revertir, y en el momento exacto en que las tres columnas
    ya reaparecieron —nulas— y todavía no se han vuelto obligatorias.
    """
    Encuesta = apps.get_model("fichas", "Encuesta")

    for encuesta in Encuesta.objects.select_related("vivienda").iterator():
        if encuesta.vivienda_id is None:
            continue

        encuesta.zona_id = encuesta.vivienda.zona_id
        encuesta.direccion = encuesta.vivienda.direccion
        encuesta.referencia = encuesta.vivienda.referencia
        encuesta.save(update_fields=["zona", "direccion", "referencia"])


class Migration(migrations.Migration):

    dependencies = [
        ("fichas", "0001_initial"),
        ("operativos", "0003_asignaciones"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ------------------------------------------------------------------
        # 1. LAS DOS TABLAS NUEVAS
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Vivienda",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("direccion", models.CharField(help_text="Calle y número. Ej.: Pasaje Los Robles 1425.", max_length=200, verbose_name="dirección")),
                ("referencia", models.CharField(blank=True, help_text="Cómo reconocerla desde la calle. Ej.: casa verde, portón negro, la del fondo del sitio.", max_length=200, verbose_name="referencia")),
                ("tipo", models.CharField(blank=True, choices=[("CASA", "Casa"), ("DEPARTAMENTO", "Departamento en edificio"), ("PIEZA", "Pieza en casa antigua o conventillo"), ("MEDIAGUA", "Mediagua o mejora"), ("RANCHO", "Rancho o choza"), ("PRECARIA", "Vivienda precaria de materiales reutilizados"), ("OTRA", "Otra")], help_text="Clasificación según el censo.", max_length=20, verbose_name="tipo de vivienda")),
                ("tenencia", models.CharField(blank=True, choices=[("PROPIA_PAGADA", "Propia, totalmente pagada"), ("PROPIA_PAGANDOSE", "Propia, pagándose"), ("ARRENDADA", "Arrendada"), ("CEDIDA", "Cedida por trabajo o por un familiar"), ("IRREGULAR", "Ocupación irregular"), ("OTRA", "Otra")], help_text="A qué título ocupa la familia esta vivienda.", max_length=20, verbose_name="tenencia")),
                ("materialidad_muros", models.CharField(blank=True, choices=[("HORMIGON", "Hormigón armado"), ("ALBANILERIA", "Albañilería (ladrillo, bloque, piedra)"), ("TABIQUE_FORRADO", "Tabique forrado por ambas caras"), ("TABIQUE_SIN_FORRO", "Tabique sin forro interior"), ("ADOBE", "Adobe, barro o quincha"), ("PRECARIO", "Materiales precarios o de desecho")], help_text="Material predominante de los muros exteriores.", max_length=20, verbose_name="materialidad de los muros")),
                ("origen_agua", models.CharField(blank=True, choices=[("RED_PUBLICA", "Red pública"), ("POZO", "Pozo o noria"), ("CAMION", "Camión aljibe"), ("SUPERFICIAL", "Río, vertiente, estero o lago"), ("OTRO", "Otro")], help_text="De dónde proviene el agua que usa la vivienda.", max_length=20, verbose_name="origen del agua")),
                ("sistema_sanitario", models.CharField(blank=True, choices=[("ALCANTARILLADO", "Conectado al alcantarillado"), ("FOSA", "Fosa séptica"), ("LETRINA", "Letrina sanitaria conectada a pozo"), ("CAJON", "Cajón sobre pozo negro"), ("NO_TIENE", "No dispone de servicio higiénico")], help_text="Cómo se eliminan las aguas servidas.", max_length=20, verbose_name="sistema sanitario")),
                ("tiene_electricidad", models.BooleanField(blank=True, help_text="Si cuenta con suministro eléctrico regular.", null=True, verbose_name="tiene electricidad")),
                ("observaciones", models.TextField(blank=True, help_text="Lo que el formulario no previó y conviene dejar anotado.", verbose_name="observaciones")),
                ("creada_en", models.DateTimeField(auto_now_add=True, verbose_name="creada en")),
                ("actualizada_en", models.DateTimeField(auto_now=True, verbose_name="actualizada en")),
                ("registrada_por", models.ForeignKey(blank=True, help_text="Quién la dio de alta en terreno.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="viviendas_registradas", to=settings.AUTH_USER_MODEL, verbose_name="registrada por")),
                ("zona", models.ForeignKey(help_text="Zona del sector en la que se ubica la vivienda.", on_delete=django.db.models.deletion.PROTECT, related_name="viviendas", to="operativos.zona", verbose_name="zona")),
            ],
            options={
                "verbose_name": "vivienda",
                "verbose_name_plural": "viviendas",
                "db_table": "fichas_vivienda",
                "ordering": ["zona__sector__nombre", "zona__nombre", "direccion"],
                "indexes": [models.Index(fields=["zona", "direccion"], name="idx_vivienda_zona")],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("tipo__in", ["CASA", "DEPARTAMENTO", "PIEZA", "MEDIAGUA", "RANCHO", "PRECARIA", "OTRA"]),
                            ("tipo", ""),
                            _connector="OR",
                        ),
                        name="vivienda_tipo_valido",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("tenencia__in", ["PROPIA_PAGADA", "PROPIA_PAGANDOSE", "ARRENDADA", "CEDIDA", "IRREGULAR", "OTRA"]),
                            ("tenencia", ""),
                            _connector="OR",
                        ),
                        name="vivienda_tenencia_valida",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="GrupoFamiliar",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("jefe_hogar_nombre", models.CharField(help_text="Nombre completo de quien la familia reconoce como jefe de hogar.", max_length=150, verbose_name="nombre del jefe o jefa de hogar")),
                ("jefe_hogar_rut", models.CharField(blank=True, help_text="Formato 12345678-9. Opcional: no se exige para poder registrar.", max_length=12, validators=[usuarios.validators.validar_rut], verbose_name="RUT del jefe o jefa de hogar")),
                ("telefono_contacto", models.CharField(blank=True, help_text="Para coordinar una segunda visita si la encuesta queda a medias.", max_length=20, verbose_name="teléfono de contacto")),
                ("integrantes_declarados", models.PositiveSmallIntegerField(help_text="Cuántas personas declara la familia. Se contrasta con las que se registren una por una.", verbose_name="personas que viven en el hogar")),
                ("ingreso_mensual", models.PositiveIntegerField(blank=True, help_text="Suma aproximada en pesos de todos los ingresos del hogar. Opcional: es la pregunta que más se prefiere no contestar.", null=True, verbose_name="ingreso mensual del hogar")),
                ("observaciones", models.TextField(blank=True, help_text="Situaciones que el formulario no recoge y conviene dejar por escrito.", verbose_name="observaciones")),
                ("registrado_en", models.DateTimeField(auto_now_add=True, verbose_name="registrado en")),
                ("actualizado_en", models.DateTimeField(auto_now=True, verbose_name="actualizado en")),
                ("encuesta", models.OneToOneField(help_text="Encuesta en la que se levantó este hogar.", on_delete=django.db.models.deletion.CASCADE, related_name="grupo_familiar", to="fichas.encuesta", verbose_name="encuesta")),
            ],
            options={
                "verbose_name": "grupo familiar",
                "verbose_name_plural": "grupos familiares",
                "db_table": "fichas_grupo_familiar",
                "ordering": ["jefe_hogar_nombre"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("integrantes_declarados__gte", 1)),
                        name="grupo_familiar_al_menos_una_persona",
                    )
                ],
            },
        ),
        # ------------------------------------------------------------------
        # 2. LA CLAVE FORÁNEA, PRIMERO NULA
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="encuesta",
            name="vivienda",
            field=models.ForeignKey(
                help_text="Vivienda en la que se levanta la información.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="encuestas",
                to="fichas.vivienda",
                verbose_name="vivienda",
            ),
        ),
        # ------------------------------------------------------------------
        # 3. EL TRASPASO DE DATOS
        # ------------------------------------------------------------------
        migrations.RunPython(traspasar, sin_vuelta_atras),
        # ------------------------------------------------------------------
        # 4. YA CON TODAS LAS FILAS APUNTADAS, SE VUELVE OBLIGATORIA
        # ------------------------------------------------------------------
        migrations.AlterField(
            model_name="encuesta",
            name="vivienda",
            field=models.ForeignKey(
                help_text="Vivienda en la que se levanta la información.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="encuestas",
                to="fichas.vivienda",
                verbose_name="vivienda",
            ),
        ),
        # ------------------------------------------------------------------
        # 5. SE RETIRA LO QUE SE MUDÓ
        #
        # El índice va antes que la columna: PostgreSQL no deja borrar una columna
        # que un índice todavía referencia.
        #
        # Los tres AlterField a null=True no hacen nada útil en el sentido de ida
        # —las columnas se borran justo después— y son imprescindibles en el de
        # vuelta: ver «SE PUEDE DESHACER» en la cabecera.
        # ------------------------------------------------------------------
        migrations.RemoveIndex(model_name="encuesta", name="idx_encuesta_zona"),
        migrations.AlterField(
            model_name="encuesta",
            name="zona",
            field=models.ForeignKey(
                help_text="Zona del sector en la que se ubica la vivienda.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="encuestas",
                to="operativos.zona",
                verbose_name="zona",
            ),
        ),
        migrations.AlterField(
            model_name="encuesta",
            name="direccion",
            field=models.CharField(max_length=200, null=True, verbose_name="dirección"),
        ),
        migrations.AlterField(
            model_name="encuesta",
            name="referencia",
            field=models.CharField(
                blank=True, max_length=200, null=True, verbose_name="referencia"
            ),
        ),
        migrations.RunPython(sin_ida, revertir),
        migrations.RemoveField(model_name="encuesta", name="zona"),
        migrations.RemoveField(model_name="encuesta", name="direccion"),
        migrations.RemoveField(model_name="encuesta", name="referencia"),
        migrations.AlterModelOptions(
            name="encuesta",
            options={
                "ordering": [
                    "vivienda__zona__sector__nombre",
                    "vivienda__zona__nombre",
                    "vivienda__direccion",
                ],
                "verbose_name": "encuesta",
                "verbose_name_plural": "encuestas",
            },
        ),
        migrations.AddIndex(
            model_name="encuesta",
            index=models.Index(fields=["vivienda", "estado"], name="idx_encuesta_vivienda"),
        ),
    ]
