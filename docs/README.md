# Guías

Lo que conviene entender para llevar un agente de voz a una centralita tradicional, en el orden
en que suele hacer falta.

| Guía | Responde a |
| --- | --- |
| [1. El audio](01-audio.md) | ¿Qué viaja por una llamada y por qué la telefonía suena distinto? |
| [2. La centralita (PBX)](02-pbx.md) | ¿Qué es una PBX y cómo se conecta con el agente? |
| [3. Troncales SIP](03-troncales-sip.md) | ¿Cómo recibo y hago llamadas reales en Asterisk y en FreeSWITCH? |
| [4. Prompts](04-prompts.md) | ¿Cómo escribo mejores prompts para voz, según el proveedor? |
| [5. Transferir la llamada](05-transferencias.md) | ¿Cómo implemento herramientas para pasar la llamada a una persona? |
| [6. Producción](06-produccion.md) | ¿Qué flujos hay que tener definidos para operar el agente? |
| [7. Casos avanzados](07-casos-avanzados.md) | Campañas salientes, redacción de datos personales y otras ideas |
| [8. Problemas comunes](08-problemas-comunes.md) | ¿Cómo diagnostico y resuelvo lo que falla en producción? |

Convenciones:

- **Probado en este repositorio** significa que hay una prueba que lo ejercita (ver el README
  principal). Lo demás son guías de diseño: explican cómo hacerlo y dónde encaja en el código,
  pero no están implementadas aquí.
- Los ejemplos de configuración usan datos ficticios (`sip.operador.example`, `203.0.113.10`).
