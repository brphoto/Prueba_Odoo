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

Tanto el formulario de cada conversación (`Chatroom > Vista clásica`) como
la app de una sola pantalla (`Chatroom > Chatroom`, ver más abajo) usan el
mismo widget de chat propio (`static/src/chatroom_thread/`), no una lista
plana:

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

## App de una sola pantalla (estilo WhatsApp Web)

**Chatroom > Chatroom** (el ícono de la app, primer ítem del menú) abre una
pantalla única en vez de navegar entre kanban/lista/formulario: lista de
conversaciones a la izquierda (buscador, filtros *Todas / No leídas / Mías*
y un selector de línea) + la conversación abierta a la derecha, con el
mismo widget de burbujas de siempre (`chatroom_thread_core`, ahora
reutilizado en vez de duplicado). En pantallas angostas (celular/tablet)
la lista y el chat ocupan toda la pantalla por turnos, con un botón de
volver.

La vista clásica (kanban/lista/formulario) sigue disponible en
**Chatroom > Vista clásica** — útil para reportes, exportar, o editar
varios campos a la vez, cosas que una app de una sola pantalla no cubre
bien.

Arriba de la lista de conversaciones hay una barra de herramientas con
accesos directos a **Dashboard**, **Plantillas**, **Respuestas rápidas** y
**Líneas** sin salir de la app (se abren como pantallas/diálogos aparte,
la conversación que tenías abierta sigue ahí cuando volvés).

## Iniciar una conversación nosotros (seguimiento, encuestas, avisos)

Hasta acá, las conversaciones solo se creaban cuando el cliente escribía
primero. El botón **+** junto al selector de línea (o **Chatroom > Nueva
conversación** en el menú, para la vista clásica) abre un diálogo para:

- Buscar un contacto existente (por nombre) y elegirlo, con su teléfono
  precargado (editable, por si querés escribirle a otro número suyo), o
- **Crear un contacto nuevo al vuelo** con nombre + número, sin salir del
  diálogo.
- Elegir la línea de WhatsApp por la que se envía, si tenés más de una.

Al confirmar, se reutiliza el mismo canal si el contacto ya tenía una
conversación (no se duplica), o se crea uno nuevo asignado a quien lo
inició. Como es una conversación que **iniciamos nosotros**, casi siempre
va a estar fuera de la ventana de 24h (`is_session_open` en `False`,
ningún mensaje entrante todavía) — la propia interfaz de chat va a pedir
una plantilla aprobada para el primer mensaje, igual que exige Meta para
cualquier conversación iniciada por el negocio. Es el mecanismo correcto
para seguimientos, encuestas o avisos: una plantilla de categoría
*Utilidad* o *Marketing* aprobada por Meta, no texto libre.

> Esto es para contactar **de a un contacto por vez**. Un envío masivo a
> una lista (campaña) necesitaría manejo de listas de opt-in, límites de
> envío de Meta y una cola de trabajos — queda fuera del alcance de esta
> iteración.

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

## Múltiples líneas de WhatsApp (Ventas, Soporte, etc.)

Si atiendes con **más de un número de WhatsApp Business**, dalos de alta en
**Chatroom > Configuración > Líneas de WhatsApp** (`chatroom.whatsapp.number`):
nombre, `Phone Number ID` propio y, opcionalmente, agentes asignados
(`member_ids`).

- El webhook lee `value.metadata.phone_number_id` en cada mensaje entrante
  y asocia la conversación a la línea que coincida (`whatsapp_number_id`
  en `chatroom.channel`). Si no hay ninguna línea configurada, o ninguna
  coincide, todo sigue funcionando como con un solo número (el de
  Ajustes) — no rompe instalaciones existentes.
- Al enviar, la conversación usa el token/Phone Number ID **de su
  línea** si los tiene; si la línea no define un token propio, cae al
  token general de Ajustes (caso típico: una sola WhatsApp Business
  Account con varios números).
- El reparto automático de conversaciones nuevas se limita a los
  `member_ids` de esa línea cuando tiene agentes definidos; si la línea
  no tiene agentes propios, se reparte entre todo el grupo *Chatroom /
  Agente* como siempre.
- **"Pin" de línea por pantalla**: en la app de una sola pantalla, el
  selector de línea (arriba de la lista) se guarda en `localStorage` del
  navegador — cada usuario/equipo puede dejar su pantalla fija en "Mi
  línea" o en una línea específica, y así queda la próxima vez que abra
  Chatroom en ese navegador. La vista clásica tiene el mismo filtro
  ("Mi línea") en la búsqueda.
- El `access_token` de cada línea solo lo puede leer/editar el grupo
  *Chatroom / Administrador* (campo con `groups=` a nivel de modelo, no
  solo oculto en la vista).

## Dashboard

**Chatroom > Dashboard** muestra un resumen de un vistazo: conversaciones
de hoy, pendientes, mensajes sin leer, mensajes enviados/recibidos hoy y
el tiempo promedio de primera respuesta (últimos 30 días), más dos
rankings de agentes (conversaciones abiertas, y velocidad de primera
respuesta). Todo se calcula en el servidor con `read_group`
(`chatroom.channel.get_dashboard_data`) para no traer registros de más al
navegador — no es un pivot/gráfico genérico, son consultas agregadas
puntuales.

## Panel de contacto (CRM, Ventas, Compras, Facturas, Tareas)

