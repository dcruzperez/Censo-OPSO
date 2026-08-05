from django.apps import AppConfig


class FichasConfig(AppConfig):
    """Configuración de la app «fichas» (HU-07 y siguientes).

    ¿POR QUÉ LA APP SE LLAMA «fichas» SI LA HISTORIA HABLA DE «ENCUESTAS»?

    Porque el nombre no se elige aquí: lo fijó la HU-04 cuando sembró el catálogo
    de permisos. Allí existen desde entonces `fichas.ver_propias`, `fichas.crear`,
    `fichas.editar` y `fichas.validar`, agrupados bajo el módulo FICHAS. Llamar
    «encuestas» a la app obligaría a que el código pidiera permisos de un módulo
    con otro nombre, y esa discordancia se paga cada vez que alguien busca dónde
    se autoriza algo.

    Los dos términos nombran las dos caras del mismo hecho y el proyecto los usa
    con esa precisión: la ENCUESTA es el trabajo de terreno (ir, tocar la puerta,
    preguntar) y la FICHA es el registro que queda. Por eso el modelo se llama
    Encuesta —lo que el encuestador organiza es su trabajo— y el módulo se llama
    fichas —lo que el sistema guarda y el supervisor valida—.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "fichas"
    verbose_name = "Encuestas y fichas de familias"
