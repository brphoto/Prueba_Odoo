# Chatroom - Reuniones (Calendario)

Extiende (sin tocar) el módulo **Chatroom WhatsApp & Redes Sociales** con
un acceso directo al **Calendario nativo de Odoo** desde el panel de
contacto — para agendar una reunión con el cliente sin salir del chat.

## Por qué existe separado

Mismo criterio que `chatroom_sales_intelligence`: `chatroom_whatsapp` no
sabe nada de Calendario ni depende de este módulo. Toda la integración
se hace extendiendo el modelo (`chatroom.channel`) y parcheando el
componente OWL del panel de contacto (`patch()` + `t-inherit`), no
editando los archivos de `chatroom_whatsapp`. Desinstalar este módulo
deja el chatroom exactamente como estaba antes de instalarlo.

## Qué agrega

En el panel de contacto de la app de una sola pantalla, junto a los
botones de Oportunidad/Presupuesto/Factura/Compra/Tarea:

- **Botón "Reunión"**: abre el formulario real de `calendar.event`
  (invitaciones, videollamada, recordatorios — todo lo nativo de
  Calendario, no una versión reducida propia) como diálogo, precargado
  con el contacto de la conversación como invitado y el asunto
  sugerido ("Reunión con {nombre}"). El agente elige fecha/hora y
  confirma desde el formulario real; no se crea ningún evento solo.
- **Botón "Ver reuniones"** (ícono de calendario con check): con una
  sola reunión agendada para ese contacto, abre su formulario directo
  como diálogo. Con varias, navega a la vista de calendario/lista
  clásica filtrada por el contacto — un diálogo con varias vistas no
  deja entrar a un registro puntual (limitación real del framework de
  Odoo con diálogos multi-vista, documentada en el README de
  `chatroom_whatsapp`), así que se evita ese caso a propósito.

Se relaciona la conversación con sus reuniones buscando por
`partner_ids` en `calendar.event` (no hay un campo de vínculo directo
`chatroom.channel` → `calendar.event`, igual criterio que ya usa
`chatroom_sales_intelligence` para relacionar la conversación con la
oportunidad de CRM del contacto).

## Instalación

Instalar `chatroom_whatsapp` (si no está instalado) y luego
`chatroom_calendar` — arrastra `calendar` (siempre viene con Odoo base)
como dependencia automáticamente.

## Alcance de esta versión

- No hay un contador/badge de reuniones a la vista sin hacer clic (a
  propósito: se evaluó una tarjeta de estadística tipo "Oport."/"Ventas"
  pero hubiera necesitado una llamada adicional en cada carga de
  conversación solo para mostrar un número — se priorizó no agregar
  peso a un panel que el propio usuario pidió optimizar en espacio y
  funcionamiento).
- No crea ni vincula un `mail.activity` de tipo "Reunión" además del
  `calendar.event` (a diferencia de agendar una reunión desde el
  chatter estándar de Odoo, que sí crea los dos); por lo tanto una
  reunión agendada acá **no** aparece en la sección "Actividades
  pendientes" del panel de contacto — son dos listas separadas.
- Nuevo en esta iteración: validado con `py_compile` y parseo de XML,
  sin instalar el módulo de verdad en una base real todavía.
