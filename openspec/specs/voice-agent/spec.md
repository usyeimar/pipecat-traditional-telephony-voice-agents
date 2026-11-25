# voice-agent Specification

## Purpose

Define la conversación que el agente mantiene en una llamada, con independencia de la centralita de la que venga: cómo arranca, cómo recibe lo que dice y marca quien llama, cómo termina y qué configuración necesita.

## Requirements

### Requirement: Configuración validada al arrancar

El agente DEBE leer su configuración del entorno al arrancar y NO DEBE iniciar el servidor si falta `BOT_TOKEN`, `DEEPGRAM_API_KEY`, `ANTHROPIC_API_KEY` o `CARTESIA_API_KEY`, si el archivo del prompt no existe o está vacío, o si una variable numérica no es un número. El error DEBE nombrar todas las variables que faltan a la vez.

#### Scenario: Faltan varias variables

- **WHEN** el entorno no define `BOT_TOKEN` y `CARTESIA_API_KEY` está vacía
- **THEN** el arranque falla con un error que nombra `BOT_TOKEN` y `CARTESIA_API_KEY`

#### Scenario: Valor numérico inválido

- **WHEN** `PORT` vale `abc`
- **THEN** el arranque falla indicando que hay un número inválido

#### Scenario: Prompt ausente

- **WHEN** `AGENT_PROMPT_FILE` apunta a un archivo que no existe
- **THEN** el arranque falla indicando que no puede leer el prompt

### Requirement: El agente habla primero

Al conectarse una llamada, el agente DEBE generar un saludo sin esperar a que quien llama hable.

#### Scenario: Llamada recién contestada

- **WHEN** la centralita conecta una llamada con el agente
- **THEN** el agente pide al LLM un saludo y lo envía como audio

### Requirement: Pipeline a la frecuencia de la llamada

El pipeline DEBE ejecutarse, en entrada y en salida, a la frecuencia de muestreo que el adaptador declara para la llamada, de modo que el audio no se remuestree dentro del agente.

#### Scenario: Llamada a 8 kHz

- **WHEN** el adaptador entrega una llamada a 8000 Hz
- **THEN** el pipeline recibe y produce audio a 8000 Hz

### Requirement: Teclas como texto

Las teclas que quien llama pulse DEBEN llegar al LLM como texto con la forma `DTMF: <teclas>`.

#### Scenario: Quien llama marca dígitos

- **WHEN** quien llama pulsa `1`, `2` y `#`
- **THEN** el LLM recibe un mensaje de usuario `DTMF: 12#`

### Requirement: El agente termina la llamada

El agente DEBE ofrecer al LLM una herramienta `end_call` sin argumentos. Al usarla, el audio ya generado DEBE reproducirse completo antes de que la llamada se cuelgue.

#### Scenario: Despedida

- **WHEN** el LLM se despide y llama a `end_call` en el mismo turno
- **THEN** quien llama oye la despedida completa y después la llamada se cuelga

### Requirement: Independencia de la centralita

El código de la conversación NO DEBE depender de ninguna centralita: recibe de cada adaptador una sesión con el transporte, el identificador de la llamada, su frecuencia de muestreo y, si se conoce, el número de quien llama.

#### Scenario: Misma conversación en dos centralitas

- **WHEN** entra una llamada por Asterisk y otra por FreeSWITCH
- **THEN** ambas ejecutan el mismo pipeline con el mismo prompt y las mismas herramientas

### Requirement: Cierre al colgar quien llama

Cuando la centralita cierra la conexión de una llamada, el agente DEBE cancelar su pipeline y liberar lo que el adaptador mantenga para esa llamada.

#### Scenario: Quien llama cuelga

- **WHEN** quien llama cuelga a mitad de la conversación
- **THEN** el pipeline de esa llamada se cancela y las demás llamadas no se ven afectadas
