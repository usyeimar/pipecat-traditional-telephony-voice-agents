# 4. Prompts para un agente de voz

Un agente de voz tiene **tres** sitios donde el texto importa, y cada uno depende de un
proveedor distinto:

| Etapa | Qué se configura | Aquí |
| --- | --- | --- |
| Voz a texto (STT) | Idioma y vocabulario que debe reconocer | Deepgram |
| LLM | El prompt del sistema y las herramientas | Claude |
| Texto a voz (TTS) | Cómo se escribe el texto para que suene bien | Cartesia |

El prompt del agente está en [`prompts/agent.md`](../prompts/agent.md) y los tres servicios se
crean en [`src/agent/services.py`](../src/agent/services.py).

## Lo que vale para cualquier proveedor

**Escribe para el oído, no para la vista.** Todo lo que el modelo escribe se convierte en voz.

- Una o dos frases por turno. Por teléfono nadie retiene un párrafo.
- Sin listas, markdown, emojis ni símbolos: el texto a voz los lee ("asterisco asterisco") o se
  los come.
- Una pregunta cada vez, y esperar la respuesta.
- Números, fechas, importes y siglas escritos como se dicen.

**Cuéntale al modelo que está en una llamada.** Sin ese contexto escribe como en un chat. Dile
también que la transcripción puede tener errores, para que pida repetir en vez de adivinar.

**Explica el porqué de cada regla.** "No des precios porque cambian cada semana; ofrece enviar la
tarifa por correo" funciona mejor que "NUNCA des precios": el modelo puede aplicar el criterio a
casos que no previste.

**Describe el trabajo, no solo la personalidad.** Qué puede resolver, qué no, qué datos necesita
recoger y en qué orden, y qué hacer cuando no puede ayudar (transferir, tomar un recado).

**Di cuándo usar cada herramienta, en su descripción.** La descripción de una herramienta es
parte del prompt: el modelo decide con ella. En este proyecto es el *docstring* de la función en
[`src/agent/tools.py`](../src/agent/tools.py).

**Dale el cierre.** Cómo despedirse y cuándo colgar; si no, la llamada se queda en un "¿algo
más?" infinito.

**Mantén el prompt estable.** Un prompt que no cambia entre turnos se puede cachear (más barato
y más rápido). Lo que varía por llamada (nombre, pedido) va en un mensaje aparte, no incrustado
al principio del prompt.

Una estructura que funciona:

```markdown
Eres el asistente telefónico de Clínica Norte. Atiendes llamadas de pacientes.

## Cómo hablas
(reglas de voz: frases cortas, sin listas, una pregunta a la vez)

## Qué puedes hacer
(agendar, mover y cancelar citas; horarios y direcciones)

## Qué no puedes hacer
(nada médico: explica que no puedes y ofrece pasar con enfermería)

## Datos que necesitas para agendar
(nombre completo, documento, especialidad, fecha preferida; de uno en uno)

## Cuándo terminar
(despídete y usa end_call en el mismo turno)
```

## LLM: diferencias por proveedor

Las reglas de arriba son las que más pesan. Lo que cambia por proveedor es la forma, no el fondo.
Cada uno mantiene su guía, y cambia con cada generación de modelos: léela antes de afinar.

### Claude (Anthropic) — el que usa este proyecto

- El prompt va en el parámetro `system` (aquí, `system_instruction`), no como primer mensaje.
- Responde bien a instrucciones en lenguaje normal con su motivo. Las mayúsculas y los
  "IMPORTANTE" repetidos, pensados para modelos antiguos, hoy tienden a que sobreactúe la regla.
- Para separar partes del prompt (instrucciones, datos del cliente, ejemplos) sirven etiquetas
  XML o encabezados; lo que importa es que cada bloque tenga nombre.
- Los modelos actuales razonan antes de contestar y eso es latencia. En voz se controla con el
  **esfuerzo** (`LLM_EFFORT=low`), no pidiendo en el prompt que "no piense".
- No admite que le escribas el principio de su respuesta (*prefill*) en los modelos actuales.
- Caché de prompt: activada aquí (`enable_prompt_caching=True`). Solo ahorra si el prompt supera
  el mínimo cacheable del modelo y no cambia entre turnos.
