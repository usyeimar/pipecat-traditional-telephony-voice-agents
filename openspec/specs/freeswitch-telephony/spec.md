# freeswitch-telephony Specification

## Purpose

Define cómo el agente atiende llamadas de FreeSWITCH a través de `mod_audio_stream`: el audio de quien llama llega por un WebSocket y la llamada se maneja por el event socket (ESL), porque la edición libre del módulo no reproduce por sí sola el audio que recibe.

## Requirements

### Requirement: Endpoint condicionado a la configuración

El endpoint `/ws/freeswitch` DEBE servirse solo si `FREESWITCH_ESL_PASSWORD` está definida. El estado del agente (`/health`) DEBE indicar qué centralitas están habilitadas.

#### Scenario: Sin contraseña del event socket

- **WHEN** el agente arranca sin `FREESWITCH_ESL_PASSWORD`
- **THEN** `/health` lista solo `asterisk` y `/ws/freeswitch` no existe

#### Scenario: Con contraseña del event socket

- **WHEN** el agente arranca con `FREESWITCH_ESL_PASSWORD`
- **THEN** `/health` lista `asterisk` y `freeswitch`

### Requirement: Identificación de la llamada por UUID

Tras aceptar el WebSocket, el adaptador DEBE leer como primer mensaje el UUID del canal y DEBE aceptar solo un UUID en forma canónica, porque ese valor se usa en comandos del event socket.

#### Scenario: UUID válido

- **WHEN** el primer mensaje es un UUID canónico
- **THEN** se crea el pipeline y el agente sigue ese canal por el event socket

#### Scenario: Primer mensaje inválido

- **WHEN** el primer mensaje es `not-a-uuid`
- **THEN** la conexión se cierra con el código 1008 y no se crea pipeline

### Requirement: Control de la llamada por el event socket

El adaptador DEBE usar el event socket de FreeSWITCH para reproducir el audio del agente, detener la reproducción cuando quien llama interrumpe, recibir las teclas pulsadas y colgar.

#### Scenario: El agente habla

- **WHEN** el agente produce audio
- **THEN** FreeSWITCH lo reproduce en el canal de la llamada

#### Scenario: Interrupción

- **WHEN** quien llama habla encima del agente
- **THEN** la reproducción en curso se detiene y el audio pendiente se descarta

### Requirement: Audio del agente por adelantado

El audio del agente DEBE entregarse a FreeSWITCH por adelantado y en bloques crecientes, de modo que una respuesta se reproduzca en pocas reproducciones y el agente siga oyendo a quien llama mientras habla.

#### Scenario: Respuesta larga

- **WHEN** el agente produce una respuesta de varios segundos
- **THEN** FreeSWITCH la recibe en unos pocos bloques y no en uno por cada fragmento del transporte

### Requirement: Colgar sin cortar la despedida

Al terminar el pipeline con normalidad, el adaptador DEBE esperar a que FreeSWITCH termine de reproducir el audio pendiente antes de colgar.

#### Scenario: Despedida

- **WHEN** el agente se despide y termina la llamada
- **THEN** quien llama oye la despedida completa antes de que el canal se cuelgue

### Requirement: Limpieza al cerrarse la conexión

Cuando el WebSocket se cierra, el adaptador DEBE colgar el canal si sigue abierto y cerrar su conexión al event socket.

#### Scenario: Quien llama cuelga

- **WHEN** quien llama cuelga
- **THEN** la conexión al event socket de esa llamada se cierra

### Requirement: La centralita cuelga si el agente desaparece

Si el WebSocket con el agente falla o se cae sin un cierre limpio, FreeSWITCH DEBE colgar la llamada en lugar de dejar a quien llama en silencio.

#### Scenario: El agente se cae en mitad de una llamada

- **WHEN** el proceso del agente termina con una llamada en curso
- **THEN** FreeSWITCH cuelga esa llamada
