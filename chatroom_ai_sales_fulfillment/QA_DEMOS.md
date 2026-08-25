# Demos y pruebas funcionales de Chatroom

Base validada: `nominaec19`.

## Escenarios DEMO QA creados

Buscar en **Chatroom → Conversaciones** por `DEMO QA`:

| Escenario | Estado esperado | Qué revisar |
|---|---|---|
| DEMO QA - Carrito abandonado | Armando carrito | Carrito con producto y evento de carrito actualizado. Tiene fecha antigua para probar el recordatorio. |
| DEMO QA - Esperando confirmación | Esperando confirmación | La venta no debe cerrarse sin una confirmación explícita. |
| DEMO QA - Pedido confirmado | Pedido confirmado | Pedido de ventas relacionado y evento de confirmación. |
| DEMO QA - Pago recibido | Postventa | Enlace de pago simulado en estado pagado; la URL es de prueba y no cobra. |
| DEMO QA - Entrega lista | Postventa / entrega lista | Despacho de inventario relacionado y evento de entrega preparada. |
| DEMO QA - Escalado a humano | Revisión humana | Bloqueo visible para validar la derivación a un agente. |

Los registros DEMO QA no envían mensajes ni usan PayPhone. El único enlace de pago
apunta a `example.test` y no representa una transacción real.

## Pruebas automatizadas ejecutadas

La regresión funcional ejecutada sobre la base incluyó 24 pruebas:

- agente IA: menú, memoria, automatizaciones, aprobaciones y respuestas locales;
- ventas autónomas: carrito, confirmación explícita y límite de monto;
- pagos: postventa, notificación y conservación de errores para reintento;
- cumplimiento: inventario, dirección, despacho, carrito abandonado y reintento de pago.

Resultado: **24 pruebas, 0 fallos, 0 errores**.

Archivo de pruebas: `tests/test_fulfillment.py`.

## Configuración segura para revisar

En **Ajustes → Ventas autónomas** se pueden activar las políticas una por una.
Por seguridad, los recordatorios de carrito, los reintentos de pago, la validación
obligatoria de inventario y la exigencia de dirección permanecen apagados hasta que
el administrador los habilite. Las notificaciones de entrega sí vienen activas,
pero requieren un pedido real y un conector WhatsApp configurado.
