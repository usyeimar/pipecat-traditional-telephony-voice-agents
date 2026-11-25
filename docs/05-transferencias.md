# 5. Transferir la llamada

Tarde o temprano el agente tiene que pasar la llamada a una persona. Esta guía explica cómo se
implementa como herramienta del LLM en cada centralita.

> Es una **guía de diseño**: la transferencia no está implementada en este repositorio. Lo que
> se apoya en comportamiento comprobado aquí está marcado como *comprobado*.

## La idea

**Quien transfiere es la centralita, no el bot.** El bot solo hace tres cosas:

1. **Decide** que hay que transferir y a dónde (el LLM llama a una herramienta).
2. **Se lo comunica** a la centralita.
3. **Sale de la llamada sin colgarla.**

El tercer punto es donde se rompen las implementaciones: en este proyecto, cuando el pipeline
termina, el adaptador cuelga. Transferir es terminar la conversación *sin* colgar a quien llama.

| Tipo | Qué pasa | Dificultad |
| --- | --- | --- |
| **Ciega** (*cold*) | La llamada se envía al destino y el bot desaparece | Baja. Empieza por aquí |
| **Con contexto** | Igual, pero el destino recibe un resumen (pantalla, nota, susurro) | Media |
| **Atendida** (*warm*) | El bot habla primero con la persona y luego une las dos llamadas | Alta: son dos llamadas y un puente |

## Reglas antes del código

- **Destinos por nombre, nunca por número.** La herramienta recibe `"ventas"` o `"soporte"` y tu
  código lo traduce a una extensión. Si el LLM pudiera marcar cualquier número, bastaría con que
  alguien se lo pidiera por teléfono para hacer llamadas a tu costa.
- **El bot avisa antes de transferir**: "Le paso con soporte, un momento."
- **Ten un plan si el destino no contesta**: cola, buzón o volver al bot. Eso se resuelve en el
  dialplan, no en el prompt.
- **Pasa el contexto.** Repetirlo todo a la persona es lo que más molesta de una transferencia.

## La herramienta

Igual en las dos centralitas. Vive en [`src/agent/tools.py`](../src/agent/tools.py):

```python
from typing import Literal

DESTINATIONS = {"ventas": "2001", "soporte": "2002"}   # nombre -> extensión


async def transfer_call(params: FunctionCallParams, department: Literal["ventas", "soporte"]):
    """Transfer the caller to a person.

    Use it when the caller asks for a person or needs something you cannot do. Tell the caller
    you are transferring them, in the same turn.

    Args:
        department: Who should take the call.
    """
    session = params.app_resources          # la CallSession de esta llamada
    await session.request_transfer(DESTINATIONS[department])
    await params.result_callback({"success": True})
    # Termina la conversación; el adaptador NO debe colgar (ver cada centralita).
    await params.llm.push_frame(EndWorkerFrame(reason="transfer"))
```

Para que la herramienta alcance la llamada, pasa la sesión al crear el pipeline
(`PipelineWorker(..., app_resources=session)` en `src/agent/pipeline.py`) y añade a `CallSession`
un `request_transfer` que cada adaptador implementa a su manera. Así la herramienta no sabe de
centralitas, igual que `end_call`.

## Asterisk

Al marcar el canal WebSocket con la opción `g`, **cuando el bot cuelga su pata el dialplan
continúa** en la siguiente prioridad con quien llama todavía en línea (*comprobado*: tras el
`HANGUP` del bot, la ejecución sigue con `DIALSTATUS=ANSWER`). Eso convierte la transferencia en
"el bot termina y el dialplan decide".

Falta que el dialplan sepa a dónde ir. `chan_websocket` no tiene un comando para fijar variables
del canal, así que el dialplan se lo pregunta al bot por HTTP:

