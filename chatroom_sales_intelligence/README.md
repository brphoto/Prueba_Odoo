# Chatroom - Inteligencia Comercial (Odoo 19)

Módulo **opcional y desacoplado** que agrega inteligencia comercial al
[Chatroom WhatsApp & Redes Sociales](../chatroom_whatsapp/README.md):
oportunidades estancadas, clasificación RFM/ABC, métricas históricas de
venta y análisis de Pareto (80/20), todo visible sin salir del chat.

## Diseño modular: "engancha", no modifica

Este módulo **depende de** `chatroom_whatsapp` (además de `crm`, `sale` y
`account`), pero `chatroom_whatsapp` **no depende de él ni sabe que
existe**. Toda la integración se hace desde afuera:

- **Vistas**: herencia estándar de `ir.ui.view` (`inherit_id` +
  `xpath`) sobre el formulario de contacto y el kanban de conversaciones.
- **Componentes OWL**: herencia de templates (`t-inherit` +
  `t-inherit-mode="extension"`) y `patch()` de las clases JS existentes
  (`ChatroomThreadCore`, `ChatroomApp`), en vez de copiar o reemplazar
  esos archivos.
- **Ningún modelo nuevo**: todos los campos son extensiones
  (`_inherit`) de `res.partner`, `crm.lead` y `chatroom.channel`, así que
  no hace falta tocar `ir.model.access.csv`.

Si desinstalás `chatroom_sales_intelligence`, el chatroom queda
exactamente como estaba antes de instalarlo — ni un botón, badge o campo
de más.

## Qué agrega

### 1. Oportunidades estancadas (semáforo de seguimiento)

Sobre `crm.lead`: `days_since_last_management` (días desde la fecha más
reciente entre el cambio de etapa nativo `date_last_stage_update`, el
último mensaje del chatter y la última actividad registrada) y
`management_alert_state` (🟢 ≤7 días, 🟡 8-15 días, 🔴 >15 días).
`chatroom.channel` resuelve automáticamente qué oportunidad "cuenta"
para la conversación: la anclada (`pinned_lead_id`) si sigue abierta, o
si no la oportunidad abierta más reciente del contacto.

### 2. Clasificación RFM / ABC

Cron diario (`_cron_compute_rfm_scores`) que calcula, para toda la
cartera de clientes con al menos una factura, un score 1-100 combinando
percentiles de Recencia (20%), Frecuencia (30%) y Monto (50%), y lo
traduce a una categoría simple: **A** (≥70), **B** (≥40) o **C**. Es a
propósito un cálculo relativo entre clientes (no un umbral fijo por
contacto), por eso corre en lote en vez de como campo computado normal.

### 3. Métricas históricas de venta

En `res.partner`: total facturado (facturas de venta en estado
publicada), cantidad de facturas, fecha de la última venta y ticket
promedio — visibles en una pestaña nueva "Inteligencia Comercial" en la
ficha del contacto.

### 4. Análisis Pareto (80/20)

`res.partner._get_top_products()` calcula, a partir de las líneas de
factura publicadas, los productos más comprados por el contacto con su
% sobre el total. Se resume en un campo (`commercial_top_product_summary`,
ej. *"Top: Producto X (42% de sus compras)"*) y hay un botón inteligente
**Top Productos** en la ficha del contacto que abre `account.invoice.report`
agrupado por producto para ver el detalle completo.

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
2. Instalar `crm`, `sale` y `account` (dependencias nativas de Odoo).
3. Instalar `chatroom_sales_intelligence`.
4. (Opcional) Ejecutar manualmente el cron **Chatroom: recalcular
   clasificación RFM de clientes** la primera vez, en vez de esperar a
   que corra solo, para ver las categorías A/B/C de inmediato.

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
