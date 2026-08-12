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
- **Mensajes citados (en los dos sentidos)**: cuando el cliente responde a
  un mensaje concreto desde WhatsApp, la burbuja muestra una vista previa
  del mensaje original citado (se extrae del campo `context.id` que envía
  Meta en el webhook y se resuelve contra `wa_message_id`). Y desde
  nuestro lado, el ícono de responder (📩) en cualquier burbuja con
  `wa_message_id` confirmado arma la cita: el composer muestra qué se está
  citando (con botón para cancelar) y el mensaje sale con
  `context: {message_id}` hacia el Graph API, así aparece como respuesta
  citada también del lado del cliente. Solo implementado para WhatsApp
  (Messenger/Instagram no soportan este flujo todavía en este módulo).
- **Reacciones con emoji**: ícono de carita en cada burbuja abre un
  selector de 6 emojis comunes (👍❤️😂😮😢🙏); reaccionar (o volver a
  tocar el mismo emoji para quitarla) manda un mensaje `type: reaction`
  al Graph API y la reacción se pega como una etiqueta sobre la esquina
  de la burbuja, sin generar un mensaje nuevo en el hilo — igual que en
  la app real de WhatsApp. Las reacciones que manda el cliente también se
  reciben por webhook y se muestran igual.
- **Reintentar envíos fallidos**: los mensajes marcados como `Fallido`
  muestran un enlace "Reintentar" en la burbuja; también hay un cron
  (`Chatroom: reintentar mensajes fallidos`, cada 10 minutos) que
  reintenta automáticamente hasta 3 veces los mensajes de texto/adjunto
  fallidos de la última hora (las plantillas y los botones interactivos
  quedan afuera del reintento automático porque su contenido puede
  necesitar ajustes manuales).
- **Quién mandó cada mensaje**: los mensajes salientes muestran el nombre
  del agente que los escribió (vacío en los que mandó la automatización
  de IA, que corre con el usuario del webhook).
- **Traducir un mensaje entrante**: ícono de traducción en cada burbuja
  entrante con texto; llama al mismo proveedor de IA configurado y
  muestra la traducción al idioma del usuario debajo del mensaje
  original, sin sobrescribirlo ni persistirla.

## App de una sola pantalla (estilo WhatsApp Web)

**Chatroom > Chatroom** (el ícono de la app, primer ítem del menú) abre una
pantalla única en vez de navegar entre kanban/lista/formulario: lista de
conversaciones a la izquierda (buscador —que busca tanto por nombre de
contacto como dentro del **contenido de los mensajes**, para encontrar
"quién preguntó por X" sin abrir chat por chat—, filtros
*Todas / No leídas / Mías* y un selector de línea) + la conversación
abierta a la derecha, con el
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
- **Responder consultas de precio con datos reales**: si el mensaje del
  cliente menciona el nombre de un producto vendible (búsqueda literal
  por palabra, no semántica), se le contesta con el precio **real**
  tomado de Odoo, no inventado por el modelo — el prompt le pasa a la IA
  la lista exacta de productos encontrados con su precio y le prohíbe
  usar cualquier otro dato. Si no encuentra ningún producto que
  coincida, no hace nada y sigue el flujo normal (clasificación /
  auto-reply genérico, si están activos) en vez de quedarse callado. Se
  ignora si "Vendedor automático" (abajo) está activo.
- **Vendedor automático (armar pedidos)**: la versión completa de lo
  anterior — la IA charla con el cliente, arma un **carrito** con
  productos y cantidades reales, y cuando el cliente confirma que quiere
  cerrar el pedido, **crea una Cotización real de Ventas** (`sale.order`
  en borrador) a partir de ese carrito. La IA **nunca la confirma sola**:
  siempre queda pendiente de que un agente la revise, ajuste lo que haga
  falta y la confirme desde el formulario normal de Odoo. Técnicamente,
  en vez de "function calling" propietario de un proveedor (que no todos
  los endpoints *chat completions* soportan igual), se le pide a la IA
  que responda con un JSON estricto de 3 formas fijas
  (`add_items` / `checkout` / `reply`) y Python ejecuta esa decisión de
  forma determinística — la IA nunca toca la base de datos directamente,
  solo elige entre esas 3 acciones. El carrito y el botón **Convertir a
  cotización** también se ven en el **panel de contacto**, así un agente
  puede terminar de armarlo o cerrarlo a mano si hace falta.
