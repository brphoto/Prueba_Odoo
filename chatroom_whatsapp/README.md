# Chatroom WhatsApp & Redes Sociales (Odoo 19)

Módulo de Odoo 19 que agrega una bandeja de conversaciones tipo *chatroom*
para WhatsApp (y, sobre la misma base, Messenger/Instagram) conectando
**directo con la API oficial de Meta (WhatsApp Business Cloud API)**.

## ¿Cloud API (Meta) o "WhatsApp Web por QR"?

Odoo **no ofrece de forma nativa** una conexión por escaneo de código QR
tipo WhatsApp Web. Las dos formas reales de conectar WhatsApp a un sistema
como Odoo son:

| Opción | Cómo funciona | Riesgos / límites |
| --- | --- | --- |
| **Meta Cloud API (oficial)** — la que implementa este módulo | Se crea una App de Meta Business, se verifica un número de WhatsApp Business y Odoo llama directo a `graph.facebook.com` con un token permanente. | Requiere verificación de negocio en Meta y usar plantillas aprobadas para iniciar conversación fuera de la ventana de 24h. Es la vía soportada y estable. |
| **"Multi-dispositivo" / QR (no oficial)** | Librerías como `whatsapp-web.js`/`Baileys` simulan un cliente web y vinculan la sesión escaneando un QR con el celular. | **No es una API de Meta**: es ingeniería inversa del protocolo. Viola los Términos de Servicio de WhatsApp para uso comercial/automatizado, el número puede ser **bloqueado sin aviso**, y no hay soporte oficial. No se implementa en este módulo por ese motivo. |

Este módulo usa exclusivamente la **Cloud API oficial**, sin pasar por
proveedores intermedios (BSP) de pago como Twilio, 360dialog, Wassenger,
Chat-API, etc. La única dependencia externa es Meta mismo.

## Configuración

