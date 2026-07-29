# HU-02 · Recuperación de contraseña por correo electrónico

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como usuario, quiero recuperar mi contraseña mediante correo electrónico para restablecer el acceso al sistema.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3
**Estado:** implementada y verificada — **80 pruebas automáticas** en total (33 nuevas de esta HU), `python manage.py test` → OK
**Depende de:** [HU-01 · Inicio de sesión seguro](HU-01_inicio_de_sesion.md)

---

## Índice

1. [Explicación inicial](#1-explicación-inicial)
2. [Flujo completo](#2-flujo-completo)
3. [Configuración del correo](#3-configuración-del-correo)
4. [Configuración de PostgreSQL](#4-configuración-de-postgresql)
5. [URLs](#5-urls)
6. [Templates](#6-templates)
7. [Formularios](#7-formularios)
8. [Envío de correo](#8-envío-de-correo)
9. [Token de recuperación](#9-token-de-recuperación)
10. [Seguridad](#10-seguridad)
11. [Archivos del proyecto](#11-archivos-del-proyecto)
12. [Migraciones](#12-migraciones)
13. [Pruebas](#13-pruebas)
14. [Posibles problemas](#14-posibles-problemas)
15. [Explicación para la defensa](#15-explicación-para-la-defensa)
16. [Posibles preguntas del profesor](#16-posibles-preguntas-del-profesor)
17. [Conclusión técnica](#17-conclusión-técnica)
18. [Explicación para entender la implementación](#18-explicación-para-entender-la-implementación)

---

## 1. Explicación inicial

### ¿Cómo funciona el proceso de recuperación de contraseña?

El problema de fondo es este: alguien perdió su contraseña, así que **no puede probar quién es** con el método habitual. Pero sí controla algo que solo esa persona debería controlar: **su casilla de correo**.

La recuperación de contraseña aprovecha eso. El razonamiento es:

> *"No puedo verificar tu identidad con la contraseña, pero sí puedo enviarte un mensaje a tu correo registrado. Si logras leerlo y abrir el enlace que contiene, demuestras que tienes acceso a esa casilla. Y como esa casilla es la que la organización registró para ti, acepto que eres tú."*

Se dice entonces que el correo electrónico actúa como **canal alternativo de verificación de identidad**.

El proceso tiene cuatro momentos:

1. **Solicitud.** La persona escribe su correo en un formulario.
2. **Generación del enlace.** Si la cuenta existe, el sistema crea un enlace especial con una firma temporal (el *token*) y lo envía por correo.
3. **Verificación.** Al abrir el enlace, el sistema comprueba que la firma sea auténtica y esté vigente.
4. **Cambio.** Recién ahí se permite escribir una contraseña nueva, que se guarda cifrada.

### ¿Por qué no se envía la contraseña actual por correo?

Por dos razones, y la primera es la más importante:

**1. Porque el sistema no la conoce.** No es una decisión de política: es una **imposibilidad técnica**. OPSO no guarda la contraseña, guarda un *hash* irreversible de ella (ver HU-01, sección 8.2). No existe ninguna operación que permita recuperar el texto original. Si un sistema puede enviarte tu contraseña actual, está confesando que la guarda en texto plano o cifrada de forma reversible, lo que es un defecto grave de seguridad.

**2. Porque el correo electrónico no es un canal seguro.** Un correo:

- viaja por varios servidores intermedios,
- se guarda indefinidamente en la casilla de destino,
- puede quedar en respaldos, en el historial y en dispositivos sincronizados,
- se puede reenviar por error.

Enviar una contraseña por ahí sería dejarla escrita en un lugar permanente y poco controlado. En cambio, el enlace que sí se envía **caduca en una hora y sirve una sola vez**: aunque el correo quede archivado para siempre, el enlace deja de valer.

### ¿Qué es un token?

Un token es un **texto corto que funciona como una firma temporal**. Con una analogía:

> Imagina que el banco te da un papel que dice: *"El portador de este papel puede cambiar la clave de la cuenta 42. Válido hasta las 15:00 de hoy."* Y ese papel lleva un **sello imposible de falsificar**, porque se estampa con un troquel que solo el banco tiene guardado.
>
> El token es ese papel. El troquel es la `SECRET_KEY` de OPSO.

En la práctica, el token de Django se ve así:

```
dcarwr-630193a6b8a32afa7c63906dc54e7d29
└────┘ └──────────────────────────────┘
 fecha        firma (HMAC-SHA256)
```

- La **primera parte** es la marca de tiempo de cuándo se generó, en base 36.
- La **segunda parte** es una firma criptográfica calculada a partir de los datos del usuario y de la clave secreta del servidor.

El punto clave es que **el token no contiene información secreta ni se guarda en la base de datos**: es una firma que el servidor puede *recalcular* para comprobar si es auténtica.

### ¿Cómo evita Django que otra persona cambie la contraseña?

Con cuatro barreras que se aplican una tras otra:

| Barrera | Qué impide |
|---|---|
| **El enlace llega solo a la casilla registrada** | Un atacante que no controle ese correo nunca ve el enlace. |
| **El token está firmado con la `SECRET_KEY`** | No se puede fabricar un token válido sin conocer esa clave, que solo está en el servidor. |
| **El token está atado a UN usuario** | El token del supervisor no sirve para la cuenta del censista, porque la firma incluye los datos de ese usuario específico. |
| **El token caduca y se invalida al usarse** | Aunque el enlace se filtre después, ya no funciona. |

Es decir: para cambiar la contraseña de alguien hay que **tener acceso a su correo** (o bien romper HMAC-SHA256, que hoy no es viable).

### ¿Por qué este proceso es seguro?

Porque cada pieza cubre un riesgo distinto:

- **No revela información.** El sistema responde exactamente lo mismo si el correo existe o no, así que no se puede usar el formulario para averiguar qué cuentas están registradas.
- **La firma es infalsificable.** Depende de una clave secreta que nunca sale del servidor.
- **La ventana de riesgo es corta.** Una hora, y un solo uso.
- **Se autoinvalida.** Al cambiar la contraseña, todos los enlaces anteriores mueren automáticamente (se explica cómo en la sección 9).
- **Cierra las sesiones ajenas.** Si un atacante ya estaba dentro de la cuenta, el restablecimiento lo expulsa.
- **Deja rastro y avisa.** Cada solicitud queda en el registro del servidor y el titular recibe un correo confirmando el cambio.
- **La contraseña nueva se guarda cifrada** con Argon2id y debe cumplir las reglas de robustez.

> **Defensa — en una frase:**
> El sistema no recupera la contraseña (es imposible: solo guarda un hash irreversible); lo que hace es verificar la identidad de la persona por un canal alternativo —su correo— mediante un enlace firmado criptográficamente, de un solo uso y con vencimiento, para luego permitirle definir una contraseña nueva.

---

## 2. Flujo completo

### Diagrama de flujo

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. El usuario olvidó su contraseña e intenta entrar                  │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  2. En /login/ presiona "¿Olvidaste tu contraseña?"                   │
│     → GET /recuperar-contrasena/                                      │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  3. PANTALLA 1: ingresa su correo electrónico                         │
│     → POST /recuperar-contrasena/  (con token CSRF)                   │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
                  ┌─────────────────────────────┐
                  │ ¿Supera el límite de         │
                  │  solicitudes (3 / 15 min)?   │
                  └──────┬───────────────┬──────┘
                      SÍ │               │ NO
                         │               ▼
                         │   ┌────────────────────────────────────┐
                         │   │ 4. VERIFICA QUE EXISTA              │
                         │   │                                     │
                         │   │ SELECT * FROM usuarios_usuario      │
                         │   │ WHERE UPPER(email)=UPPER('...')     │
                         │   │   AND is_active = true              │
                         │   └──────┬──────────────────┬──────────┘
                         │  no existe│                  │ existe
                         │           │                  ▼
                         │           │   ┌──────────────────────────────┐
                         │           │   │ 5. GENERA EL TOKEN TEMPORAL   │
                         │           │   │                               │
                         │           │   │ HMAC-SHA256(                  │
                         │           │   │   pk + password_hash +        │
                         │           │   │   last_login + timestamp +    │
                         │           │   │   email,                      │
                         │           │   │   clave = SECRET_KEY )        │
                         │           │   │                               │
                         │           │   │ NO se guarda en la base:      │
                         │           │   │ se recalcula al verificar     │
                         │           │   └──────────┬───────────────────┘
                         │           │              ▼
                         │           │   ┌──────────────────────────────┐
                         │           │   │ 6. ENVÍA EL CORREO            │
                         │           │   │                               │
                         │           │   │ http://opso.cl/restablecer/   │
                         │           │   │        <uid>/<token>/         │
                         │           │   │                               │
                         │           │   │ Texto plano + HTML            │
                         │           │   └──────────┬───────────────────┘
                         ▼           ▼              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PANTALLA 2 (siempre la misma, en los TRES casos):                    │
│  "Si la dirección corresponde a una cuenta registrada, recibirás      │
│   un mensaje con las instrucciones."                                  │
│                                                                       │
│  ← ANTI-ENUMERACIÓN: el atacante no puede distinguir los casos        │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  7. El usuario abre su correo y hace clic en el enlace                │
│     → GET /restablecer/Mw/dcarwr-630193a6.../                         │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  8. DJANGO VALIDA EL TOKEN                                            │
│                                                                       │
│     a) Decodifica el uid (base64) → id del usuario → SELECT           │
│     b) Recalcula la firma con los datos actuales de ese usuario        │
│     c) La compara en tiempo constante con la firma recibida            │
│     d) Verifica que no hayan pasado más de 60 minutos                  │
└──────┬──────────────────────────────────────────────┬────────────────┘
       │ inválido / expirado / ya usado               │ válido
       ▼                                              ▼
┌──────────────────────────┐   ┌────────────────────────────────────────┐
│ PANTALLA 3-B:            │   │ Guarda el token en la SESIÓN y redirige │
│ "El enlace no es válido" │   │ a /restablecer/Mw/set-password/         │
│  + botón para pedir otro │   │                                         │
└──────────────────────────┘   │ ← el token desaparece de la URL para    │
                               │   que no se filtre por el Referer       │
                               └──────────────────┬─────────────────────┘
                                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  9. PANTALLA 3-A: ingresa la contraseña nueva (dos veces)             │
│     → POST /restablecer/Mw/set-password/  (con token CSRF)            │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
                  ┌─────────────────────────────┐
                  │ ¿Coinciden las dos?          │
                  │ ¿Cumple las reglas?          │
                  │ (10 caracteres, no común...) │
                  └──────┬───────────────┬──────┘
                      NO │               │ SÍ
                         ▼               ▼
              Vuelve al formulario   ┌──────────────────────────────────┐
              con los errores        │ 10. ACTUALIZA PostgreSQL          │
                                     │                                   │
                                     │ set_password() → hash Argon2id    │
                                     │                                   │
                                     │ UPDATE usuarios_usuario           │
                                     │ SET password = 'argon2$...'       │
                                     │ WHERE id = 3;                     │
                                     │                                   │
                                     │ EFECTOS AUTOMÁTICOS:              │
                                     │  · el token queda inservible      │
                                     │  · caen las sesiones abiertas     │
                                     └──────────────┬───────────────────┘
                                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  11. Se envía el CORREO DE AVISO al titular                           │
│      "Tu contraseña fue actualizada el 26/07/2026 a las 00:26"        │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  12. PANTALLA 4: "¡Listo! Tu contraseña fue actualizada"              │
│      + botón "Iniciar sesión"                                         │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  13. El usuario inicia sesión con su contraseña nueva                 │
│      → y el flujo de la HU-01 lo lleva al panel de su rol            │
└──────────────────────────────────────────────────────────────────────┘
```

### Versión resumida (para la diapositiva)

```
Olvidó su contraseña
        ↓
Presiona "¿Olvidaste tu contraseña?"
        ↓
Ingresa su correo electrónico
        ↓
El sistema verifica que exista (SELECT en PostgreSQL)
        ↓
Genera un token temporal (HMAC-SHA256, sin guardarlo en la BD)
        ↓
Envía un correo con un enlace seguro
        ↓
El usuario abre el enlace
        ↓
Django valida el token (firma + vigencia + usuario)
        ↓
El usuario ingresa una nueva contraseña
        ↓
Se actualiza la contraseña en PostgreSQL (hash Argon2id)
        ↓
Puede volver a iniciar sesión
```

> **Defensa — ¿por qué la pantalla 2 es siempre la misma?**
> Porque si dijera "te enviamos un correo" solo cuando la cuenta existe, cualquiera podría probar direcciones y armar una lista de usuarios registrados de OPSO. Eso se llama enumeración de usuarios y es el primer paso de un ataque dirigido. Al responder igual en todos los casos, el formulario no entrega ninguna información.

---

## 3. Configuración del correo

Todo en [`config/settings.py`](../config/settings.py), sección 10, con los valores leídos desde `.env`.

### Los parámetros, uno por uno

| Parámetro | Valor en OPSO | Para qué sirve |
|---|---|---|
| **`EMAIL_BACKEND`** | consola (desarrollo) / SMTP (producción) | Elige el **motor** que entrega el correo. Es el parámetro más importante: cambiándolo, el mismo código envía a la terminal, por SMTP real o a memoria (pruebas). |
| **`EMAIL_HOST`** | `smtp.gmail.com` | Dirección del servidor SMTP que entrega el mensaje. Es la "oficina de correos" a la que OPSO le pasa la carta. |
| **`EMAIL_PORT`** | `587` | Puerto del servidor. `587` = STARTTLS, `465` = SSL directo, `25` = sin cifrado (nunca usar en internet). |
| **`EMAIL_USE_TLS`** | `True` | Cifra la conexión con el servidor SMTP. **Indispensable**: sin esto, la contraseña de la cuenta de correo y el contenido del mensaje viajarían en texto plano. |
| **`EMAIL_USE_SSL`** | `False` | Alternativa a TLS para el puerto 465. Son **mutuamente excluyentes**: activar ambos produce un error de conexión. |
| **`EMAIL_HOST_USER`** | (en `.env`) | Cuenta con la que OPSO se autentica ante el servidor SMTP. |
| **`EMAIL_HOST_PASSWORD`** | (en `.env`) | Contraseña de esa cuenta. En Gmail debe ser una **contraseña de aplicación** de 16 caracteres. |
| **`DEFAULT_FROM_EMAIL`** | `OPSO - Operativo Social <no-responder@opso.cl>` | Remitente que ve el usuario en su bandeja. Se usa cuando el código no indica otro. |
| `SERVER_EMAIL` | igual al anterior | Remitente de los mensajes automáticos de error del servidor. |
| `EMAIL_TIMEOUT` | `10` | Segundos antes de abandonar la conexión. Sin esto, un servidor de correo caído dejaría la petición HTTP colgada. |
| `EMAIL_SUBJECT_PREFIX` | `[OPSO] ` | **Cuidado:** Django solo lo aplica a `mail_admins()`, **no** a los correos normales. El asunto del correo de recuperación se define en su propia plantilla. |

### Los tres backends y cuándo se usa cada uno

```python
# DESARROLLO — imprime el correo completo en la terminal de runserver.
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# PRODUCCIÓN — lo envía de verdad por SMTP.
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend

# PRUEBAS — Django lo activa SOLO durante los tests, sin configurarlo:
#           guarda los mensajes en la lista mail.outbox.
django.core.mail.backends.locmem.EmailBackend
```

**Decisión: en desarrollo se usa el backend de consola.** Tres razones concretas:

1. **No requiere cuenta de correo, ni internet, ni configuración.** El proyecto funciona recién clonado.
2. **El enlace aparece listo para copiar** en la terminal, lo que hace la demostración de la defensa mucho más directa y visible que abrir Gmail.
3. **No hay riesgo de enviar correos reales por accidente** durante las pruebas.

### Variables de entorno: `.env`

```bash
# --- Desarrollo (por defecto, no requiere nada más) ---
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# --- Producción: descomentar y completar ---
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=OPSO - Operativo Social <no-responder@opso.cl>
```

**¿Por qué en `.env` y no en `settings.py`?** Porque `settings.py` se sube al repositorio y `.env` no (está en `.gitignore`). Si la contraseña del correo estuviera en el código, quedaría en el historial de Git **para siempre**, visible para cualquiera con acceso al repositorio, y borrarla después no serviría: seguiría en los commits anteriores. Es el principio de **separar configuración de código** (metodología *12-factor app*).

### Gmail: la trampa más común

Google **bloquea el acceso directo de aplicaciones desde mayo de 2022**. Usar la contraseña personal de Gmail produce el error `535 Username and Password not accepted`. Hay que:

1. Activar la verificación en dos pasos de la cuenta.
2. Ir a https://myaccount.google.com/apppasswords
3. Generar una **contraseña de aplicación** de 16 caracteres.
4. Poner esa contraseña (sin espacios) en `EMAIL_HOST_PASSWORD`.

### Alternativa recomendada para pruebas: Mailtrap

Para probar el envío real sin arriesgar correos a personas reales, [Mailtrap](https://mailtrap.io) ofrece un servidor SMTP de prueba gratuito que **captura** todos los mensajes en una bandeja web:

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=sandbox.smtp.mailtrap.io
EMAIL_PORT=2525
EMAIL_HOST_USER=<usuario que entrega Mailtrap>
EMAIL_HOST_PASSWORD=<clave que entrega Mailtrap>
```

Es útil para verificar cómo se ve el correo HTML en distintos clientes.

> **Defensa — ¿por qué usar variables de entorno?**
> Porque las credenciales no deben estar en el código. `settings.py` se versiona en Git; `.env` no. Así el repositorio se puede publicar o entregar al profesor sin filtrar la contraseña del correo ni la de la base de datos. Además permite que el mismo código funcione en desarrollo (correo por consola) y en producción (SMTP real) cambiando solo un archivo de configuración, sin tocar una línea de Python.

---

## 4. Configuración de PostgreSQL

### ¿Es necesario modificar la base de datos?

**No. Esta funcionalidad no requiere ninguna tabla nueva ni ninguna columna nueva.**

Es un resultado que sorprende, y explicarlo bien es uno de los puntos más fuertes de esta historia de usuario.

### ¿Qué tablas utiliza Django?

| Tabla | Rol en la recuperación | ¿Se modifica? |
|---|---|---|
| **`usuarios_usuario`** | Se **lee** para encontrar al usuario por su correo y para construir la firma del token. Se **escribe** la columna `password` (el hash nuevo) al final del proceso. | Solo se actualiza una fila existente. No cambia la estructura. |
| **`django_session`** | Guarda temporalmente el token cuando Django lo saca de la URL, y se usa para invalidar las sesiones abiertas al cambiar la contraseña. | Se usan filas, no se altera el esquema. |

Y eso es todo.

### ¿Qué información relacionada con la recuperación se almacena?

**Ninguna, de forma permanente.** Este es el punto central:

```
❌ NO existe una tabla "tokens_recuperacion"
❌ NO se guarda el token en ninguna parte
❌ NO se guarda la fecha de la solicitud en la base de datos
❌ NO se guarda el enlace enviado
```

Lo único que queda registrado es:

| Dato | Dónde | Permanencia |
|---|---|---|
| El hash nuevo de la contraseña | `usuarios_usuario.password` | Permanente (reemplaza el anterior) |
| El token, mientras dura el proceso | `django_session.session_data` | Temporal (se borra al terminar) |
| El contador de solicitudes | **Caché** (memoria / Redis) | 15 minutos |
| El registro del evento | Archivo de log del servidor | Según la política de logs |

### ¿Por qué el token no se guarda? El diseño *stateless*

Aquí está la elegancia del mecanismo. El token **no es un dato guardado, es un cálculo verificable**.

Cuando Django genera el token, calcula:

```python
firma = HMAC_SHA256(
    mensaje = f"{user.pk}{user.password}{user.last_login}{timestamp}{user.email}",
    clave   = settings.SECRET_KEY
)
```

Cuando después tiene que verificarlo, **vuelve a hacer exactamente el mismo cálculo** con los datos actuales del usuario y compara el resultado con la firma que llegó en el enlace. Si coinciden, el token es auténtico.

Comparación con el enfoque tradicional (guardar el token en una tabla):

| Aspecto | Con tabla de tokens | Sin tabla (Django) |
|---|---|---|
| Escrituras en la BD por solicitud | 1 `INSERT` | **0** |
| Consultas al validar | 1 `SELECT` extra | 0 (solo el `SELECT` del usuario) |
| Limpieza de tokens vencidos | Requiere una tarea periódica | **Innecesaria**: no hay nada que limpiar |
| Riesgo si se filtra la BD | Los tokens vigentes quedan expuestos | **No hay tokens que filtrar** |
| Invalidación al usarse | Hay que marcarla o borrar la fila | **Automática** (ver sección 9) |
| Complejidad del código | Modelo + migración + limpieza | Ninguna |

**El único requisito** es que la `SECRET_KEY` no cambie: si se cambia, todos los enlaces pendientes se invalidan de golpe. Django prevé incluso eso con `SECRET_KEY_FALLBACKS`, que permite rotar la clave manteniendo válidos los enlaces emitidos con la anterior.

> **Defensa — ¿por qué PostgreSQL sigue siendo adecuado aquí?**
> Porque aunque esta funcionalidad no cree tablas, depende de dos garantías que PostgreSQL entrega y que son críticas: (1) que el `UPDATE` de la contraseña sea **atómico y durable** —si el servidor se cae en medio de la operación, la contraseña queda íntegra en su valor anterior o en el nuevo, nunca a medias—; y (2) que la restricción `UNIQUE` sobre el correo garantice que la búsqueda por correo devuelva **exactamente un usuario**, lo que es un requisito de correctitud del proceso: si dos cuentas compartieran el mismo correo, no habría forma de saber a quién restablecer.

---

## 5. URLs

En [`usuarios/urls.py`](../usuarios/urls.py). Cuatro rutas, una por paso:

```python
app_name = "usuarios"

urlpatterns = [
    # ... login, logout ...

    path("recuperar-contrasena/",
         views.RecuperarContrasenaView.as_view(),        name="password_reset"),

    path("recuperar-contrasena/enviado/",
         views.RecuperarContrasenaEnviadoView.as_view(), name="password_reset_done"),

    path("restablecer/<uidb64>/<token>/",
         views.RestablecerContrasenaView.as_view(),      name="password_reset_confirm"),

    path("restablecer/completado/",
         views.RestablecerContrasenaCompletadoView.as_view(), name="password_reset_complete"),
]
```

### Qué hace cada URL

| URL | Nombre | Método | Qué hace |
|---|---|---|---|
| `/recuperar-contrasena/` | `password_reset` | GET, POST | **GET:** muestra el formulario del correo. **POST:** busca la cuenta, genera el token y envía el correo. Luego redirige al paso 2. |
| `/recuperar-contrasena/enviado/` | `password_reset_done` | GET | Confirmación neutra. Se llega aquí **siempre**, exista o no la cuenta. |
| `/restablecer/<uidb64>/<token>/` | `password_reset_confirm` | GET, POST | El enlace del correo. Valida el token; si es correcto, muestra el formulario de la contraseña nueva y la guarda. |
| `/restablecer/completado/` | `password_reset_complete` | GET | Aviso de éxito con el enlace para iniciar sesión. |

### Los dos parámetros del enlace

```
/restablecer/Mw/dcarwr-630193a6b8a32afa7c63906dc54e7d29/
             └┬┘ └──────────────────┬────────────────────┘
           uidb64                 token
```

**`uidb64`** — el id del usuario codificado en base64 seguro para URL. `Mw` es `"3"` codificado.

Es importante ser preciso en la defensa: **base64 NO es cifrado**. Es solo una forma de representar datos con caracteres válidos en una URL, y cualquiera puede decodificarlo. ¿Por qué no importa? Porque el id del usuario **no es un secreto**: la seguridad la aporta el token, no el uid. Saber que existe el usuario 3 no permite hacer nada.

**`token`** — la firma temporal. Aquí sí está la seguridad.

### Detalle relevante: la misma ruta atiende dos casos

La ruta del paso 3 responde a dos direcciones distintas:

```
/restablecer/Mw/dcarwr-630193a6.../      ← primera visita (token en la URL)
/restablecer/Mw/set-password/            ← después de que Django lo movió a la sesión
```

Django detecta que el segmento vale `set-password` (el valor de `reset_url_token`) y en ese caso busca el token **en la sesión** en lugar de en la URL. El motivo se explica en la sección 10.

### Por qué se conservaron los nombres de Django

Los nombres (`password_reset`, `password_reset_done`, …) son exactamente los que usa Django internamente, aunque las direcciones estén en español. Motivo: cualquier código nativo o de terceros que espere esos nombres seguirá funcionando. Las **direcciones** están en español porque las ve el usuario; los **nombres** son internos.

### Un ajuste obligatorio

Las vistas de Django tienen escrito `success_url = reverse_lazy("password_reset_done")`, **sin espacio de nombres**. Como las URLs de OPSO viven bajo `app_name = "usuarios"`, hay que redefinirlo en cada subclase:

```python
success_url = reverse_lazy("usuarios:password_reset_done")
```

Sin esto, Django lanzaría `NoReverseMatch` al enviar el formulario. Es el error más común al usar estas vistas con namespaces.

---

## 6. Templates

```
templates/usuarios/
├── base_publico.html              ← estructura común de las 4 pantallas
├── password_reset.html            ← PASO 1
├── password_reset_done.html       ← PASO 2
├── password_reset_confirm.html    ← PASO 3 (dos caras)
├── password_reset_complete.html   ← PASO 4
└── correo/
    ├── recuperacion_asunto.txt    ← asunto del correo
    ├── recuperacion.txt           ← cuerpo en texto plano
    ├── recuperacion.html          ← cuerpo en HTML
    └── aviso_cambio.txt           ← aviso posterior al cambio
```

### `base_publico.html` — por qué existe

Las cuatro pantallas comparten estructura: encabezado con el logo, tarjeta blanca centrada, indicador de progreso y pie. Escribir eso cuatro veces sería repetir código y arriesgar que las pantallas se vean distintas entre sí.

**¿Por qué no reutilizar `base.html` (el de los paneles)?** Porque `base.html` incluye la barra de navegación con el nombre del usuario, su rol y el botón de salir. Quien está recuperando su contraseña **no tiene sesión**: mostrarle ese menú sería incoherente y además fallaría al intentar leer datos de un usuario anónimo.

### Cuándo se muestra cada pantalla

| Plantilla | Se muestra cuando… | Qué contiene |
|---|---|---|
| **`password_reset.html`** | La persona hace clic en "¿Olvidaste tu contraseña?" o abre `/recuperar-contrasena/`. | Campo de correo con icono, aviso de que el enlace dura 60 minutos y sirve una vez. |
| **`password_reset_done.html`** | Inmediatamente después de enviar el formulario, **en los tres casos posibles** (cuenta existe / no existe / límite superado). | Texto en **condicional** ("*Si* la dirección que ingresaste…"), lista de qué hacer si el correo no llega, botón para reintentar. |
| **`password_reset_confirm.html`** | Al abrir el enlace del correo. | **Dos caras** (ver abajo). |
| **`password_reset_complete.html`** | Tras guardar la contraseña nueva. | Confirmación, botón "Iniciar sesión", advertencia de qué hacer si no fue la persona quien cambió la clave. |

### Las dos caras de `password_reset_confirm.html`

Esta plantilla es la más interesante. `PasswordResetConfirmView` entrega la variable `validlink`:

```django
{% if validlink %}
    → formulario con los dos campos de contraseña nueva
{% else %}
    → aviso "El enlace no es válido" + botón para pedir otro
{% endif %}
```

Detalle de seguridad: **el mensaje de error no distingue entre "expirado", "ya usado" y "manipulado"**. Es deliberado en Django: cualquier detalle adicional le daría a un atacante información sobre el estado de la cuenta. La plantilla sí enumera las **causas posibles**, lo que ayuda al usuario legítimo sin revelar cuál se aplicó.

Otro detalle: los requisitos de la contraseña se muestran con `{{ campo.help_text|safe }}`, y ese texto lo **genera Django automáticamente** desde `AUTH_PASSWORD_VALIDATORS`. Si mañana la regla cambia de 10 a 12 caracteres en `settings.py`, el texto de la pantalla se actualiza solo. No hay nada duplicado.

### Diseño

- **Bootstrap 5.3 servido localmente** (`static/vendor/bootstrap/`): la aplicación funciona sin internet, importante en terreno rural y en la sala de la defensa.
- **Identidad OPSO**: los colores provienen de los mismos tokens de diseño del prototipo (`static/css/opso.css`).
- **Responsivo**: una sola columna centrada que se adapta con las clases `col-12 col-sm-10 col-md-8 col-lg-6`.
- **Indicador de progreso**: cuatro barras que muestran en qué paso va la persona.
- **Accesibilidad**: `<label for>` en cada campo, `aria-live="assertive"` en los errores, `aria-pressed` en el botón de mostrar contraseña, y contraste AA.

### Un error que se encontró y corrigió durante el desarrollo

Vale la pena mencionarlo porque es un aprendizaje real y podría preguntarlo el profesor:

En Django, la etiqueta corta de comentario `{# … #}` **solo funciona en una línea**. Su expresión regular interna (`{#.*?#}`) no incluye la bandera `DOTALL`, así que un comentario escrito en varias líneas **no se reconoce como comentario** y se renderiza como texto visible en la página. Para comentarios de varias líneas hay que usar:

```django
{% comment %}
   Comentario que ocupa
   varias líneas.
{% endcomment %}
```

Se detectó porque una plantilla del correo lanzó `TemplateSyntaxError: Unclosed tag 'autoescape'` — el comentario multilínea no se ignoró y Django intentó interpretar las etiquetas que había dentro. Se corrigieron las 26 apariciones del proyecto y se agregó una verificación que compila las 16 plantillas.

---

## 7. Formularios

### ¿Crear formularios propios o usar los de Django?

**Decisión: heredar de los de Django y personalizar solo la presentación.**

Django aporta dos formularios ya resueltos:

| Formulario de Django | Qué resuelve |
|---|---|
| **`PasswordResetForm`** | Busca los usuarios que pueden recuperar (`get_users`), genera el token, arma el contexto del correo y lo envía en dos formatos. |
| **`SetPasswordForm`** | Compara las dos contraseñas, aplica los validadores de robustez y guarda el hash con `set_password()`. |

### Qué se personalizó y por qué

```python
class RecuperarContrasenaForm(PasswordResetForm):
    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={
            "class": "form-control form-control-lg",
            "autocomplete": "email",
            "autofocus": True,
            "inputmode": "email",          # teclado de correo en el móvil
        }),
    )

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()
```

| Personalización | Justificación |
|---|---|
| Etiquetas y textos en español | El de Django dice "Email"; los usuarios de OPSO son personal de terreno en Chile. |
| Clases de Bootstrap | Sin ellas, el campo se vería sin estilo y rompería la identidad visual. |
| `autocomplete="email"` | Permite que el navegador y el gestor de contraseñas reconozcan el campo. |
| `inputmode="email"` | En un teléfono muestra el teclado con `@`, útil para censistas en terreno. |
| `clean_email()` normaliza a minúsculas | Para que `Censista@OPSO.CL` encuentre la cuenta `censista@opso.cl`. |

**Nótese lo que `clean_email()` NO hace:** no valida si el correo existe ni lanza un error cuando no existe. Sería el error clásico que abre la puerta a la enumeración de usuarios. La búsqueda la hace `get_users()` y, si no encuentra nada, simplemente no envía correo.

```python
class EstablecerContrasenaForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            campo.label = self.ETIQUETAS.get(nombre, campo.label)
            campo.widget.attrs.update({
                "class": "form-control form-control-lg",
                "autocomplete": "new-password",
            })
```

Aquí hay una decisión de técnica que conviene poder explicar: los campos se modifican **en `__init__`** en lugar de volver a declararlos. Motivo: `SetPasswordForm` construye sus campos con `help_text` generado desde `AUTH_PASSWORD_VALIDATORS`. Si se redeclararan, ese texto se perdería y habría que escribir los requisitos a mano, con el riesgo de que quedaran desactualizados respecto a la configuración real.

`autocomplete="new-password"` le indica al gestor de contraseñas del navegador que **ofrezca generar una contraseña fuerte** y guardarla, en vez de autocompletar la anterior.

### Lo que NO se tocó — y es lo más importante

**No se reescribió nada de la generación ni de la verificación del token.** Eso es criptografía aplicada: HMAC-SHA256, comparación en tiempo constante, codificación de la marca de tiempo. Reimplementarlo sería el error más grave posible en esta funcionalidad, porque un fallo ahí no se nota en las pruebas funcionales —el flujo "funcionaría"— pero dejaría el sistema vulnerable.

> **Defensa — ¿por qué usar las vistas y formularios nativos de Django?**
> Por tres razones. **Seguridad:** el mecanismo de tokens es criptografía revisada por la comunidad durante casi veinte años; una implementación propia introduciría errores en el componente más delicado, y un fallo criptográfico no se detecta probando la aplicación. **Detalles que uno no anticipa:** las vistas de Django ya resuelven cosas que a un desarrollador se le pasan, como mover el token de la URL a la sesión para que no se filtre por el encabezado Referer, o usar comparación en tiempo constante para no filtrar información por el tiempo de respuesta. **Mantenimiento:** al actualizar Django, las mejoras de seguridad llegan sin reescribir código propio.

---

## 8. Envío de correo

### El correo se envía en dos formatos a la vez

```python
class RecuperarContrasenaView(PasswordResetView):
    subject_template_name   = "usuarios/correo/recuperacion_asunto.txt"
    email_template_name     = "usuarios/correo/recuperacion.txt"    # texto plano
    html_email_template_name = "usuarios/correo/recuperacion.html"  # HTML
```

Django construye un mensaje `multipart/alternative` que contiene **las dos versiones**, y cada cliente de correo elige la que puede mostrar.

**¿Por qué molestarse en mantener la versión de texto plano?** Porque muchos clientes corporativos bloquean el HTML por política de seguridad, algunos lectores de pantalla trabajan mejor con texto, y ciertos filtros antispam penalizan los mensajes que solo traen HTML. Con ambas versiones el correo llega y se lee siempre.

### Contenido del correo

El correo incluye los cinco elementos solicitados:

| Elemento | Cómo se implementó |
|---|---|
| **Saludo** | `Hola {{ user.get_short_name\|default:user.email }}:` — usa el nombre de pila; si está vacío, el correo. |
| **Explicación del motivo** | "Recibimos una solicitud para restablecer la contraseña de tu cuenta en OPSO (censista@opso.cl)". Indica **para qué cuenta** es, lo que ayuda a quien administra varias. |
| **Enlace para restablecer** | Botón azul en la versión HTML **y** la dirección completa como texto, para quien copia y pega. |
| **Advertencia de seguridad** | "Si no solicitaste este cambio, puedes ignorar este mensaje: tu contraseña actual seguirá funcionando y nadie podrá modificarla sin abrir el enlace." Más la advertencia de no compartir el enlace y de que OPSO nunca pide contraseñas por correo (**prevención de phishing**). |
| **Despedida profesional** | "Saludos cordiales, Equipo OPSO — Operativo Social", correo de soporte y aviso de que es un mensaje automático. |

### Cómo Django genera automáticamente el enlace seguro

Este es el punto que más conviene dominar. La plantilla escribe:

```django
{{ protocol }}://{{ domain }}{% url 'usuarios:password_reset_confirm' uidb64=uid token=token %}
```

Y produce:

```
http://127.0.0.1:8000/restablecer/Mw/dcarwr-630193a6b8a32afa7c63906dc54e7d29/
```

Las variables las prepara `PasswordResetForm.save()`:

| Variable | Cómo se obtiene |
|---|---|
| `protocol` | `"https" if request.is_secure() else "http"` — se adapta solo al entorno. |
| `domain` | Del sitio actual. **Sin la app `django.contrib.sites` instalada**, Django usa el encabezado `Host` de la petición, que `ALLOWED_HOSTS` ya validó. |
| `uid` | `urlsafe_base64_encode(force_bytes(user.pk))` — el id en base64 apto para URL. |
| `token` | `default_token_generator.make_token(user)` — la firma (ver sección 9). |
| `user`, `email` | El objeto usuario y su correo. |

Y `{% url %}` construye la dirección a partir del **nombre** de la ruta, no de un texto escrito a mano. Ventaja concreta: si mañana la URL cambia de `/restablecer/` a `/nueva-clave/`, los correos siguen generando enlaces correctos sin tocar las plantillas.

**Un ajuste que se hizo:** sin la app `sites`, la variable `site_name` valdría `"127.0.0.1:8000"`, lo que se vería mal en el correo. Se sobrescribe con `extra_email_context`:

```python
extra_email_context = {
    "nombre_sistema": settings.OPSO_NOMBRE_SISTEMA,      # "OPSO"
    "site_name": settings.OPSO_NOMBRE_SISTEMA,
    "correo_soporte": settings.OPSO_CORREO_SOPORTE,
    "minutos_validez": settings.PASSWORD_RESET_TIMEOUT // 60,
}
```

`minutos_validez` se **calcula** desde la configuración: si se cambia `PASSWORD_RESET_TIMEOUT`, el correo y las cuatro pantallas dicen el número correcto automáticamente. Nada queda escrito a mano en dos lugares.

### El asunto debe ser de una sola línea

```django
{{ nombre_sistema }}: instrucciones para restablecer tu contraseña
```

Django ejecuta `"".join(subject.splitlines())`, es decir **elimina todos los saltos de línea**. No es un capricho: un salto de línea dentro de un encabezado de correo permitiría inyectar encabezados adicionales, por ejemplo una copia oculta hacia la casilla de un atacante. Ese ataque se llama **inyección de encabezados** (*header injection*) y Django lo neutraliza justo ahí.

### Detalle sobre `{% autoescape off %}`

En la versión de **texto plano** se desactiva el escapado automático:

```django
{% autoescape off %}Hola {{ user.get_short_name }}: ...{% endautoescape %}
```

Motivo: Django escapa las variables por defecto para prevenir XSS en HTML. En texto plano eso es contraproducente — un apellido como `O'Higgins` se mostraría como `O&#x27;Higgins`. Como no hay HTML que pueda ejecutarse, desactivarlo es correcto.

**En la versión HTML NO se desactiva**, porque ahí sí importa: si el nombre de un usuario contuviera caracteres de HTML, deben escaparse para que no rompan la maqueta ni inyecten contenido.

### Maquetación del correo HTML

Los correos se maquetan con reglas distintas a las de una página web:

1. **Tablas** para la estructura, no flexbox ni grid: Outlook usa el motor de Word y no soporta CSS moderno.
2. **Estilos en línea** (atributo `style`): Gmail elimina las etiquetas `<style>` del `<head>`.
3. **Ancho máximo 600 px**: el estándar que se ve bien en escritorio y en móvil.
4. **Sin JavaScript ni imágenes externas**: los clientes los bloquean y podrían marcar el mensaje como sospechoso.

### El segundo correo: aviso de cambio

Además del enlace, se envía un correo **después** de cambiar la contraseña:

```
Detalle del cambio:
  Cuenta : censista@opso.cl
  Fecha  : 26/07/2026 a las 00:26 h
  Origen : 127.0.0.1
```

**¿Por qué?** Es un control de **detección**, no de prevención. Si un atacante logró acceder al correo de la víctima y restableció la contraseña, la víctima se entera de inmediato y puede avisar. Sin este aviso, el acceso indebido podría pasar inadvertido durante semanas.

Está implementado en `usuarios/seguridad.py` y **nunca hace fallar la operación**: si el envío falla, se registra el error en el log y la petición continúa. Sería absurdo mostrar un error al usuario cuando su contraseña ya se cambió correctamente.

Y por supuesto, **no incluye la contraseña nueva**: el sistema no la conoce.

---

## 9. Token de recuperación

### ¿Qué es un token?

Un texto corto que actúa como **firma temporal e infalsificable**. Autoriza una acción concreta (cambiar la contraseña de un usuario específico) durante un tiempo limitado.

### ¿Cómo se genera?

`PasswordResetTokenGenerator.make_token(user)` produce dos partes unidas por un guion:

```
dcarwr - 630193a6b8a32afa7c63906dc54e7d29
  (1)              (2)
```

**Parte 1 — la marca de tiempo.** Segundos transcurridos desde el 1 de enero de 2001, escritos en base 36 (dígitos + letras) para que ocupen poco.

**Parte 2 — la firma.** Se calcula así:

```python
mensaje = f"{user.pk}{user.password}{user.last_login}{timestamp}{user.email}"

firma = HMAC_SHA256(mensaje, clave=settings.SECRET_KEY).hexdigest()[::2]
```

Vale la pena analizar **por qué entra cada dato en el mensaje**:

| Dato incluido | Para qué sirve |
|---|---|
| `user.pk` | Ata el token a **ese** usuario: el token del supervisor no sirve para el censista. |
| `user.password` (el hash) | **La clave del uso único.** Al cambiar la contraseña, el hash cambia y la firma anterior deja de coincidir. |
| `user.last_login` | Refuerza lo anterior: iniciar sesión también invalida los enlaces pendientes. |
| `timestamp` | Permite verificar la antigüedad. |
| `user.email` | Si se le cambia el correo a la cuenta, los enlaces enviados al anterior mueren. |
| `SECRET_KEY` (como clave) | Hace la firma **infalsificable** sin acceso al servidor. |

El `[::2]` toma un carácter de cada dos del resultado hexadecimal, para acortar la URL. Quedan 32 caracteres: 128 bits, más que suficientes para que adivinar sea imposible.

**Un punto importante para la defensa:** el token es un HMAC, no un cifrado. No se puede "descifrar" para obtener la contraseña. Y como el hash de la contraseña entra en el mensaje pero el resultado es irreversible, tampoco se puede deducir nada de la contraseña a partir del token.

### ¿Cuánto tiempo dura?

```python
PASSWORD_RESET_TIMEOUT = 3600   # 1 hora (el valor por defecto de Django son 3 días)
```

**Justificación de reducirlo a una hora:** cuanto menos vive el enlace, menor es la ventana en que un correo filtrado, un computador compartido o una casilla comprometida permiten secuestrar la cuenta. Una hora es tiempo suficiente para que una persona lea su correo y reaccione.

Es un equilibrio explícito entre seguridad y usabilidad: 5 minutos sería más seguro pero frustrante para un censista en terreno con señal intermitente; 3 días sería más cómodo pero deja una ventana de riesgo innecesariamente amplia.

### ¿Por qué no puede reutilizarse?

Esta es la parte más elegante del diseño, y la pregunta favorita de los profesores.

**No hay ninguna marca de "usado" en ninguna tabla.** El uso único es consecuencia automática de que **el hash de la contraseña forma parte del mensaje firmado**:

```
ANTES del cambio:
  password = "argon2$argon2id$v=19$...AAA"
  firma    = HMAC(pk + "argon2$...AAA" + ... , SECRET_KEY) = 630193a6...

Se cambia la contraseña → set_password() genera un hash NUEVO
  (distinto incluso si se elige la misma contraseña, porque la sal es aleatoria)

DESPUÉS del cambio:
  password = "argon2$argon2id$v=19$...BBB"     ← ¡cambió!
  firma    = HMAC(pk + "argon2$...BBB" + ... , SECRET_KEY) = 9f2c41e8...

El enlace viejo trae 630193a6..., Django recalcula 9f2c41e8...
  → NO coinciden → token rechazado
```

El token **se autoinvalida** al cumplir su función. No hay que borrar nada, ni marcar nada, ni programar una tarea de limpieza.

Y hay un detalle fino digno de mención: funciona **incluso si la persona elige la misma contraseña de antes**, porque `set_password()` genera una sal aleatoria nueva y por lo tanto un hash distinto.

*Verificado por:* `test_el_token_no_se_puede_reutilizar`.

### ¿Cómo verifica Django su validez?

`check_token(user, token)` ejecuta cuatro comprobaciones:

```python
# 1. ¿Tiene el formato "timestamp-firma"?
ts_b36, _ = token.split("-")
ts = base36_to_int(ts_b36)

# 2. ¿La firma es auténtica? Se RECALCULA con los datos actuales del usuario.
if constant_time_compare(self._make_token_with_timestamp(user, ts, secret), token):
    ...

# 3. ¿Sigue vigente?
if (self._num_seconds(self._now()) - ts) > settings.PASSWORD_RESET_TIMEOUT:
    return False

# 4. (En la vista) ¿el uid corresponde a un usuario existente?
```

**`constant_time_compare` merece explicación**, porque es el tipo de detalle que distingue una implementación correcta. Una comparación normal de textos (`a == b`) termina en cuanto encuentra el primer carácter distinto. Eso significa que comparar `"aXXX"` con `"bYYY"` es **más rápido** que comparar `"aaaX"` con `"aaaY"`. Midiendo esos microsegundos, un atacante podría ir adivinando la firma carácter por carácter: es un **ataque de temporización**. `constant_time_compare` siempre tarda lo mismo, sin importar dónde esté la diferencia.

### ¿Qué sucede si expira?

La vista muestra la cara "El enlace no es válido" de `password_reset_confirm.html`, con:

- las cuatro causas posibles enumeradas (ya usado / caducado / incompleto / contraseña ya cambiada),
- un botón para solicitar un enlace nuevo.

**Sin mensajes distintos por causa.** Django no distingue entre "expirado" y "ya usado", y es deliberado: cualquier detalle adicional le daría a un atacante información sobre el estado de la cuenta.

La contraseña, por supuesto, **no cambia**: sigue siendo la anterior y la persona puede pedir otro enlace cuantas veces quiera.

*Verificado por:* `test_token_expirado_es_rechazado`, `test_el_token_sigue_valido_dentro_del_plazo`, `test_token_manipulado_es_rechazado`, `test_token_de_otro_usuario_es_rechazado`.

> **Defensa — ¿por qué utilizar tokens?**
> Porque hay que autorizar una acción muy sensible (cambiar una contraseña) a alguien que **no puede autenticarse**. El token resuelve exactamente eso: es un permiso acotado —para un usuario, para una acción, por un tiempo— que el servidor puede verificar sin haber guardado nada. La alternativa sería enviar un código por correo y guardarlo en una tabla, lo que implicaría escrituras en la base de datos, una tarea de limpieza de códigos vencidos y el riesgo de que esos códigos se filtren si la base se ve comprometida. Con el token firmado, no hay nada que filtrar.

---

## 10. Seguridad

### ✔ Tokens temporales

**Implementación:** `PASSWORD_RESET_TIMEOUT = 3600` (1 hora). La marca de tiempo va dentro del token y `check_token()` verifica la antigüedad en cada validación.

**Por qué mejora la seguridad:** limita la **ventana de exposición**. Un correo queda archivado indefinidamente en la casilla, en respaldos y en dispositivos sincronizados; el enlace, en cambio, se convierte en basura inofensiva después de una hora. Si alguien accede a ese correo un mes después, no puede hacer nada con él.

### ✔ Enlaces únicos

**Implementación:** cada token incluye `user.pk`, `user.email` y una marca de tiempo, todo firmado con la `SECRET_KEY`. Dos solicitudes generan tokens distintos, y el token de un usuario no sirve para otro.

**Por qué mejora la seguridad:** impide la **reutilización cruzada**. Un atacante que obtenga un enlace válido de su propia cuenta no puede modificarlo para apuntar a otra: cambiar el `uid` invalida la firma, porque el `pk` es parte del mensaje firmado.

*Verificado por:* `test_token_de_otro_usuario_es_rechazado`.

### ✔ Contraseñas cifradas mediante hash

**Implementación:** `SetPasswordForm.save()` llama a `user.set_password()`, que aplica Argon2id con sal aleatoria (ver HU-01, sección 8.2). Se aplican además los cuatro validadores de robustez: mínimo 10 caracteres, no parecida a los datos del usuario, no estar entre las 20.000 más comunes, no ser puramente numérica.

**Por qué mejora la seguridad:** garantiza que **la contraseña nueva reciba el mismo tratamiento que la original**. Sería absurdo tener un login robusto y una recuperación que guardara la clave en texto plano. Aquí se reutiliza exactamente el mismo mecanismo, así que no hay una "puerta trasera" con estándares más bajos.

*Verificado por:* `test_la_contrasena_nueva_se_guarda_hasheada`, `test_se_aplican_los_validadores_de_robustez`.

### ✔ Protección CSRF

**Implementación:** `{% csrf_token %}` en los dos formularios (solicitud y cambio), más `CsrfViewMiddleware`. Además, `PasswordResetView` está decorada con `@csrf_protect` explícitamente en Django.

**Por qué mejora la seguridad:** sin ella, un sitio malicioso podría publicar un formulario oculto que dispare miles de solicitudes de recuperación (usando OPSO como máquina de spam) o, más grave, que envíe la contraseña nueva desde el navegador de la víctima si esta tuviera un enlace válido abierto.

*Verificado por:* `test_post_sin_token_csrf_es_rechazado` → 403.

### ✔ Validación del usuario

**Implementación:** `PasswordResetForm.get_users()` filtra con tres condiciones:

```python
active_users = UserModel._default_manager.filter(email__iexact=email, is_active=True)
return (u for u in active_users
        if u.has_usable_password() and _unicode_ci_compare(email, u.email))
```

| Condición | Qué impide |
|---|---|
| `is_active=True` | Que una cuenta desactivada (por ejemplo, un censista que dejó el operativo) recupere su acceso. |
| `has_usable_password()` | Que una cuenta creada sin contraseña utilizable —pensada para autenticarse por otro medio— se apropie por esta vía. |
| `_unicode_ci_compare` | Ataques por **homoglifos Unicode**: dos cadenas visualmente idénticas pero con distinta codificación. |

**Por qué mejora la seguridad:** la recuperación es una vía de acceso al sistema y debe respetar **las mismas reglas** que el inicio de sesión. Si una cuenta desactivada pudiera recuperar su contraseña, la desactivación no serviría para nada.

*Verificado por:* `test_cuenta_desactivada_no_recibe_correo`.

### ✔ Expiración del enlace

Cubierto arriba en "Tokens temporales". Se agrega un detalle: la expiración se evalúa **en el momento de la verificación**, comparando el reloj del servidor con la marca de tiempo del token. No depende de una tarea programada ni de ningún proceso en segundo plano, así que no puede fallar por un servicio caído.

### ✔ Prevención de la reutilización del token

**Implementación:** el hash de la contraseña forma parte del mensaje firmado (sección 9). Al cambiar la contraseña, el hash cambia y la firma anterior deja de coincidir.

**Por qué mejora la seguridad:** es **automático e imposible de olvidar**. En una implementación con tabla de tokens, el uso único depende de que el programador recuerde marcar la fila como usada — y de que esa escritura no falle. Aquí es una propiedad matemática del mecanismo, no un paso que se pueda omitir.

Como refuerzo, `PasswordResetConfirmView.form_valid()` también borra el token de la sesión (`del self.request.session[INTERNAL_RESET_SESSION_TOKEN]`).

*Verificado por:* `test_el_token_no_se_puede_reutilizar`.

### ✔ Prevención de enumeración de usuarios

Es el requisito con más implicancias, porque afecta el diseño de toda la funcionalidad. Se aplican **cinco** medidas coordinadas:

| Medida | Implementación |
|---|---|
| **1. Respuesta idéntica** | Los tres casos (existe / no existe / límite superado) redirigen a la misma pantalla con el mismo código HTTP. |
| **2. Texto en condicional** | "*Si* la dirección que ingresaste corresponde a una cuenta registrada…" — nunca "te enviamos un correo". |
| **3. Sin errores de validación por inexistencia** | `clean_email()` no verifica si la cuenta existe. |
| **4. El límite no se anuncia** | Al superar el límite, el usuario ve la misma pantalla; el evento queda solo en el log del servidor. |
| **5. Fallos de envío silenciosos** | `PasswordResetForm.send_mail()` de Django captura las excepciones y las registra en el log, sin mostrar error. |

**Por qué mejora la seguridad:** sin esto, el formulario de recuperación sería una **herramienta gratuita de reconocimiento**. Un atacante probaría una lista de correos institucionales y obtendría la nómina de quién trabaja en el operativo — el primer paso para un ataque dirigido o de *phishing*. Al no revelar nada, el formulario no aporta información al atacante.

*Verificado por:* `test_la_respuesta_es_identica_exista_o_no_la_cuenta`, `test_correo_inexistente_no_genera_ningun_mensaje`, `test_la_pantalla_de_confirmacion_no_afirma_que_se_envio_el_correo`.

### Medidas adicionales que se incorporaron

#### El token sale de la URL

Al abrir el enlace, Django **no muestra el formulario de inmediato**. Guarda el token en la sesión y redirige:

```
/restablecer/Mw/dcarwr-630193a6.../   →  302  →  /restablecer/Mw/set-password/
```

**Por qué:** si el token quedara en la barra de direcciones, podría filtrarse por el encabezado `Referer` (que el navegador envía al cargar recursos externos), quedar en el historial compartido del navegador, o aparecer en los registros de un proxy corporativo.

*Verificado por:* `test_el_enlace_valido_redirige_ocultando_el_token`.

#### Control de frecuencia

Tres solicitudes por correo y diez por IP cada 15 minutos, contadas en la **caché** (no en PostgreSQL, porque es un dato efímero).

**Los dos límites son necesarios:** el límite por correo solo no detiene a quien prueba mil correos distintos; el límite por IP solo no protege a una persona atacada desde varias redes.

**Compromiso que conviene reconocer en la defensa:** un atacante podría mantener bloqueada la recuperación de una cuenta concreta enviando solicitudes repetidas (una denegación de servicio dirigida). Se aceptó ese riesgo porque el daño es bajo y temporal (15 minutos, y el administrador siempre puede restablecer la contraseña desde `/admin/`), mientras que el beneficio —impedir el bombardeo de correo a una casilla ajena— es concreto.

**Limitación técnica que hay que declarar:** `LocMemCache` vive en la memoria de **un** proceso. En producción con varios trabajadores de Gunicorn, cada uno llevaría su propia cuenta, así que el límite efectivo se multiplicaría. Por eso `.env` documenta el cambio a Redis, que comparte el contador entre procesos.

*Verificado por:* `test_se_descartan_las_solicitudes_que_exceden_el_limite`, `test_el_limite_es_por_correo_y_no_afecta_a_otras_cuentas`.

#### Cierre de las sesiones abiertas

Al cambiar la contraseña, **todas las sesiones activas de esa cuenta dejan de funcionar automáticamente**, en cualquier dispositivo.

**Cómo funciona:** cada sesión guarda un valor derivado de la contraseña (`_auth_user_hash`). En cada petición, `AuthenticationMiddleware` lo compara con el que corresponde al hash actual. Al cambiar la contraseña, dejan de coincidir y la sesión se descarta.

**Por qué es crucial:** si un atacante ya estaba conectado a la cuenta, restablecer la contraseña lo **expulsa**. Sin este comportamiento, la víctima cambiaría su clave y el atacante seguiría dentro con su sesión activa — y la recuperación no habría servido de nada.

Es un comportamiento nativo de Django que no requiere código, pero **sí requiere saber que existe** para poder afirmarlo en la defensa.

*Verificado por:* `test_cambiar_la_contrasena_cierra_las_sesiones_abiertas`.

#### No se inicia sesión automáticamente

```python
post_reset_login = False
```

Django permite autenticar al usuario justo después del cambio. Se decidió **no** hacerlo: obligar a escribir la contraseña nueva confirma que la persona la recuerda o la guardó, y mantiene un único camino de autenticación, con su bitácora de accesos y su bloqueo por intentos fallidos.

#### Auditoría

Cada solicitud y cada cambio quedan en el log del servidor con correo, IP y resultado:

```
INFO usuarios: Solicitud de recuperación recibida | correo=censista@opso.cl | ip=127.0.0.1
INFO usuarios: Contraseña restablecida | usuario=censista@opso.cl | ip=127.0.0.1
WARNING usuarios: Solicitud de recuperación descartada | correo=... | límite por correo superado
```

Nunca se registra el token ni la contraseña.

### Resumen: ataque → defensa

| Ataque | Cómo lo bloquea OPSO |
|---|---|
| Enumerar usuarios registrados | Respuesta idéntica en todos los casos |
| Falsificar un token | HMAC-SHA256 con `SECRET_KEY` (no se puede sin acceso al servidor) |
| Reutilizar un enlace ya usado | El hash de la contraseña forma parte de la firma |
| Usar un enlace antiguo filtrado | Expiración a los 60 minutos |
| Usar el token de otra cuenta | El `pk` del usuario está en la firma |
| Adivinar la firma por temporización | `constant_time_compare` |
| Bombardear una casilla con correos | Límite de 3 solicitudes / 15 min por correo |
| Disparar solicitudes desde otro sitio | Token CSRF |
| Robar el token del `Referer` | Django lo mueve a la sesión y lo saca de la URL |
| Inyectar encabezados en el correo | El asunto se fuerza a una sola línea |
| Mantener la sesión tras el cambio | Las sesiones abiertas se invalidan solas |
| Recuperar una cuenta desactivada | `get_users()` filtra `is_active=True` |
| Cambiar la contraseña sin ser detectado | Correo de aviso al titular |
| Poner una contraseña débil | Cuatro validadores de robustez |

---

## 11. Archivos del proyecto

### Archivos modificados

| Archivo | Cambio realizado |
|---|---|
| **[`config/settings.py`](../config/settings.py)** | **Sección 10:** los 7 parámetros de correo + `EMAIL_TIMEOUT`, `SERVER_EMAIL`, `OPSO_NOMBRE_SISTEMA`, `OPSO_CORREO_SOPORTE`. **Sección 11:** `PASSWORD_RESET_TIMEOUT = 3600`. **Sección 12:** `CACHES` (control de frecuencia). **Sección 13:** los tres límites de solicitudes. |
| **[`usuarios/urls.py`](../usuarios/urls.py)** | Cuatro rutas nuevas con los nombres `password_reset`, `password_reset_done`, `password_reset_confirm`, `password_reset_complete`. |
| **[`usuarios/views.py`](../usuarios/views.py)** | Cuatro vistas que heredan de las nativas. Se ajusta `success_url` (obligatorio por el namespace), se apuntan las plantillas del correo, se agrega el control de frecuencia, la auditoría y el aviso posterior. |
| **[`usuarios/forms.py`](../usuarios/forms.py)** | `RecuperarContrasenaForm` (hereda de `PasswordResetForm`) y `EstablecerContrasenaForm` (hereda de `SetPasswordForm`): Bootstrap, español y normalización del correo. |
| **[`usuarios/seguridad.py`](../usuarios/seguridad.py)** | Funciones nuevas: `registrar_solicitud_recuperacion()`, `notificar_cambio_contrasena()` y los ayudantes de caché `_clave_cache()` / `_incrementar_contador()`. |
| **[`templates/usuarios/login.html`](../templates/usuarios/login.html)** | El enlace "¿Olvidaste tu contraseña?" pasa de `href="#"` a `{% url 'usuarios:password_reset' %}`. |
| **[`static/css/opso.css`](../static/css/opso.css)** | Estilos de las pantallas públicas: `.pagina-publica`, `.icono-circulo`, `.pasos-recuperacion`, `.logo-publico`. |
| **[`.env` / `.env.example`](../.env.example)** | Bloque de correo, `PASSWORD_RESET_TIMEOUT`, límites de solicitudes y configuración de caché. |
| **[`usuarios/tests.py`](../usuarios/tests.py)** | 33 pruebas nuevas en 6 clases. |
| **Todas las plantillas** | Corrección de los comentarios multilínea: `{# … #}` → `{% comment %} … {% endcomment %}` (26 casos). |

### Archivos nuevos

| Archivo | Qué es |
|---|---|
| `templates/usuarios/base_publico.html` | Estructura común de las cuatro pantallas |
| `templates/usuarios/password_reset.html` | Pantalla 1 |
| `templates/usuarios/password_reset_done.html` | Pantalla 2 |
| `templates/usuarios/password_reset_confirm.html` | Pantalla 3 |
| `templates/usuarios/password_reset_complete.html` | Pantalla 4 |
| `templates/usuarios/correo/recuperacion_asunto.txt` | Asunto del correo |
| `templates/usuarios/correo/recuperacion.txt` | Cuerpo en texto plano |
| `templates/usuarios/correo/recuperacion.html` | Cuerpo en HTML |
| `templates/usuarios/correo/aviso_cambio.txt` | Aviso posterior al cambio |
| `docs/HU-02_recuperacion_contrasena.md` | Este documento |

### Lo que NO se modificó — y es significativo

```
✗ usuarios/models.py       → ningún modelo nuevo ni campo nuevo
✗ usuarios/migrations/     → ninguna migración nueva
✗ config/urls.py           → las rutas ya estaban incluidas vía usuarios.urls
✗ usuarios/middleware.py   → sin cambios
✗ usuarios/mixins.py       → sin cambios
✗ dashboards/              → sin cambios
```

Que una funcionalidad completa de seguridad se implemente **sin tocar la base de datos** es la mejor evidencia de la calidad del diseño de Django, y del valor de haber elegido `AbstractUser` en la HU-01: al heredar del modelo de usuario de Django, toda la maquinaria de recuperación funciona sin adaptaciones.

---

## 12. Migraciones

### ¿Esta funcionalidad requiere migraciones nuevas?

**No. Ninguna.**

```bash
$ python manage.py makemigrations
No changes detected
```

### ¿Por qué?

Una migración existe para reflejar un cambio en la **estructura** de la base de datos: una tabla nueva, una columna nueva, un índice, una restricción. Y en esta funcionalidad **nada de eso cambia**.

Tres razones concretas:

**1. El token no se guarda.** Es el punto central. El diseño es *stateless*: el token se **recalcula** al verificarlo, en lugar de consultarse. Si se hubiera implementado con una tabla `tokens_recuperacion`, habría sido necesaria una migración; el mecanismo de Django la vuelve innecesaria.

**2. La contraseña ya tiene su columna.** El cambio de contraseña es un `UPDATE` sobre `usuarios_usuario.password`, una columna que existe desde `0001_initial`. Actualizar el **valor** de una fila no es una migración: es una operación normal de la aplicación (DML, no DDL).

```sql
-- Lo que ejecuta el proceso: un UPDATE, no un ALTER TABLE.
UPDATE usuarios_usuario
SET password = 'argon2$argon2id$v=19$m=102400,t=2,p=8$...'
WHERE id = 3;
```

**3. La sesión y la caché ya están resueltas.** El almacenamiento temporal del token usa `django_session`, creada por la migración de `django.contrib.sessions` en la HU-01. El contador de solicitudes vive en la caché en memoria, que no es parte de la base de datos.

### Diferencia entre DDL y DML — el concepto de fondo

| | DDL (*Data Definition Language*) | DML (*Data Manipulation Language*) |
|---|---|---|
| Qué modifica | La **estructura**: tablas, columnas, índices | Los **datos**: filas |
| Ejemplos | `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX` | `INSERT`, `UPDATE`, `DELETE`, `SELECT` |
| ¿Requiere migración? | **Sí** | No |
| En esta HU | Nada | El `UPDATE` de la contraseña |

### Cómo verificarlo en la defensa

```bash
$ python manage.py makemigrations --check --dry-run
No changes detected

$ python manage.py showmigrations usuarios
usuarios
 [X] 0001_initial
 [X] 0002_roles_iniciales
```

Las mismas dos migraciones de la HU-01. Ninguna nueva.

> **Defensa — respuesta si preguntan "¿y no necesitaste guardar los tokens?"**
> No, y ese es precisamente el mérito del diseño. El token de Django no es un dato guardado sino una **firma verificable**: se calcula con HMAC-SHA256 a partir de los datos del usuario y de la clave secreta del servidor, y para validarlo se vuelve a calcular y se compara. Eso trae cuatro ventajas: cero escrituras en la base por cada solicitud, ninguna tarea de limpieza de tokens vencidos, ningún token expuesto si la base se filtrara, y —lo más elegante— invalidación automática al usarse, porque el hash de la contraseña forma parte de la firma.

---

## 13. Pruebas

### Prueba manual paso a paso

#### Preparación

```bash
cd backend
..\.venv\Scripts\activate

# La configuración por defecto ya usa el backend de consola: no hay que
# configurar ninguna cuenta de correo.
python manage.py migrate
python manage.py crear_usuarios_demo
python manage.py runserver
```

#### Paso 1 — Crear usuario

Ya está creado por `crear_usuarios_demo`:

| Correo | Contraseña inicial |
|---|---|
| `censista@opso.cl` | `Censo2026#Opso` |

Para crear uno propio: `python manage.py createsuperuser`, o desde `/admin/`.

#### Paso 2 — Solicitar la recuperación

1. Abre http://127.0.0.1:8000/login/
2. Haz clic en **"¿Olvidaste tu contraseña?"**
3. Escribe `censista@opso.cl`
4. Presiona **"Enviar enlace de recuperación"**

**Resultado esperado:** la pantalla 2 con el texto *"Si la dirección que ingresaste corresponde a una cuenta registrada…"*.

#### Paso 3 — Revisar el correo

Con el backend de consola, el correo aparece **en la terminal donde corre `runserver`**:

```
Content-Type: multipart/alternative; boundary="===============..."
Subject: OPSO: instrucciones para restablecer tu contraseña
From: OPSO - Operativo Social <no-responder@opso.cl>
To: censista@opso.cl

Hola Marta:

Recibimos una solicitud para restablecer la contraseña de tu cuenta en
OPSO (censista@opso.cl).

Para crear una contraseña nueva, abre el siguiente enlace:

http://127.0.0.1:8000/restablecer/Mw/dcarwr-630193a6b8a32afa7c63906dc54e7d29/

Este enlace es personal, sirve UNA SOLA VEZ y caduca en 60 minutos.
```

#### Paso 4 — Abrir el enlace

Copia la dirección y pégala en el navegador.

**Resultado esperado:** aparece el formulario de contraseña nueva, y **fíjate en la barra de direcciones**: cambió a `/restablecer/Mw/set-password/`. El token desapareció de la URL — esa es la protección contra la filtración por `Referer` que conviene mostrar en la defensa.

#### Paso 5 — Cambiar la contraseña

1. Escribe `ClaveRecuperada2026#` en los dos campos
2. Presiona **"Guardar nueva contraseña"**

**Resultado esperado:** pantalla 4, *"¡Listo! Tu contraseña fue actualizada"*. Y en la terminal aparece un **segundo correo** con el aviso del cambio.

#### Paso 6 — Iniciar sesión nuevamente

1. Haz clic en **"Iniciar sesión"**
2. Entra con `censista@opso.cl` y `ClaveRecuperada2026#`

**Resultado esperado:** entra y es redirigido a `/dashboard/censista/`.

#### Verificaciones adicionales que impresionan en la defensa

```
a) Reutilizar el enlace  → pégalo otra vez: "El enlace no es válido"
b) Contraseña antigua    → intenta entrar con Censo2026#Opso: rechazada
c) Correo inexistente    → pide recuperación para nadie@opso.cl:
                           misma pantalla, pero NO aparece correo en la terminal
d) Sesión ajena          → abre sesión en otro navegador, cambia la contraseña
                           desde el primero: el segundo queda fuera
```

### Comprobar el hash en la base de datos

```bash
python manage.py shell
```

```python
from usuarios.models import Usuario
u = Usuario.objects.get(email="censista@opso.cl")
print(u.password)     # argon2$argon2id$v=19$... — no se parece a la contraseña
print(u.check_password("ClaveRecuperada2026#"))   # True
print(u.check_password("Censo2026#Opso"))         # False (la anterior ya no vale)
```

### Pruebas automáticas

```bash
python manage.py test                                    # 80 pruebas
python manage.py test usuarios.tests.CambioContrasenaTest -v 2
```

Las 33 pruebas de esta HU, agrupadas por lo que verifican:

| Clase | Pruebas | Qué demuestra |
|---|---|---|
| `SolicitudRecuperacionTest` | 9 | Pantalla pública, correo enviado solo si corresponde, **respuesta idéntica exista o no la cuenta**, cuenta desactivada excluida, CSRF obligatorio |
| `ContenidoCorreoTest` | 6 | **El correo nunca contiene una contraseña**, incluye el enlace, va en texto plano + HTML, asunto de una línea, advertencia de seguridad |
| `ValidacionTokenTest` | 6 | El token sale de la URL, token manipulado rechazado, token de otro usuario rechazado, uid inválido rechazado, **expiración funciona** |
| `CambioContrasenaTest` | 9 | Flujo completo, hash Argon2id, login con la clave nueva, la antigua deja de servir, **token de un solo uso**, validadores aplicados, **sesiones ajenas cerradas**, aviso enviado |
| `LimiteSolicitudesTest` | 2 | Control de frecuencia por correo, sin afectar otras cuentas |
| *(reutilizadas)* | 1 | La página es pública pese a `LoginRequiredMiddleware` |

Dos pruebas merecen mención especial por la técnica que usan:

**Simular el paso del tiempo** (para probar la expiración sin esperar una hora):

```python
futuro = datetime.now() + timedelta(hours=2)
with patch("django.contrib.auth.tokens.PasswordResetTokenGenerator._now",
           return_value=futuro):
    respuesta = self.client.get(ruta)
self.assertFalse(respuesta.context["validlink"])
```

**Verificar que se cierran las sesiones ajenas** (usando dos clientes que simulan dos dispositivos):

```python
otro_dispositivo = Client()
otro_dispositivo.force_login(self.censista)
self.assertEqual(otro_dispositivo.get("/dashboard/censista/").status_code, 200)

self.completar_flujo()          # se cambia la contraseña desde el otro cliente

respuesta = otro_dispositivo.get("/dashboard/censista/")
self.assertEqual(respuesta.status_code, 302)   # quedó fuera
```

**Detalle sobre el correo en las pruebas:** Django activa automáticamente el backend `locmem` durante los tests, que guarda los mensajes en `mail.outbox` en lugar de enviarlos. Así se puede inspeccionar el contenido real del correo sin conexión ni cuenta SMTP:

```python
self.assertEqual(len(mail.outbox), 1)
self.assertNotIn(CLAVE_VALIDA, mail.outbox[0].body)   # nunca la contraseña
```

**Y un detalle importante de las pruebas del límite:** `setUp()` ejecuta `cache.clear()`. Sin eso, el contador de una prueba quedaría alto y haría fallar la siguiente — un caso real de pruebas que se contaminan entre sí.

---

## 14. Posibles problemas

### 1. El correo no se envía

**Síntoma:** la pantalla 2 aparece normalmente, pero no llega ningún correo.

**Recuerda que esto es intencional en tres casos legítimos:** el correo no existe, la cuenta está desactivada, o se superó el límite de solicitudes. Lo primero es revisar el log del servidor, que sí dice qué pasó.

| Causa | Cómo verificarla | Solución |
|---|---|---|
| Backend de consola activo | `grep EMAIL_BACKEND .env` | Es lo normal en desarrollo: el correo está **en la terminal de `runserver`**, no en tu bandeja |
| La cuenta no existe | `Usuario.objects.filter(email__iexact="...").exists()` en el shell | Verificar el correo escrito |
| Cuenta desactivada | `u.is_active` | Reactivarla desde `/admin/` |
| Límite superado | Buscar `descartada` en el log | Esperar 15 minutos o reiniciar el servidor (limpia la caché en memoria) |
| Credenciales SMTP erróneas | Ver punto 5 de esta lista | Corregir `.env` |

**Prueba de aislamiento** — comprobar el envío sin pasar por el formulario:

```bash
python manage.py shell
```

```python
from django.core.mail import send_mail
send_mail("Prueba OPSO", "Cuerpo de prueba", None, ["destino@ejemplo.cl"])
# Devuelve 1 si se envió correctamente.
```

Si esto funciona y el formulario no, el problema está en la lógica; si esto tampoco funciona, el problema es la configuración SMTP.

### 2. Token expirado

**Síntoma:** "El enlace no es válido" en un enlace que se acaba de recibir.

| Causa | Solución |
|---|---|
| Pasó más de 1 hora | Solicitar un enlace nuevo (comportamiento correcto) |
| El reloj del servidor está desajustado | `w32tm /resync` en Windows. Un reloj adelantado hace que los tokens "nazcan expirados" |
| Se cambió la `SECRET_KEY` | Todos los enlaces pendientes se invalidan. Usar `SECRET_KEY_FALLBACKS` si hay que rotarla en producción |
| Ya se usó | Es correcto: los enlaces son de un solo uso |

Para dar más holhoura en un ambiente de pruebas: `PASSWORD_RESET_TIMEOUT=86400` en `.env` (un día).

### 3. Enlace inválido

**Síntoma:** el enlace no funciona aunque nunca se usó.

| Causa | Detalle | Solución |
|---|---|---|
| **El enlace se cortó** | Es la causa más frecuente. Algunos clientes de correo cortan las direcciones largas al pasar de línea | Copiar el enlace **completo** o usar el botón del correo HTML |
| El correo lo modificó | Algunos filtros de seguridad reescriben los enlaces | Usar la versión de texto plano |
| Se cambió la contraseña por otra vía | Invalida todos los enlaces pendientes | Solicitar uno nuevo |
| El usuario fue eliminado | El `uid` ya no corresponde a nadie | Recrear la cuenta |

### 4. Usuario inexistente

**Síntoma:** se pide la recuperación y no llega nada.

Es el **comportamiento diseñado**: el sistema no revela que la cuenta no existe. Para confirmarlo como administrador:

```python
from usuarios.models import Usuario
Usuario.objects.filter(email__iexact="sospechoso@opso.cl").exists()
```

O revisar el log: si hay una línea `Solicitud de recuperación recibida` pero no salió correo, la cuenta no existe o está desactivada.

### 5. Configuración SMTP incorrecta

| Error que aparece | Causa | Solución |
|---|---|---|
| `SMTPAuthenticationError: 535 Username and Password not accepted` | Se usó la contraseña personal de Gmail | Generar una **contraseña de aplicación** en https://myaccount.google.com/apppasswords |
| `SMTPAuthenticationError: 534 Application-specific password required` | Falta la verificación en dos pasos | Activarla y luego generar la contraseña de aplicación |
| `SMTPServerDisconnected` / `ConnectionRefusedError` | Puerto equivocado, o el firewall bloquea la salida | Verificar `EMAIL_PORT` (587 con TLS / 465 con SSL) |
| `SMTPNotSupportedError: STARTTLS extension not supported` | `EMAIL_USE_TLS=True` con el puerto 465 | Usar el puerto 587 con TLS, **o** el 465 con `EMAIL_USE_SSL=True` |
| `ValueError: EMAIL_USE_TLS/EMAIL_USE_SSL are mutually exclusive` | Ambos en `True` | Dejar solo uno |
| `TimeoutError` tras 10 segundos | El servidor no responde | Verificar `EMAIL_HOST` y la conexión de red |
| `[SSL: CERTIFICATE_VERIFY_FAILED]` | Certificados del sistema desactualizados | Actualizar Python o los certificados raíz |

### 6. Variables de entorno mal configuradas

**Síntoma característico:** el cambio en `.env` "no tiene efecto".

| Causa | Detalle | Solución |
|---|---|---|
| **No se reinició el servidor** | La causa más común. `settings.py` se lee **una vez al arrancar** | Detener y volver a levantar `runserver` |
| Comillas en el valor | `EMAIL_HOST_PASSWORD="abc123"` guarda las comillas como parte de la clave | Escribir sin comillas: `EMAIL_HOST_PASSWORD=abc123` |
| Espacios alrededor del `=` | `EMAIL_PORT = 587` | Sin espacios: `EMAIL_PORT=587` |
| `.env` en la carpeta equivocada | Debe estar junto a `manage.py`, en `backend/` | Moverlo |
| Booleano mal escrito | `cast=bool` interpreta `"False"` correctamente, pero `"false"` o `"0"` pueden confundir | Usar `True` / `False` con mayúscula inicial |
| Falta `DJANGO_SECRET_KEY` | `config("DJANGO_SECRET_KEY")` sin `default` lanza `UndefinedValueError` al arrancar | Copiar `.env.example` como `.env` y completarla |

**Cómo verificar qué está leyendo Django realmente:**

```bash
python manage.py shell
```

```python
from django.conf import settings
print(settings.EMAIL_BACKEND)
print(settings.EMAIL_HOST, settings.EMAIL_PORT, settings.EMAIL_USE_TLS)
print(settings.PASSWORD_RESET_TIMEOUT)
```

### 7. `NoReverseMatch: Reverse for 'password_reset_done' not found`

**La causa más probable al implementar esta funcionalidad.** Ocurre al enviar el formulario.

**Motivo:** las vistas de Django tienen escrito `success_url = reverse_lazy("password_reset_done")`, **sin el namespace**. Como las URLs de OPSO viven bajo `app_name = "usuarios"`, el nombre real es `usuarios:password_reset_done`.

**Solución:**

```python
class RecuperarContrasenaView(PasswordResetView):
    success_url = reverse_lazy("usuarios:password_reset_done")   # ← con namespace
```

Hay que hacerlo en `RecuperarContrasenaView` y en `RestablecerContrasenaView`.

### 8. `TemplateSyntaxError` en una plantilla del correo

**Síntoma:** `Unclosed tag on line N: 'autoescape'` o etiquetas que aparecen como texto visible en la página.

**Causa:** la etiqueta corta de comentario `{# … #}` de Django **solo funciona en una línea**. Un comentario escrito en varias líneas no se reconoce como comentario: se renderiza como texto y las etiquetas que contiene se intentan interpretar.

**Solución:** usar `{% comment %} … {% endcomment %}` para todo comentario de más de una línea.

Este error se encontró y corrigió durante el desarrollo de esta HU; se agregó una verificación que compila las 16 plantillas del proyecto para detectarlo.

### 9. La pantalla se ve sin estilos

| Causa | Solución |
|---|---|
| Bootstrap no está descargado | Verificar que exista `static/vendor/bootstrap/bootstrap.min.css` |
| Caché del navegador | `Ctrl+F5` para recargar sin caché |
| `DEBUG=False` sin `collectstatic` | Ejecutar `python manage.py collectstatic`, o poner `USAR_MANIFIESTO_ESTATICOS=False` en desarrollo |

---

## 15. Explicación para la defensa

### ¿Por qué utilizó Django para esta funcionalidad?

Porque Django trae la recuperación de contraseña **resuelta y auditada**, y esta es una de las funcionalidades donde equivocarse es más grave.

Tres razones concretas:

1. **El mecanismo de tokens es criptografía.** HMAC-SHA256, comparación en tiempo constante, codificación de la marca de tiempo. La implementación de Django ha sido revisada por la comunidad durante casi veinte años. Escribir una propia sería introducir errores en el componente más delicado del sistema.
2. **Un fallo criptográfico no se detecta probando la aplicación.** Si el token estuviera mal generado, el flujo "funcionaría" igual: se enviaría el correo, el enlace abriría y la contraseña cambiaría. El problema aparecería solo cuando alguien lograra falsificar un token. Es un error silencioso.
3. **Django resuelve detalles que uno no anticipa.** Por ejemplo, mover el token de la URL a la sesión para que no se filtre por el encabezado `Referer`. Nadie piensa en eso al diseñar la funcionalidad desde cero.

### ¿Por qué utilizar tokens?

Porque hay que autorizar una acción muy sensible —cambiar una contraseña— a alguien que **no puede autenticarse**. El token resuelve exactamente ese problema: es un permiso acotado en tres dimensiones (un usuario, una acción, un tiempo) que el servidor puede verificar **sin haber guardado nada**.

La alternativa sería enviar un código y guardarlo en una tabla, lo que implicaría escrituras en la base por cada solicitud, una tarea periódica de limpieza de códigos vencidos, y el riesgo de que esos códigos se filtren si la base se ve comprometida. Con el token firmado, no hay nada que filtrar.

### ¿Por qué no enviar la contraseña por correo?

Dos razones, y la primera es definitiva:

1. **Porque el sistema no la conoce.** No es una política, es una imposibilidad técnica: solo se guarda un hash irreversible. Si un sistema puede enviarte tu contraseña actual, está confesando que la guarda de forma reversible, lo que es un defecto grave.
2. **Porque el correo no es un canal seguro.** Un correo se guarda indefinidamente, pasa por servidores intermedios, queda en respaldos y se puede reenviar por error. Enviar una contraseña por ahí la dejaría escrita en un lugar permanente y poco controlado. El enlace, en cambio, caduca en una hora y sirve una vez.

### ¿Por qué almacenar las contraseñas cifradas?

Porque garantiza que **la contraseña nueva reciba el mismo tratamiento que la original**. Sería absurdo tener un inicio de sesión robusto y una recuperación que guardara la clave en texto plano: el atacante siempre buscará el punto más débil. Aquí se reutiliza exactamente el mismo mecanismo (Argon2id con sal aleatoria) y los mismos cuatro validadores de robustez, así que la recuperación no es una puerta trasera con estándares más bajos.

Y hay un beneficio adicional específico de esta funcionalidad: **como el hash cambia, el token se invalida solo**. El cifrado no solo protege la contraseña, además hace que el enlace sea de un solo uso sin necesidad de código extra.

### ¿Por qué utilizar PostgreSQL?

Aunque esta funcionalidad no crea tablas, depende de dos garantías que PostgreSQL entrega:

1. **Atomicidad y durabilidad del `UPDATE`.** Si el servidor se cae en medio del cambio de contraseña, la fila queda íntegra en su valor anterior o en el nuevo, **nunca a medias**. Una contraseña corrupta dejaría al usuario permanentemente fuera del sistema.
2. **La restricción `UNIQUE` sobre el correo.** Garantiza que la búsqueda por correo devuelva exactamente un usuario. Es un requisito de correctitud: si dos cuentas compartieran el mismo correo, no habría forma de saber a quién restablecer.

A eso se suman las razones generales del proyecto: cumplimiento ACID, concurrencia con control multiversión, soporte oficial de Django y software libre sin costo de licencia.

### ¿Por qué usar variables de entorno?

Porque las credenciales no deben estar en el código. `settings.py` se versiona en Git; `.env` no.

Si la contraseña del correo estuviera escrita en `settings.py`, quedaría en el historial de Git **para siempre**, y borrarla después no serviría: seguiría visible en los commits anteriores. Con `.env` en `.gitignore`, el repositorio se puede entregar o publicar sin filtrar nada.

Beneficio adicional: el **mismo código** funciona en desarrollo (correo por consola) y en producción (SMTP real) cambiando solo un archivo de configuración. Es el principio de separar configuración de código, de la metodología *12-factor app*.

### ¿Por qué utilizar las vistas nativas de Django?

Además de la seguridad ya explicada, por dos razones prácticas:

1. **Cantidad de código.** Las cuatro vistas de OPSO son subclases que redefinen entre 3 y 8 atributos cada una. Implementar el mismo comportamiento desde cero requeriría varios cientos de líneas, todas ellas por probar y mantener.
2. **Mantenimiento a futuro.** Al actualizar Django, cualquier mejora o corrección de seguridad en el mecanismo de recuperación llega automáticamente. Con una implementación propia habría que auditarla y actualizarla a mano.

Y algo que conviene decir explícitamente en la defensa: **usar las vistas nativas no significa no haber trabajado**. El trabajo estuvo en entender qué hace cada vista, elegir qué puntos de extensión personalizar (el namespace de `success_url`, las plantillas del correo, el control de frecuencia, la auditoría, el aviso posterior), diseñar las cuatro pantallas, redactar los correos y demostrar con 33 pruebas que todo funciona. Reescribir criptografía habría sido más código y peor resultado.

---

## 16. Posibles preguntas del profesor

**1. ¿Por qué no le envía al usuario su contraseña actual por correo?**
Por dos razones. La primera es que **el sistema no la conoce**: solo guarda un hash irreversible generado con Argon2id, y no existe operación que permita recuperar el texto original. Si un sistema puede enviarte tu contraseña, está confesando que la guarda de forma reversible. La segunda es que el correo no es un canal seguro: se guarda indefinidamente, pasa por servidores intermedios y queda en respaldos. El enlace que sí se envía caduca en una hora y sirve una sola vez.

**2. ¿Qué es exactamente un token y qué contiene?**
Es una firma temporal con dos partes separadas por un guion: la marca de tiempo de su generación en base 36, y un HMAC-SHA256 calculado sobre el id del usuario, el hash de su contraseña, su último inicio de sesión, la marca de tiempo y su correo, usando la `SECRET_KEY` del servidor como clave. No contiene información secreta y no se guarda en ninguna parte: el servidor lo **recalcula** para verificarlo.

**3. ¿Dónde se guarda el token? ¿Creó una tabla para eso?**
No creé ninguna tabla, y esa es la parte elegante del diseño. El token no se guarda: es un cálculo verificable. Para validarlo, Django rehace el mismo HMAC con los datos actuales del usuario y compara. Eso da cuatro ventajas: cero escrituras en la base por solicitud, ninguna tarea de limpieza de tokens vencidos, ningún token expuesto si la base se filtrara, e invalidación automática al usarse.

**4. ¿Cómo logra que el enlace sirva solo una vez, si no guarda que fue usado?**
Porque **el hash de la contraseña forma parte del mensaje firmado**. Al cambiar la contraseña, `set_password()` genera un hash nuevo, así que cuando Django recalcula la firma obtiene un valor distinto al que trae el enlace viejo, y lo rechaza. El token se autoinvalida al cumplir su función. Y funciona incluso si la persona elige la misma contraseña de antes, porque la sal aleatoria es nueva y el hash también.

**5. ¿Cuánto dura el enlace y por qué eligió ese tiempo?**
Una hora. El valor por defecto de Django son tres días, y lo reduje deliberadamente: cuanto menos vive el enlace, menor es la ventana en que un correo filtrado o un equipo compartido permiten secuestrar la cuenta. Una hora es suficiente para que una persona lea su correo y reaccione. Es un equilibrio explícito: cinco minutos sería más seguro pero frustrante para un censista en terreno con señal intermitente; tres días deja una ventana innecesariamente amplia.

**6. ¿Qué pasa si escribo el correo de otra persona en el formulario?**
Esa persona recibe un correo que no pidió, pero no ocurre nada más: usted no lo ve y sin abrir ese enlace nadie puede cambiar su contraseña. El correo lo dice explícitamente: "si no solicitaste este cambio, puedes ignorar este mensaje". Además hay un límite de tres solicitudes por correo cada quince minutos, justamente para que el formulario no se pueda usar como máquina de bombardear una casilla ajena.

**7. ¿Cómo evita que alguien averigüe qué correos están registrados en OPSO?**
Con cinco medidas coordinadas. La respuesta HTTP es idéntica exista o no la cuenta, el texto de la pantalla está en condicional ("*si* la dirección corresponde a una cuenta registrada"), el formulario no lanza errores de validación cuando el correo no existe, el bloqueo por exceso de solicitudes tampoco se anuncia, y los fallos de envío se registran en el log sin mostrarse. Sin esto, el formulario sería una herramienta gratuita para obtener la nómina de quién trabaja en el operativo. Hay una prueba que compara las dos respuestas para garantizar que no divergan.

**8. ¿Por qué la URL del enlace incluye el id del usuario codificado? ¿No es un riesgo?**
No, y es importante ser preciso: **base64 no es cifrado**, es solo una forma de representar datos con caracteres válidos en una URL, y cualquiera puede decodificarlo. No importa porque el id del usuario no es un secreto: saber que existe el usuario 3 no permite hacer nada. La seguridad la aporta el token, no el uid. Y si alguien modificara el uid, la firma dejaría de coincidir, porque el id forma parte del mensaje firmado.

**9. Noté que la URL cambia después de abrir el enlace. ¿Por qué?**
Django detecta el token válido, lo guarda en la sesión del servidor y redirige a una dirección donde el token se reemplaza por la palabra `set-password`. El motivo es que si el token quedara en la barra de direcciones podría filtrarse por el encabezado `Referer` que el navegador envía al cargar recursos externos, quedar en el historial de un equipo compartido, o aparecer en los registros de un proxy corporativo. Es un detalle que difícilmente se me habría ocurrido implementando la funcionalidad desde cero, y es un buen argumento a favor de usar las vistas nativas.

**10. ¿Qué pasa con las sesiones que el usuario tenía abiertas en otros dispositivos?**
Se cierran automáticamente. Cada sesión guarda un valor derivado de la contraseña, y `AuthenticationMiddleware` lo compara en cada petición con el que corresponde al hash actual; al cambiar la contraseña dejan de coincidir y la sesión se descarta. Es crucial: si un atacante ya estaba conectado a la cuenta, el restablecimiento lo expulsa. Sin este comportamiento, la víctima cambiaría su clave y el atacante seguiría dentro. Es nativo de Django, pero hay que saber que existe para poder afirmarlo, y hay una prueba con dos clientes que lo demuestra.

**11. ¿Esta funcionalidad requirió migraciones? ¿Por qué?**
Ninguna. `makemigrations` responde "No changes detected". Las migraciones existen para cambios de **estructura** —tablas, columnas, índices— y aquí no cambia nada de eso: el token no se guarda, la columna `password` ya existía desde la primera migración, y el cambio de contraseña es un `UPDATE`, que es DML y no DDL. El almacenamiento temporal del token usa la tabla de sesiones, que ya existía, y el contador de solicitudes vive en la caché, que no es parte de la base de datos.

**12. ¿Por qué usó las vistas nativas de Django en lugar de programarlas?**
Porque el mecanismo de tokens es criptografía revisada durante casi veinte años, y un error ahí sería silencioso: el flujo funcionaría igual y el problema solo aparecería cuando alguien lograra falsificar un token. Además Django resuelve detalles que uno no anticipa, como sacar el token de la URL o usar comparación en tiempo constante. El trabajo estuvo en entender qué hace cada vista, elegir los puntos de extensión que OPSO necesitaba, diseñar las pantallas y los correos, y demostrarlo con 33 pruebas.

**13. ¿Qué es `constant_time_compare` y por qué se usa?**
Es la comparación de textos que Django usa para verificar la firma del token. Una comparación normal termina en cuanto encuentra el primer carácter distinto, así que comparar cadenas que difieren al final tarda **más** que comparar cadenas que difieren al principio. Midiendo esos microsegundos, un atacante podría ir adivinando la firma carácter por carácter: es un ataque de temporización. `constant_time_compare` siempre tarda lo mismo, sin importar dónde esté la diferencia.

**14. ¿Cómo probó la expiración del token sin esperar una hora?**
Reemplazando temporalmente el reloj del generador de tokens con `unittest.mock.patch`: se sustituye el método `_now()` por uno que devuelve la fecha actual más dos horas, se pide la página en ese contexto y se verifica que `validlink` sea `False`. Es la técnica estándar para probar lógica dependiente del tiempo, y por eso mismo Django expone `_now()` como método separado: para hacerlo sustituible en pruebas.

**15. ¿Qué pasa si se cambia la `SECRET_KEY` del servidor?**
Todos los enlaces pendientes se invalidan de inmediato, porque la firma se calcula con esa clave. En producción eso podría afectar a usuarios en medio del proceso, así que Django ofrece `SECRET_KEY_FALLBACKS`: una lista de claves anteriores que se siguen aceptando para verificar, aunque las firmas nuevas se generen con la clave actual. Permite rotar la clave sin romper los enlaces en curso.

**16. ¿Cómo probó esto sin tener un servidor de correo?**
De dos formas. Para las pruebas manuales, con el backend de consola: Django imprime el correo completo en la terminal de `runserver`, con el enlace listo para copiar. Para las pruebas automáticas, Django activa por sí solo el backend `locmem`, que guarda los mensajes en la lista `mail.outbox`; así puedo inspeccionar el asunto, el remitente y el cuerpo, y verificar por ejemplo que el correo nunca contenga una contraseña, todo sin conexión.

**17. ¿Por qué el correo se envía en texto plano y en HTML a la vez?**
Porque el mensaje viaja como `multipart/alternative` con ambas versiones y cada cliente elige la que puede mostrar. Es necesario porque muchos clientes corporativos bloquean el HTML por política de seguridad, algunos lectores de pantalla trabajan mejor con texto plano, y ciertos filtros antispam penalizan los mensajes que solo traen HTML. Con las dos versiones el correo llega y se lee siempre.

**18. ¿Qué impide que alguien use el formulario para enviar miles de correos?**
Un control de frecuencia: tres solicitudes por correo y diez por dirección IP cada quince minutos. Los dos límites son necesarios, porque el límite por correo no detiene a quien prueba mil correos distintos, y el límite por IP no protege a una persona atacada desde varias redes. El contador vive en la caché y no en PostgreSQL, porque es un dato efímero que solo interesa quince minutos; guardarlo en la base implicaría una escritura por intento y una tabla que crece sin aportar información.

**19. ¿Hay algún compromiso o limitación que reconozca en su implementación?**
Dos, y prefiero declararlos. El primero: un atacante podría mantener bloqueada la recuperación de una cuenta concreta enviando solicitudes repetidas, una denegación de servicio dirigida; lo acepté porque el daño es bajo y temporal —quince minutos, y el administrador siempre puede restablecer la contraseña desde `/admin/`— frente al beneficio de impedir el bombardeo de una casilla ajena. El segundo: `LocMemCache` vive en la memoria de un proceso, así que en producción con varios trabajadores de Gunicorn cada uno llevaría su propia cuenta y el límite efectivo se multiplicaría; por eso el archivo `.env` documenta el cambio a Redis.

**20. ¿Por qué no inicia la sesión automáticamente después del cambio?**
Django lo permite con `post_reset_login = True`, y decidí no usarlo. Obligar a escribir la contraseña nueva confirma que la persona la recuerda o la guardó en su gestor, en lugar de dejarla dentro del sistema con una clave que quizá olvide al cerrar el navegador. Además mantiene un único camino de autenticación, que es el que tiene la bitácora de accesos y el bloqueo por intentos fallidos de la HU-01.

**21. ¿Qué diferencia hay entre un hash y un cifrado? Lo usó en los dos sentidos.**
Un cifrado es **reversible**: con la clave se recupera el texto original; se usa cuando hay que leer el dato después, como el contenido de un mensaje. Un hash es **irreversible**: solo permite verificar si un dato coincide con el original. Las contraseñas usan hash porque el sistema nunca necesita leerlas, solo comparar. El token usa HMAC, que es un hash con clave: sirve para verificar autenticidad, no para ocultar información. Y la conexión SMTP sí usa cifrado (TLS), porque el servidor de correo tiene que poder leer el mensaje.

---

## 17. Conclusión técnica

En el marco del desarrollo del sistema OPSO (Operativo Social), se implementó la historia de usuario correspondiente a la recuperación de contraseña mediante correo electrónico, funcionalidad que complementa el módulo de autenticación desarrollado previamente y que resuelve un escenario operativo inevitable: la pérdida de credenciales por parte del personal que participa en el levantamiento de información de familias.

La solución desarrollada se estructura en cuatro etapas secuenciales —solicitud, generación y envío del enlace, verificación de identidad y actualización de la credencial—, materializadas en cuatro vistas que heredan de las clases nativas del framework, cuatro pantallas construidas sobre una plantilla base común y un mensaje de correo emitido simultáneamente en formato de texto plano y HTML. El mecanismo de verificación se sustenta en un token generado mediante HMAC-SHA256, cuyo mensaje incorpora el identificador del usuario, el resumen criptográfico de su contraseña vigente, la fecha de su último acceso, una marca temporal y su dirección de correo, empleando como clave la variable secreta del servidor. Este diseño, de naturaleza *stateless*, prescinde por completo de almacenamiento persistente del token: la validación se efectúa recalculando la firma a partir del estado actual del usuario y comparándola en tiempo constante con la recibida, procedimiento que neutraliza los ataques de temporización.

La decisión de emplear las herramientas nativas de Django, antes que desarrollar una implementación propia, se fundamenta en tres consideraciones. En primer término, el mecanismo de tokens constituye criptografía aplicada, cuyo código ha sido objeto de revisión sostenida por la comunidad durante casi dos décadas; una implementación alternativa introduciría riesgo en el componente más sensible del sistema, con el agravante de que un defecto criptográfico no se manifiesta en las pruebas funcionales —el flujo operaría con aparente normalidad— y solo se evidenciaría al ser explotado. En segundo término, las vistas del framework resuelven consideraciones de seguridad que difícilmente se anticipan en un diseño desde cero, entre ellas el traslado del token desde la dirección URL hacia la sesión del servidor, medida que previene su filtración a través del encabezado `Referer`. En tercer término, la adopción del código nativo garantiza que las futuras correcciones de seguridad del framework se incorporen mediante la simple actualización de la dependencia, sin necesidad de auditar código propio. El aporte del desarrollo consistió, en consecuencia, en la comprensión del funcionamiento interno de dichas vistas, en la selección fundamentada de los puntos de extensión pertinentes al dominio del proyecto, en el diseño de la interfaz y de los mensajes, y en la verificación empírica del comportamiento resultante.

Resulta pertinente destacar que la funcionalidad no requirió la creación de tablas, columnas ni migraciones adicionales, hecho que constituye evidencia de la adecuación del diseño adoptado en la historia de usuario precedente: la elección de un modelo de usuario derivado de `AbstractUser` permitió que la totalidad del mecanismo de recuperación operara sin adaptaciones. La única modificación que la funcionalidad introduce en el esquema de datos es la actualización del valor de la columna que almacena el resumen de la contraseña, operación de manipulación de datos y no de definición de estructura. En este contexto, PostgreSQL aporta dos garantías indispensables: la atomicidad y durabilidad de dicha actualización, que impide que una interrupción del servicio deje la credencial en un estado inconsistente y al usuario permanentemente excluido del sistema; y la restricción de unicidad sobre la dirección de correo, que asegura la correspondencia biunívoca entre la dirección ingresada y la cuenta a restablecer, condición de correctitud del procedimiento.

La protección de la información del usuario se articula en múltiples capas concurrentes. La contraseña nueva se somete al mismo tratamiento que la original —resumen mediante Argon2id con sal aleatoria individual y aplicación de cuatro validadores de robustez—, de modo que la funcionalidad no constituye una vía de acceso con estándares atenuados. El enlace de verificación posee vigencia limitada a sesenta minutos y su unicidad de uso es consecuencia automática del diseño: al incorporar el resumen de la contraseña en el mensaje firmado, la modificación de esta invalida intrínsecamente toda firma previa, sin requerir marcas de estado ni procesos de limpieza. La actualización de la credencial provoca, adicionalmente, la invalidación inmediata de todas las sesiones activas de la cuenta en cualquier dispositivo, lo que expulsa a un eventual intruso previamente autenticado. Se implementaron asimismo cinco medidas coordinadas de prevención de enumeración de usuarios, que impiden emplear el formulario como instrumento de reconocimiento para determinar qué direcciones se encuentran registradas; un control de frecuencia de solicitudes que evita el uso abusivo del formulario como mecanismo de envío masivo; protección contra falsificación de peticiones entre sitios en ambos formularios; y la emisión de una notificación posterior al titular de la cuenta, que opera como control de detección ante un restablecimiento no autorizado. La totalidad de estos mecanismos fue verificada mediante treinta y tres pruebas automatizadas específicas, que elevan a ochenta el total de pruebas del proyecto y constituyen evidencia reproducible del comportamiento descrito.

En síntesis, la funcionalidad desarrollada aporta al proyecto OPSO autonomía operativa y continuidad del servicio. Permite que el personal de terreno recupere su acceso sin intervención del administrador del sistema, lo que resulta particularmente relevante en operativos desplegados en sectores rurales, donde la coordinación remota es limitada y la interrupción del trabajo de un censista repercute directamente en la cobertura del levantamiento. Simultáneamente, elimina la práctica —extendida e insegura— de que las contraseñas se comuniquen verbalmente o se restablezcan por vías informales, sustituyéndola por un procedimiento verificable, auditable y de un solo uso. Al preservar el principio de que ninguna contraseña resulta legible para el sistema ni para sus administradores, la solución consolida el estándar de resguardo de la información de las familias participantes, en concordancia con la normativa chilena sobre protección de datos personales y con la responsabilidad ética inherente al tratamiento de datos de población en situación de vulnerabilidad.

---

## 18. Explicación para entender la implementación

Esta sección está escrita como una clase, con el mínimo de tecnicismos.

### 18.1 Una analogía para empezar

Imagina que perdiste la llave de tu casillero en el gimnasio.

El encargado **no puede darte una copia de tu llave**, porque no tiene copias: solo tiene una cerradura que reconoce la llave correcta. Lo que sí puede hacer es esto:

1. Te pide tu nombre y busca tu ficha.
2. En la ficha está anotado **tu número de teléfono**.
3. Te manda un mensaje a ese teléfono con un código: *"Muestra este código en el mostrador antes de las 15:00 para que te pongamos una cerradura nueva"*.
4. Cuando llegas con el código, el encargado verifica que sea auténtico y **te deja poner una llave nueva** — no te devuelve la vieja.
5. Ese código sirve una sola vez: en cuanto cambias la cerradura, deja de valer.

Eso es exactamente la recuperación de contraseña en OPSO:

| En el gimnasio | En OPSO |
|---|---|
| La llave | Tu contraseña |
| La cerradura (reconoce pero no revela) | El hash guardado en PostgreSQL |
| Tu teléfono anotado en la ficha | Tu correo registrado |
| El código con hora límite | El token del enlace |
| Poner una cerradura nueva | Definir una contraseña nueva |
| El código deja de valer al usarse | El token se autoinvalida |

**La idea central:** el sistema no te devuelve tu contraseña (no puede), te da la oportunidad de poner una nueva, después de comprobar que tienes acceso a tu correo.

### 18.2 Qué hace cada archivo que interviene

**`config/settings.py` — la ficha técnica**
Aquí están los datos del servidor de correo (¿a qué servidor le entrego la carta? ¿con qué usuario?) y dos decisiones importantes: cuánto dura el enlace (una hora) y cuántas solicitudes se permiten (tres cada quince minutos).

**`.env` — la caja fuerte**
La contraseña de la cuenta de correo vive aquí, no en el código. Este archivo **no se sube al repositorio**. Si estuviera en `settings.py`, quedaría en el historial de Git para siempre.

**`usuarios/urls.py` — el índice de direcciones**
Dice qué código atiende cada dirección: `/recuperar-contrasena/` → tal vista, `/restablecer/<uid>/<token>/` → tal otra.

**`usuarios/views.py` — quien toma las decisiones**
Cuatro clases, una por pantalla. Son cortas porque **heredan** de las de Django: solo cambian las plantillas, agregan el control de frecuencia y el aviso posterior.

**`usuarios/forms.py` — el portero que revisa los papeles**
Dos formularios: uno recibe el correo, otro recibe la contraseña nueva y verifica que las dos coincidan y que cumpla las reglas.

**`usuarios/seguridad.py` — las funciones de apoyo**
Cuenta las solicitudes para frenar abusos y envía el correo de aviso posterior al cambio.

**`templates/usuarios/*.html` — lo que la persona ve**
Las cuatro pantallas. Todas heredan de `base_publico.html`, así que el encabezado y la tarjeta se escriben una sola vez.

**`templates/usuarios/correo/*` — lo que la persona recibe**
El asunto, el cuerpo en texto y el cuerpo en HTML del correo, más el aviso posterior.

### 18.3 Qué ocurre desde que presionas "Olvidé mi contraseña"

Paso a paso, con lo que pasa en cada momento:

**Paso 1.** Haces clic en el enlace. El navegador pide la dirección `/recuperar-contrasena/`.

**Paso 2.** Django mira su índice de direcciones, encuentra que esa dirección la atiende `RecuperarContrasenaView`, y esa vista dibuja la pantalla con el campo de correo.

Detalle interesante: OPSO tiene activada una regla que dice *"todas las páginas exigen sesión iniciada"*. Pero esta página es una excepción declarada, porque justamente la usa alguien que **no puede** iniciar sesión.

**Paso 3.** Escribes `censista@opso.cl` y presionas el botón. El navegador arma un paquete con tu correo y un **token secreto** que Django había escondido en la página, y lo envía.

**Paso 4.** Django **primero** revisa ese token secreto (el token CSRF). Si falta, corta con un error. Esto impide que otro sitio web dispare solicitudes de recuperación en tu nombre.

**Paso 5.** Django cuenta cuántas solicitudes ya se hicieron para ese correo en los últimos quince minutos. Si van tres o más, no envía nada — pero **no te lo dice**, para no dar pistas.

**Paso 6.** Busca tu correo en la base de datos, y aquí puede pasar una de tres cosas: la cuenta existe y está activa (envía el correo), la cuenta no existe (no envía nada), o la cuenta está desactivada (no envía nada).

**Paso 7.** En los tres casos ves **exactamente la misma pantalla**: *"Si la dirección que ingresaste corresponde a una cuenta registrada, recibirás un mensaje…"*.

Esto es a propósito, y es importante que lo puedas explicar: si la pantalla dijera "te enviamos un correo" solo cuando la cuenta existe, cualquiera podría probar direcciones y armar la lista de quién trabaja en OPSO.

### 18.4 Cómo Django genera el token

Esta es la parte que más conviene entender bien.

Django toma **cinco datos tuyos** y los pega en un solo texto:

```
"3" + "argon2$argon2id$v=19$...tu_hash..." + "2026-07-26 00:15:00" + "812345678" + "censista@opso.cl"
 │                    │                              │                    │              │
 tu id           tu hash actual            tu último ingreso        la hora ahora    tu correo
```

Luego pasa ese texto por una máquina llamada **HMAC-SHA256**, usando como "troquel" la clave secreta del servidor:

```
firma = HMAC-SHA256(ese texto, clave = SECRET_KEY)
      = "630193a6b8a32afa7c63906dc54e7d29"
```

Y el token final es la hora + la firma:

```
dcarwr-630193a6b8a32afa7c63906dc54e7d29
```

**Tres cosas que hay que tener claras:**

1. **La firma no se puede falsificar sin la clave secreta.** Es como un sello que solo el servidor tiene.
2. **El token no se guarda en ninguna parte.** No hay una tabla de tokens. Cuando haya que verificarlo, Django **vuelve a hacer el mismo cálculo** y compara.
3. **Cada dato que entra cumple una función:**
   - Tu **id**, para que el token sirva solo para tu cuenta.
   - Tu **hash actual**, para que el token muera al cambiar la contraseña (te lo explico en 18.7).
   - La **hora**, para poder saber si ya caducó.
   - Tu **correo**, para que si te cambian el correo, los enlaces viejos mueran.

### 18.5 Cómo se envía el correo

Django arma un mensaje con **dos versiones del mismo contenido**: una en texto simple y otra en HTML con colores y botón. Cada programa de correo elige la que puede mostrar. Se hace así porque algunos programas bloquean el HTML por seguridad.

El enlace se construye con una instrucción especial:

```django
{{ protocol }}://{{ domain }}{% url 'usuarios:password_reset_confirm' uidb64=uid token=token %}
```

Que produce:

```
http://127.0.0.1:8000/restablecer/Mw/dcarwr-630193a6b8a32afa7c63906dc54e7d29/
```

Nota que la dirección **no está escrita a mano**: Django la arma a partir del *nombre* de la ruta. Si mañana cambias `/restablecer/` por otra cosa, los correos siguen funcionando.

**Y en desarrollo, ¿a dónde va el correo?** A la terminal donde corre `runserver`. Django lo imprime completo, con el enlace listo para copiar. No necesitas cuenta de correo ni internet. Para la defensa es ideal: puedes mostrar el correo en pantalla en vez de cambiar a Gmail.

### 18.6 Cómo se valida el enlace

Copias el enlace y lo abres. Django hace cuatro cosas:

**1. Saca tu id.** El `Mw` del enlace es el número `3` escrito en base64. Con eso busca tu cuenta.

Aclaración importante: base64 **no es cifrado**, es solo una forma de escribir un número con letras válidas en una dirección web. Cualquiera puede decodificarlo, y no importa: saber que existe el usuario 3 no sirve de nada. La seguridad está en el token.

**2. Recalcula la firma.** Toma tus datos actuales, hace otra vez el mismo cálculo, y compara con la firma que venía en el enlace. Si no coinciden → rechazado.

La comparación usa un truco: **siempre tarda lo mismo**, incluso si la diferencia está en el primer carácter. Si terminara antes al encontrar una diferencia temprana, alguien podría medir esos microsegundos e ir adivinando la firma letra por letra.

**3. Revisa la hora.** Si pasaron más de sesenta minutos → rechazado.

**4. Esconde el token.** Y aquí viene algo que sorprende: si todo está bien, Django **no te muestra el formulario todavía**. Guarda el token en tu sesión y te redirige a otra dirección:

```
/restablecer/Mw/dcarwr-630193a6.../   →   /restablecer/Mw/set-password/
```

**¿Por qué?** Porque una dirección web se filtra por muchos lados: queda en el historial del navegador, y si la página cargara algo de otro sitio, el navegador le avisaría "vengo de esta dirección". Sacando el token de ahí, eso deja de ser posible.

En la defensa, muestra la barra de direcciones antes y después: es una demostración muy concreta.

### 18.7 Cómo se cambia la contraseña y cómo PostgreSQL la guarda

Escribes tu contraseña nueva dos veces y presionas guardar.

**Primero se valida:**
- ¿Las dos coinciden? (si no, era un error de tipeo)
- ¿Tiene al menos 10 caracteres?
- ¿No se parece a tu nombre o correo?
- ¿No está entre las 20.000 más comunes?
- ¿No es solo números?

**Después se guarda.** Django ejecuta `set_password()`, que:

1. Genera una **sal** aleatoria nueva (un texto al azar).
2. Mezcla tu contraseña con esa sal.
3. Pasa la mezcla por Argon2id, una operación lenta a propósito.
4. Guarda el resultado.

Y en PostgreSQL se ejecuta esto:

```sql
UPDATE usuarios_usuario
SET password = 'argon2$argon2id$v=19$m=102400,t=2,p=8$bnVldmFzYWw$K9pQ...'
WHERE id = 3;
```

**Fíjate:** es un `UPDATE`, no un `CREATE TABLE`. Se cambia el **valor** de una casilla que ya existía. Por eso esta funcionalidad **no necesitó ninguna migración**: no cambió la estructura de la base de datos, solo un dato.

**Y aquí ocurre la magia del uso único.** Recuerda que el token se calculó usando tu hash **anterior**:

```
Antes:   hash = "...AAA"  →  firma del token = 630193a6...
Ahora:   hash = "...BBB"  →  Django recalcula = 9f2c41e8...

El enlace trae 630193a6..., Django obtiene 9f2c41e8...  →  NO coinciden  →  rechazado
```

**El enlace se destruyó solo.** Nadie tuvo que marcarlo como usado ni borrarlo de una tabla: dejó de funcionar como consecuencia matemática de haber cumplido su propósito.

Y funciona **incluso si eliges la misma contraseña de antes**, porque la sal es nueva y por lo tanto el hash también.

### 18.8 Cómo Django verifica que todo sea seguro

Resumamos las barreras, en orden:

| Momento | Qué se verifica |
|---|---|
| Al pedir el enlace | Que el token CSRF sea válido (que la solicitud nazca en OPSO) |
| | Que no se hayan hecho más de 3 solicitudes en 15 minutos |
| | Que la cuenta exista, esté activa y tenga contraseña utilizable |
| Al abrir el enlace | Que el id corresponda a un usuario que existe |
| | Que la firma sea auténtica (recalculándola) |
| | Que la comparación tarde siempre lo mismo (anti-temporización) |
| | Que no hayan pasado más de 60 minutos |
| Al guardar | Que el token siga en la sesión |
| | Que el token CSRF sea válido |
| | Que las dos contraseñas coincidan |
| | Que cumpla las cuatro reglas de robustez |
| Después de guardar | Se cifra con Argon2id + sal nueva |
| | El token queda inservible (automático) |
| | Las sesiones abiertas en otros dispositivos caen (automático) |
| | Se envía el aviso al titular |
| | Queda registro en el log del servidor |

**Sobre las sesiones que caen:** este punto vale la pena entenderlo. Cuando inicias sesión, Django guarda en tu sesión un valor derivado de tu contraseña. En cada página que pides, compara ese valor con el que corresponde a tu contraseña actual. Al cambiarla, dejan de coincidir y la sesión se descarta.

¿Por qué es tan importante? Imagina que alguien te robó la contraseña y está dentro de tu cuenta. Tú la cambias para echarlo. Si las sesiones no cayeran, **él seguiría dentro** con su sesión abierta, y el cambio no habría servido de nada.

### 18.9 Las seis ideas que debes poder explicar sin dudar

1. **El sistema no puede enviarte tu contraseña** porque no la tiene: solo guarda un hash irreversible. Un sistema que puede enviártela está guardándola mal.
2. **El token es una firma, no un dato guardado.** No existe tabla de tokens: Django recalcula la firma para verificarla.
3. **El enlace sirve una sola vez porque el hash de la contraseña es parte de la firma.** Al cambiar la contraseña, la firma vieja deja de coincidir. Es automático.
4. **La respuesta es igual exista o no la cuenta**, para que nadie pueda usar el formulario para averiguar quién está registrado.
5. **Cambiar la contraseña expulsa a quien estuviera dentro**, porque invalida todas las sesiones abiertas.
6. **Esta funcionalidad no necesitó migraciones**, porque no cambió la estructura de la base de datos: solo actualiza el valor de una columna que ya existía.

---

## Apéndice A · Comandos rápidos

```bash
# Levantar y probar (el correo sale por la terminal)
cd backend
python manage.py runserver
#   → http://127.0.0.1:8000/login/ → "¿Olvidaste tu contraseña?"

# Pruebas
python manage.py test                                   # 80 pruebas
python manage.py test usuarios.tests.CambioContrasenaTest -v 2
python manage.py test usuarios.tests.ValidacionTokenTest -v 2

# Verificar que no hay migraciones pendientes
python manage.py makemigrations --check --dry-run        # "No changes detected"

# Ver la configuración de correo que Django está usando
python manage.py shell -c "from django.conf import settings; print(settings.EMAIL_BACKEND, settings.PASSWORD_RESET_TIMEOUT)"

# Probar el envío de correo aislado del formulario
python manage.py shell -c "from django.core.mail import send_mail; print(send_mail('Prueba','Cuerpo',None,['destino@ejemplo.cl']))"
```

### Demostración en el shell (efectiva ante el profesor)

```python
from usuarios.models import Usuario
from django.contrib.auth.tokens import default_token_generator

u = Usuario.objects.get(email="censista@opso.cl")

# 1. El sistema no conoce la contraseña, solo su hash
print(u.password)

# 2. Se genera un token y se verifica
token = default_token_generator.make_token(u)
print(token)
print(default_token_generator.check_token(u, token))    # True

# 3. Se cambia la contraseña...
u.set_password("OtraClaveNueva2026#")
u.save()

# 4. ...y el token anterior queda inservible SOLO, sin borrar nada
print(default_token_generator.check_token(u, token))    # False
```