- **Switch IA / agente humano**: cada conversación tiene un interruptor
  (arriba del chat, junto al selector de línea) para pausar/reactivar
  las automatizaciones de IA. Se pausa **sola** en cuanto un agente
  humano manda un mensaje real en esa conversación (texto, adjunto,
  reacción, reintento, plantilla o botones — cualquier acción que hable
  con el cliente), para que la IA no le pise la respuesta a la persona
  que ya está atendiendo; también se puede pausar/reactivar a mano en
  cualquier momento. Mientras está pausada, "Sugerir respuesta con IA"
  (el botón manual del encabezado) sigue funcionando igual — pausar solo
  apaga el piloto automático, no la IA como asistente del agente.

Cualquier error de IA (endpoint caído, credenciales inválidas, respuesta
inesperada, JSON mal formado del vendedor automático) se registra en el
log del servidor y **no interrumpe** la recepción de mensajes por el
webhook.

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

## Horario de atención

En **Ajustes > Chatroom WhatsApp > Horario de atención** se puede definir
un horario (hora de inicio/fin, días de la semana, zona horaria) fuera
del cual se manda un aviso automático de "estamos fuera de horario" al
primer mensaje del día de cada conversación — no en cada mensaje que
mande el cliente de madrugada, solo el primero (`last_away_message_date`
lo controla). El texto del aviso también es configurable. Desactivado
por defecto: sin activarlo, el chat sigue respondiendo/asignando
conversaciones a toda hora, igual que siempre. Cuando se manda el aviso,
no se dispara además la automatización de IA para ese mismo mensaje (no
tiene sentido que conteste dos veces).

## Etiquetas de conversación

**Chatroom > Configuración > Etiquetas** para crear etiquetas libres
(nombre + color) y así categorizar conversaciones más allá del estado o
la intención detectada por IA — por ejemplo "Reclamo" o "Venta caliente".
Se agregan/quitan desde el encabezado del chat (ícono "+", junto a las
etiquetas ya puestas) tanto en la app como en el formulario clásico, y
se pueden filtrar y agrupar en la vista clásica (kanban/lista) para
reportes — la app de una sola pantalla todavía no tiene un filtro por
etiqueta en su propia lista de conversaciones, solo verlas/editarlas por
chat.

## Mensajes programados