1. Crea una App en [developers.facebook.com](https://developers.facebook.com/)
   con el producto **WhatsApp**.
2. En *Meta Business Suite > WhatsApp > Configuración de la API* obtén:
   - `Phone Number ID`
   - `WhatsApp Business Account ID`
   - Un **token permanente** (crea un System User en Meta Business Settings
     con rol Admin y permisos `whatsapp_business_messaging` +
     `whatsapp_business_management`, y genera un token sin expiración).
3. En Odoo: **Ajustes > Chatroom WhatsApp**, completa esos tres datos, la
   versión de la Graph API (por defecto `v20.0`) y define un
   **Webhook Verify Token** (cualquier cadena que tú elijas).
4. Copia la **URL del Webhook** que se muestra en Ajustes y regístrala en
   el panel de la App de Meta (*WhatsApp > Configuration > Webhook*),
   junto con el mismo Verify Token. Suscríbete al campo `messages`.
5. (Recomendado) Copia el **App Secret** de la App de Meta al campo
   correspondiente en Odoo: se usa para verificar la firma
   `X-Hub-Signature-256` de cada webhook y confirmar que la petición viene
   realmente de Meta.

A partir de aquí, cada mensaje que llegue al número de WhatsApp Business
creará automáticamente el contacto (`res.partner`) y la conversación
(`chatroom.channel`) si no existían.

## Interfaz de chat

El formulario de cada conversación (`Chatroom > Conversaciones`) usa un
widget de chat propio (`static/src/chatroom_thread/`), no una lista plana:

- Burbujas de mensaje diferenciadas por dirección, con hora y ticks de
  estado (enviado / entregado / leído / fallido).
- **Adjuntar archivos** por botón o arrastrando y soltando sobre la
  conversación; vista previa de imágenes, reproductor inline para audios.
- **Notas de voz**: botón de micrófono que graba con la API
  `MediaRecorder` del navegador, muestra un cronómetro mientras grabas, y
  permite cancelar o adjuntar. Se envían como mensaje de audio de
  WhatsApp igual que cualquier otro adjunto.
  > *Limitación conocida*: WhatsApp acepta audio en AAC, MP4, MP3, AMR u
  > OGG/Opus. La mayoría de navegadores (Chrome, Edge) solo graban en
  > `audio/webm;codecs=opus`, que Meta también reproduce pero **no** lo
  > muestra como burbuja nativa de "nota de voz" (sí como archivo de
  > audio reproducible). Firefox graba directo en `audio/ogg;codecs=opus`
  > y sí se ve como nota de voz nativa. Convertir el códec en servidor
  > (p.ej. con `ffmpeg`) queda fuera del alcance de este módulo.
- Actualización en **tiempo real** (bus de Odoo) sin recargar la página.
- El encabezado del chat es clicable y abre la ficha del contacto, y
  muestra la **foto real del contacto** (`res.partner.avatar_128`) en vez
  de solo un ícono con la inicial cuando hay una cargada.
- **Separadores de fecha** ("Hoy", "Ayer" o la fecha) entre bloques de
  mensajes de días distintos, igual que WhatsApp.
- **Mensajes citados**: cuando el cliente responde a un mensaje concreto
  desde WhatsApp, la burbuja muestra una vista previa del mensaje
  original citado (se extrae del campo `context.id` que envía Meta en el
  webhook y se resuelve contra `wa_message_id`).
- **Traducir un mensaje entrante**: ícono de traducción en cada burbuja
  entrante con texto; llama al mismo proveedor de IA configurado y
  muestra la traducción al idioma del usuario debajo del mensaje
  original, sin sobrescribirlo ni persistirla.

## Flujo comercial y panel de accesos rápidos

Desde cada conversación un agente puede:

- Responder directamente (texto, adjuntos o notas de voz vía Cloud API).
- Pedir una **sugerencia de respuesta con IA** (botón *Sugerir respuesta
  con IA*) — configurable en Ajustes con cualquier proveedor LLM que
  exponga un endpoint tipo *chat completions* (OpenAI, Anthropic vía proxy
  compatible, Azure OpenAI, modelo propio, etc.).
- **Crear una Oportunidad** (CRM), un **Presupuesto** (Ventas) o una
  **Tarea** (Proyectos) con un clic, precargando el contacto y el
  historial de la conversación (o el **resumen de IA**, si ya se generó
  uno, en vez del volcado completo de mensajes). La oportunidad creada
  queda **anclada** a la conversación (`pinned_lead_id`); también se
  puede vincular una ya existente eligiéndola en ese mismo campo.
- **Botones inteligentes** en la ficha (arriba a la derecha) con el
  conteo de Oportunidades, Presupuestos, Facturas y Tareas del contacto
  — un clic abre esos registros filtrados, sin salir del contexto de la
  conversación. Se ocultan automáticamente si CRM, Ventas, Contabilidad
  o Proyectos no están instalados.
- **Actividades y calendario nativos de Odoo**: al heredar
  `mail.activity.mixin`, cada conversación puede tener actividades
  programadas (llamada, reunión, tarea de seguimiento) desde el propio
  chatter — aparecen en la campanita de Actividades y en el Calendario
  de Odoo como cualquier otro registro con actividades, sin
  desarrollo adicional.

## Automatización con IA

En **Ajustes > Chatroom WhatsApp > Automatización** (requiere activar
primero las sugerencias de IA):

- **Clasificar intención automáticamente**: al recibir un mensaje, la IA
  etiqueta la conversación como *Consulta*, *Venta*, *Soporte* o *Queja*
  (campo `ai_intent`, visible como badge en la ficha, el kanban y la
  lista; se puede agrupar/filtrar por él).
- **Crear Oportunidad automáticamente**: si la clasificación detecta
  *Venta* y la conversación aún no tiene una oportunidad anclada, se crea
  y se ancla sola.
- **Responder automáticamente con IA**: envía la sugerencia sin que un
  agente la revise antes. Apagado por defecto — actívalo solo si confías
  en el prompt/modelo configurado, ya que no hay paso de aprobación
  humana.

Cualquier error de IA (endpoint caído, credenciales inválidas, respuesta
inesperada) se registra en el log del servidor y **no interrumpe** la
recepción de mensajes por el webhook.

Además, con un clic (botón **Resumir con IA** en el encabezado) se puede
generar un resumen corto de toda la conversación (`ai_summary`) para que
un agente que recién la recibe se ponga al día sin leer todo el
historial; ese resumen también se usa como descripción al crear una
Oportunidad o Tarea, en vez del volcado completo de mensajes.

## Plantillas de WhatsApp (HSM) — mensajes fuera de la ventana de 24h

La Cloud API solo permite texto libre durante las 24h siguientes al
último mensaje del cliente (`chatroom.channel.is_session_open`). Pasada
esa ventana, **la única forma de volver a escribirle es con una plantilla
aprobada por Meta**:

1. Registra y espera la aprobación de tus plantillas en Meta Business
   Suite (WhatsApp Manager > Plantillas de mensajes).
2. En Odoo, ve a **Chatroom > Configuración > Plantillas de WhatsApp** y
   pulsa **Sincronizar con Meta** — trae nombre, idioma, categoría,
   estado y cuerpo de cada plantilla vía Graph API (requiere el
   `WhatsApp Business Account ID` configurado en Ajustes).
3. Cuando la ventana está cerrada, el chat muestra un aviso con un botón
   **Enviar plantilla**; también está disponible siempre en el
   encabezado de la conversación. El asistente pide la plantilla y un
   valor por cada variable `{{1}}`, `{{2}}`... con vista previa antes de
   enviar.

## Asignación automática y notificaciones

- Cada conversación **nueva** se reparte automáticamente entre los
  usuarios del grupo *Chatroom / Agente*, priorizando al que menos
  conversaciones abiertas tenga (se puede desactivar en Ajustes:
  *Asignación automática de conversaciones*).
- El agente asignado recibe una **notificación nativa de Odoo** (aparece
  en la campanita/bandeja de Discuss, no solo si tiene la conversación
  abierta) cada vez que llega un mensaje nuevo o cuando le reasignan una
  conversación — usa `mail.thread`, no infraestructura adicional.

## Botones de respuesta rápida (WhatsApp Interactive Messages)

El ícono de lista en el composer del chat abre un panel para definir
hasta 3 botones (máx. 20 caracteres cada uno); al enviar, el cliente ve
un mensaje con botones tocables en vez de tener que escribir texto. Las
respuestas del cliente llegan por el webhook igual que cualquier mensaje
entrante. No incluye listas largas ni catálogo de productos (requieren
Meta Commerce Manager) — queda como extensión futura.

## Messenger / Instagram

Comparten el mismo modelo de datos y el mismo webhook que WhatsApp
(`chatroom.channel.channel_type`), con **texto entrante y saliente
funcionando end-to-end**: el webhook detecta el payload de Messenger/
Instagram (`object: "page"` o `"instagram"`), crea el contacto y la
conversación igual que WhatsApp, y descarga los adjuntos entrantes
(las URLs de Messenger/Instagram son públicas, a diferencia de las de
WhatsApp). Para enviar hay que configurar el **Token de Página** en
Ajustes (es distinto del token de WhatsApp, aunque compartan App de
Meta). Adjuntos salientes, plantillas y botones interactivos por estos
dos canales quedan como extensión futura — hoy son exclusivos de
WhatsApp.

## Opt-out / consentimiento

En Ajustes puedes definir palabras clave de baja y de alta (por
defecto `stop,baja,cancelar,unsubscribe` / `iniciar,start,alta`). Si un
contacto escribe una de baja, el chatroom se lo confirma, marca
`res.partner.whatsapp_opt_out` y **bloquea el envío de cualquier
mensaje** a ese contacto (texto, adjunto, plantilla o botones) hasta que
vuelva a escribir la palabra de alta o un agente lo reactive a mano
desde la ficha del contacto. Es la protección más simple y más
importante contra que Meta bloquee tu número por spam.

## Marcar como leído (con acuse real a Meta)

Al abrir una conversación, el chat marca localmente como leídos los
mensajes entrantes pendientes y, si es WhatsApp, le avisa a Meta
(`status: read` sobre el último mensaje) para que el cliente vea el
check azul de su lado. Si no hay credenciales configuradas o Meta no
responde, el acuse remoto simplemente se omite (con un log de aviso) y
el mensaje igual queda marcado como leído en Odoo — nunca bloquea la UI.

## Respuestas rápidas guardadas

En **Chatroom > Respuestas rápidas** cualquier agente puede guardar
mensajes frecuentes (título + texto). Desde el composer del chat, el
ícono de rayo abre un panel para insertarlas con un clic — útil para
preguntas repetitivas sin gastar una llamada a la IA.

## Ícono en la barra superior

Los agentes y administradores (grupo *Chatroom / Agente* o superior) ven
un ícono de WhatsApp en la barra superior de Odoo, con un contador de
conversaciones pendientes que se actualiza en tiempo real (bus) sin
recargar la página. Un clic abre el Chatroom filtrado a pendientes.

## Modo oscuro

El widget de chat incluye overrides para el modo oscuro de Odoo
(`chatroom_thread.dark.scss`, registrado en el bundle
`web.assets_web_dark`, el mismo mecanismo que usa el módulo `mail`) con
una paleta inspirada en el WhatsApp oscuro real. **Nota**: el modo
oscuro es una función de Odoo Enterprise; no se pudo verificar
visualmente en este entorno porque solo se probó contra Community, pero
el archivo sigue exactamente la convención verificada en el código
fuente de `mail`.

## Validado contra un Odoo 19 real

Este módulo se instaló y probó en una instancia real de Odoo 19.0
(clonada de `github.com/odoo/odoo`, rama `19.0`) con PostgreSQL, no solo
con revisión de sintaxis. Esa prueba encontró y corrigió varios cambios
de API que rompen módulos escritos "a la manera de Odoo 17/18":

- `_sql_constraints` fue reemplazado por `models.Constraint(...)`.
- `res.groups` ya no tiene `category_id` ni `users`: ahora es
  `privilege_id` (a través de `res.groups.privilege`) y `user_ids`.
- Un `Many2one` a un modelo de un módulo no instalado (p. ej. `crm.lead`
  cuando CRM es opcional) rompe la carga del registro completo; se
  cambió `pinned_lead_id` a un id plano + resolución manual.
- Los filtros de búsqueda sobre campos computados exigen que el campo
  sea `store=True`.
- El `<group>` de "Agrupar por" en las vistas de búsqueda ya no acepta
  `expand`/`string`.
- Las vistas de Ajustes cambiaron de `<div class="settings">` +
  Bootstrap a bloques declarativos `<app>`/`<block>`/`<setting>`.
- Un `<i class="fa ...">` sin texto/título visible rompe la validación
  de accesibilidad de las vistas (`ir_ui_view`) — hay que agregarle
  `title`.
- El servicio de usuario del frontend **no** se inyecta con
  `useService("user")` (eso rompía la carga de *todo* el webclient, no
  solo del ícono): se importa directo como `import { user } from
  "@web/core/user"`.
- **`res.partner` ya no tiene el campo `mobile`** (se unificó con
  `phone`); un dominio de búsqueda que lo referencie revienta con
  `KeyError: 'mobile'`. Se encontró corriendo los tests automatizados,
  no antes.
- Los `user_ids` de un grupo **no incluyen** a quienes lo tienen por
  `implied_ids` de otro grupo (ej. los administradores no aparecían como
  miembros explícitos de "Agente" aunque "Administrador" implica
  "Agente"): hay que unir los `user_ids` de ambos grupos a mano si se
  necesita la lista completa de gente con ese permiso.

Se verificó con capturas de pantalla (Playwright + Chromium headless,
sin errores de consola) que el kanban (con el ícono nuevo de canal y
tiempo relativo), el formulario con el widget de chat, el lightbox de
imágenes, el panel de respuestas rápidas, el ícono de la barra superior,
el marcado de leído (confirmado también por consulta directa a la base
de datos), el panel de botones rápidos, el envío con manejo de errores,
Ajustes, Métricas y el asistente de plantillas cargan y funcionan
correctamente.

## Robustez de producción

Pensado para tráfico real, no solo para la demo:

- **Idempotencia del webhook**: Meta garantiza entrega "al menos una
  vez" — ante un timeout o un 5xx nuestro, reintenta el mismo evento.
  Cada mensaje se identifica por su `wa_message_id`/`mid`; si ya existe,
  el evento se descarta sin duplicar mensajes, contactos, notificaciones
  ni respuestas de IA.
- **Deduplicación de contactos por teléfono**: si el número que escribe
  ya existe en Odoo (importado, creado a mano, de otra integración) pero
  todavía no tiene `whatsapp_id`, se reutiliza ese contacto en vez de
  crear uno nuevo — comparando solo dígitos, sin importar el formato
  (espacios, guiones, `+`).
- **Reintentos con backoff** ante `429` (límite de tasa) y `5xx`
  transitorios de Meta (hasta 2 reintentos, backoff exponencial corto).
  No se reintentan errores de negocio (token inválido, número mal
  formado): esos no se arreglan solos. El mismo mecanismo protege
  también la llamada al proveedor de IA.
- **Tests automatizados** (`tests/test_chatroom.py`, 9 casos) corridos
  contra la misma instancia real de Odoo 19: idempotencia del webhook,
  deduplicación de contactos, bloqueo por opt-out, marcar como leído,
  asignación a un agente real (no al usuario del sistema) y manejo de
  errores sin credenciales. `0 failed, 0 error(s)` en la última corrida.
- **Plantilla de traducción** (`i18n/chatroom_whatsapp.pot`, 264
  cadenas) generada con la herramienta real de Odoo (`odoo-bin i18n
  export`), lista para traducir a cualquier idioma.

## Alcance de esta versión

- Envío/recepción de texto, imagen, audio (incluye notas de voz), video,
  documento, plantillas y botones interactivos para WhatsApp,
  end-to-end (subida/bajada de media contra la Graph API de Meta).
- Messenger/Instagram: texto entrante y saliente funcionando; adjuntos
  salientes, plantillas y botones interactivos son exclusivos de
  WhatsApp por ahora.
- La sugerencia y la clasificación de IA usan el historial de los
  últimos 10 mensajes de la conversación como contexto.
- El panel de accesos rápidos (Oportunidades/Presupuestos/Facturas) es
  de solo navegación; no permite crear/editar líneas de factura o pedido
  desde el propio chat.
- Las listas interactivas y el catálogo de productos de WhatsApp no
  están implementados, solo botones de respuesta rápida (máx. 3).
- El modo oscuro tiene el CSS listo pero no se pudo verificar
  visualmente (requiere Odoo Enterprise, no disponible en este entorno
  de pruebas).
- La deduplicación de contactos por teléfono compara en Python sobre
  los contactos con `phone` cargado (no hay forma limpia de comparar
  "solo dígitos" a nivel SQL sin una extensión de PostgreSQL); en bases
  de datos con cientos de miles de contactos esto puede ser lento — no
  es un problema para el volumen típico de una pyme o empresa mediana.
