# telephony-auth Specification

## Purpose

Define cómo el agente comprueba que quien abre un WebSocket es una centralita autorizada, para que nadie más pueda abrir llamadas contra los servicios de pago ni manejar llamadas ajenas.

## Requirements

### Requirement: Credencial en el saludo del WebSocket

Todo endpoint de telefonía DEBE exigir el secreto compartido `BOT_TOKEN` en la cabecera `Authorization` y DEBE aceptarlo en dos formas: `Bearer <token>` y HTTP Basic, donde la contraseña es el token y el usuario se ignora.

#### Scenario: Bearer válido

- **WHEN** la centralita envía `Authorization: Bearer <BOT_TOKEN>`
- **THEN** la conexión se acepta

#### Scenario: Basic válido

- **WHEN** la centralita envía credenciales Basic cuya contraseña es `BOT_TOKEN`
- **THEN** la conexión se acepta

#### Scenario: Contraseña con dos puntos

- **WHEN** las credenciales Basic son `asterisk:a:b`
- **THEN** el token considerado es `a:b`

### Requirement: Rechazo antes de aceptar

Una conexión sin credencial, con un esquema distinto o con un token incorrecto DEBE rechazarse antes de aceptar el WebSocket, de forma que el saludo falle con HTTP 403 y no se cree ningún pipeline.

#### Scenario: Sin credencial

- **WHEN** un cliente abre el WebSocket sin cabecera `Authorization`
- **THEN** el saludo falla con 403

#### Scenario: Token incorrecto

- **WHEN** un cliente envía `Authorization: Bearer otro-valor`
- **THEN** el saludo falla con 403

#### Scenario: Credencial mal formada

- **WHEN** un cliente envía `Authorization: Basic !!!`
- **THEN** el saludo falla con 403

### Requirement: Comparación en tiempo constante

El token recibido DEBE compararse con el esperado en tiempo constante.

#### Scenario: Token casi correcto

- **WHEN** un cliente envía un token que difiere del esperado solo en el último carácter
- **THEN** se rechaza igual que cualquier otro token incorrecto
