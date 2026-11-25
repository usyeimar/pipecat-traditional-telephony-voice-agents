# 1. El audio

Un agente de voz es, antes que nada, un programa que recibe y envía audio en tiempo real. Casi
todos los problemas raros ("no me oye", "se corta", "suena metálico") se explican con los
conceptos de esta página.

## Del sonido a los números

Un micrófono convierte la presión del aire en una señal eléctrica. Digitalizarla es medir esa
señal muchas veces por segundo y guardar cada medida como un número.

- **Frecuencia de muestreo**: cuántas medidas por segundo. Una señal muestreada a `N` Hz solo
  puede representar sonidos de hasta `N/2` Hz.
- **Profundidad**: cuántos bits tiene cada medida. Con 16 bits, cada muestra es un entero entre
  -32768 y 32767.
- **Canales**: uno (mono) en telefonía.

Ese formato, sin comprimir, se llama **PCM lineal**. En Asterisk es `slin` (*signed linear*) y en
FreeSWITCH `L16`. Es lo único que entienden los modelos de voz, y por eso es lo que viaja entre
la centralita y el bot.

| Calidad | Muestreo | Voz que cabe | Dónde aparece |
| --- | --- | --- | --- |
| Telefónica (banda estrecha) | 8 000 Hz | hasta ~3,4 kHz | red telefónica, G.711 |
| Banda ancha ("HD") | 16 000 Hz | hasta ~7 kHz | G.722, Opus entre softphones |
| Estudio | 44 100 / 48 000 Hz | todo el rango audible | música, vídeo |

A 8 kHz se pierden las frecuencias altas, que es donde viven consonantes como la *s* y la *f*.
Por eso por teléfono se confunden "seis" y "siete" o los apellidos, y por eso los modelos de voz
a texto aciertan menos con audio telefónico que con un micrófono.

**Cuentas útiles.** PCM de 16 bits, mono, a 8 kHz son 16 000 bytes por segundo. 20 ms de audio
son 160 muestras, 320 bytes: justo el `optimal_frame_size` que Asterisk anuncia para `slin`.

## Códecs

Un códec comprime el audio para enviarlo por la red.

| Códec | Muestreo | Ancho de banda | Notas |
| --- | --- | --- | --- |
| G.711 (PCMU / PCMA) | 8 kHz | 64 kbit/s | El de la red telefónica. PCMU (ley µ) en América, PCMA (ley A) en Europa |
| G.722 | 16 kHz | 64 kbit/s | Banda ancha entre teléfonos IP |
| Opus | hasta 48 kHz | variable | El mejor, pero casi ningún operador lo acepta en un troncal |
| G.729 | 8 kHz | 8 kbit/s | Muy comprimido; degrada el reconocimiento |

Este proyecto usa **G.711 a 8 kHz de extremo a extremo**: es lo que entrega un troncal real, y
al no cambiar de frecuencia en ningún punto no hay que remuestrear. Remuestrear cuesta CPU, añade
retardo y, si se hace por bloques, deja chasquidos en las uniones.

La centralita hace la conversión entre G.711 (lo que habla el teléfono) y PCM lineal (lo que
habla el bot). El bot nunca ve audio comprimido.

## Cómo viaja: tramas, RTP y tiempo real

El audio no se envía de golpe, sino en **tramas** de 20 ms (el *ptime*). Entre el teléfono y la
centralita cada trama va en un paquete **RTP** sobre UDP: si un paquete se pierde no se reenvía,
porque llegaría tarde. Entre la centralita y el bot va por WebSocket (TCP).

La consecuencia práctica: **el audio hay que entregarlo al ritmo al que se reproduce**. Un texto
a voz genera un segundo de audio en mucho menos de un segundo; si el bot lo enviara todo de
golpe, la centralita lo acumularía en una cola y una interrupción llegaría tarde. Por eso el
transporte de Pipecat envía al ritmo real y cada adaptador sabe vaciar la cola de su centralita.

## Los cuatro problemas de la voz por teléfono

**Latencia.** El silencio entre que la persona calla y el bot contesta. Se suma en cadena:
detectar que terminó de hablar, transcribir, pensar (LLM), sintetizar y transportar. El LLM y la
detección de fin de turno son los que más pesan. Una persona nota la pausa a partir de más o
menos un segundo.

**Detección de voz (VAD).** Un modelo pequeño (Silero) decide en cada trama si hay voz. De él
dependen dos cosas: saber cuándo la persona terminó su turno y saber cuándo interrumpe al bot. El
audio telefónico llega mucho más bajo que el de un micrófono, así que el umbral de volumen por
defecto de Pipecat (`0.6`) se pierde interrupciones; aquí es `0.4` (`VAD_MIN_VOLUME`).

**Interrupción (*barge-in*).** Cuando la persona habla encima del bot hay que hacer tres cosas a
la vez: dejar de generar, dejar de enviar y **descartar lo que la centralita ya tiene en cola**.
En Asterisk es el comando `FLUSH_MEDIA`; en FreeSWITCH, `uuid_break` por el event socket.

**Eco y nivel.** El bot no debe oírse a sí mismo. Los teléfonos cancelan el eco, pero lo hacen
bajando el micrófono cuando suena el altavoz: si la voz del bot llega demasiado fuerte, el
teléfono silencia a quien llama y la interrupción deja de funcionar. La voz sintetizada sale unos
12 dB por encima del nivel telefónico, y por eso se atenúa antes de enviarla (`OUTPUT_GAIN_DB`).

## DTMF: las teclas

Las teclas del teléfono no viajan como sonido (o no solo). Lo habitual es **RFC 2833/4733**: un
evento dentro de RTP que dice "tecla 5". La centralita lo traduce y se lo entrega al bot como un
mensaje (`DTMF_END` en Asterisk, un evento del event socket en FreeSWITCH), y el bot se lo pasa al
LLM como texto: `DTMF: 123#`.

Las teclas son más fiables que la voz para números largos y, sobre todo, permiten capturar datos
sensibles sin que pasen por el reconocimiento de voz ni por el LLM (ver
[casos avanzados](07-casos-avanzados.md)).

## Dónde está cada cosa en el código

| Concepto | Dónde |
| --- | --- |
| Frecuencia de la llamada (8 kHz) | `SAMPLE_RATE` en `src/telephony/freeswitch.py`; en Asterisk la anuncia `MEDIA_START` |
| Tramas exactas hacia Asterisk | `fixed_audio_packet_size` en `src/telephony/asterisk/router.py` |
| Atenuación de la voz del bot | `output_gain_db` en `src/config.py` |
| Umbrales del VAD | `vad_min_volume` y `vad_confidence` en `src/config.py` |
| Esperar a que termine el audio antes de colgar | `_wait_for_playout` en `src/telephony/asterisk/serializer.py` |
