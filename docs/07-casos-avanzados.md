# 7. Casos avanzados

Ideas para ir más allá de "contesta y conversa", con el punto del código donde encaja cada una.

> Son **guías de diseño**: nada de esta página está implementado en el repositorio.

## Pasar contexto a cada llamada

Casi todo lo avanzado empieza igual: el bot necesita saber *algo* de la llamada antes de saludar
(quién es, de qué campaña viene, en qué idioma). El canal ya existe: los parámetros de la URL
del WebSocket.

```ini
; Asterisk
Dial(WebSocket/voice_agent/c(slin)f(json)v(caller=${URIENCODE(${CALLERID(num)})},campaign=cobros,lead=8841))
```

```xml
<!-- FreeSWITCH: en la URL de uuid_audio_stream -->
ws://bot:8765/ws/freeswitch?caller=${caller_id_number}&amp;campaign=cobros&amp;lead=8841
```

En el bot, cada adaptador lee `websocket.query_params` (hoy solo `caller`). Añade un campo
`metadata` a `CallSession` y úsalo en `run_call` para preparar la conversación:

- **Buscar a quien llama** en el CRM por su número y saludar por su nombre.
- **Elegir el prompt** según la campaña o el DID marcado.
- **Añadir los datos como un mensaje de contexto**, no dentro del prompt del sistema: así el
  prompt sigue siendo idéntico entre llamadas y se puede cachear.

Envía identificadores (`lead=8841`), no datos personales: las URL acaban en registros. El bot
resuelve el identificador contra tu sistema.

## Campañas salientes

En una campaña el agente llama en vez de contestar. El agente no cambia: **quien marca es la
centralita**, y cuando la persona contesta la envía a la misma extensión del agente.

```
lista de contactos ─▶ marcador ─▶ centralita ─▶ operador ─▶ persona
                         ▲             │
                         │             └─▶ (contesta) ─▶ extensión del agente ─▶ bot
                         └── resultado de cada llamada ◀── bot / centralita
```

**Originar la llamada.**

```bash
# Asterisk (CLI; desde un programa, la acción Originate de AMI o ARI)
channel originate PJSIP/573001234567@operador extension 9000@campanas

# FreeSWITCH (event socket)
originate {origination_caller_id_number=MI_DID}sofia/gateway/operador/573001234567 9000 XML campanas
```

**El marcador** es un servicio aparte que hace falta escribir. Sus responsabilidades:

| Responsabilidad | Detalle |
| --- | --- |
| Ritmo | No lanzar más llamadas que agentes libres y que el límite de tus proveedores |
| Reintentos | No contesta, ocupado, buzón: cuándo y cuántas veces volver a intentar |
| Resultado | Guardar qué pasó en cada llamada (contactado, promesa de pago, no interesado, número erróneo) |
| Horarios y exclusiones | Franjas permitidas y lista de quienes pidieron no ser llamados |

**Detección de buzón de voz.** Una parte de las llamadas la contesta una máquina. Las dos
centralitas tienen detección (`AMD()` en Asterisk, `mod_avmd` en FreeSWITCH), pero falla en una
fracción de los casos. Complétala en el prompt: si lo primero que se oye es un mensaje grabado,
dejar un recado breve y colgar.

**Quién habla primero.** En una llamada saliente la persona dice "¿aló?" y espera. El saludo del
agente debe identificarse y decir el motivo en una frase; cambia `GREETING_INSTRUCTION` según el
sentido de la llamada.

**El resultado como herramienta.** Dale al LLM una herramienta `record_outcome(result, notes)`
que llame antes de despedirse. Es más fiable que deducir el resultado de la transcripción.

**Cumplimiento.** Las llamadas automatizadas están reguladas en casi todos los países:
consentimiento previo, horarios, identificación de quien llama, aviso de que es un sistema
automático y derecho a no volver a ser llamado. Revísalo con quien lleve lo legal antes de la
primera campaña; los límites técnicos (horarios, exclusiones) van en el marcador, no en el
prompt.

## Datos personales (PII)

Una llamada pasa datos personales por cinco sitios. Decide en cada uno qué entra y qué se queda.

