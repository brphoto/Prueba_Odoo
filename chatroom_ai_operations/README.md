# Chatroom Operaciones y Automatización

Módulo separado para operar Chatroom sin mezclar paneles, automatizaciones y demos dentro de los módulos de WhatsApp o IA.

## Menú

En **Agente IA > Operaciones** se encuentran:

- **Panel operativo**: métricas de conversaciones, SLA, pagos, entregas, IA, alertas y demos.
- **Playbooks de comunicación**: reglas parametrizables para carrito abandonado, pago fallido, entrega preparada, postventa, cumpleaños y pruebas manuales.
- **Demos QA**: genera seis escenarios visibles con el prefijo `DEMO QA` y tres playbooks de ejemplo desactivados.
- **Salud y preparación**: comprueba doce capacidades locales por empresa (WhatsApp, proveedor IA, conocimiento, catálogo, Ventas, Calendario, pagos, seguridad, dependencias, costos, automatizaciones y Chatter). Las comprobaciones son persistentes, tienen recomendación accionable y no llaman APIs externas ni consumen tokens.

## Lote DEMO QA persistente

En `nominaec19` se dejó generado el lote **DEMO QA** para revisión funcional. Incluye seis conversaciones marcadas: carrito abandonado, confirmación pendiente, pedido confirmado, pago recibido, entrega preparada y escalamiento a humano. También deja tres playbooks inactivos para probar alcance e historial sin activar envíos.

Para repetirlo desde Odoo: abre **Agente IA > Operaciones > Demos QA** y pulsa **Generar escenarios**. La operación es idempotente y no borra pruebas existentes. Para validar el estado general, abre **Agente IA > Operaciones > Salud y preparación** y pulsa **Comprobar todo**.

## Historial y control de ejecuciones

Cada playbook conserva un resumen rápido y un historial persistente. Al pulsar
**Ejecutar ahora**, o cuando actúa el cron, se registra una ejecución con:

- origen manual o automático y fecha;
- canales procesados;
- avisos internos, plantillas enviadas, bloqueos y errores;
- estado final: completada, con incidencias o fallida.

Desde la ficha del playbook usa **Ver historial** para abrir la lista completa;
también puedes consultar la pestaña **Historial** de la misma ficha. Cada
ejecución tiene su propia ficha Odoo y Chatter para dejar trazabilidad sin
mezclarla con la configuración.

Los playbooks están aislados por empresa. El modo seguro no usa tokens, no
llama a proveedores externos y no envía WhatsApp. Las plantillas y acciones de
envío siguen sujetas a aprobación humana, permisos y validación de estado en
Meta.

## Seguridad y envío

Los playbooks nacen en modo **Solo avisar al equipo** y con aprobación humana. Para enviar una plantilla se requiere seleccionar una plantilla WhatsApp aprobada y quitar la aprobación obligatoria. El método de envío reutiliza `chatroom.channel.action_send_template`, por lo que no se envía texto libre fuera de la ventana permitida.

El cron de playbooks corre cada hora, respeta el máximo por ejecución, la espera mínima y las notificaciones deduplicadas. Los escenarios DEMO no llaman a Meta, PayPhone ni a ningún proveedor externo.
