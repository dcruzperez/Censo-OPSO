# HU-22 · Sincronizar los datos al recuperar conexión

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como censista, quiero sincronizar los datos cuando exista conexión para enviar la información al servidor central.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3
**Estado:** **satisfecha sin código propio** — es la consecuencia directa del diseño de la HU-21

> Mismo patrón que la HU-17: esta historia no agrega ni una línea de código nueva. Se
> resuelve explicando por qué el mecanismo de la HU-21 —el envío normal del
> formulario— **ya es** la sincronización que pide el enunciado, y por qué construir
> un motor de sincronización aparte habría sido resolver dos veces el mismo problema.

---

## Índice

1. [Por qué esta historia no tiene implementación propia](#1-por-qué-esta-historia-no-tiene-implementación-propia)
2. [Qué es "sincronizar" aquí, exactamente](#2-qué-es-sincronizar-aquí)
3. [La alternativa descartada: un motor de sincronización aparte](#3-la-alternativa-descartada)
4. [Lo que sí falta —y por qué queda fuera de esta historia](#4-lo-que-sí-falta)
5. [Explicación para la defensa](#5-explicación-para-la-defensa)
6. [Posibles preguntas del profesor](#6-posibles-preguntas-del-profesor)

---

## 1. Por qué esta historia no tiene implementación propia

Leída junto a su vecina, el par de historias dice algo coherente: la HU-21 guarda lo
que el censista escribe mientras no hay conexión (o mientras se corta a ratos); esta
pide que, cuando la conexión vuelva, **eso llegue al servidor**. Antes de programar un
mecanismo de sincronización se revisó qué construyó la HU-21, y resultó que la
pregunta "¿cómo llega el dato al servidor?" ya tenía una respuesta desde antes de que
existiera esta historia: **el mismo botón "Guardar" de siempre**, el POST normal de un
formulario HTML que este proyecto usa en todas partes.

`autoguardado.js` (HU-21) no guarda una cola de encuestas completas pendientes de
enviar en algún almacén propio de OPSO. Guarda, en el navegador, una copia de lo que
hay ESCRITO EN LA PANTALLA que está abierta ahora mismo. Cuando el censista aprieta
"Guardar" —con conexión, que es el único momento en que tiene sentido apretarlo— ese
envío es indistinguible de cualquier otro guardado que el sistema ya hacía desde la
HU-08, HU-09, HU-10 y HU-11. No hay un segundo camino que sincronizar.

---

## 2. Qué es "sincronizar" aquí

Dicho en un diagrama:

```
Conexión intermitente:

  [escribe]  --corte--  [sigue escribiendo, localStorage lo protege (HU-21)]
      │                                                    │
      └── conexión vuelve ── [aprieta "Guardar"] ── POST normal ── servidor
                                                        ↑
                                            ESTO es la sincronización.
                                       No hay un paso más entre "hay señal"
                                       y "el dato ya está en PostgreSQL".
```

"Sincronizar" en la lectura habitual del término —una app que guarda registros
completos localmente y los reenvía en lote más tarde, resolviendo conflictos si el
servidor cambió entretanto— es un problema que corresponde al escenario de
**desconexión total durante horas**, que la conversación previa a la HU-21 descartó
explícitamente por no ser el escenario real (ver `docs/HU-21_*.md`, §1 y §2). Con
conexión intermitente, no hay nada que reconciliar: el navegador nunca llegó a tener
una copia de una encuesta que el servidor no tuviera también, porque cada paso del
flujo (vivienda, hogar, cada integrante) ya se guarda en su propio POST desde que
existen esas historias.

---

## 3. La alternativa descartada

Se evaluó, y se descartó, construir un mecanismo explícito de sincronización: una cola
en `IndexedDB` con las encuestas completas armadas en el cliente, un detector de
`navigator.onLine` que reintente el envío automáticamente al recuperar señal, y algún
criterio para resolver qué hacer si el servidor rechaza un envío tardío (¿la encuesta
sigue abierta? ¿alguien más la tocó mientras tanto?).

Se descartó por dos razones:

1. **Resolvería un problema que no es el real.** Ese diseño tiene sentido para
   desconexión total, no para conexión intermitente. Construirlo de todos modos habría
   sido la puerta de entrada, no pedida, hacia la PWA completa que la HU-21 decidió no
   construir.
2. **Introduciría justo el riesgo que el diseño actual evita.** Un reintento
   automático en segundo plano puede enviar una encuesta minutos u horas después de
   que el censista creyó haberla completado, sin que la vea en pantalla en ese
   momento. El diseño actual —el censista aprieta "Guardar" y ve el resultado ahí
   mismo, con los mensajes de éxito o de error que el sistema ya muestra— es más
   simple y más seguro: nunca hay un envío que ocurra sin que la persona lo sepa.

---

## 4. Lo que sí falta

Nada, dentro del alcance que el usuario confirmó para este par de historias. Si en el
futuro el escenario real cambiara a "sin conexión todo el día", esta historia y la
HU-21 tendrían que revisarse juntas —no por separado—, porque en ese escenario sí
haría falta una cola de sincronización real, y el diseño actual de `autoguardado.js`
(pensado para una pantalla a la vez, sin cola) no alcanzaría.

---

## 5. Explicación para la defensa

**En una frase:** "sincronizar cuando vuelve la conexión" ya estaba resuelto por el
mismo botón "Guardar" que existe desde la HU-08; lo único que faltaba era proteger lo
escrito ANTES de apretarlo, que es exactamente lo que construyó la HU-21.

**Lo que conviene poder defender:**

1. **Las dos historias del enunciado describen un solo mecanismo visto desde dos
   momentos.** HU-21 protege el "antes" (mientras se escribe, sin señal); esta HU
   pregunta por el "después" (cuando vuelve la señal), y el "después" ya estaba
   resuelto por el flujo normal de guardado.
2. **No se construyó una cola de sincronización porque no hay nada que poner en
   ella.** Cada paso de la encuesta se guarda en su propio POST desde que existen esas
   pantallas; `localStorage` nunca acumula una encuesta completa esperando enviarse,
   solo el contenido de un formulario abierto.
3. **Un reintento automático en segundo plano se evaluó y se rechazó a propósito**,
   porque introduciría un envío que el censista no ve ocurrir, contrario al principio
   de que cada guardado se confirma en pantalla.

---

## 6. Posibles preguntas del profesor

**Si no hay código nuevo, ¿qué demuestra esta historia?**
Que se investigó antes de programar, igual que en cada HU de este proyecto. Escribir
un motor de sincronización sin revisar primero qué hacía ya la HU-21 habría producido
código redundante resolviendo un problema inexistente en el escenario confirmado.

**¿Qué pasaría si un censista pierde señal DESPUÉS de apretar "Guardar" pero antes de
que el servidor responda?**
Es el límite que ya documenta `docs/HU-21_*.md` §6: el navegador no llega a cambiar de
página, así que la pantalla sigue abierta con lo escrito visible, y el censista puede
volver a intentar apenas tenga señal. No se pierde el dato en ese instante; si además
cierra la pestaña sin reintentar, sí se pierde, y es una limitación conocida del
diseño optimista elegido, no un caso que esta historia resuelva de otra forma.

**¿Por qué no usar el evento `navigator.onLine` / `online` del navegador para
reintentar automáticamente?**
Porque introduciría un envío en segundo plano que el censista no presenciaría, y este
proyecto —incluida la propia HU-21— prioriza que cada guardado se confirme en pantalla
en el momento en que ocurre. Es la misma razón por la que se descartó la cola de
sincronización del §3.
