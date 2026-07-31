"""Filtro de plantilla para consultar permisos (HU-05).

¿POR QUÉ HACE FALTA ESTO?

Porque el lenguaje de plantillas de Django no permite llamar a un método CON
ARGUMENTOS. Esto no funciona y nunca funcionará:

    {% if user.tiene_permiso("operativos.ver") %}   ✗ error de sintaxis
    {% if user.tiene_permiso "operativos.ver" %}    ✗ tampoco

La limitación es deliberada: las plantillas están pensadas para presentar, no para
ejecutar lógica. Cuando hace falta pasar un argumento, la salida prevista por
Django es un filtro, y eso es exactamente lo que hay aquí:

    {% load permisos %}
    {% if user|tiene_permiso:"operativos.ver" %}

LA ALTERNATIVA QUE SE DESCARTÓ

Cada vista podría poner en su contexto una bandera booleana
(`contexto["puede_gestionar"] = ...`), y de hecho las vistas de la HU-05 lo hacen
para lo que necesitan. Pero base.html no pertenece a ninguna vista: la heredan
TODAS, incluidas las de las apps usuarios y dashboards. Resolverlo con contexto
obligaría a que cada vista del proyecto recordara pasar la bandera, y la primera
que se olvidara dejaría el menú incompleto sin que nadie lo notara.

Un context processor también serviría, pero se ejecutaría en cada petición
—incluidas las que no dibujan el menú— y consultaría permisos que quizá nadie va a
mirar. El filtro solo consulta cuando la plantilla realmente pregunta.

ESTO NO ES SEGURIDAD. Ocultar un enlace es comodidad para el usuario: evita
ofrecerle una pantalla que le va a responder "no tienes permiso". La seguridad real
está en las vistas, con PermisoRequeridoMixin, porque la URL siempre se puede
escribir a mano.
"""

from django import template

register = template.Library()


@register.filter
def tiene_permiso(usuario, codigo):
    """True si el usuario tiene concedido ese permiso. Uso: user|tiene_permiso:"x.y"

    Delega en Usuario.tiene_permiso(), que ya resuelve el rol, el administrador
    implícito y los permisos desactivados. No se reimplementa ninguna regla aquí:
    un filtro que decidiera por su cuenta podría contradecir a la vista, y el
    usuario vería un enlace que al pulsarlo lo rechaza.

    Un visitante anónimo no tiene el método (es AnonymousUser), así que se
    comprueba antes con hasattr en vez de dejar que estalle: base.html se dibuja
    también en pantallas donde la sesión pudo expirar.
    """
    if not hasattr(usuario, "tiene_permiso"):
        return False

    return usuario.tiene_permiso(codigo)


@register.filter
def tiene_algun_permiso(usuario, codigos):
    """True si tiene al menos uno de los permisos. Los códigos van separados por comas.

    Uso: {% if user|tiene_algun_permiso:"operativos.ver,operativos.gestionar" %}

    Existe porque un elemento del menú suele abrirse con cualquiera de varios
    permisos, y anidar dos filtros con `or` en una plantilla se vuelve ilegible.
    """
    if not hasattr(usuario, "tiene_algun_permiso"):
        return False

    lista = [codigo.strip() for codigo in codigos.split(",") if codigo.strip()]
    return usuario.tiene_algun_permiso(*lista)
