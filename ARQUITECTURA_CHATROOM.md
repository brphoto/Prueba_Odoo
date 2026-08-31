# Arquitectura funcional de Chatroom

Este documento define la responsabilidad de cada módulo y evita agregar la
misma lógica en varios lugares. La regla general es: **un motor calcula y las
capas de integración solo muestran o conectan**.

## Capas del producto

### Base y canal

- `chatroom_whatsapp`: conversaciones, mensajes, plantillas, webhook de Meta,
  adjuntos, reintentos y conversaciones desde el chatter.
- `chatroom_ui`: tema visual, preferencias de usuario y comportamiento
  responsive. No calcula RFM ni decide acciones de IA.
- `chatroom_calendar`: reuniones y acciones de calendario.

### Inteligencia comercial

- `crm_customer_intelligence`: motor único de RFM/ABC, Pareto, históricos,
  segmentos, reglas de reactivación y KPI de clientes.
- `crm_stagnation_management`: motor único de salud y estancamiento de
  oportunidades, límites por etapa, capital atrapado y depuración.
- `crm_stagnation_intelligence`: integración ligera que combina los motores
  anteriores en una vista ejecutiva. No debe recibir nuevos cálculos.
- `chatroom_sales_intelligence`: capa de presentación dentro de Chatroom,
  campañas RFM, conocimiento comercial y acceso contextual al CRM. Reutiliza
  los motores anteriores.
- `crm_customer_history`: carga de históricos comerciales sin modificar las
  ventas actuales; alimenta el análisis RFM.

### IA

- `chatroom_ai`: proveedor/base de integración y respuestas IA.
- `chatroom_ai_usage`: modelos disponibles, consumo, costos, límites,
  pruebas y simulador seguro.
- `chatroom_ai_knowledge`: asistentes de carga y configuración del
  conocimiento.
- `chatroom_ai_agent`: tareas, planes, herramientas, memoria, automatizaciones,
  aprobaciones, auditoría y checklist operativo.
- `chatroom_ai_autonomy`: políticas por empresa, canal o cliente para definir
  cuándo la IA asiste, solicita aprobación o actúa automáticamente.
- `chatroom_ai_operations`: operaciones y automatizaciones complementarias.

### Ventas y pagos

- `chatroom_ai_sales`: conversión controlada de conversaciones en oportunidades,
  cotizaciones y acciones comerciales.
- `chatroom_ai_sales_fulfillment`: validación posterior de inventario,
  entrega y cumplimiento.
- `chatroom_ai_sales_payment`: acciones posteriores a pago y trazabilidad.
- `chatroom_payment`: contrato común de enlaces de pago.
- `chatroom_payment_payphone`: conector opcional de PayPhone; solo se instala
  cuando se desea ese proveedor.

### Operación y soporte

- `chatroom_notifications`: notificaciones y recordatorios.
- `chatroom_control_center`: panel resumido de accesos y estado.
- `kpi_engine`: mixin compartido para objetivos y mediciones.

## Flujo recomendado

```text
WhatsApp / chatter
        |
        v
chatroom_whatsapp -----> crm_customer_intelligence
        |                         |
        |                         v
        |                crm_stagnation_management
        |                         |
        v                         v
chatroom_ai_agent <------- chatroom_sales_intelligence
        |
        +--> chatroom_ai_knowledge / chatroom_ai_usage
        +--> chatroom_ai_autonomy
        +--> chatroom_ai_sales
                         |
                         +-ment --> PayPhone opcional-> chatroom_pay
```

## Reglas para nuevas mejoras

1. No agregar cálculos RFM en Chatroom; se consultan desde
   `crm_customer_intelligence`.
2. No agregar otro semáforo de oportunidades; se consulta desde
   `crm_stagnation_management`.
3. No enviar mensajes directamente desde el agente: se crea una acción
   autorizada y se utiliza el conector de WhatsApp.
4. No guardar claves en código, archivos de requisitos ni datos demo.
5. Las acciones comerciales sensibles requieren aprobación, salvo una política
   autónoma explícita con límites.
6. Todo proceso costoso debe ser acotado, reintentable y auditable.
7. Los módulos opcionales deben ampliar mediante herencia o integración, sin
   hacer que el núcleo dependa de PayPhone, IA u OCR.

## Orden de configuración para un cliente nuevo

1. Instalar Chatroom y configurar WhatsApp.
2. Instalar la inteligencia de clientes si se necesitan RFM/ABC.
3. Instalar gestión de estancadas si se necesita salud del pipeline.
4. Instalar enlaces de pago y, opcionalmente, PayPhone.
5. Instalar IA, seleccionar proveedor/modelo y revisar el checklist.
6. Crear conocimiento, indexarlo, revisarlo y publicarlo.
7. Definir políticas de autonomía y automatizaciones.
8. Ejecutar el simulador y activar producción progresivamente.
