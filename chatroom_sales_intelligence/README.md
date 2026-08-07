# Chatroom - Inteligencia Comercial (Odoo 19)

Módulo **opcional y desacoplado** que agrega inteligencia comercial al
[Chatroom WhatsApp & Redes Sociales](../chatroom_whatsapp/README.md):
oportunidades estancadas, clasificación RFM/ABC, métricas históricas de
venta y análisis de Pareto (80/20), todo visible sin salir del chat.

## Diseño modular: "engancha", no modifica

Este módulo **depende de** `chatroom_whatsapp` y de
[`crm_customer_intelligence`](../crm_customer_intelligence/README.md)
(que a su vez solo depende de `crm`/`sale`/`account`, sin ningún canal
de mensajería), pero ninguno de los dos depende de este ni sabe que
existe. Toda la integración se hace desde afuera:

- **Vistas**: herencia estándar de `ir.ui.view` (`inherit_id` +
  `xpath`) sobre el kanban de conversaciones.
- **Componentes OWL**: herencia de templates (`t-inherit` +
  `t-inherit-mode="extension"`) y `patch()` de las clases JS existentes
  (`ChatroomThreadCore`, `ChatroomApp`), en vez de copiar o reemplazar
  esos archivos.
- **Ningún modelo nuevo**: el único campo/método propio de este módulo
  vive en `chatroom.channel` (resolver qué oportunidad "cuenta" para la
  conversación y armar el paquete de datos del panel); la clasificación
  RFM, las métricas de venta y el Pareto de productos son de
  `crm_customer_intelligence`. No hace falta tocar `ir.model.access.csv`.

Si desinstalás `chatroom_sales_intelligence`, el chatroom queda
exactamente como estaba antes de instalarlo — ni un botón, badge o campo
de más. La clasificación RFM y el resto de `crm_customer_intelligence`
siguen funcionando igual (ese módulo no sabe que este existió).

**¿Por qué separado en dos módulos?** Porque la clasificación de
clientes por valor (RFM) sirve para más que el chat — por ejemplo para
segmentar una campaña de Email/SMS Marketing por `rfm_category` — y no
tiene sentido que instalar eso obligue a instalar WhatsApp. Si solo
necesitás la inteligencia de clientes sin el chatroom, instalá
únicamente `crm_customer_intelligence`.

## Qué agrega

### 1-4. Oportunidades estancadas, RFM/ABC, ventas históricas y Pareto

Los campos y la lógica (`crm.lead.management_alert_state`,
`res.partner.rfm_category`/`rfm_score`, métricas de venta,
`_get_top_products()`) viven en
[`crm_customer_intelligence`](../crm_customer_intelligence/README.md) —
ver ese README para el detalle de cada uno. Este módulo solo agrega:
`chatroom.channel._get_relevant_lead()` (qué oportunidad "cuenta" para
la conversación: la anclada vía `pinned_lead_id` si sigue abierta, o si
no la más reciente del contacto) y
`chatroom.channel.get_commercial_intelligence()` (arma en una sola
llamada todo el paquete de datos que necesita el panel lateral).

### 5. Micro-indicadores en el chat

- Badge de categoría (A/B/C) junto al nombre del contacto en el
  encabezado del chat, en la lista de la app de una sola pantalla y en
  el kanban de conversaciones.
- Punto rojo (🔴 estancada) o de reloj (🟡 sin gestión reciente) en los
  mismos tres lugares.
- Aviso contextual amarillo/rojo arriba de los mensajes cuando la
  oportunidad lleva más de 7 días sin gestión, con un botón **Escribir
  mensaje** que enfoca directo el composer.

### 6. Panel lateral deslizable

Deslizar el dedo (swipe) sobre el área de mensajes, o el manijero visible
en el borde derecho (para mouse/teclado), abre un panel con la
"inteligencia profunda" sin salir del chat:

- **Salud de la oportunidad**: fecha de creación, última gestión, y un
  botón **Generar excusa de seguimiento** que usa el mismo proveedor de
  IA configurado en `chatroom_whatsapp` para redactar un mensaje corto
  de retoma de contacto — el texto se precarga en el composer, el
  vendedor lo revisa antes de enviar (no se manda solo).
- **Perfil de compra**: categoría/score RFM y chips visuales con los
  productos top (Pareto) en vez de una tabla de números.
- **Última venta**: total facturado, cantidad de facturas y fecha de la
  última.

Los datos completos se traen con una sola llamada
(`chatroom.channel.get_commercial_intelligence()`) recién cuando se abre
el panel, no en cada carga del chat — los micro-indicadores del punto 5
sí se cargan siempre, pero son solo 2-3 campos livianos.

## Instalación

1. Instalar `chatroom_whatsapp` (si no está instalado).
2. Instalar `chatroom_sales_intelligence` — arrastra automáticamente
   `crm_customer_intelligence` (y con él `crm`/`sale`/`account`) como
   dependencia.
3. (Opcional) Ejecutar manualmente el cron **Recalcular clasificación
   RFM de clientes** la primera vez, en vez de esperar a que corra
   solo, para ver las categorías A/B/C de inmediato.

## Alcance de esta versión

- El score RFM es relativo a la cartera de clientes con facturas en el
  momento del cálculo; agregar/quitar clientes cambia el ranking de
  todos, no solo del nuevo.
- El botón "Generar excusa de seguimiento" requiere la IA activada y
  configurada en Ajustes > Chatroom WhatsApp (mismo requisito que
  "Sugerir respuesta con IA" del módulo base).
- El gesto de deslizar (swipe) funciona en dispositivos táctiles; en
  desktop se usa el manijero visible del borde derecho del chat.
- El análisis Pareto usa `account.move.line` de facturas publicadas
  (`out_invoice`); no incluye presupuestos ni pedidos sin facturar.
