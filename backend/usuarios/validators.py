"""Validadores propios del dominio chileno.

¿Por qué validar el RUT aquí y no en el navegador?
Porque la validación de JavaScript se puede saltar (deshabilitando JS o
enviando la petición con curl/Postman). La validación del servidor es la
única que realmente protege la integridad de los datos.
"""

import re

from django.core.exceptions import ValidationError

RUT_PERMITIDO = re.compile(r"^\d{7,8}-[\dkK]$")

# Nombre de usuario: minúsculas, números, punto, guion y guion bajo.
# Se prohíben espacios, acentos y símbolos para que el identificador sea fácil
# de dictar por teléfono en terreno y no dependa de la codificación del teclado.
NOMBRE_USUARIO_PERMITIDO = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")


def limpiar_rut(valor: str) -> str:
    """Normaliza un RUT al formato canónico 12345678-9.

    Acepta "12.345.678-9", "12345678-9" o "123456789" y devuelve siempre la
    misma forma, para que la base de datos no guarde el mismo RUT escrito de
    tres maneras distintas (lo que rompería la restricción UNIQUE).
    """
    if valor is None:
        return valor
    limpio = str(valor).strip().upper().replace(".", "").replace(" ", "")
    if "-" not in limpio and len(limpio) > 1:
        # Si viene sin guion, separamos el último carácter como dígito verificador.
        limpio = f"{limpio[:-1]}-{limpio[-1]}"
    return limpio


def calcular_digito_verificador(cuerpo: str) -> str:
    """Calcula el dígito verificador con el algoritmo módulo 11.

    Es el mismo cálculo que usa el Registro Civil: se multiplica cada dígito
    (de derecha a izquierda) por la serie 2,3,4,5,6,7 de forma cíclica.
    """
    suma = 0
    multiplicador = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1

    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def validar_rut(valor: str) -> None:
    """Valida formato y dígito verificador. Lo usa el modelo y los formularios."""
    rut = limpiar_rut(valor)

    if not RUT_PERMITIDO.match(rut):
        raise ValidationError(
            "El RUT debe tener el formato 12345678-9 (sin puntos).",
            code="rut_formato",
        )

    cuerpo, digito = rut.split("-")
    if calcular_digito_verificador(cuerpo) != digito.upper():
        raise ValidationError(
            "El RUT ingresado no es válido: el dígito verificador no coincide.",
            code="rut_invalido",
        )


# ==========================================================================
# NOMBRE DE USUARIO (identificador corto, NO es la credencial de acceso)
# ==========================================================================
# Agregado en la HU-03 (Administración de usuarios).
#
# ¿Por qué existe si en OPSO se inicia sesión con el correo?
# Porque son dos cosas distintas:
#   - el CORREO es la credencial de acceso (USERNAME_FIELD),
#   - el NOMBRE DE USUARIO es una etiqueta corta y legible para identificar a
#     la persona en listados, planillas y conversaciones de terreno
#     ("la ficha la levantó msoto").
# Mantener el correo como única credencial evita tener dos formas de entrar al
# sistema, que es una fuente clásica de errores y de agujeros de seguridad.


def limpiar_nombre_usuario(valor):
    """Normaliza el nombre de usuario: minúsculas, sin espacios.

    Devuelve None cuando queda vacío, porque la columna es UNIQUE y admite
    NULL: en SQL varios NULL no chocan entre sí, pero varias cadenas vacías sí
    violarían la restricción de unicidad.
    """
    if valor is None:
        return None
    limpio = str(valor).strip().lower().replace(" ", "")
    return limpio or None


def validar_nombre_usuario(valor):
    """Valida el formato del nombre de usuario."""
    limpio = limpiar_nombre_usuario(valor)

    if limpio is None:
        return

    if not NOMBRE_USUARIO_PERMITIDO.match(limpio):
        raise ValidationError(
            "El nombre de usuario debe tener entre 3 y 30 caracteres y solo "
            "puede contener letras sin acento, números, punto, guion y guion "
            "bajo. Debe comenzar con una letra o un número.",
            code="nombre_usuario_formato",
        )