El ícono de reloj en el composer permite dejar un mensaje de texto
armado para que salga más tarde (seguimiento a las 48h, recordatorio de
pago, etc.) en vez de mandarlo ya: se elige fecha/hora y un cron
(`Chatroom: enviar mensajes programados`, cada 5 minutos) lo manda solo
cuando se cumple. Los pendientes de esa conversación se ven arriba del
composer, con opción de cancelarlos antes de que salgan. Por ahora es
solo texto simple (sin adjuntos ni plantillas); **Chatroom > Mensajes
programados** lista todos los de todas las conversaciones, útil para un
manager que quiere ver/cancelar en un solo lugar.

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
- **Transferir una conversación a otra línea/equipo**: en el encabezado
  del chat (app y widget clásico) hay un selector para cambiar la línea
  de la conversación en cualquier momento, sin salir del chat. Al
  cambiarla queda una nota interna con el rastro ("Conversación
  transferida de X a Y") y, si no se reasignó también a un agente
  puntual en la misma acción, se reparte sola entre el equipo de la
  línea nueva — para no dejarla en un agente que puede no pertenecer a
  ese equipo.
  > **Ojo con esto si de verdad usás números de WhatsApp distintos** (no
  > solo "líneas" internas del mismo número): la ventana de 24h para
  > responder libremente la abre el número **al que el cliente le
  > escribió**. Si transferís a una línea con un Phone Number ID
  > realmente distinto, los próximos mensajes van a intentar salir desde
  > ese número nuevo hacia un cliente que nunca le escribió a ese
  > número — Meta puede rechazarlo o exigir una plantilla en vez de
  > texto libre. Es 100% seguro para reorganizar equipos que comparten
  > la misma línea real; con líneas de verdad distintas, usalo sabiendo
  > esto.

## Envío masivo de WhatsApp desde cualquier lista

Desde el menú de **Acciones** (⚙) de la lista de **Contactos**,
**Oportunidades**, **Presupuestos/Pedidos** o **Facturas**: seleccioná
varias filas y elegí **Enviar WhatsApp masivo**. El asistente:

- Resuelve un contacto por cada fila seleccionada (directo si es la
  lista de Contactos; por `partner_id` en los demás casos) y
  **deduplica por número de WhatsApp** — si dos filas seleccionadas
  son del mismo contacto (ej. dos facturas de la misma persona), le
  llega una sola vez.
- Solo deja elegir **plantillas aprobadas por Meta** (nunca texto
  libre): un envío masivo casi siempre le llega a alguien fuera de la
  ventana de 24h, y Meta rechaza texto libre en ese caso.
- Las variables de la plantilla se completan solas por contacto
  usando el mismo motor de `chatroom.template.variable_mapping_ids`
  que ya usa el envío individual (ej. `invoice_total`, tomado de la
  factura más reciente de cada contacto) — no hay que tipear nada por
  persona.
- Si el contacto no tiene todavía una conversación de WhatsApp, se le
  crea una (`action_start_conversation`, la misma lógica que "Nueva
  conversación"); los dados de baja se omiten solos.

## Notificaciones automáticas por eventos de Odoo

En **Ajustes > Chatroom WhatsApp > Notificaciones automáticas**: elegí
una plantilla aprobada para **"pedido confirmado"** y/o **"factura
publicada"**, y se manda sola por WhatsApp cuando pasa ese evento —
sin que un agente tenga que acordarse. Dos decisiones de diseño a
propósito:

- Usa **plantillas**, no texto libre: un evento de Odoo (confirmar un
  pedido, publicar una factura) casi siempre pasa fuera de la ventana
  de 24h de la última vez que ese cliente escribió, y Meta rechaza
  texto libre en ese caso.
- **Solo se manda a contactos que ya tienen una conversación de
  WhatsApp** — no le crea una conversación nueva a nadie. Mandarle una
  plantilla a cualquier cliente con teléfono cargado, así nunca haya
  usado WhatsApp con el negocio, es justo el ruido que se quiere
  evitar. Si más adelante hace falta notificar también por
  entregas/despachos (`stock.picking`), habría que sumar `stock` como
  dependencia — no está implementado en esta versión para no ampliar
  las dependencias obligatorias del módulo sin que haga falta.

## Ubicación: recibir y enviar por WhatsApp

- **Recibir**: si un cliente comparte su ubicación por WhatsApp (por
  ejemplo, para indicar dónde entregar), llega como un mensaje más en
  el hilo con el nombre/dirección (si el cliente los cargó) y un link
  de Google Maps con las coordenadas.
- **Enviar**: ícono de pin en el composer (📍) manda la ubicación del
  local configurada en **Ajustes > Chatroom WhatsApp > Ubicación del
  negocio** (nombre, dirección, latitud/longitud) como mensaje de
  ubicación nativo de WhatsApp — el cliente lo ve con el mapa embebido
  y el botón "Cómo llegar" propio de WhatsApp, no un link de texto.

## Link de pago en Facturas y Presupuestos

En el panel de contacto, junto al botón de enviar el PDF de cada
presupuesto/factura reciente, hay un segundo botón ($) que genera un
**link de pago** con el mismo asistente nativo de Odoo que usan los
botones "Enviar link de pago" de Ventas/Facturación
(`payment.link.wizard`) y lo manda por WhatsApp como texto. No inventa
ningún mecanismo de cobro propio: si no hay un método de pago en línea
configurado (Stripe, Mercado Pago, etc.) o el módulo de Pagos no está
instalado, avisa con un error claro en vez de mandar un link roto.

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

**Desde esta versión, Ventas, Compras, CRM y Facturación son
dependencias reales del módulo** (`depends` en `__manifest__.py`), no
opcionales: al instalar o actualizar `chatroom_whatsapp` en Odoo, esas
cuatro apps se instalan solas si no lo estaban. La idea es que este
módulo sea el centro de operación para un vendedor que atiende por
WhatsApp — no tendría sentido que el panel de accesos rápidos dependa de
que alguien se acuerde de instalar cada app por separado. El código
igual sigue revisando `'modelo' in self.env` en cada método (por si el
módulo se reusa algún día en una instalación más liviana), pero en la
práctica esas cuatro ya van a estar instaladas siempre.

> **Importante**: agregar una dependencia nueva no las instala solas en
> una base ya existente hasta que actualices el módulo (**Apps > Chatroom
> WhatsApp > Actualizar**, o `-u chatroom_whatsapp` si lo hacés por
> línea de comandos). Además, que la app esté instalada no alcanza: cada
> botón de "crear" (Oportunidad/Presupuesto/Factura/Compra) sigue
> respetando los permisos de esa app — un agente que solo está en el
> grupo *Chatroom / Agente* también necesita el grupo de Usuario de
> Ventas/CRM/Compras/Facturación correspondiente para poder usarlos, la
> misma regla de siempre de Odoo, este módulo no le da un permiso
> especial por izquierda.

En la app de una sola pantalla, el ícono de tarjeta de contacto (arriba a
la derecha del chat, cuando hay una conversación abierta) muestra/oculta
un panel lateral con:

- Foto, nombre, empresa, ciudad, teléfono, email y **saldo pendiente**
  del contacto (`res.partner.credit`, "lo que te debe" — solo se
  muestra si es distinto de cero) — clic en el encabezado abre su ficha
  completa.
- Contadores clicables de Oportunidades, Ventas, Compras, Facturas y
  Tareas (cada uno se oculta solo si el módulo correspondiente no está
  instalado, igual que los stat buttons de la ficha clásica). **Abren en
  una pestaña nueva del navegador** (Odoo completo: lista, kanban con
  arrastrar y soltar, filtros, acciones en lote) en vez de un diálogo —
  un diálogo (`target: "new"`) no deja cambiar de vista adentro
  (limitación real del framework, no un botón roto: ver el detalle en
  "Validado contra un Odoo 19 real"), así que para *browsear* varios
  registros y entrar a cualquiera hace falta la pestaña nueva. El chat
  queda intacto en la pestaña original, y el panel se refresca solo
  cuando volvés a esa pestaña (por si creaste o confirmaste algo).
- Botones para crear una **Oportunidad**, un **Presupuesto**, una
  **Factura directa** (sin pasar por un presupuesto antes, para ventas
  rápidas de contado), una **Orden de Compra** (para cuando el contacto
  de WhatsApp es un proveedor, no un cliente) o una **Tarea**. Estos sí
  abren como **diálogo** encima de la app, sin navegar a otra pantalla
  ni perder el chat — porque van directo a un único formulario (sin
  lista de por medio), que es justo el caso que un diálogo maneja bien.
  Es el formulario real de Odoo (con sus botones nativos: Confirmar,
  Crear factura, Registrar pago, etc.), no una versión reducida propia.
  Cerrar el diálogo te deja exactamente donde estabas, con el panel
  actualizado. Así, para pasar un Presupuesto a Factura: abrilo desde
  "Crear Presupuesto" o desde la lista de recientes, agregale las
  líneas, confirmalo y usá el botón "Crear factura" del propio
  formulario de Odoo — sin salir nunca del chat.
- **Actividades pendientes del contacto**: las que están agendadas
  directo en su ficha, más las de sus oportunidades de CRM (que es
  donde de verdad suele vivir un "llamar el jueves" en un flujo de
  ventas) — en rojo las vencidas.
- **Últimos presupuestos y facturas del contacto, con un botón para
  mandar el PDF directo por la misma conversación de WhatsApp** (botón
  de avión de papel junto a cada uno): genera el reporte con el motor de
  reportes de Odoo (`ir.actions.report._render_qweb_pdf`) y lo envía
  como adjunto, reusando el mismo mecanismo de envío de archivos de
  siempre — respeta la ventana de 24h, el opt-out, etc. Abrir uno
  puntual desde la lista de recientes (clic en el nombre) sí es un
  diálogo, como las creaciones — es un único registro, no una lista.
  **"Presupuestos recientes" solo muestra los que están en borrador o
  enviados** (`draft`/`sent`): uno cancelado es ruido que nadie va a
  retomar, y uno ya confirmado dejó de ser un "presupuesto" — pasó a
  pedido, y si se facturó ya aparece solo en "Facturas recientes" (el
  contador "Ventas" de arriba sí sigue mostrando el total sin filtrar).
  **"Facturas recientes" excluye las canceladas** por el mismo motivo,
  pero conserva los borradores (ej. el que arma "+Factura": es trabajo
  en curso del agente, no algo terminado que ya no importe).
- **Catálogo de productos**: buscador para encontrar un producto
  vendible (`sale_ok`) y mandarlo por WhatsApp con un clic — la foto del
  producto como imagen y "Nombre - Precio" como pie de foto (si no tiene
  foto cargada, se manda como texto). "Ver todo" abre el catálogo
  completo de Odoo en una pestaña nueva (mismo motivo que arriba).
- **Cada sección (Actividades, Presupuestos recientes, Facturas
  recientes, Carrito, Catálogo) es plegable** — clic en el título la
  abre/cierra, y se recuerda entre sesiones (`localStorage`). Arrancan
  plegadas todas menos el Catálogo (lo que más se usa para mandar algo
  por WhatsApp), así no hace falta scrollear un montón para llegar a
  buscar un producto cuando hay actividades/presupuestos/facturas
  recientes cargados arriba.
- **Carrito armado por la IA** (ver "Automatización con IA" más arriba):
  si el vendedor automático fue agregando productos charlando con el
  cliente, se ve acá línea por línea con un botón para "Convertir a
  cotización" a mano, aunque la IA todavía no haya cerrado el pedido
  sola.

Todo se resuelve en una sola llamada (`chatroom.channel.
get_contact_panel_data`) para que abrir el panel no dispare media
docena de peticiones. El saldo pendiente (`res.partner.credit`) es un
campo con permisos propios de Facturación (`groups=`); se lee con
`sudo()` solo para ese campo puntual, para que un vendedor sin acceso a
Contabilidad igual pueda verlo en el panel sin que le rompa con un error
de permisos.

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

## Datos de demostración

**Chatroom > Configuración > Generar conversaciones de prueba** crea 2
conversaciones con historial realista (Bryan Cando y Cynthia Molina, con
números reales) para poder probar la interfaz sin esperar tráfico real:

- **Bryan Cando**: consulta de producto sin resolver (queda con un
  mensaje sin leer, para probar el badge/Dashboard), + una Oportunidad
  y un Presupuesto en borrador (para probar el panel de contacto y
  "enviar PDF por WhatsApp").
- **Cynthia Molina**: pedido ya resuelto (conversación tranquila, sin
  pendientes), + una Oportunidad, un Presupuesto **confirmado** y su
  **factura** (para probar esa parte del panel con un documento real).

Es manual (no se carga solo al instalar, porque usa números de teléfono
reales) e idempotente (si el contacto ya tiene conversación, no la toca
ni la duplica). Los datos de CRM/Ventas/Facturas se crean "mejor
esfuerzo": si algo no aplica en tu base (falta un diario contable
configurado, etc.) se omite con un log, sin romper la creación de las
conversaciones.

**Importante para probar con seguridad**: generar la demo solo inserta
filas en la base — no llama a la API de Meta, así que no manda nada
real. Pero la interfaz de chat que ves ahí es la real: si le das
"Enviar" a un mensaje de texto o le mandás el PDF/producto a Bryan o
Cynthia con el token de WhatsApp configurado en Ajustes, **eso sí sale
de verdad** hacia esos números.

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
- **Un campo `Text` con `config_parameter` en `res.config.settings`
  rompe la pantalla de Ajustes completa apenas se abre** (no solo al
  guardar): `_get_classified_fields()` solo acepta
  `boolean/integer/float/char/selection/many2one/datetime` para esos
  campos, y esa validación corre en el primer `onchange`. Se encontró
  en producción (no en la prueba automatizada) con el mensaje de
  "fuera de horario" configurable — se cambió a `Char` (sin límite real
  de caracteres en Odoo, así que no se pierde nada).
- **Un `ir.actions.act_window` multi-vista (`list,form` o similar)
  abierto como diálogo (`target: "new"`) no deja cambiar de vista
  adentro del diálogo**: `switchView()` en `action_service.js` tiene una
  guarda (`if (dialog) return`) que se activa apenas el diálogo está
  montado, así que ni haciendo clic en una fila de una lista abre su
  formulario — no es un botón roto del lado del negocio, es una
  limitación real del framework con diálogos multi-vista. La solución
  que se usa ahora es mantenerlas como acciones nativas con
  `target: "new"`, dentro de un diálogo sobre el chat. Las listas
  conservan los filtros y vistas nativas de Odoo; los formularios de
  documentos recientes se abren también como diálogos, sin cambiar de
  pestaña ni perder la conversación.
- **El avatar del contacto (`/web/image/res.partner/<id>/avatar_128`)
  se queda con la respuesta vieja cacheada por el navegador** si subís
  una foto nueva después de haber abierto esa conversación una vez: la
  URL es siempre la misma string, así que el navegador nunca vuelve a
  pedirla. Se corrigió agregando `?unique=<write_date>` a la URL (con
  el helper `imageUrl()` de `@web/core/utils/urls`) — el mismo patrón
  que usa el propio menú de usuario de Odoo (`user_menu.js`) para el
  mismo campo, encontrado ahí buscando cómo lo resuelve el core en vez
  de inventar una solución propia.

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
  contacto (con catálogo de productos), envío de PDF/producto por
  WhatsApp, probar conexión, salud del webhook, notificaciones de
  escritorio, notas internas, reasignar rápido, "Siguiente pendiente" y
  preview de adjuntos son nuevos en esta iteración**: validación por
  sintaxis + revisión contra el código fuente real de Odoo 19, pero la
  prueba real en navegador ya encontró un bug de verdad — los botones
  del panel de contacto (Facturas, Oportunidades, etc.) rompían con
  "Cannot read properties of undefined (reading 'map')" porque las
  acciones que arma `chatroom.channel` no traían la clave `views`,
  necesaria cuando se llaman por `orm.call()` en vez de por un botón
  clásico (`clean_action()` del servidor la completa solo para botones,
  no para RPC directo) — ya está corregido (`_window_action()`), pero
  es una buena señal de que **conviene seguir probando en navegador
  antes de asumir que algo nuevo funciona**, esta sección no es solo
  formalidad.
- La deduplicación de contactos por teléfono compara en Python sobre
  los contactos con `phone` cargado (no hay forma limpia de comparar
  "solo dígitos" a nivel SQL sin una extensión de PostgreSQL); en bases
  de datos con cientos de miles de contactos esto puede ser lento — no
  es un problema para el volumen típico de una pyme o empresa mediana.
- **Reintentos de envío, búsqueda por contenido de mensaje, trazabilidad
  de agente, citar respondiendo y reaccionar con emoji son nuevos en
  esta iteración**: se validó sintaxis (`py_compile` de los tres archivos
  Python tocados, parseo del XML del template) y se revisó el payload
  del Graph API (`context`/`reaction`) contra la documentación de la
  Cloud API de Meta, pero **no se probaron todavía en un navegador contra
  un Odoo corriendo** — a diferencia de otras secciones de este README,
  esta no tiene una prueba end-to-end real detrás todavía. Antes de
  confiar en producción conviene probar a mano: reintentar un mensaje
  fallido, citar un mensaje real, reaccionar y confirmar que la reacción
  llega también desde el lado del cliente.
- **Horario de atención, etiquetas, transferir a otra línea, mensajes
  programados y respuesta de IA con precios reales son nuevos en esta
  iteración**: validado con `py_compile` de todo el módulo y parseo de
  XML, con los mismos huecos honestos que la tanda anterior — **sin
  prueba en navegador todavía**. Adicionalmente, acá conviene remarcar
  dos puntos de diseño, no solo bugs posibles: (1) la búsqueda de
  productos para la respuesta de precios es literal por palabra del
  nombre, no semántica — si el cliente escribe con errores de tipeo o
  usa un sinónimo que no está en el nombre del producto, no va a
  encontrar nada (y ahí cae al flujo normal, no se queda sin contestar
  nada raro, pero tampoco "entiende" lo que quiso decir); (2) transferir
  a otra línea reutiliza el campo `whatsapp_number_id` de siempre (no
  hay una acción/wizard separada) — ver la advertencia sobre la ventana
  de 24h en la sección "Múltiples líneas" de arriba antes de usarlo con
  números de WhatsApp genuinamente distintos.
- **Vendedor automático (carrito + cotización) y switch IA/humano son
  nuevos en esta iteración**: validado con `py_compile` y parseo de XML
  de todo el módulo, sin prueba en navegador todavía. Puntos a tener en
  cuenta antes de confiar en producción: (1) el "vendedor automático"
  depende de que el modelo configurado de verdad devuelva el JSON que
  se le pide — si un proveedor/modelo no sigue bien esa instrucción, la
  respuesta se descarta y se registra en el log (no rompe el webhook),
  pero el cliente se queda sin respuesta automática para ese mensaje
  puntual; conviene probarlo primero con el modelo real que vayas a usar
  antes de dejarlo prendido sin supervisión. (2) La detección de "un
  agente humano tomó la conversación" para pausar la IA sola distingue
  webclient (pausa) de webhook/cron (no pausa) revisando si hay un
  `http.request` activo además de si el usuario es el público — no se
  probó todavía con RPC externo o `xmlrpc` de terceros, que tampoco pasan
  por un `http.request` de Odoo y por lo tanto **no pausarían la IA**
  aunque en la práctica sea una persona escribiendo por otro canal
  técnico. (3) No hay una vista clásica dedicada para auditar carritos
  abandonados de todas las conversaciones a la vez, solo por
  conversación (panel de contacto) — para eso, por ahora, hay que mirar
  conversación por conversación.
- **Sale/Purchase/CRM/Account como dependencias obligatorias, Factura y
  Orden de Compra directas desde el panel, actividades pendientes del
  contacto y saldo pendiente son nuevos en esta iteración**: validado
  con `py_compile`/parseo de XML de todo el módulo, sin instalar de
  verdad las apps nuevas en una base real todavía (este entorno no tiene
  Odoo corriendo para probarlo). Antes de subir esto a una instalación
  en producción: (1) hacé un backup antes de actualizar el módulo,
  porque instalar Ventas/Compras/CRM/Facturación de una en una base que
  no las tenía es un cambio de verdad, no cosmético — crea tablas,
  menús, secuencias y datos por defecto de esas apps; (2) confirmá que
  los agentes que van a usar los botones nuevos tengan además los
  permisos de cada app (ver la nota en "Panel de contacto"); (3) la
  actividad de un contacto solo mira `res.partner` y `crm.lead`, no
  otros documentos (ej. actividades puestas directo en una factura o un
  presupuesto no van a aparecer en esa lista).
- **Envío masivo desde listas, notificaciones automáticas por eventos,
  ubicación y link de pago son nuevos en esta iteración**: validado
  con `py_compile` y parseo de XML de todo el módulo, sin instalar el
  módulo de verdad en una base real todavía (surgieron comparando este
  módulo contra varios conectores de WhatsApp de terceros del Odoo
  Apps Store — casi todos de pago y con API no oficial, algo que este
  módulo evita a propósito desde el inicio). Puntos concretos a
  revisar antes de confiar en producción: (1) el envío masivo y las
  notificaciones automáticas dependen de que ya haya plantillas
  aprobadas por Meta configuradas con sus variables mapeadas — sin eso
  no hay nada para elegir; (2) las notificaciones de "pedido
  confirmado"/"factura publicada" no cubren entregas/despachos
  (necesitaría `stock` como dependencia nueva, no se agregó); (3) el
  link de pago depende de tener un proveedor de pago en línea
  configurado en Odoo — sin eso, avisa con un error en vez de mandar
  un link que no sirve, pero no configura ningún proveedor por vos.
