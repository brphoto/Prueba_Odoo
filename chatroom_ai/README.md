# Chatroom IA controlada

Sugerencias de IA con aprobación, trazabilidad y fuentes. Nada se envía al
cliente sin que una persona lo revise.

## Acciones de IA (19.0.1.2)

Las acciones de IA son instrucciones reutilizables que el agente ejecuta desde
el chat. Reemplazan las tres opciones fijas que tenía antes el asistente
(respuesta, resumen e intención).

### Dónde se usan

| Dónde | Cómo |
|---|---|
| **Compositor del chat** | Botón ✨ junto al mensaje: lista las acciones de la conversación. |
| **Atajos** | Escribe `/` y el atajo al final del mensaje (`/precio`, `/mejorar`...). ↑↓ para elegir, Enter para usar y Esc para cerrar. Lo escrito antes del atajo es el borrador. |
| **Panel «Asistente IA»** | Selector de acciones con su descripción, botón *Ejecutar* y ⚙ para configurarlas (administradores). |

### Configuración

**Chatroom → Configuración → Acciones de IA.** Cada acción tiene:

- **Instrucción**: qué hace la IA. Acepta las variables `{cliente}`, `{empresa}`,
  `{agente}`, `{linea}`, `{ultimo_mensaje}` y `{borrador}`.
- **Qué hace con el resultado**:
  - *Borrador de respuesta*: crea un borrador auditable para revisar, aprobar y enviar.
  - *Reescribir mi borrador*: reemplaza lo escrito en el mensaje (mejorar, traducir).
  - *Nota interna*: la guarda en el chat; el cliente no la ve.
  - *Resumen interno* o *Clasificar intención*: actualizan la conversación.
  - *Tarea del agente*: solo si está instalado el Agente IA. Prepara acciones en
    Odoo que quedan esperando aprobación.
- **Conocimiento**: base de conocimiento, memoria del cliente, catálogo con
  precio y stock en vivo, y pedidos y facturas del cliente. Cada casilla se
  activa por separado: con menos fuentes la respuesta sale más enfocada y consume menos.
- **Estilo**: tono, idioma, máximo de palabras y cuántos mensajes de la conversación lee.
- **Quién la ve**: líneas de WhatsApp y grupos. Vacío significa todas y todos.
- **Modelo de IA** (con *Chatroom IA - Modelos y Consumo*): por ejemplo, uno
  económico para clasificar y uno mejor para responder.

Se instalan nueve acciones de ejemplo que puedes editar o archivar:

| Acción | Atajo | Qué hace |
|---|---|---|
| Respuesta sugerida | `/responder` | Borrador de respuesta |
| Mejorar mi borrador | `/mejorar` | Reescribe lo escrito |
| Responder con precio y stock | `/precio` | Usa el catálogo en vivo |
| Seguimiento de cotización | `/seguimiento` | Usa pedidos y facturas |
| Respuesta a reclamo | `/reclamo` | Tono empático |
| Resumen de conversación | `/resumen` | Resumen interno |
| Nota para traspaso | `/traspaso` | Nota interna |
| Clasificar intención | `/intencion` | Actualiza la intención |
| Traducir mi borrador | `/traducir` | Traduce lo escrito |

### Persona por línea

En cada **Línea de WhatsApp**, el bloque *Asistente IA de esta línea* define
cómo habla la IA en ese número: marca, tono, qué ofrece y qué no debe prometer.
Se aplica a todas las consultas de IA de sus conversaciones. Ahí también se
eligen las acciones exclusivas de la línea.

### Calidad

La lista de acciones muestra el **% de borradores útiles** y el **% de editados**
según la evaluación de los agentes (👍 útil, ✏️ la edité, 🚫 no es segura).
Si una acción se edita mucho, conviene ajustar su instrucción o sus fuentes.
El botón *Borradores* de cada acción abre los borradores que generó.

### Seguridad

- Los borradores de respuesta siempre pasan por revisión humana.
- Con la IA pausada en una conversación no se generan textos para el cliente.
  Los resúmenes y las notas internas sí se pueden generar.
- Un agente solo ve las acciones de sus líneas y grupos. El servidor vuelve a
  comprobarlo al ejecutar la acción.
