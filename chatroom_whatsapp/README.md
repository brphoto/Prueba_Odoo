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
- El encabezado del chat es clicable y abre la ficha del contacto.

## Flujo comercial y panel de accesos rápidos

Desde cada conversación un agente puede:

- Responder directamente (texto, adjuntos o notas de voz vía Cloud API).
- Pedir una **sugerencia de respuesta con IA** (botón *Sugerir respuesta
  con IA*) — configurable en Ajustes con cualquier proveedor LLM que
  exponga un endpoint tipo *chat completions* (OpenAI, Anthropic vía proxy
  compatible, Azure OpenAI, modelo propio, etc.).
- **Crear una Oportunidad** (CRM) o un **Presupuesto** (Ventas) con un
  clic, precargando el contacto y el historial de la conversación. La
  oportunidad creada queda **anclada** a la conversación
  (`pinned_lead_id`); también se puede vincular una ya existente
  eligiéndola en ese mismo campo.
- **Botones inteligentes** en la ficha (arriba a la derecha) con el
  conteo de Oportunidades, Presupuestos y Facturas del contacto — un
  clic abre esos registros filtrados, sin salir del contexto de la
  conversación. Se ocultan automáticamente si CRM, Ventas o Contabilidad
  no están instalados.

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

## Alcance de esta versión

- Envío/recepción de texto, imagen, audio (incluye notas de voz), video,
  documento, plantillas y botones interactivos para WhatsApp,
  end-to-end (subida/bajada de media contra la Graph API de Meta).
- Messenger/Instagram comparten el mismo modelo de datos
  (`chatroom.channel.channel_type`) pero el webhook y el envío directo
  para esos canales quedan como extensión (misma Graph API de Meta, otro
  formato de payload).
- La sugerencia y la clasificación de IA usan el historial de los
  últimos 10 mensajes de la conversación como contexto.
- El panel de accesos rápidos (Oportunidades/Presupuestos/Facturas) es
  de solo navegación; no permite crear/editar líneas de factura o pedido
  desde el propio chat.
- Las listas interactivas y el catálogo de productos de WhatsApp no
  están implementados, solo botones de respuesta rápida (máx. 3).
