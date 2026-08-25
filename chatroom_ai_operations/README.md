# Chatroom Operaciones y Automatización

Módulo separado para operar Chatroom sin mezclar paneles, automatizaciones y demos dentro de los módulos de WhatsApp o IA.

## Menú

En **Agente IA > Operaciones** se encuentran:

- **Panel operativo**: métricas de conversaciones, SLA, pagos, entregas, IA, alertas y demos.
- **Playbooks de comunicación**: reglas parametrizables para carrito abandonado, pago fallido, entrega preparada, postventa, cumpleaños y pruebas manuales.
- **Demos QA**: genera seis escenarios visibles con el prefijo `DEMO QA` y tres playbooks de ejemplo desactivados.

## Seguridad y envío

Los playbooks nacen en modo **Solo avisar al equipo** y con aprobación humana. Para enviar una plantilla se requiere seleccionar una plantilla WhatsApp aprobada y quitar la aprobación obligatoria. El método de envío reutiliza `chatroom.channel.action_send_template`, por lo que no se envía texto libre fuera de la ventana permitida.

El cron de playbooks corre cada hora, respeta el máximo por ejecución, la espera mínima y las notificaciones deduplicadas. Los escenarios DEMO no llaman a Meta, PayPhone ni a ningún proveedor externo.