```ini
; asterisk/conf/extensions.conf
exten = 9000,1,Set(CALL_ID=${UNIQUEID})
 same = n,Dial(WebSocket/voice_agent/c(slin)f(json)v(call_id=${CALL_ID}),,g)
 ; El bot ya salió. ¿Pidió transferir?
 same = n,Set(NEXT=${CURL(http://bot:8765/calls/${CALL_ID}/next)})
 same = n,GotoIf($["${NEXT}" = ""]?fin)
 same = n,Goto(transferencias,${NEXT},1)
 same = n(fin),Hangup()

; Solo se puede transferir a lo que esté aquí.
[transferencias]
exten = 2001,1,Dial(PJSIP/1000,30)
 same = n,VoiceMail(2001@default)
exten = 2002,1,Queue(soporte)
```

Del lado del bot:

- `request_transfer(ext)` guarda `{call_id: ext}` en memoria. El `call_id` llega como parámetro
  de la URL del WebSocket (*comprobado*: los parámetros de `v(...)` llegan al bot; así recibe hoy
  `caller`).
- Un endpoint `GET /calls/{call_id}/next` devuelve la extensión una sola vez y la borra.
  Protégelo: que solo sea alcanzable desde la red de la centralita, o con la misma credencial.
- El serializer no cambia: `EndWorkerFrame` → `HANGUP` cuelga solo el canal WebSocket.

Añade a `asterisk/conf/modules.conf` los módulos que usa ese dialplan: `res_curl.so`,
`func_curl.so` y los de destino (`app_queue.so`, `app_voicemail.so`...).

Con varias réplicas del bot, guarda el destino en un almacén compartido (Redis): la consulta HTTP
puede caer en otra réplica.

**Alternativa sin HTTP:** que el bot use AMI o ARI para redirigir el canal de quien llama
(`Redirect`). Es más directo, pero da al bot una credencial de control sobre Asterisk.

## FreeSWITCH

Aquí el bot ya tiene el event socket, así que puede ordenar la transferencia él mismo:

```
uuid_transfer <uuid> 2002 XML transferencias
```

El canal sale de `park` y entra en el contexto `transferencias`. El paquete `pipecat-freeswitch`
exporta el cliente necesario:

```python
from pipecat_freeswitch import ESLConnection

async def request_transfer(self, extension: str) -> None:
    conn = await ESLConnection.connect(host, port, password, timeout=5.0)
    try:
        # Deja de enviar el audio de la llamada al bot.
        await conn.api(f"uuid_audio_stream {self.call_id} stop")
        await conn.api(f"uuid_transfer {self.call_id} {extension} XML transferencias")
    finally:
        await conn.close()
```

**La trampa:** el serializer cuelga la llamada (`uuid_kill`) cuando el pipeline termina o el
WebSocket se cierra, y eso mataría la llamada recién transferida. Para una llamada que puede
transferirse:

1. Crea el serializer con `auto_hang_up=False`.
2. Como ya no cuelga solo, `end_call` tiene que colgar explícitamente (`uuid_kill` por el event
   socket) después de que termine de sonar la despedida.
3. En `on_disconnect`, no llames a nada que cuelgue si la sesión está marcada como transferida.

El contexto `transferencias` se define como cualquier otro, con sus propios destinos:

```xml
<context name="transferencias">
  <extension name="soporte">
    <condition field="destination_number" expression="^2002$">
      <action application="bridge" data="user/1001"/>
    </condition>
  </extension>
</context>
```

## Pasar el contexto a la persona

| Forma | Cómo |
| --- | --- |
| **Nota en tu sistema** | Antes de transferir, la herramienta guarda un resumen en el CRM o ticket, asociado al número de quien llama. La persona lo ve al contestar |
| **Variables de la llamada** | El resumen viaja como cabecera SIP o variable del canal y el softphone lo muestra |
| **Susurro** | La centralita reproduce un audio a la persona antes de unir las llamadas ("llamada de Ana, pregunta por su factura") |

El resumen lo puede escribir el propio LLM: añade un parámetro `summary` a la herramienta y pide
en su descripción dos frases con el motivo de la llamada y lo ya resuelto.

## Cómo probarlo

1. Llamada de prueba: pide "quiero hablar con una persona" y comprueba que suena la extensión.
2. El destino no contesta: ¿quien llama acaba en un sitio razonable?
3. Pide un destino que no existe o dicta un número: el agente no debe poder marcarlo.
4. Cuelga durante el aviso de transferencia: no deben quedar canales abiertos
   (`core show channels` / `show channels`).