- Guía oficial: <https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview>

### GPT (OpenAI)

- Instrucciones en el mensaje de sistema o *developer*. Los modelos recientes siguen las
  instrucciones de forma muy literal: sé explícito con lo que quieres y revisa que dos reglas no
  se contradigan.
- Los encabezados markdown para estructurar el prompt son la convención habitual.
- Guía oficial: <https://platform.openai.com/docs/guides/prompt-engineering>

### Gemini (Google)

- Instrucciones en `system_instruction`. Agradece prompts concisos y con algún ejemplo del
  formato de respuesta esperado.
- Guía oficial: <https://ai.google.dev/gemini-api/docs/prompting-strategies>

### Cambiar de proveedor

Pipecat tiene un servicio por proveedor con la misma interfaz. Se cambia en `build_llm`, y el
resto del pipeline (contexto, herramientas) no se toca:

```python
# src/agent/services.py
from pipecat.services.openai.llm import OpenAILLMService


def build_llm(settings):
    return OpenAILLMService(
        api_key=settings.openai_api_key,
        settings=OpenAILLMService.Settings(
            model="...",
            system_instruction=settings.system_prompt,
        ),
    )
```

Hay que añadir el extra a las dependencias (`pipecat-ai[openai]`) y la clave a `config.py`.
Después de cambiar de modelo, **vuelve a probar el prompt**: uno afinado para un modelo rara vez
es el mejor para otro.

## Voz a texto: ayudarle a oír

El reconocimiento no lleva "prompt", pero sí configuración que cumple ese papel.

- **Idioma.** Fija el idioma de la llamada (`AGENT_LANGUAGE`). La detección automática añade
  errores con audio telefónico.
- **Vocabulario del negocio.** Nombres de productos, apellidos y siglas son lo que más falla a
  8 kHz. Deepgram permite pasar términos clave para favorecerlos; consulta en su documentación
  la opción vigente para tu modelo y añádela en `build_stt`.
- **Compénsalo en el prompt del LLM.** Dile qué palabras suele confundir el reconocimiento
  ("si oyes 'clínica norte' o 'clínica corte', es Clínica Norte") y que confirme los datos
  críticos repitiéndolos.
- **Números largos por teclado.** Para un documento o una tarjeta, pedir que lo marquen es más
  fiable que dictarlo.

## Texto a voz: escribir para que suene bien

El texto que sale del LLM es la "partitura" del sintetizador.

- **La puntuación es la entonación.** Las comas y los puntos marcan las pausas; una frase larga
  sin comas suena atropellada. Pídeselo al LLM: frases cortas y bien puntuadas.
- **Números y fechas.** Cartesia los normaliza según el idioma (opción `normalization` del
  servicio). Aun así, lo más seguro para teléfonos, códigos y referencias es pedir al LLM que los
  escriba separados: "tres, cero, cero; uno, dos, tres".
- **Pronunciación.** Para marcas y nombres propios que el sintetizador dice mal hay diccionarios
  de pronunciación (`pronunciation_dict_id` en Cartesia) y reglas de reemplazo de texto en
  Pipecat (`text_transforms`).
- **Voz e idioma.** Elige una voz nativa del idioma (`CARTESIA_VOICE_ID`); una voz multilingüe
  habla español con acento. La velocidad y la emoción se ajustan en `generation_config`.
- **Nivel.** La voz sintetizada sale más fuerte que el nivel telefónico; ya se atenúa
  (`OUTPUT_GAIN_DB`).

## Cómo iterar

1. **Llama y escucha.** Los fallos de un agente de voz no se ven leyendo el prompt.
2. **Lee la transcripción junto al audio**: separa los errores de oído (STT) de los de criterio
   (LLM) y de los de pronunciación (TTS). Cada uno se arregla en un sitio distinto.
3. **Cambia una cosa cada vez** y repite las mismas llamadas de prueba.
4. **Guarda casos difíciles** (quien interrumpe, quien no dice nada, quien pide algo fuera de
   alcance) y repásalos tras cada cambio. Pipecat incluye un ejecutor de evaluaciones
   (`pipecat eval`) para automatizar este repaso.
