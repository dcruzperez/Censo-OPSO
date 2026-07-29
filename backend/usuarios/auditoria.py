"""Registro de auditoría de la administración de usuarios (HU-03).

¿Por qué un módulo aparte y no código dentro de las vistas?

1. UNA SOLA FORMA DE REGISTRAR. Si cada vista armara su propia fila, tarde o
   temprano una olvidaría la IP o escribiría la acción con otro texto, y la
   bitácora dejaría de ser comparable.
2. SE PUEDE PROBAR SOLO. registrar_accion() es una función normal: una prueba
   la llama y verifica la fila resultante, sin simular una petición HTTP.
3. SE PUEDE REUTILIZAR. Mañana un comando de gestión o una API podrán registrar
   en la misma bitácora con la misma llamada.

Es el mismo criterio que ya se aplicó en la HU-01 con seguridad.py.
"""

import logging

from .models import AccionAuditoria, RegistroAuditoria
from .seguridad import obtener_ip, obtener_user_agent

logger = logging.getLogger("usuarios")


def registrar_accion(administrador, accion, usuario_afectado, detalle="", request=None):
    """Escribe una fila en la bitácora de auditoría y la devuelve.

    Parámetros:
        administrador    -> Usuario que ejecuta la acción (request.user).
        accion           -> valor de AccionAuditoria.
        usuario_afectado -> Usuario sobre el que se actuó.
        detalle          -> texto libre con el cambio exacto.
        request          -> para obtener IP y navegador (contexto forense).

    Se guardan los correos como texto además de las claves foráneas: si una
    cuenta se eliminara físicamente algún día, la fila seguiría siendo legible
    (ver la explicación en el modelo RegistroAuditoria).
    """
    registro = RegistroAuditoria.objects.create(
        administrador=administrador if getattr(administrador, "pk", None) else None,
        administrador_email=getattr(administrador, "email", "") or "",
        accion=accion,
        usuario_afectado=usuario_afectado,
        usuario_afectado_email=usuario_afectado.email,
        detalle=detalle,
        ip=obtener_ip(request),
        user_agent=obtener_user_agent(request),
    )

    # El log en texto es un segundo respaldo: si la base de datos se corrompiera
    # o alguien lograra borrar filas, el archivo de log conserva el rastro.
    logger.info(
        "AUDITORÍA | %s | admin=%s | afectado=%s | %s",
        AccionAuditoria(accion).label,
        registro.administrador_email or "(desconocido)",
        registro.usuario_afectado_email,
        detalle or "sin detalle",
    )
    return registro


def _valor_legible(formulario, nombre_campo, valor):
    """Convierte un valor interno en algo entendible por una persona.

    Sin esta traducción, la bitácora diría "rol: 3 -> 2" (los identificadores
    de la tabla usuarios_rol), que no le sirve a nadie en una revisión.
    """
    if valor is None or valor == "":
        return "(vacío)"

    if isinstance(valor, bool):
        return "Activo" if valor else "Inactivo"

    campo = formulario.fields.get(nombre_campo)

    # Los campos de clave foránea (ModelChoiceField) tienen "queryset". El valor
    # llega como objeto (desde cleaned_data) o como id (desde form.initial).
    if campo is not None and hasattr(campo, "queryset"):
        if hasattr(valor, "pk"):
            return str(valor)
        objeto = campo.queryset.filter(pk=valor).first()
        return str(objeto) if objeto else "(vacío)"

    return str(valor)


def describir_cambios(formulario):
    """Arma el texto del detalle a partir de los campos realmente modificados.

    form.changed_data es una lista que Django calcula comparando el valor
    inicial (lo que había en la base de datos) con el valor enviado. Solo se
    registra lo que cambió: una bitácora con los 8 campos en cada edición sería
    ruido y escondería lo importante.

    Resultado de ejemplo:
        rol: «Censista» -> «Supervisor»; teléfono: «(vacío)» -> «+56 9 1234 5678»
    """
    partes = []

    for nombre_campo in formulario.changed_data:
        campo = formulario.fields.get(nombre_campo)
        if campo is None:
            continue

        etiqueta = campo.label or nombre_campo
        antes = _valor_legible(
            formulario, nombre_campo, formulario.initial.get(nombre_campo)
        )
        despues = _valor_legible(
            formulario, nombre_campo, formulario.cleaned_data.get(nombre_campo)
        )

        if antes != despues:
            partes.append(f"{etiqueta}: «{antes}» → «{despues}»")

    return "; ".join(partes)
