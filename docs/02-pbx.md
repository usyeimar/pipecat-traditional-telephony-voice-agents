# 2. La centralita (PBX)

## Qué es

Una **PBX** (*Private Branch Exchange*, centralita) es el conmutador telefónico de una
organización. Decide qué pasa con cada llamada: a qué extensión suena, qué menú escucha, en qué
cola espera, por qué línea sale. Asterisk y FreeSWITCH son centralitas por software: un programa
en un servidor en lugar de un armario con cables.

Lo que una PBX hace por ti, y que el agente no tiene que reimplementar:

- **Registrar teléfonos**: saber en qué dirección está cada extensión.
- **Conectar con la red pública** a través de troncales ([guía 3](03-troncales-sip.md)).
- **Enrutar**: el *dialplan* dice qué hacer con cada número marcado.
- **Convertir códecs** entre lo que habla cada extremo.
- **Servicios de llamada**: transferir, poner en espera, colas, grabación, buzón.

## Las piezas

| Pieza | Qué es |
| --- | --- |
| **SIP** | El protocolo de señalización: establece, modifica y termina llamadas. No lleva audio |
| **RTP** | El protocolo que lleva el audio, en paquetes UDP, una vez SIP acordó dónde enviarlo |
| **SDP** | El cuerpo de un mensaje SIP donde cada extremo dice "envíame el audio a esta IP y puerto, con estos códecs" |
| **Extensión** | Un número interno. Puede ser un teléfono (`1000`) o una acción (`9000` = el agente) |
| **Dialplan** | Las reglas que dicen qué hacer con cada número marcado |
| **Canal** | Una "pata" de la llamada dentro de la centralita. Una llamada entre dos teléfonos son dos canales unidos por un puente |
| **Troncal** | La conexión SIP con un operador, por donde entran y salen las llamadas de la red pública |
| **DID** | Un número público que el operador te entrega por el troncal |

Una llamada SIP mínima:

```
teléfono                         centralita
   │ ── INVITE (quiero llamar al 9000, mi audio en IP:puerto) ──▶ │
   │ ◀── 100 Trying / 180 Ringing ─────────────────────────────── │
   │ ◀── 200 OK (contesto, mi audio en IP:puerto) ──────────────── │
   │ ── ACK ─────────────────────────────────────────────────────▶ │
   │ ◀═══════════════ audio RTP en ambos sentidos ═══════════════▶ │
   │ ── BYE (cuelgo) ────────────────────────────────────────────▶ │
```

**El problema clásico: NAT.** SIP anuncia direcciones IP *dentro* de los mensajes. Si la
centralita está tras un NAT (Docker lo es) y anuncia su IP privada, el teléfono envía el audio a
un sitio que no existe: la llamada conecta pero no se oye nada, o se oye en un solo sentido. Por
eso hay que decirle a la centralita qué dirección anunciar (`EXTERNAL_IP`), y por eso en
producción se recomienda `network_mode: host`.

## Cómo se conecta el agente

La centralita trata al agente como un destino más del dialplan. Cuando una llamada llega a la
extensión del agente, la centralita abre un **WebSocket hacia el bot** y le envía el audio de
quien llama. Lo que cambia entre centralitas es cómo vuelve el audio del bot y cómo se controla
la llamada.

### Asterisk: `chan_websocket`

```
teléfono ──SIP/RTP──▶ Asterisk ══ un WebSocket ══▶ bot
                                  audio ⇄ (binario)
                                  control ⇄ (JSON)
```

`chan_websocket` es un *canal*: para Asterisk, el bot es un interlocutor más al que se "marca".

```ini
; asterisk/conf/extensions.conf
exten = 9000,1,Dial(WebSocket/voice_agent/c(slin)f(json)v(caller=${URIENCODE(${CALLERID(num)})}))
```

1. Asterisk abre el WebSocket definido como `voice_agent` en `websocket_client.conf`, con
   credenciales HTTP Basic.
2. Envía `MEDIA_START` (JSON): formato del audio, tamaño de trama, identificador del canal.
3. A partir de ahí, mensajes **binarios** con audio en ambos sentidos y mensajes de **texto**
   con control:

   | Dirección | Mensaje | Significado |
   | --- | --- | --- |
   | Asterisk → bot | `DTMF_END` | Tecla pulsada |
   | bot → Asterisk | `FLUSH_MEDIA` | Descarta el audio en cola (interrupción) |
   | bot → Asterisk | `HANGUP` | Cuelga el canal |

Todo va por una sola conexión, así que no hace falta nada más para manejar la llamada.

### FreeSWITCH: `mod_audio_stream` + event socket

```
teléfono ──SIP/RTP──▶ FreeSWITCH ── WebSocket ──▶ bot      (audio de quien llama)
                          ▲                        │
                          └──── event socket ──────┘      (reproducir, interrumpir, colgar, DTMF)
```

`mod_audio_stream` es una *derivación* del audio de un canal: copia lo que dice quien llama
hacia un WebSocket. La edición libre no reproduce el audio que recibe de vuelta: lo escribe en
un archivo y avisa con un evento. Por eso el bot abre además una conexión al **event socket
(ESL)**, que es la interfaz de control de FreeSWITCH, y por ahí:

- ordena reproducir cada archivo (`playback`),
- corta la reproducción cuando hay una interrupción (`uuid_break`),
- cuelga (`uuid_kill`),
- recibe las teclas (evento `DTMF`).

```xml
<!-- freeswitch/conf/dialplan/default.xml -->
<action application="answer"/>
<action application="set" data='STREAM_EXTRA_HEADERS={"Authorization":"Bearer $${bot_token}"}'/>
<action application="set" data="r=${uuid_audio_stream(${uuid} start $${bot_ws_url} mono 8k ${uuid})}"/>
<action application="park"/>
```

El último argumento de `uuid_audio_stream` es el UUID del canal: el bot lo recibe como primer
mensaje y lo usa para dirigir sus órdenes por el event socket.

### Qué implica la diferencia

| | Asterisk | FreeSWITCH |
| --- | --- | --- |
| Conexiones por llamada | 1 (WebSocket) | 2 (WebSocket + event socket) |
| El bot necesita llegar a la centralita | No | Sí, al puerto 8021 |
| Credencial | HTTP Basic en el WebSocket | Bearer en el WebSocket + contraseña del event socket |
| Riesgo si se filtra la credencial | Abrir llamadas contra el bot | Además, control total de FreeSWITCH por el event socket |
| Interrupción | Vacía una cola de tramas | Corta la reproducción de archivos |

El event socket da control completo de FreeSWITCH (originar llamadas, leer configuración,
colgar cualquier canal). Trátalo como una credencial de administrador: contraseña propia, lista
de acceso y nunca publicado fuera de la red privada.

## El papel de cada uno

Una regla que ahorra problemas de diseño: **la centralita es dueña de la llamada; el agente es
dueño de la conversación.**

- Numeración, horarios, colas, transferencias, grabación y facturación viven en el dialplan.
- Qué decir, qué preguntar y cuándo terminar vive en el agente.
- Cuando el agente necesita algo de telefonía (transferir, colgar), se lo *pide* a la centralita;
  no intenta hacerlo él ([guía 5](05-transferencias.md)).