En la app de una sola pantalla, el ícono de tarjeta de contacto (arriba a
la derecha del chat, cuando hay una conversación abierta) muestra/oculta
un panel lateral con:

- Foto, nombre, empresa, ciudad, teléfono y email del contacto —
  clic en el encabezado abre su ficha completa.
- Contadores clicables de Oportunidades, Ventas, Compras, Facturas y
  Tareas (cada uno se oculta solo si el módulo correspondiente no está
  instalado, igual que los stat buttons de la ficha clásica).
- Botones para crear una Oportunidad, un Presupuesto o una Tarea sin
  salir del contexto de la conversación.
- **Últimos presupuestos y facturas del contacto, con un botón para
  mandar el PDF directo por la misma conversación de WhatsApp** (botón
  de avión de papel junto a cada uno): genera el reporte con el motor de
  reportes de Odoo (`ir.actions.report._render_qweb_pdf`) y lo envía
  como adjunto, reusando el mismo mecanismo de envío de archivos de
  siempre — respeta la ventana de 24h, el opt-out, etc.

Todo se resuelve en una sola llamada (`chatroom.channel.
get_contact_panel_data`) para que abrir el panel no dispare media
docena de peticiones.

## Probar conexión y salud del webhook

- **Ajustes > Chatroom WhatsApp > Probar conexión**: valida el token y
  el Phone Number ID contra la Graph API real (pide el nombre verificado
  y la calidad del número) **sin enviar ningún mensaje**. Cada línea de
  `Chatroom > Configuración > Líneas de WhatsApp` tiene el mismo botón
  con sus propias credenciales.
- **Ajustes** y el **Dashboard** muestran "Último webhook recibido"
  (hace cuánto llegó el último evento de Meta, de cualquier tipo). Si
  dice "Nunca", la URL del webhook no está bien registrada en Meta o
  el servidor no es alcanzable desde internet — antes de sospechar del
  resto de la configuración, hay que resolver eso primero.

## Notificaciones de escritorio y sonido

Con el permiso del navegador otorgado (se pide solo, la primera vez que
cargás Odoo con el módulo instalado), cuando llega un mensaje nuevo de
un cliente a **tu** conversación asignada (o a una sin asignar) sonás un
aviso corto (generado con Web Audio, sin archivo de sonido de por medio)
y aparece una notificación del sistema operativo con el nombre del
contacto y el texto, aunque tengas Odoo en otra pestaña. Un clic en la
notificación te lleva directo al Chatroom. No suena para conversaciones
asignadas a otro agente.

## Notas internas, reasignar y cola de pendientes

- **Notas internas**: el ícono de nota amarilla en el composer alterna
  entre "mensaje al cliente" y "nota interna" (el composer y el botón de
  enviar cambian de color mientras está activo, para no mandarle a un
  cliente algo que era solo para el equipo). Las notas se guardan en el
  chatter de siempre (`mail.message`, subtipo "Nota") pero se ven
  mezcladas con las burbujas del chat, con otro estilo (centrada,
  amarilla, con el nombre de quien la escribió) para no confundirlas con
  un mensaje real. El modo se desactiva solo después de mandar una nota.
- **Reasignar rápido**: el selector que aparece en el encabezado del chat
  (a la derecha del nombre del canal) cambia el agente asignado con un
  clic, sin abrir el formulario. Para reasignar varias conversaciones a
  la vez, seleccionalas en **Chatroom > Vista clásica** (lista) y usá
  "Reasignar conversaciones" en el menú de Acción.
- **Siguiente pendiente**: el botón "Siguiente" de la barra de
  herramientas salta a la conversación pendiente más antigua (distinta
  de la que tenés abierta) — útil para no andar buscando manualmente
  cuál atender primero.
- **Vista previa de adjuntos**: si el último mensaje de una conversación
  no tiene texto (una foto, un audio...), la lista/kanban/sidebar
  muestran "📷 Foto", "🎤 Audio", etc. en vez de quedar en blanco.

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
- **App de una sola pantalla, múltiples líneas y Dashboard**: se validó
  sintaxis (Python, XML, manifest, existencia de cada archivo de assets
  referenciado), se revisó `_read_group`/hooks de OWL contra el código
  fuente real de Odoo 19, y el usuario confirmó que la app carga y
  navega correctamente contra un Odoo real corriendo.
- **Iniciar conversación (diálogo "+" / Nueva conversación), panel de
  contacto, envío de PDF por WhatsApp, probar conexión, salud del
  webhook, notificaciones de escritorio, notas internas, reasignar
  rápido, "Siguiente pendiente" y preview de adjuntos son nuevos en
  esta iteración**: mismo nivel de validación por sintaxis + revisión
  contra el código fuente real de Odoo 19 (reportes PDF, `Notification`
  API, `binding_view_types`, `html2plaintext`, etc.), pero **todavía no
  se probaron en navegador** — conviene abrir el panel de contacto con
  un contacto que tenga ventas/facturas reales y mandar un PDF de
  prueba, y probar el modo nota interna, antes de usarlos con un
  cliente de verdad.
- La deduplicación de contactos por teléfono compara en Python sobre
  los contactos con `phone` cargado (no hay forma limpia de comparar
  "solo dígitos" a nivel SQL sin una extensión de PostgreSQL); en bases
  de datos con cientos de miles de contactos esto puede ser lento — no
  es un problema para el volumen típico de una pyme o empresa mediana.
