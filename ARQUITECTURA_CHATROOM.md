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
   Meta Cloud API (WhatsApp / Messenger / Instagram)
                     |
                     v
        /chatroom_whatsapp/webhook  (firma HMAC + evento auditable)
                     |
                     v
   chatroom.channel  +  chatroom.message ----> bus (refresco en vivo)
        |       |                                     |
        |       |                                     v
        |       |                        chatroom_ui / app de bandeja
        |       |
        |       +--> crm_customer_intelligence  (RFM / ABC / Pareto)
        |       |            |
        |       |            v
        |       |    crm_stagnation_management  (salud del pipeline)
        |       |            |
        |       |            v
        |       +--> chatroom_sales_intelligence  (solo presentación)
        |
        v
   chatroom_ai  (proveedor + respuesta)
        |
        +--> chatroom_ai_usage       modelos, costo, límites
        +--> chatroom_ai_knowledge   base de conocimiento
        +--> chatroom_ai_autonomy    política: asistir / aprobar / actuar
        +--> chatroom_ai_agent       tareas, herramientas, auditoría
                 |
                 v
        chatroom_ai_sales ──> chatroom_ai_sales_fulfillment
                 |
                 v
        chatroom_payment ──> chatroom_payment_payphone (opcional)
```

## Invariantes de rendimiento

La bandeja pinta hasta decenas de conversaciones a la vez y el hilo puede
tener miles de mensajes. Estas reglas evitan que una mejora funcional
devuelva la vista a tiempos de varios segundos:

1. **Ningún campo calculado hace una consulta por registro.** Los
   contadores de mensajes, la ventana de 24 h, el semáforo de SLA y los
   contadores de CRM/ventas/facturas se resuelven con agregados en lote
   (`_message_aggregates`, `_next_activity_by_partner`, `_read_group`).
   Un `search`/`search_count` dentro de un `for rec in self` es un error.
2. **Los filtros se resuelven en el servidor.** Los campos calculados que
   se usan como filtro (`first_response_sla_state`,
   `next_activity_overdue`) tienen método `search`. Filtrar en el
   navegador después de un `limit` esconde registros de forma silenciosa.
3. **Todo listado es paginado.** El hilo carga los últimos mensajes y
   ofrece "Ver mensajes anteriores"; la bandeja carga por tandas. Nada
   debe hacer un `searchRead` sin `limit`.
4. **El tiempo real lo lleva el bus; el sondeo es solo respaldo.** El
   sondeo del hilo se espacia solo cuando el bus está entregando eventos,
   cuando la pestaña está en segundo plano o cuando no hay actividad.
5. **Índices donde se ordena.** `chatroom.message` está indexado por
   `(channel_id, date, id)`, que es la forma de todas sus consultas
   calientes.

## Invariantes de envio y de tiempo

Todo lo que sale a la Cloud API de Meta tiene un efecto que no se puede
deshacer: el cliente ya recibio el mensaje. Y casi todo lo que decide
"cuando" pasa algo depende de la zona horaria del negocio, no de UTC.

1. **Un cron que envia confirma cada envio por separado.** Los mensajes
   programados y los reintentos usan `savepoint` por registro y
   `cr.commit()` (salvo en tests, via `modules.module.current_test`). Sin
   eso, una excepcion a mitad de la corrida revierte la transaccion y
   deja como "pendientes" mensajes que el cliente ya recibio: el cron
   siguiente los reenvia.
2. **Un cron que envia atrapa `Exception`, no solo `UserError`.** Un
   corte de red es `requests.RequestException` y tumbaba la corrida
   entera.
3. **Las fechas de negocio se calculan en la zona del negocio.** Nunca
   `fields.Date.today()` ni `datetime.date()` sobre un campo UTC para
   decidir "es hoy": en America eso ya es manana despues de las 19:00.
   Se usa `fields.Date.context_today` o `_business_hours_localize`.
4. **Los horarios admiten turnos que cruzan medianoche** (22:00-06:00) y
   toleran valores mal escritos en Ajustes sin romper el webhook.
5. **Las palabras clave de baja se comparan normalizadas** (sin acentos
   ni puntuacion) contra el mensaje COMPLETO. Ni por subcadena (daria de
   baja a quien pregunte "el precio baja?") ni por igualdad exacta del
   texto crudo (dejaba pasar "STOP." y "BAJA!").
6. **Un metodo `search` de campo calculado mira el CONTENIDO del valor,
   no su tipo.** Odoo normaliza `=` a `in` con un `OrderedSet`, que no es
   subclase de `set` y que siempre es "verdadero" si tiene un elemento.

## Como se prueba

- **Modelo y crons:** `chatroom_whatsapp/tests/test_chatroom.py`. Incluye
  regresiones de cada bug corregido (turno nocturno, ajuste no numerico,
  palabras clave de baja, agregados en lote, filtros `search`).
- **Interfaz:** `chatroom_whatsapp/tests/test_chatroom_tour.py` levanta la
  app en Chrome headless y recorre
  `static/tests/tours/chatroom_app_tour.js`: paginacion del historial,
  borradores por conversacion y busqueda contra el servidor. Es lo unico
  que detecta un bundle roto o una regresion de Owl.

  Requiere el paquete `websocket-client` en el Python de Odoo (no viene
  en `requirements.txt`, es dependencia opcional de los tests de
  navegador). Sin el, Odoo SALTA el test en vez de fallar, asi que
  conviene comprobar que aparece como ejecutado y no como omitido.

```bash
odoo-bin -d <base> -u chatroom_whatsapp --test-enable     --test-tags "/chatroom_whatsapp" --stop-after-init
```

En Windows, ejecutar esto desde Git Bash NO funciona: MSYS convierte la
barra inicial de `/chatroom_whatsapp` en una ruta (`C:/Program
Files/Git/chatroom_whatsapp`) y Odoo no encuentra ningun test, pero
termina con exito y reporta "0 tests". Hay que usar PowerShell o
`MSYS_NO_PATHCONV=1`. Un "0 tests" siempre hay que leerlo como un fallo
de invocacion, no como que todo esta bien.

Al escribir un paso de tour, la asercion va en el `trigger`, no dentro de
`run`: el hilo carga de forma asincrona y un `run` se ejecuta en cuanto el
selector existe, antes de que Owl haya repintado. Dos falsos positivos de
esta revision salieron justo de ahi.

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
