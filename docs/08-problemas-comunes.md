# 8. Problemas comunes en producción

Para cada problema: cómo se manifiesta, cómo confirmar la causa y cómo se resuelve. Empieza
siempre por localizar **en qué tramo** está el fallo:

```
teléfono ──①── operador ──②── centralita ──③── bot ──④── proveedores (STT, LLM, TTS)
```

| Comprobación | Si funciona, descarta |
| --- | --- |
| Llamar a la extensión de eco (**9196**) | ① y ②: señalización, audio y NAT hasta la centralita |
| Llamada sin teléfono (`channel originate` / `originate`, ver README) | ③: que la centralita llega al bot y se autentica |
| `docker compose logs bot` durante una llamada | ④: errores de los proveedores |

Herramientas:

```bash
docker compose logs -f bot                                         # el bot
docker compose exec asterisk asterisk -rvvv                        # consola de Asterisk
docker compose exec asterisk asterisk -rx "core show channels"     # llamadas activas
docker compose exec freeswitch sh -c 'fs_cli -p "$FREESWITCH_ESL_PASSWORD"'   # consola de FreeSWITCH
```

## Audio

### No se oye nada, o solo en un sentido

**Causa casi segura: NAT.** La señalización llega, pero el audio se envía a una dirección
equivocada.

- Confirma: la llamada conecta y dura, pero la extensión de eco tampoco se oye.
- Resuelve:
  1. `EXTERNAL_IP` debe ser la dirección por la que el teléfono o el operador alcanzan la
     centralita (IP pública con un troncal, IP local en una red de oficina).
  2. El rango RTP (`17000-17040` Asterisk, `16384-16424` FreeSWITCH) abierto en el cortafuegos
     y publicado en `compose.yaml`.
  3. En producción, `network_mode: host`.

### El eco funciona, pero el agente no habla

El audio llega a la centralita; el fallo está del bot en adelante.

- **El bot no arrancó**: `docker compose ps`. Sin las claves de API se detiene al iniciar y lo
  dice en su registro.
- **Credencial rechazada**: el bot registra `Rejected WebSocket`. `BOT_TOKEN` debe ser el mismo
  en el bot y en la centralita; tras cambiarlo, reinicia ambos.
- **Un proveedor rechaza la clave**: errores `401` en el registro del bot. La llamada se queda
  en silencio (ver [guía 6](06-produccion.md), flujo de fallos).
- **FreeSWITCH: el bot no alcanza el event socket**: el registro del bot dice
  `lost the event socket connection; audio will not play`. Revisa `FREESWITCH_ESL_HOST`, la
  contraseña y la lista de acceso `esl_clients` en `acl.conf.xml`.

### La voz del agente se corta o suena a saltos

- **Asterisk**: los mensajes de audio deben medir un múltiplo exacto de la trama; lo que sobra
  se descarta. El adaptador lo garantiza con `fixed_audio_packet_size`; revísalo si cambiaste el
  códec del dialplan (`c(slin)` → `c(slin16)` cambia el tamaño de trama).
- **FreeSWITCH**: falta `rtp-timer-name=soft` en el perfil SIP por el que entra la llamada.
- **El bot va justo de CPU**: los envíos se retrasan y la centralita rellena con silencio.
  Mira el uso de CPU por réplica y añade réplicas.
- **Pérdida de paquetes** entre el teléfono y la centralita: se oye igual en la extensión de eco.

### El agente suena distorsionado o demasiado fuerte

La voz sintetizada sale por encima del nivel telefónico. Baja `OUTPUT_GAIN_DB` (por defecto
`-12`; prueba `-15`). Si suena débil, súbelo de 3 en 3 dB.

### El agente se oye a sí mismo y se interrumpe solo

Eco: el teléfono devuelve la voz del bot por el micrófono (manos libres, altavoces).

1. Baja `OUTPUT_GAIN_DB`: menos volumen, menos eco.
2. Sube `VAD_MIN_VOLUME` (de `0.4` a `0.5`) o `VAD_CONFIDENCE`: hará falta hablar más alto para
   interrumpir.

Son dos fuerzas opuestas: cuanto más sensible la interrupción, más fácil que el eco la dispare.

## Conversación

### No puedo interrumpir al agente

- El VAD no detecta la voz porque llega baja: baja `VAD_MIN_VOLUME`.
- El teléfono silencia el micrófono porque el bot suena fuerte: baja `OUTPUT_GAIN_DB`.
- **FreeSWITCH**: cada reproducción que empieza hace perder unos 35 ms del audio de quien llama.
  Con bloques pequeños el bot se queda sordo mientras habla. Comprueba que el pipeline incluye
  `serializer.lookahead()` (lo añade el adaptador).

### El agente tarda en contestar

Mide dónde se va el tiempo antes de tocar nada (activa las métricas de Pipecat,
[guía 6](06-produccion.md)).