| Sitio | Riesgo | Medida |
| --- | --- | --- |
| Registros del bot | En `DEBUG` se escribe el prompt y cada transcripción | `LOGURU_LEVEL=INFO` en producción |
| Voz a texto | El proveedor recibe todo el audio | Opciones de redacción del proveedor; acuerdo de tratamiento de datos |
| LLM | Recibe la transcripción y la guarda según su política | Redactar antes de enviarla; política de retención del proveedor |
| Tu almacenamiento | Transcripciones y resúmenes | Guardar la versión redactada, cifrada y con caducidad |
| Grabaciones de la centralita | El audio completo | Pausar la grabación en los tramos sensibles; retención corta |

**Redactar antes del LLM.** Un procesador entre el reconocimiento y el contexto sustituye lo
sensible. Va en `src/agent/pipeline.py`, justo después de `build_stt(settings)`:

```python
import re
from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


class PIIRedactor(FrameProcessor):
    """Replaces sensitive data in what the caller said, before the LLM sees it."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            frame.text = CARD.sub("[tarjeta]", frame.text)
        await self.push_frame(frame, direction)
```

Las expresiones regulares sirven para lo que tiene forma fija (tarjetas, documentos, teléfonos).
Para nombres y direcciones hace falta un modelo de detección de entidades, y ninguno acierta
siempre con transcripciones telefónicas: trátalo como reducción de riesgo, no como garantía.

**Lo que el agente necesita no se puede redactar.** Si el agente debe buscar por número de
documento, tiene que recibirlo. La alternativa es que no pase por el LLM: una herramienta
`lookup_customer()` sin argumentos que lee el último número marcado por teclado.

**Datos de tarjeta: por teclado y fuera del LLM.** Es el patrón más seguro:

1. El agente dice "marque los dieciséis dígitos de su tarjeta" y llama a una herramienta
   `start_secure_input()`.
2. Mientras dura ese modo, un procesador **captura los `InputDTMFFrame` y no los deja pasar**: ni
   el reconocimiento ni el LLM ven los dígitos.
3. El procesador envía los dígitos directamente a tu pasarela de pago y devuelve al LLM solo el
   resultado ("pago aprobado").
4. La centralita pausa la grabación durante el tramo.

Si procesas pagos, el alcance de PCI DSS depende de por dónde pasan esos dígitos: diseña este
flujo con quien lleve el cumplimiento.

## Conversaciones con etapas

Cuando la llamada tiene pasos con reglas distintas (identificar → diagnosticar → agendar →
confirmar), un solo prompt gigante empieza a fallar: el modelo se salta pasos o usa herramientas
antes de tiempo. **Pipecat Flows** (`pipecat.flows`) pone una máquina de estados sobre el
pipeline: cada etapa tiene su prompt, sus herramientas y sus transiciones. Úsalo cuando el
proceso deba *cumplirse*, no solo sugerirse.

## Conocimiento y sistemas

- **Consultar sistemas**: cada consulta (estado de un pedido, disponibilidad) es una herramienta
  más en `src/agent/tools.py`. Mientras espera, el agente debe decir algo ("un momento, lo
  consulto"): pídelo en la descripción de la herramienta.
- **Base de conocimiento**: una herramienta `search_knowledge(query)` que busca en tus
  documentos y devuelve los fragmentos relevantes. Mejor que meter el manual entero en el prompt.
- **Recursos compartidos** (clientes HTTP, conexiones): pásalos con
  `PipelineWorker(..., app_resources=...)` y léelos en la herramienta como
  `params.app_resources`.

## Después de la llamada

Al terminar, el contexto del LLM tiene la conversación completa. En `on_client_disconnected`
(`src/agent/pipeline.py`) puedes lanzar, sin bloquear el cierre:

- un **resumen** y el **resultado** de la llamada hacia tu CRM,
- la **transcripción** redactada a tu almacenamiento,
- **métricas** de la llamada (duración, turnos, transferida o no).

Hazlo en una tarea aparte y con reintentos: la llamada ya terminó y no debe depender de que tu
CRM responda.

## Otras ideas

| Idea | Cómo |
| --- | --- |
| **Varios idiomas** | Un DID por idioma, o detectar el idioma en el primer turno y cambiar la voz y el reconocimiento |
| **Varios agentes** | Una extensión por agente; el parámetro `agent=` de la URL elige el prompt |
| **Horario** | Fuera de horario el dialplan envía al agente; en horario, a personas |
| **Desbordamiento** | El agente atiende solo cuando la cola de personas supera cierto tiempo de espera |
| **Encuesta tras la llamada** | Al colgar la persona de soporte, el dialplan envía la llamada a un agente con prompt de encuesta |
| **Recordatorios** | Una campaña saliente con un agente que confirma, mueve o cancela la cita |
