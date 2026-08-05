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

## Flujo comercial

Desde cada conversación (`Chatroom > Conversaciones`) un agente puede:

- Responder directamente (mensaje de texto vía Cloud API).
- Pedir una **sugerencia de respuesta con IA** (botón *Sugerir respuesta
  con IA*) — configurable en Ajustes con cualquier proveedor LLM que
  exponga un endpoint tipo *chat completions* (OpenAI, Anthropic vía proxy
  compatible, Azure OpenAI, modelo propio, etc.).
- **Crear una Oportunidad** (CRM) o un **Presupuesto** (Ventas) con un
  clic, precargando el contacto y el historial de la conversación.

## Alcance de esta primera versión

- Envío/recepción de **texto** para WhatsApp implementado end-to-end.
- Mensajes multimedia (imagen/audio/video/documento) se registran en el
  histórico con su `media id` de Meta; la descarga/envío de adjuntos queda
  como siguiente iteración.
- Messenger/Instagram comparten el mismo modelo de datos
  (`chatroom.channel.channel_type`) pero el webhook y el envío directo
  para esos canales quedan como extensión (misma Graph API de Meta, otro
  formato de payload).
- La sugerencia de IA usa el historial de los últimos 10 mensajes de la
  conversación como contexto.