| Tramo lento | Qué hacer |
| --- | --- |
| LLM | `LLM_EFFORT=low`, un modelo más rápido (`claude-haiku-5-5`), prompt más corto, caché de prompt |
| Fin de turno | El agente espera demasiado para decidir que terminaste: ajusta el silencio de fin de turno del VAD |
| TTS | Frases más cortas (el primer audio sale antes); un modelo de voz más rápido |
| Red | Bot y centralita lejos de la región de los proveedores |
| Herramientas | Una consulta lenta a tu sistema: que el agente diga "un momento" y pon un tiempo máximo |

### El agente me corta antes de terminar

El VAD da el turno por terminado en una pausa. Sube el tiempo de silencio de fin de turno
(`stop_secs` en `VADParams`, `src/agent/pipeline.py`) o usa una estrategia de fin de turno más
elaborada de Pipecat. Es el equilibrio contrario al anterior: más espera, menos cortes, más
latencia.

### Entiende mal nombres, números o productos

- Fija el idioma (`AGENT_LANGUAGE`) y pasa el vocabulario del negocio al reconocimiento.
- Pide en el prompt que confirme los datos críticos repitiéndolos.
- Números largos, por teclado.
- Detalle en la [guía 4](04-prompts.md).

### Lee símbolos, o dice los números raros

Es el prompt: el LLM está escribiendo para la vista. Refuerza las reglas de voz (sin listas ni
símbolos, números como se dicen) y, para códigos y teléfonos, que los escriba separados.

### No cuelga, o cuelga a media despedida

- **No cuelga**: el LLM no llama a `end_call`. Revisa que el prompt diga cuándo terminar y que
  la descripción de la herramienta sea clara.
- **Corta la despedida**: los adaptadores esperan a que termine de sonar antes de colgar. Si
  ocurre, mira si el LLM llama a la herramienta *antes* de escribir la despedida; pídele que se
  despida y use la herramienta en el mismo turno.

## Conexión y capacidad

### Las llamadas se cortan a los 30 segundos

La centralita envía `200 OK` y nunca recibe el `ACK`, así que da la llamada por perdida. Es NAT
en la señalización: `EXTERNAL_IP` y que el puerto SIP sea el mismo dentro y fuera del contenedor
(por eso `compose.yaml` publica `5070:5070` y no `5070:5060`).

### El softphone no registra

- Puerto: Asterisk `5070`, FreeSWITCH `5080` (no el 5060 habitual).
- Contraseña: `SIP_PASSWORD` del `.env`; usuario `1000` o `1001`.
- Mira el intento en la consola de la centralita: `401` repetido es contraseña; nada es red.

### Funciona con pocas llamadas y falla al subir

| Síntoma | Causa | Arreglo |
| --- | --- | --- |
| Las llamadas nuevas no tienen audio | Rango RTP agotado (dos puertos por llamada) | Amplía el rango en la centralita **y** en `compose.yaml` |
| Algunas llamadas se quedan mudas, con errores `429` o de conexión en el bot | Límite de concurrencia de un proveedor | Sube el plan o limita las llamadas simultáneas en la centralita |
| Todas las llamadas se degradan a la vez | El bot sin CPU | Más réplicas |
| FreeSWITCH rechaza llamadas | `max-sessions` (100) | Súbelo en `switch.conf.xml` |

### Quedan llamadas "fantasma"

Canales que siguen abiertos sin nadie.

- Confirma: `core show channels` / `show channels` muestra llamadas más largas de lo posible.
- Causa habitual: quien llama colgó pero la pata del bot siguió, o al revés.
- Resuelve: duración máxima en el dialplan ([guía 6](06-produccion.md)) como red de seguridad, y
  revisa el registro del bot para ese identificador de llamada.

### Tras un despliegue se cortaron llamadas

Parar una réplica del bot corta sus llamadas. Vacía antes de retirar
([guía 6](06-produccion.md), flujo de despliegue).

## Coste

### La factura sube más que las llamadas

- **Llamadas que no terminan**: pon duración máxima.
- **El prompt crece**: cada turno reenvía toda la conversación. Activa la caché (ya lo está) y
  mantén el prompt estable para que funcione.
- **Modelo sobrado para la tarea**: prueba uno más pequeño con tu conjunto de casos.
- **Llamadas de prueba o de bots** entrando por el troncal: restringe por IP y revisa el origen.

## Cuando nada de lo anterior encaja

Reúne esto antes de pedir ayuda (o de abrir el código):

1. El identificador de la llamada (aparece en `Call ... started` en el registro del bot).
2. El registro del bot y el de la centralita de ese intervalo.
3. Si falla siempre o a veces, y desde cuándo (¿coincide con un despliegue o un cambio de
   prompt?).
4. Si ocurre también en la extensión de eco y en la llamada sin teléfono.
