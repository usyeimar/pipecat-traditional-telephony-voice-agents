# asterisk-telephony Specification

## Purpose

Define cómo el agente atiende llamadas de Asterisk a través de `chan_websocket`: una sola conexión por llamada que lleva el audio en mensajes binarios y el control en mensajes JSON.

## Requirements

### Requirement: Arranque de la llamada con MEDIA_START

Tras aceptar el WebSocket en `/ws/asterisk`, el adaptador DEBE esperar el evento `MEDIA_START` en formato JSON y tomar de él el identificador del canal, el formato de audio y el tamaño de trama. Si se ofrece el subprotocolo `media`, DEBE seleccionarlo.

#### Scenario: Llamada válida

- **WHEN** Asterisk envía `MEDIA_START` con `format` `slin` y `optimal_frame_size` 320
- **THEN** se crea el pipeline a 8000 Hz identificado por el `channel_id` del evento

#### Scenario: Formato de control en texto plano

- **WHEN** el primer mensaje no es JSON
- **THEN** el adaptador envía `HANGUP`, cierra la conexión y no crea pipeline

#### Scenario: MEDIA_START no llega

- **WHEN** pasan 5 segundos sin recibir el primer mensaje
- **THEN** el adaptador envía `HANGUP` y cierra la conexión

### Requirement: Solo audio lineal a 8 o 16 kHz

El adaptador DEBE aceptar únicamente los formatos `slin` (8000 Hz) y `slin16` (16000 Hz) y DEBE rechazar la llamada con cualquier otro.

#### Scenario: Códec comprimido

- **WHEN** `MEDIA_START` anuncia `format` `ulaw`
- **THEN** el adaptador envía `HANGUP` y cierra la conexión

### Requirement: Audio en ambos sentidos

Cada mensaje binario de Asterisk DEBE convertirse en audio de entrada del pipeline. El audio del agente DEBE enviarse en mensajes binarios cuyo tamaño sea exactamente una trama de Asterisk.

#### Scenario: Audio de quien llama

- **WHEN** Asterisk envía un mensaje binario de 320 bytes a 8000 Hz
- **THEN** el pipeline recibe ese audio sin modificar

#### Scenario: Audio del agente

- **WHEN** el agente produce 2 segundos de audio
- **THEN** Asterisk los recibe en mensajes de 320 bytes y los reproduce completos

### Requirement: Atenuación de la voz del agente

El audio del agente DEBE atenuarse según `OUTPUT_GAIN_DB` antes de enviarse.

#### Scenario: Ganancia de -6 dB

- **WHEN** la ganancia configurada es -6,02 dB
- **THEN** cada muestra enviada tiene la mitad de amplitud que la producida

### Requirement: Interrupción

Cuando quien llama interrumpe al agente, el adaptador DEBE enviar `FLUSH_MEDIA` para que Asterisk descarte el audio que aún tiene en cola.

#### Scenario: Quien llama habla encima

- **WHEN** el pipeline emite una interrupción
- **THEN** Asterisk recibe el comando `FLUSH_MEDIA`

### Requirement: Teclas

Un evento `DTMF_END` con un dígito del teclado telefónico DEBE entregarse al pipeline como tecla pulsada. Los dígitos que no existen en un teclado telefónico DEBEN ignorarse.

#### Scenario: Tecla válida

- **WHEN** Asterisk envía `DTMF_END` con `digit` `5`
- **THEN** el pipeline recibe la tecla 5

#### Scenario: Dígito fuera del teclado

- **WHEN** Asterisk envía `DTMF_END` con `digit` `A`
- **THEN** no se entrega nada al pipeline

### Requirement: Colgar sin cortar la despedida

Al terminar el pipeline con normalidad, el adaptador DEBE esperar a que Asterisk haya reproducido el audio ya enviado, más un margen, y entonces enviar `HANGUP` una sola vez. La espera NO DEBE superar 5 segundos. Si el pipeline se cancela, DEBE enviar `HANGUP` sin esperar.

#### Scenario: Fin tras hablar

- **WHEN** el pipeline termina justo después de enviar 2 segundos de audio
- **THEN** `HANGUP` se envía cuando esos 2 segundos han tenido tiempo de reproducirse

#### Scenario: Audio descartado por una interrupción

- **WHEN** hubo una interrupción después del último audio enviado y el pipeline termina
- **THEN** `HANGUP` se envía sin esperar

#### Scenario: Cancelación

- **WHEN** el pipeline se cancela
- **THEN** `HANGUP` se envía de inmediato

#### Scenario: Segundo fin

- **WHEN** el pipeline emite un segundo fin después de haber colgado
- **THEN** no se envía otro `HANGUP`

### Requirement: Número de quien llama

El adaptador DEBE tomar el número de quien llama del parámetro `caller` de la URL del WebSocket, cuando el dialplan lo envía.

#### Scenario: Dialplan con v(caller=...)

- **WHEN** Asterisk abre `/ws/asterisk?caller=1000`
- **THEN** la sesión de la llamada lleva `1000` como número de quien llama
