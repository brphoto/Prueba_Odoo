# Demos y pruebas funcionales de IA

Base validada: `nominaec19`.

## Datos demo preparados

Se dejaron cuatro manuales indexados y vinculados a la empresa actual:

- **Servicios de implementación Odoo**: implementación, configuración, migración, capacitación, salida a producción y desarrollos a medida.
- **Tarifas y contratación**: tarifa referencial de **USD 20 por hora**, con aclaración de que el precio final depende del alcance aprobado.
- **Preguntas frecuentes comerciales**: guía para identificar necesidad, proceso actual, urgencia y siguiente paso.
- **Guía de atención por WhatsApp**: límites de la IA, escalamiento, consentimiento y casos que requieren revisión humana.

También se preparó el contacto y canal **DEMO IA | Cliente de prueba**, con nueve mensajes visibles de conversación, respuestas IA simuladas y una **propuesta comercial PDF** adjunta. El canal es de prueba y no se utilizó para enviar mensajes externos.

Los chats históricos **Contacto 1** y **Contacto 2** se conservaron sin cambios para revisar la bandeja y los flujos de Chatroom.

## Cómo revisar los demos

1. Entra a **Agente IA → Conocimiento → Base de conocimiento** y verifica que los cuatro manuales estén activos e indexados.
2. Abre **Probar conocimiento**, selecciona el canal demo y usa preguntas como:
   - `¿Cuál es la tarifa por hora?`
   - `Necesito personalizar mi CRM y conectar WhatsApp.`
   - `¿Pueden capacitar y acompañar el lanzamiento?`
   - `Quiero un descuento y una fecha de entrega.`
3. Revisa **Agente IA → Sandbox IA**. Se dejaron casos de respuesta, resumen, clasificación, próxima acción y agente para ejecutar de forma controlada.
4. Revisa **Agente IA → Autonomía → Simulador seguro** para comprobar qué acciones se permiten, cuáles requieren aprobación y cuáles quedan bloqueadas.
5. Revisa **Consumo de IA** para ver modelo, tokens y solicitudes auditadas.

## Resultado de las pruebas

- Catálogo de modelos sincronizado: el selector tiene modelos compatibles con Chatroom y el modelo configurado es `gpt-4o-mini`.
- Pruebas reales controladas contra OpenAI: **correctas**, 2 solicitudes y 1.190 tokens totales auditados; una consulta directa consumió 124 tokens y el caso de sandbox 1.066. No hubo envío a WhatsApp.
- Recuperación local: seis consultas probadas, con manuales y datos vivos de Odoo.
- Checklist del Agente IA: **6 de 6 comprobaciones listas**.

## Panel operativo y siguiente acción

En **Agente IA → Operación diaria → Operaciones → Panel operativo** el sistema
resume la atención prioritaria con un clic. La prioridad se ordena así:

1. pagos fallidos, tareas IA fallidas y conversaciones fuera de SLA;
2. actividades vencidas, oportunidades estancadas y entregas atrasadas;
3. conversaciones sin leer y pagos pendientes.

El botón **Atender prioridad** abre directamente la lista nativa correspondiente
en una ventana de Odoo. **Siguiente paso** dirige a la configuración guiada de
WhatsApp, a los ajustes de IA o al proveedor PayPhone según el estado real de
la base. No envía mensajes ni realiza cobros automáticamente.

La regresión completa posterior a esta mejora quedó en
`qa_full_suite_priority.log`: **141 pruebas, 0 fallos y 0 errores**.

## Segunda batería de pruebas QA

Se ejecutó una regresión ampliada sobre IA, autonomía, conocimiento,
operaciones, ventas, pagos, WhatsApp, notificaciones, CRM e inteligencia
comercial: **141 pruebas, 0 fallos y 0 errores**. El detalle está en
`qa_full_suite_extended.log`.

También se validó directamente sobre `nominaec19`:

- Canal demo largo: 30 mensajes; el reporte respeta un límite de 10 líneas.
- Recuperación local: 23 manuales indexados, 3 fuentes relevantes y contexto
  acotado a 1.658 caracteres / 415 tokens estimados.
- PDF real del canal demo: generado correctamente, 27.832 bytes y cabecera
  PDF válida. No se cerró el servidor.
- Política de autonomía en modo aprobación: pagos requieren aprobación,
  confianza baja requiere aprobación y confirmación de pedido queda bloqueada.
- Política autónoma limitada: monto superior al máximo requiere aprobación y
  monto dentro del límite queda permitido.
- Webhook: verificación inválida rechazada; verificación válida respondió
  correctamente con el challenge. El token usado fue temporal y se eliminó.
- Assets principales y `/web/login`: HTTP 200.
- Compilación Python de los módulos comerciales: correcta.
- Regresión automatizada anterior: **117 pruebas, 0 fallos y 0 errores**.
- Regresión completa posterior al flujo largo: **141 pruebas, 0 fallos y 0 errores**.
- Ventas autónomas globales: permanecen desactivadas para evitar confirmaciones reales durante QA.
- Política demo disponible: modo **Controlado: requiere aprobación**, con confirmación de pedidos y links de pago protegidos. Se deja inactiva por defecto para no cambiar la operación actual; actívala manualmente cuando quieras probarla.

