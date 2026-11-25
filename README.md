<img src="assets/icon.svg" width="64" height="64" alt="">

# Pipecat Traditional Telephony Voice Agents

Agente de voz con [Pipecat](https://pipecat.ai) que atiende llamadas de centralitas
tradicionales: **Asterisk** y **FreeSWITCH**. El agente es el mismo; solo cambia el adaptador de
cada centralita.

```
                      ┌─ Asterisk ──── chan_websocket ───────────────┐
teléfono ──SIP/RTP──▶ │                                              ├──▶ bot (Pipecat)
                      └─ FreeSWITCH ── mod_audio_stream + ESL ───────┘
                                                        Deepgram → Claude → Cartesia
```

- [Por qué](#por-qué)
- [El problema](#el-problema)
- [Cómo usarlo](#cómo-usarlo)
- [Cómo configurar el proyecto paso a paso](#cómo-configurar-el-proyecto-paso-a-paso)
- [Cómo escalar](#cómo-escalar)
- [Guías](#guías)
- [Estructura del código](#estructura-del-código)
- [Desarrollo](#desarrollo)

## Por qué

Muchas empresas ya tienen su telefonía en Asterisk o FreeSWITCH: troncales SIP, extensiones,
colas, IVR y años de dialplan. Para ponerles un agente de voz con IA no hace falta migrar a una
plataforma de telefonía en la nube ni pagar minutos a un intermediario: la centralita ya sabe
contestar llamadas, y solo necesita un sitio al que enviar el audio.

Este proyecto es ese sitio. La centralita sigue siendo la dueña de la llamada (numeración,
enrutamiento, transferencias, grabación) y delega la conversación en un agente Pipecat que corre
en tu propia infraestructura.

## El problema

Pipecat trae integraciones para proveedores en la nube (Twilio, Telnyx, Plivo...), pero no para
las centralitas tradicionales. Conectarlas a mano tiene más trampas de las que parece:

- **Cada centralita habla un protocolo distinto.** Asterisk envía audio y control por un
  WebSocket (`chan_websocket`). El `mod_audio_stream` libre de FreeSWITCH solo envía el audio de
  quien llama: para reproducir la voz del bot, interrumpirla o colgar hay que manejar la llamada
  por el event socket (ESL).
- **El audio de teléfono no es el de un micrófono.** Llega a 8 kHz y mucho más bajo, así que la
  detección de voz por defecto no nota cuando alguien interrumpe al bot. Y la voz sintetizada
  sale unos 12 dB por encima del nivel telefónico: distorsiona y hace que el teléfono silencie a
  quien llama.
- **Los detalles de cada protocolo cortan el audio.** Asterisk descarta lo que no llena una
  trama exacta, y colgar descarta lo que aún no se ha reproducido, así que la despedida se queda
  a medias si no se espera lo justo.
- **Sin autenticación, cualquiera que alcance el puerto del bot** puede abrir llamadas contra
  tus claves de API o, en FreeSWITCH, colgar llamadas ajenas.
- **Mezclar todo eso con la lógica del agente** obliga a reescribirlo por cada centralita.

Aquí cada uno de esos puntos está resuelto en un adaptador por centralita, y la conversación
(voz a texto, LLM, texto a voz, herramientas) vive aparte y no sabe de dónde viene la llamada.

| | Asterisk | FreeSWITCH |
| --- | --- | --- |
| Módulo | `chan_websocket` (Asterisk 22.6+) | `mod_audio_stream` (edición libre) |
| Audio del bot | por el mismo WebSocket | archivos que FreeSWITCH reproduce vía event socket |
| Interrumpir / colgar / DTMF | mensajes JSON en el WebSocket | event socket (ESL) |
| Serializer | propio: [`telephony/asterisk`](src/telephony/asterisk) | [`pipecat-freeswitch`](https://github.com/marujofln/pipecat-freeswitch) |
| Endpoint del bot | `/ws/asterisk` | `/ws/freeswitch` |
| Puerto SIP | 5070 | 5080 |

## Cómo usarlo

Con el proyecto ya configurado (sección siguiente):

```bash
docker compose up -d --build     # bot + las centralitas elegidas en COMPOSE_PROFILES
docker compose logs -f bot       # sigue las llamadas
```

Registra un softphone (Linphone, Zoiper, MicroSIP...) y llama a la extensión **9000**:

| Campo      | Asterisk                    | FreeSWITCH              |
| ---------- | --------------------------- | ----------------------- |
| Servidor   | `127.0.0.1:5070` (UDP)      | `127.0.0.1:5080` (UDP)  |
| Usuario    | `1000` (o `1001`)           | `1000` (o `1001`)       |
| Contraseña | `SIP_PASSWORD` de tu `.env` | la misma                |
| Códec      | PCMU o PCMA (G.711)         | PCMU o PCMA (G.711)     |

Durante la llamada:

- El agente saluda, conversa y **cuelga solo** cuando te despides (herramienta `end_call`).
- Puedes **interrumpirlo** hablando encima: deja de hablar y te escucha.
- Las **teclas** que marques le llegan como texto (`DTMF: 123#`).
- La extensión **9196** es una prueba de eco, para comprobar el audio sin el bot.

Para usarlo desde tu propio dialplan, envía la llamada al bot igual que lo hace la extensión
9000:

```ini
; Asterisk (extensions.conf)
same = n,Dial(WebSocket/voice_agent/c(slin)f(json)v(caller=${URIENCODE(${CALLERID(num)})}))
```

```xml
<!-- FreeSWITCH (dialplan) -->
<action application="answer"/>
<action application="set" data='STREAM_EXTRA_HEADERS={"Authorization":"Bearer $${bot_token}"}'/>
<action application="set" data="r=${uuid_audio_stream(${uuid} start $${bot_ws_url} mono 8k ${uuid})}"/>
<action application="park"/>
```

## Cómo configurar el proyecto paso a paso

**1. Requisitos.** Docker con Compose v2, y [uv](https://docs.astral.sh/uv/) si vas a
desarrollar. Cuentas en [Deepgram](https://console.deepgram.com),
[Anthropic](https://console.anthropic.com) y [Cartesia](https://play.cartesia.ai).

**2. Crea el archivo de entorno.**

```bash
cp .env.example .env
```

**3. Pon las claves de API** en `.env`: `DEEPGRAM_API_KEY`, `ANTHROPIC_API_KEY` y
`CARTESIA_API_KEY`.

**4. Genera los secretos.** Uno distinto para cada variable:

```bash
openssl rand -hex 32   # BOT_TOKEN: credencial de la centralita ante el bot
openssl rand -hex 32   # FREESWITCH_ESL_PASSWORD: event socket (solo FreeSWITCH)
openssl rand -hex 8    # SIP_PASSWORD: cuentas 1000 y 1001 de los softphones
```

**5. Elige las centralitas** con `COMPOSE_PROFILES`: `asterisk`, `freeswitch` o
`asterisk,freeswitch`.

**6. Ajusta la red** si hace falta:

| Variable | Por defecto | Cuándo cambiarla |
| --- | --- | --- |
| `EXTERNAL_IP` | `127.0.0.1` | Pon la IP local de la máquina para llamar desde otros dispositivos |
| `ASTERISK_SIP_PORT` | `5070` | Si el puerto está ocupado |
| `SIP_PORT` | `5080` | Puerto SIP de FreeSWITCH, si está ocupado |

**7. Construye y arranca.** La primera vez se compilan las centralitas: Asterisk ~5 min,
FreeSWITCH 15-30 min.

```bash
docker compose up -d --build
docker compose ps        # las centralitas deben quedar "healthy"
```

**8. Comprueba sin teléfono.** La centralita se llama a sí misma y el bot debe registrar
`Call ... started`:

```bash
docker compose exec asterisk asterisk -rx "channel originate Local/9000@phones application Echo"

docker compose exec freeswitch sh -c \
  'fs_cli -p "$FREESWITCH_ESL_PASSWORD" -x "originate loopback/9000/default &park()"'

docker compose logs --tail 20 bot
```

**9. Llama desde un softphone** con los datos de [Cómo usarlo](#cómo-usarlo).

**10. Personaliza el agente.**

| Qué | Dónde |
| --- | --- |
| Personalidad e instrucciones | [`prompts/agent.md`](prompts/agent.md) |
| Idioma (`AGENT_LANGUAGE`), modelo (`LLM_MODEL`), voz (`CARTESIA_VOICE_ID`) | `.env` |
| Herramientas (funciones) | [`agent/tools.py`](src/agent/tools.py), lista `TOOLS` |
| Proveedores de voz y LLM | [`agent/services.py`](src/agent/services.py) |
| Extensiones de Asterisk | [`asterisk/conf/extensions.conf`](asterisk/conf/extensions.conf) |
| Extensiones de FreeSWITCH | [`freeswitch/conf/dialplan/default.xml`](freeswitch/conf/dialplan/default.xml) |

Elige en Cartesia una voz nativa del idioma: la voz por defecto habla español con acento.
`LLM_MODEL=claude-haiku-5-5` responde más rápido y cuesta menos. Tras cambiar `.env` o la
configuración de una centralita, `docker compose up -d` (o `docker compose restart <servicio>`).

## Cómo escalar

Cada llamada es un WebSocket y un pipeline independientes dentro del bot; no hay estado
compartido entre llamadas. Eso define cómo crece cada pieza:

**El bot escala en horizontal.** Las conexiones las abre la centralita, así que basta con más
réplicas detrás del mismo nombre:

```bash
docker compose up -d --scale bot=4
```

El DNS de Compose reparte las conexiones nuevas entre las réplicas. En Kubernetes o detrás de un
balanceador, cualquiera que soporte WebSockets sirve; no hacen falta sesiones pegajosas, porque
una llamada vive entera en su conexión. El trabajo local por llamada es la detección de voz
(Silero) y poco más: el resto es esperar a los servicios externos. Mide con tu tráfico cuántas
llamadas aguanta una réplica antes de fijar el número.

**Los proveedores suelen ser el primer límite.** Deepgram y Cartesia limitan las conexiones
simultáneas y Anthropic las peticiones y tokens por minuto, según tu plan. Revisa esos límites
antes de añadir réplicas: una llamada más allá del límite falla aunque sobre CPU.

**Las centralitas tienen su propia capacidad.**

- *Puertos RTP*: cada llamada usa dos. Los rangos publicados (`17000-17040` en Asterisk,
  `16384-16424` en FreeSWITCH) dan para unas 20 llamadas simultáneas cada uno. Amplíalos en
  `asterisk/conf/rtp.conf` o `freeswitch/conf/autoload_configs/switch.conf.xml` **y** en
  `compose.yaml`.
- *Red*: en producción usa Linux con `network_mode: host` en las centralitas. Evita el NAT de
  Docker, que es lo que más limita y complica SIP/RTP.
- *Sesiones*: FreeSWITCH está limitado a 100 (`max-sessions` en `switch.conf.xml`).

**Varias centralitas.** Con Asterisk no hay nada que cambiar: cada instancia abre sus WebSockets
contra el bot. Con FreeSWITCH hay una limitación: el bot conecta al event socket de **un** host
(`FREESWITCH_ESL_HOST`). Para varios FreeSWITCH haría falta que cada llamada indique su host,
por ejemplo como parámetro en la URL del WebSocket, y que el adaptador lo use.

**Latencia.** Pon el bot cerca de la centralita y en la región de los proveedores. El modelo es
lo que más pesa en la pausa antes de cada respuesta: `LLM_EFFORT=low` (por defecto) y
`claude-haiku-5-5` la reducen.

**Seguridad al salir de una sola máquina.**

- Usa `wss://` o una red privada entre la centralita y el bot: con `ws://` la credencial viaja
  en claro.
- El event socket de FreeSWITCH da control total: no publiques el puerto 8021.
- Para recibir llamadas de un troncal SIP hay que añadir el troncal y su contexto; los
  dialplans incluidos solo atienden a los usuarios registrados.

## Guías

En [`docs/`](docs/README.md):

| Guía | Responde a |
| --- | --- |
| [El audio](docs/01-audio.md) | Qué viaja por una llamada y por qué la telefonía suena distinto |
| [La centralita (PBX)](docs/02-pbx.md) | Qué es una PBX y cómo se conecta con el agente |
| [Troncales SIP](docs/03-troncales-sip.md) | Recibir y hacer llamadas reales en Asterisk y FreeSWITCH |
| [Prompts](docs/04-prompts.md) | Escribir mejores prompts para voz, según el proveedor |
| [Transferir la llamada](docs/05-transferencias.md) | Herramientas para pasar la llamada a una persona |
| [Producción](docs/06-produccion.md) | Los flujos para operar el agente |
| [Casos avanzados](docs/07-casos-avanzados.md) | Campañas salientes, datos personales y otras ideas |
| [Problemas comunes](docs/08-problemas-comunes.md) | Diagnosticar y resolver lo que falla en producción |

## Estructura del código

```
src/
├── main.py              punto de entrada
├── config.py            configuración leída del entorno, validada al arrancar
├── app.py               aplicación FastAPI: monta un endpoint por centralita
├── agent/               la conversación, independiente de la centralita
│   ├── services.py        STT, LLM y TTS (cambia aquí de proveedor)
│   ├── tools.py           herramientas que el LLM puede llamar (end_call)
│   └── pipeline.py        arma y ejecuta el pipeline de una llamada
└── telephony/           un adaptador por centralita
    ├── auth.py            autenticación del WebSocket
    ├── freeswitch.py      mod_audio_stream + event socket
    └── asterisk/          chan_websocket
        ├── protocol.py      mensajes de control (JSON)
        ├── serializer.py    frames de Pipecat ⇄ protocolo
        └── router.py        endpoint /ws/asterisk
asterisk/                imagen y configuración de Asterisk
freeswitch/              imagen y configuración de FreeSWITCH
prompts/agent.md         personalidad e instrucciones del agente
tests/                   pruebas unitarias
```

Cada adaptador acepta el WebSocket de su centralita, lo autentica, crea el transporte de Pipecat
con su serializer y entrega una `CallSession` a `agent.run_call`. Para añadir otra centralita
basta un módulo nuevo en `telephony/` con su `create_router` y montarlo en `app.py`.

## Desarrollo

```bash
uv sync                    # instala dependencias y herramientas de desarrollo
uv run pytest              # pruebas
uv run ruff check . && uv run ruff format .
docker compose watch       # recarga el bot al editar src/ o prompts/
```

El bot en tu máquina y las centralitas en Docker:

```bash
# en .env: ASTERISK_BOT_WS_URL=ws://host.docker.internal:8765/ws/asterisk
#          BOT_WS_URL=ws://host.docker.internal:8765/ws/freeswitch
#          FREESWITCH_ESL_HOST=127.0.0.1
docker compose up -d asterisk freeswitch
uv run src/main.py
```

La configuración de Asterisk son plantillas: los valores `${...}` de despliegue (IP, puertos,
secretos) los rellena `asterisk/docker-entrypoint.sh` al arrancar.

## Créditos

La imagen y parte de la configuración de FreeSWITCH están adaptadas del banco de pruebas de
`pipecat-freeswitch` (BSD 2-Clause, ver `freeswitch/LICENSE.pipecat-freeswitch`).