## Seguridad del entorno de prueba

Los escenarios no llaman al envío externo de WhatsApp, no usan PayPhone y no crean cobros reales. La generación de texto contra OpenAI sí consume tokens y queda registrada en **Consumo de IA**.

## Flujo comercial largo y estancamiento

Se agregó el contacto **DEMO QA | Cliente flujo comercial largo** y el canal **DEMO QA | Cliente flujo comercial largo (WhatsApp)**. El canal contiene **30 mensajes** ordenados cronológicamente:

- descubrimiento de necesidad, módulos, usuarios e integraciones;
- preguntas sobre RFM/ABC, históricos y oportunidades olvidadas;
- tarifa referencial de USD 20 por hora y preparación de propuesta;
- objeción de presupuesto, trabajo por fases y cronograma;
- PDF de propuesta, solicitud de PayPhone, reunión y seguimiento;
- respuestas salientes marcadas como simulación IA, sin llamada de envío externo.

El canal está vinculado a tres oportunidades para revisar el semáforo de gestión:

| Oportunidad | Resultado esperado | Días | Capital estimado |
| --- | --- | ---: | ---: |
| DEMO QA — Oportunidad saludable - Fase 1 | Saludable | 2 | USD 0 |
| DEMO QA — Oportunidad en precaución - Integración | Precaución | 22 | USD 1.080 |
| DEMO QA — Oportunidad estancada - Proyecto integral | Estancada | 45 | USD 6.400 |

La oportunidad estancada está anclada al canal, tiene motivo **Sin respuesta del cliente**, probabilidad del 35 % y una próxima acción calculada por el módulo. La oportunidad saludable tiene una actividad pendiente **DEMO QA | Confirmar alcance** para probar el seguimiento normal.

Además, se dejó una cotización en borrador por aproximadamente USD 2.760 y un registro de pago **DEMO QA | Link PayPhone simulado** en estado **Generado**, con proveedor PayPhone de pruebas y URL `example.test`. Es un registro trazable para revisar la interfaz; no representa un cobro ni un envío real.

### Validaciones ejecutadas

- 30 mensajes: 15 entrantes, 15 salientes, 1 documento PDF y 15 marcados como generados por IA.
- Panel comercial: 3 oportunidades visibles y la oportunidad estancada seleccionada como contexto del canal.
- Estancamiento: estados `healthy`, `warning` y `stagnant` calculados correctamente; 45 días sin actividad y USD 6.400 atrapados en el caso crítico.
- Recuperación local de conocimiento: manuales encontrados para consultas de implementación, WhatsApp, presupuesto y tarifas; sin consumo de OpenAI.
- Cotización y link de pago: existen, son coherentes con el cliente y permanecen en modo seguro.
- Se conservó el evento demo `DEMO19 Evento 01` y se movió al día siguiente para que no interfiera con el test de eventos personalizados del mismo día.

Para revisar el flujo, abre el canal por su nombre, entra en **Oportunidades**, revisa las tres fichas y luego consulta el panel de **Inteligencia comercial**. En la oportunidad estancada usa **Actualizar análisis** y revisa el semáforo, días, capital y próxima acción.

## Panel operativo mejorado

El módulo `chatroom_ai_operations` ahora muestra tarjetas accionables para toda la operación. Cada tarjeta abre una lista filtrada en una ventana Odoo independiente: conversaciones activas, conversaciones sin leer, SLA, pagos fallidos o pendientes, carritos abandonados, entregas en curso o atrasadas, tareas y aprobaciones IA, oportunidades estancadas y contactos demo.

También se agregó el indicador **Oportunidades estancadas** y se corrigió el contador de demos para contemplar todos los registros con prefijo `DEMO QA`. La actualización del módulo fue validada con **15 pruebas propias, 0 fallos y 0 errores**.

La segunda mejora del tablero agregó **Oportunidades abiertas**, **Pipeline abierto**, **Capital atrapado**, **Actividades vencidas** y **Actividades de hoy**. Estos valores se calculan al actualizar el panel y las tarjetas de oportunidades/actividades abren directamente sus registros filtrados. La regresión completa posterior quedó en **141 pruebas, 0 fallos y 0 errores**.

La tercera mejora agregó el bloque **IA y control de consumo**, con solicitudes IA del día, tokens utilizados, fallos IA y estado resumido de configuración. Las solicitudes y fallos abren el detalle filtrado de consumo; el tablero no muestra claves ni datos sensibles. La actualización fue validada nuevamente con **15 pruebas del módulo y 141 pruebas globales, todas correctas**.

La cuarta mejora agregó **Salud de integraciones**. El panel identifica si existe una línea de WhatsApp con credenciales utilizables, si la IA está lista y si PayPhone está habilitado en modo de prueba o producción, sin exponer secretos. En la validación actual: IA **Lista**, PayPhone **Disponible** y WhatsApp **Sin línea configurada**; esto último es una alerta honesta de configuración, no un error del módulo.
