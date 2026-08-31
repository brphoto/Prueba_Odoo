# Chatroom CRM Omnicanal — artefacto maestro de QA, configuración y operación

**Base auditada:** `nominaec19`  
**Odoo:** 19 Enterprise  
**Fecha de revisión:** 26 de agosto de 2026  
**Ruta de módulos:** `C:\Program Files\Odoo 19.0e.20251201\server\addons\Prueba_Odoo`

## 1. Resumen ejecutivo

La solución está organizada como una plataforma modular de atención, ventas y analítica comercial sobre Odoo. El núcleo de WhatsApp no depende obligatoriamente de IA, PayPhone ni de la capa visual; cada capacidad puede instalarse y gobernarse por separado.

### Estado actual

| Área | Estado local | Evidencia |
|---|---|---|
| Carga de módulos y vistas | Validado | Actualización de 24 módulos objetivo, salida 0 |
| Pruebas automáticas | Validado | 142 pruebas, 0 fallos, 0 errores |
| WhatsApp y conversaciones | Validado con simulación | Webhook, idempotencia, canales, mensajes, auditoría y demo larga |
| RFM/ABC y Pareto | Validado | Reglas, recalculo, segmentos, históricos y campañas |
| Oportunidades estancadas | Validado | Semáforo, días, capital atrapado, depuración y tendencia |
| IA local | Validado | Manuales, contexto local, simulador, fuentes y trazabilidad |
| IA externa/OpenAI | Preparado | Requiere proveedor, clave y modelo configurados; no se considera probado contra cobro real |
| Enlaces de pago | Validado en modo controlado | Flujo base, PayPhone opcional, reintentos y auditoría |
| PDF de conversación | Validado | Reporte PDF generado: 27.832 bytes, cabecera `%PDF` |
| Cobro real de PayPhone | Pendiente externo | Requiere credenciales y ambiente sandbox/producción |
| Envío real por Meta WhatsApp | Pendiente externo | Requiere credenciales, número y webhook público |

**Conclusión:** la base es funcional para pruebas internas y demostración. Las integraciones externas deben cerrarse con credenciales reales y pruebas controladas antes de venderla como operación autónoma en producción.

## 2. Arquitectura y modularidad

```text
chatroom_whatsapp
├── chatroom_ui                         capa visual opcional
├── chatroom_calendar                   reuniones opcionales
├── chatroom_payment                    enlaces de pago base
│   └── chatroom_payment_payphone       conector PayPhone opcional
├── chatroom_ai                         sugerencias aprobables
│   ├── chatroom_ai_agent               agente, memoria, herramientas y automatizaciones
│   │   ├── chatroom_ai_knowledge       menú del conocimiento
│   │   ├── chatroom_ai_autonomy        políticas y simulador seguro
│   │   ├── chatroom_ai_usage           modelos y consumo
│   │   ├── chatroom_ai_operations      panel operativo y playbooks
│   │   ├── chatroom_ai_sales           ventas conversacionales
│   │   ├── chatroom_ai_sales_payment   postventa de pago y factura
│   │   └── chatroom_ai_sales_fulfillment inventario, entrega y carrito
│   └── chatroom_notifications          alertas y escalamiento
├── crm_customer_intelligence           RFM, ABC, Pareto, segmentos y KPIs
├── crm_customer_history                históricos sin crear ventas ni productos
├── crm_stagnation_management           reglas de estancamiento
├── crm_stagnation_intelligence         lectura integral RFM + pipeline
├── crm_engagement_automation           cumpleaños, recordatorios y mensajes
├── chatroom_sales_intelligence         paneles, campañas y conocimiento comercial
└── kpi_engine                          motor compartido de indicadores
```

La separación permite instalar WhatsApp sin IA, usar RFM sin IA, usar Payment Links sin PayPhone y cambiar el proveedor de IA sin modificar la operación comercial.

## 3. Inventario de módulos y función

| Módulo | Propósito | Menú o entrada principal |
|---|---|---|
| `chatroom_whatsapp` | Canales, conversaciones, mensajes, plantillas, webhook, auditoría, dashboard y reportes | Chatroom → Operación / Comunicación / Configuración |
| `chatroom_ui` | Tema, colores, fondo, tamaño y preferencias visuales del Chatroom | Ajustes de Chatroom UI |
| `chatroom_calendar` | Reuniones y eventos relacionados con conversaciones | Reuniones |
| `chatroom_payment` | Enlaces de pago desacoplados del proveedor | Enlaces de pago |
| `chatroom_payment_payphone` | Adaptador PayPhone para generar y notificar enlaces | Configuración del proveedor PayPhone |
| `chatroom_ai` | Sugerencias IA con aprobación, intención, confianza y trazabilidad | Sugerencias de IA |
| `chatroom_ai_agent` | Agente operativo, tareas, herramientas, memoria, auditoría y automatizaciones | Agente IA |
| `chatroom_ai_knowledge` | Acceso sencillo a conocimiento y prueba de fuentes | Agente IA → Conocimiento |
| `chatroom_ai_autonomy` | Perfiles, políticas, decisiones, plantillas y simulador sin envío | Agente IA → Conocimiento y autonomía |
| `chatroom_ai_usage` | Selector de modelos, solicitudes, tokens, costos y calidad | Consumo de IA |
| `chatroom_ai_operations` | Prioridades, siguiente acción, métricas, playbooks y demos QA | Agente IA → Operaciones |
| `chatroom_ai_sales` | Conversación → carrito/cotización/pedido con controles | Agente IA → Ventas autónomas |
| `chatroom_ai_sales_payment` | Confirmación de pago, factura y comunicación postventa | Actividad y auditoría |
| `chatroom_ai_sales_fulfillment` | Stock, dirección, entrega, carrito abandonado y reintentos | Ventas autónomas |
| `chatroom_notifications` | Alertas, SLA, escalamiento y seguimiento operativo | Operación → Notificaciones |
| `chatroom_sales_intelligence` | Paneles comerciales, campañas RFM, automatizaciones, conocimiento y reportes | Inteligencia comercial |
| `crm_customer_intelligence` | RFM/ABC, Pareto, segmentos, objetivos, snapshots y alertas | CRM → Inteligencia Comercial |
| `crm_customer_history` | Carga de históricos de compras sin alterar ventas ni productos | Históricos comerciales |
| `crm_stagnation_management` | Oportunidades estancadas, semáforo, capital atrapado y depuración | CRM → Estancamiento |
| `crm_stagnation_intelligence` | Vista integral de salud del pipeline | Inteligencia Comercial → Salud del pipeline |
| `crm_engagement_automation` | Cumpleaños, recordatorios y eventos comerciales personalizados | Automatizaciones comerciales |
| `kpi_engine` | Motor común para definiciones, objetivos, snapshots y cálculo | Usado por Chatroom y CRM |
| `payment_payphone` | Proveedor PayPhone para Odoo Payment | Facturación → Proveedores de pago |
| `chatroom_control_center` | Accesos rápidos y estado general de integraciones | Centro de control |

## 4. Orden recomendado de configuración

### Fase A — Base y canales

1. Confirmar compañía, moneda, zona horaria, usuarios y correo saliente.
2. Instalar `chatroom_whatsapp` y abrir **Chatroom → Configuración guiada**.
3. Crear una línea/canal y definir usuario responsable, equipo, etapas y etiquetas.
4. Configurar webhook Meta: URL pública HTTPS, token de verificación y firma `X-Hub-Signature-256`.
5. Crear plantillas aprobadas por Meta. Usar el detector de variables y validar cada plantilla antes de enviarla.
6. Probar primero con conversaciones de prueba; no iniciar envíos masivos.

### Fase B — CRM y segmentación

1. Instalar `crm_customer_intelligence`.
2. Revisar el **Catálogo RFM** y definir categorías RFM/ABC según el negocio.
3. Configurar ventanas de análisis, pesos, umbrales y reglas de categoría.
4. Si existen históricos, instalar `crm_customer_history`, crear una carga y subir líneas con:
   - cliente/contacto;
   - fecha de compra;
   - número o referencia de factura;
   - monto;
   - estado de pago, si está disponible;
   - producto o descripción opcional.
5. Validar la carga y ejecutar recalculo. Los históricos alimentan RFM y no crean ventas, productos ni facturas.
6. Revisar segmentos, clientes por categoría, snapshots y campañas de reactivación.

### Fase C — Estancamiento y salud comercial

1. Instalar `crm_stagnation_management`.
2. Crear reglas por equipo, etapa, días máximos y nivel de riesgo.
3. Definir exclusiones: oportunidades ganadas/perdidas, equipos o etapas especiales.
4. Ejecutar análisis y revisar:
   - días en etapa;
   - días sin actividad;
   - nivel saludable, advertencia o crítico;
   - capital estimado atrapado;
   - diferencia entre probabilidad real y ficticia;
   - recomendación de mantener, revisar o depurar.
5. Usar `crm_stagnation_intelligence` para cruzar estancamiento con RFM y priorizar acciones.

### Fase D — Pagos y postventa

1. Instalar `chatroom_payment` para mantener la abstracción de enlaces.
2. Instalar `payment_payphone` y `chatroom_payment_payphone` solo si PayPhone será utilizado.
3. Configurar ambiente sandbox, token, store/entorno y datos del proveedor.
4. Generar un enlace desde una oportunidad, presupuesto o conversación.
5. Verificar estado pendiente, pagado, expirado o fallido, y el registro de auditoría.
6. Probar reintento limitado y notificación postventa antes de activar cobro real.

### Fase E — IA y conocimiento

1. Instalar `chatroom_ai` si se requieren sugerencias en la conversación.
2. Instalar `chatroom_ai_agent` para tareas, memoria, herramientas y automatizaciones.
3. Configurar proveedor y modelo en **Consumo de IA → Modelos disponibles**. No escribir el modelo manualmente si existe selector.
4. Instalar `chatroom_ai_knowledge` y crear un perfil de conocimiento.
5. Cargar manuales propios de la empresa, precios, catálogo, políticas, preguntas frecuentes y procesos.
6. Indexar, probar con preguntas conocidas y revisar fuentes encontradas antes de habilitar respuestas.
7. Activar primero modo asistido, luego aprobación humana y solo después autonomía limitada.

### Fase F — Operación, automatizaciones y KPI

1. Configurar notificaciones, SLA y responsables.
2. Crear recordatorios de cumpleaños, renovación, vencimiento, seguimiento y pago.
3. Definir KPIs y metas por equipo, agente, canal y período.
4. Revisar el panel operativo diario y el tablero ejecutivo.
5. Ejecutar los demos QA conservándolos para capacitación y regresión.

## 5. Cómo configurar el conocimiento de la IA

### Qué significa “entrenar” en esta solución

El flujo recomendado no consiste en reentrenar un modelo cada vez que cambia un precio. Se usa una base local de conocimiento con indexación, selección de fuentes relevantes y datos vivos de Odoo. Esto reduce costos y permite corregir información sin volver a entrenar el modelo.

### Fuentes recomendadas

| Fuente | Ejemplo | Frecuencia |
|---|---|---|
| Manual de texto | `Servicios y alcance.txt` | Al cambiar el proceso |
| PDF | catálogo, política, contrato o instructivo | Al actualizar el documento |
| Preguntas frecuentes | horarios, garantías, cobertura | Mensual o cuando cambie |
| Catálogo Odoo | productos, precios y disponibilidad | Consulta viva |
| Empresa Odoo | nombre, correo, teléfono, dirección | Consulta viva |
| CRM | cliente, RFM, oportunidad y próxima acción | Consulta viva |
| Históricos | compras anteriores y monto acumulado | Después de cada carga |

### Procedimiento amigable para un usuario no técnico

1. Entrar a **Agente IA → Conocimiento y autonomía → Perfiles de conocimiento**.
2. Crear o abrir el perfil de la empresa.
3. En **Manuales para IA**, pulsar **Nuevo**.
4. Elegir origen: texto o PDF; pegar contenido o adjuntar archivo.
5. Escribir un nombre claro, categoría, etiquetas de palabras clave y prioridad.
6. Guardar y pulsar **Indexar**.
7. Confirmar estado **Indexado**, cantidad de fragmentos y fecha de revisión.
8. Abrir **Probar conocimiento**, hacer preguntas reales y revisar las fuentes encontradas.
9. Si la respuesta es correcta, asociar el perfil al agente; si no, corregir el manual y volver a indexar.

### Campos importantes de la base local

- **Nombre:** identificador visible para el equipo.
- **Categoría:** empresa, servicios, precios, catálogo, soporte, políticas o proceso.
- **Prioridad:** orden de preferencia cuando existen fuentes similares.
- **Origen:** texto o PDF.
- **Etiquetas:** palabras que ayudan a encontrar la fuente.
- **Estado:** pendiente, indexado o error.
- **Versión y digest:** evita reprocesar contenido que no cambió.
- **Revisión:** fecha y periodicidad para que un manual no quede obsoleto.
- **Uso:** contador y última fecha en que se utilizó la fuente.

### Optimización de tokens

- Mantener manuales cortos, por tema y con títulos claros.
- Evitar copiar conversaciones completas como conocimiento permanente.
- Mantener precios y existencias como datos vivos de Odoo.
- Usar etiquetas y categorías para seleccionar solo las fuentes necesarias.
- Limitar fragmentos y caracteres de contexto; el simulador muestra tokens estimados.
- No enviar el manual completo en cada pregunta.
- Reindexar solo cuando cambie el digest del contenido.
- Resumir conversaciones antes de guardarlas como memoria.
- Usar el modelo económico para clasificación y el modelo más capaz solo para casos complejos.
- Revisar consumo por solicitud en **Consumo de IA → Actividad por solicitud**.

### Base de conocimiento inicial sugerida para la empresa

1. Quiénes somos: implementadores de Odoo y desarrollo personalizado.
2. Servicios: implementación, CRM, WhatsApp, integraciones, soporte y capacitación.
3. Tarifa referencial: USD 20 por hora, sujeto a alcance y propuesta.
4. Preguntas frecuentes: tiempos, información requerida, reuniones y soporte.
5. Productos y servicios de Odoo disponibles en la base.
6. Políticas de pago, entrega, cambios y escalamiento a una persona.
7. Guía de tono: español claro, profesional, breve y sin prometer lo que no está confirmado.

## 6. Modos de operación de IA

| Modo | Qué hace | Uso recomendado |
|---|---|---|
| Asistido | Sugiere respuesta; el agente decide | Inicio y capacitación |
| Aprobación | Puede preparar acciones, pero requiere aprobación | Cotizaciones, descuentos, pagos y respuestas sensibles |
| Autónomo limitado | Ejecuta acciones permitidas dentro de límites | Preguntas frecuentes, clasificación y seguimiento de bajo riesgo |
| Autónomo comercial | Puede cotizar, tomar pedido y cobrar según políticas | Solo después de sandbox, métricas y aprobación de dirección |

La política puede controlar respuesta, cotización, pedido, pago, entrega, monto máximo, confianza mínima, límite diario, descuentos y mensajes de contenido negativo. Toda decisión debe quedar en la trazabilidad del agente.

### Ejemplos de decisión

- Pregunta sobre horario con fuente confiable: permitir respuesta.
- Pregunta sin fuente suficiente: escalar o pedir aprobación.
- Cotización menor al límite y con producto disponible: permitir o solicitar aprobación según política.
- Descuento no autorizado: bloquear.
- Pago real: aprobación obligatoria hasta completar pruebas externas.
- Dirección de entrega incompleta: solicitar datos, no confirmar entrega.

## 7. Casos de uso completos

### Caso 1 — Nuevo contacto desde WhatsApp

1. Llega mensaje entrante.
2. Se normaliza el teléfono y se busca/crea el contacto.
3. Se crea o reutiliza el canal correcto de forma idempotente.
4. Se guarda el mensaje y se asigna responsable.
5. IA clasifica intención y propone siguiente acción.
6. El agente responde, pide datos o crea oportunidad.

### Caso 2 — Consulta de producto y cotización

1. IA consulta producto, precio y disponibilidad desde Odoo.
2. Responde solo con datos disponibles.
3. Si faltan cantidades o configuración, pregunta antes de cotizar.
4. Genera oportunidad o cotización.
5. Envía enlace de pago si la política lo permite.
6. Deja actividad de seguimiento.

### Caso 3 — Pago y postventa

1. Se genera Payment Link.
2. Se notifica por WhatsApp cuando el canal y la ventana lo permiten; si no, se utiliza plantilla aprobada.
3. Se recibe confirmación del proveedor.
4. Se actualiza pago, pedido y factura según configuración.
5. Se notifica el resultado y se crea actividad si falla.
6. El reintento es limitado y auditable.

### Caso 4 — RFM/ABC y reactivación

1. Odoo toma compras reales e históricos válidos.
2. Se calculan recencia, frecuencia, monto y score.
3. El catálogo asigna A/B/C o categorías personalizadas.
4. Se segmentan clientes y se genera campaña.
5. La automatización envía mensaje personalizado con variables fáciles de seleccionar.
6. Se mide respuesta, conversión y cambio de categoría.

### Caso 5 — Oportunidad estancada

1. Una regla detecta días en etapa o días sin actividad.
2. Se calcula semáforo y capital atrapado.
3. Se crea alerta, actividad o playbook.
4. El responsable revisa la oportunidad.
5. Puede continuar, cambiar etapa, reactivar o depurar.
6. El histórico permite medir cuánto pipeline se recuperó.

### Caso 6 — Cumpleaños y recordatorios

1. Se define evento, audiencia, plantilla, canal y horario.
2. Se eligen variables desde campos guiados, no escribiendo expresiones técnicas.
3. Se aplica ventana de anticipación y frecuencia máxima.
4. El sistema genera cola de envíos.
5. Se registran enviados, fallidos, reintentos y respuestas.

### Caso 7 — Atención IA con escalamiento

1. IA detecta intención, confianza y sentimiento/riesgo.
2. Responde si la fuente y política son suficientes.
3. Si no, crea tarea para agente.
4. El supervisor revisa la cola priorizada.
5. La respuesta humana puede convertirse en manual o ejemplo revisado.

## 8. Paneles, menús y métricas

### Chatroom

- **Dashboard:** volumen, pendientes, SLA y actividad.
- **Operación:** conversaciones, nuevas conversaciones, mensajes fallidos, programados y notificaciones.
- **Comunicación:** plantillas, respuestas rápidas y sugerencias IA.
- **Configuración:** canales, líneas, etapas, etiquetas, perfiles y herramientas de prueba.

### Inteligencia comercial

- Mis pendientes.
- Dashboard RFM y KPIs.
- Salud del pipeline.
- Tablero ejecutivo.
- Automatizaciones comerciales.
- Campañas RFM.
- Manuales para IA y prueba de conocimiento.
- Reportes programados.

### Agente IA

- Resumen ejecutivo.
- Centro de control IA.
- Aprobaciones pendientes.
- Tareas fallidas.
- Tareas.
- Checklist de preparación.
- Automatizaciones.
- Herramientas autorizadas.
- Memoria empresarial.
- Auditoría.
- Conocimiento y autonomía.

### Consumo de IA

- Resumen de consumo.
- Modelos disponibles.
- Actividad por solicitud.
- Pruebas de calidad.
- Historial de pruebas.
- Simulador IA sin envío.

### KPIs recomendados

| KPI | Qué mide | Acción de gestión |
|---|---|---|
| Conversaciones entrantes | Demanda por canal | Distribuir agentes |
| Tiempo de primera respuesta | Velocidad de atención | Ajustar turnos y SLA |
| Conversaciones sin asignar | Riesgo de abandono | Asignación automática |
| Mensajes fallidos | Salud técnica | Revisar token, plantilla y proveedor |
| Oportunidades nuevas | Captación | Medir campañas |
| Conversión por etapa | Eficacia comercial | Mejorar guiones |
| Pipeline estancado | Riesgo comercial | Activar playbook |
| Capital atrapado | Valor inmovilizado | Priorizar recuperación |
| Clientes A/B/C | Concentración de valor | Diseñar atención diferenciada |
| Recencia | Tiempo desde última compra | Reactivar |
| Frecuencia | Repetición | Fidelizar |
| Monto | Valor acumulado | Priorizar cuentas |
| Enlaces pendientes | Cobros por cerrar | Recordar o escalar |
| Pagos fallidos | Fricción de cobro | Reintentar y contactar |
| Tareas IA pendientes | Carga operativa | Revisar aprobaciones |
| Confianza media | Calidad de IA | Ajustar fuentes/políticas |
| Respuestas útiles | Valor de sugerencias | Mejorar prompts y manuales |
| Respuestas inseguras | Riesgo | Aumentar escalamiento humano |
| Tokens por solicitud | Eficiencia | Reducir contexto o cambiar modelo |
| Costo por conversación | Rentabilidad | Controlar automatización |

## 9. Roles y permisos recomendados

| Rol | Conversaciones | CRM/RFM | IA | Pagos | Configuración |
|---|---|---|---|---|---|
| Agente | Ver/asignar/responder propias | Ver clientes y oportunidades propias | Usar sugerencias y ejecutar bajo política | Generar enlace si autorizado | No |
| Supervisor | Equipo completo | Recalcular, campañas, estancadas | Aprobar respuestas y tareas | Revisar pagos | Parcial |
| Administrador comercial | Todo | Configurar catálogo, reglas y KPIs | Configurar perfiles y automatizaciones | Configurar flujo | Sí comercial |
| Administrador IA | Según grupo | Consultar contexto | Modelos, conocimiento, políticas y auditoría | No necesariamente | Sí IA |
| Administrador técnico | Todo | Todo | Todo | Todo | Sí técnico |

Ante un error 403, revisar el usuario en **Ajustes → Usuarios y empresas → Usuarios → Derechos de acceso** y asignar el grupo del módulo. Los grupos importantes incluyen usuario/administrador del agente IA, autonomía, operaciones y notificaciones. No se recomienda resolver un 403 quitando reglas de seguridad.

## 10. Pruebas realizadas y resultados

### Suite de regresión

Se ejecutó actualización y carga de los 24 módulos objetivo con `--test-enable --stop-after-init`.

**Resultado final:** `0 failed, 0 error(s) of 142 tests when loading`.

| Módulo con pruebas | Casos |
|---|---:|
| `chatroom_ai` | 6 |
| `chatroom_ai_agent` | 20 |
| `chatroom_ai_autonomy` | 14 |
| `chatroom_ai_knowledge` | 3 |
| `chatroom_ai_operations` | 7 |
| `chatroom_ai_sales` | 10 |
| `chatroom_ai_sales_fulfillment` | 8 |
| `chatroom_ai_sales_payment` | 4 |
| `chatroom_ai_usage` | 16 |
| `chatroom_control_center` | 4 |
| `chatroom_notifications` | 6 |
| `chatroom_sales_intelligence` | 19 |
| `chatroom_whatsapp` | 30 |
| `crm_customer_history` | 8 |
| `crm_customer_intelligence` | 14 |
| `crm_engagement_automation` | 6 |
| `crm_stagnation_management` | 5 |
| **Total** | **142** |

Los módulos `chatroom_calendar`, `chatroom_payment`, `chatroom_payment_payphone`, `chatroom_ui`, `crm_stagnation_intelligence`, `kpi_engine` y `payment_payphone` quedaron incluidos en la actualización/carga de modelos y vistas, pero no aparecen con pruebas unitarias propias en este resultado. Es una diferencia de cobertura, no un fallo de instalación.

### Smoke tests funcionales

| Prueba | Resultado |
|---|---|
| Demo de conversación larga | 30 mensajes, 15 entrantes y 15 salientes |
| Conversación de demostración | Canal `demo-qa-flujo-largo-001`, ID 4778 |
| PDF de conversación | Generado correctamente, 27.832 bytes |
| Límite de transcript | Lectura limitada a 10 mensajes sobre 30 |
| Base de conocimiento | 23 manuales indexados; 3 fuentes relevantes en consulta |
| Contexto local | 415 tokens estimados y 1.658 caracteres en consulta de prueba |
| Política IA aprobación | Pago requiere aprobación; baja confianza requiere aprobación |
| Política IA autónoma limitada | Monto mayor al máximo requiere aprobación; monto permitido puede autorizarse |
| Webhook con token válido | Challenge devuelto en prueba temporal |
| Webhook sin token o inválido | Rechazo controlado, sin considerar esto una falla del servidor |
| Activos principales | SCSS e iconos IA/operaciones responden HTTP 200 |
| Sintaxis Python | `compileall` finalizado con código 0 |
| Demos existentes | Conservadas; no se borraron chats ni pruebas |

### Flujos que deben probarse con credenciales reales

- Recepción real de Meta WhatsApp.
- Respuesta real dentro de la ventana de 24 horas.
- Plantilla real aprobada por Meta fuera de ventana.
- Cobro sandbox y callback real de PayPhone.
- Llamada real al proveedor OpenAI y medición de factura.
- Entrega real, inventario real y facturación real.

## 11. Demos QA preservadas

La base conserva ejemplos para revisar el producto visualmente y repetir regresiones:

- Contactos demo numerados, sin depender de nombres personales.
- Conversación larga con preguntas sobre implementación, tarifa de USD 20/hora, alcance, PDF, catálogo y seguimiento.
- Oportunidades vinculadas en estado saludable, advertencia y crítica.
- Actividad de seguimiento.
- Cotización de prueba.
- Enlace de pago simulado.
- Manuales de empresa y manuales de demostración.

No borrar estos registros durante una demo. Si se necesita repetir una prueba, usar el generador idempotente de Demos QA o crear una nueva serie con prefijo de fecha.

## 12. Checklist de aceptación antes de producción

### Seguridad

- [ ] HTTPS y webhook público.
- [ ] Tokens fuera del código y con permisos mínimos.
- [ ] Usuarios separados por agente, supervisor, IA y administrador.
- [ ] Política de aprobación para pagos, descuentos, pedidos y mensajes sensibles.
- [ ] Auditoría revisada por supervisor.

### Datos

- [ ] Clientes deduplicados por teléfono/correo.
- [ ] Históricos validados antes de recalcular RFM.
- [ ] Categorías RFM/ABC aprobadas por negocio.
- [ ] Reglas de estancamiento ajustadas a cada ciclo de venta.
- [ ] Productos y precios reales publicados en Odoo.

### IA

- [ ] Proveedor y modelo seleccionados.
- [ ] Límite diario y presupuesto revisados.
- [ ] Manuales indexados y con fecha de revisión.
- [ ] Pruebas de conocimiento aprobadas.
- [ ] Simulador sin envío revisado.
- [ ] Modo asistido validado antes de autonomía.
- [ ] Fuentes obligatorias para precios, stock y políticas.

### Operación

- [ ] SLA y horarios definidos.
- [ ] Cola de fallidos revisada.
- [ ] Plantillas Meta aprobadas.
- [ ] Payment Link probado en sandbox.
- [ ] PDF y reportes descargados.
- [ ] KPIs con metas y responsables.
- [ ] Plan de contingencia cuando IA, Meta o PayPhone no respondan.

## 13. Mantenimiento recomendado

### Diario

- Revisar conversaciones sin asignar, tareas IA, pagos fallidos y oportunidades críticas.
- Revisar el panel operativo y el siguiente paso recomendado.

### Semanal

- Revisar calidad de sugerencias IA, respuestas inseguras y costos.
- Revisar oportunidades estancadas y capital atrapado.
- Revisar fallos de plantillas, webhook y reintentos.

### Mensual

- Recalcular RFM según la ventana acordada.
- Revisar campañas y categorías ABC.
- Revisar manuales vencidos y reindexar solo lo que cambió.
- Exportar snapshots de KPIs y revisar metas.
- Ejecutar la suite de regresión antes de actualizar módulos.

## 14. Deuda técnica y mejoras pendientes identificadas

Estas observaciones no bloquean la operación local, pero son importantes para una versión comercial:

1. Agregar pruebas unitarias propias para calendario, UI, Payment Links, PayPhone, `kpi_engine` y salud integral del pipeline.
2. Añadir prueba de navegador para validar navegación de tree/kanban/form en popups nativos.
3. Consolidar el diseño visual de los centros de control para ocupar todo el ancho útil y evitar espacio lateral.
4. Revisar iconos de todos los módulos y mantener un único sistema visual.
5. Agregar un asistente de configuración inicial con pasos y estado de completitud.
6. Agregar una pantalla de presupuesto IA con alertas de consumo y costo estimado.
7. Añadir pruebas de carga para reportes PDF y conversaciones grandes.
8. Incorporar pruebas reales en sandbox de Meta, PayPhone y OpenAI.
9. Crear pruebas de permisos por rol para prevenir regresiones 403.
10. Preparar un paquete de demostración reproducible que cree datos sin eliminar los existentes.

## 15. Evidencias técnicas

- Suite completa: `C:\Users\Bryan\Desktop\odoo19e\server\addons\qa_all_chatroom_modules.log`
- Suite final posterior al arreglo de restauración: `C:\Users\Bryan\Desktop\odoo19e\server\addons\qa_all_chatroom_modules_after_restore_fix.log`
- Prueba dirigida del arreglo: `C:\Users\Bryan\Desktop\odoo19e\server\addons\qa_restore_mobile_targeted.log`
- Suite ampliada anterior: `C:\Users\Bryan\Desktop\odoo19e\server\addons\qa_full_suite_extended.log`
- Pruebas operativas: `C:\Users\Bryan\Desktop\odoo19e\server\addons\qa_operations_priority.log`
- Demos y QA de agente: `chatroom_ai_agent/QA_DEMOS.md`

Las advertencias observadas en el arranque pertenecen principalmente a módulos externos o compatibilidad de Odoo: ausencia de `pdfminer.six` para indexación automática de PDF, uso legado de `_sql_constraints` y avisos de traducción relacionados. No produjeron fallos en la suite ni impidieron generar el PDF de conversaciones.

## 15.1. Incidente de restauración: campo `mobile`

En una restauración apareció el error:

`Wrong @depends on '_compute_data_quality'. Dependency field 'mobile' not found in model res.partner.`

La causa era que `crm_customer_intelligence` declaraba `mobile` como dependencia de un campo calculado, aunque Odoo 19 no lo garantiza en `res.partner`. La corrección aplicada fue:

- cambiar la dependencia a `phone` y `email`;
- calcular coincidencias de teléfono usando `phone`;
- eliminar dominios ORM que consultaban `res.partner.mobile`;
- corregir la variable de teléfono de plantillas WhatsApp;
- corregir la identificación telefónica de históricos;
- aumentar versiones de los módulos afectados para facilitar la actualización;
- agregar una prueba de regresión compatible tanto con una base sin `mobile` como con una integración que lo agregue opcionalmente.

La regresión posterior terminó con **142 pruebas, 0 fallos y 0 errores**. Para aplicar la solución en otro servidor hay que copiar estos archivos actualizados y actualizar `crm_customer_intelligence`, `chatroom_whatsapp` y `crm_customer_history` antes de iniciar el servicio con la base restaurada.

## 16. Resultado final

La plataforma ya tiene una base sólida para:

- atender WhatsApp desde Odoo;
- clasificar y priorizar clientes;
- medir RFM/ABC y Pareto;
- cargar históricos sin alterar ventas;
- detectar oportunidades estancadas;
- automatizar recordatorios y campañas;
- consultar conocimiento empresarial;
- sugerir respuestas y operar con aprobación;
- preparar ventas, pagos y postventa;
- medir consumo, calidad, SLA y rendimiento.

La autonomía completa debe habilitarse progresivamente. La ruta segura es: **asistido → aprobación → autónomo limitado → autonomía comercial**, manteniendo límites de dinero, fuentes obligatorias, auditoría y escalamiento humano.

## 17. Batería específica de IA y conocimiento — 27 de agosto de 2026

Se ejecutaron pruebas adicionales enfocadas en los problemas reportados:

- PDF con texto seleccionable: indexado correctamente usando el fallback `PyPDF2` disponible en el entorno; se validó contenido, fragmentos y ausencia de error.
- PDF sin texto seleccionable: queda en `Error` con instrucciones para aplicar OCR o cargar una versión con texto.
- Reindexación idempotente y control de estado: validada.
- Resumen de conversación: se guarda como información interna y no crea ni modifica una respuesta enviable.
- Clasificación de intención: validada con respuesta estructurada.
- Análisis de intención, sentimiento y urgencia: validado con JSON correcto y con JSON inválido; ante datos inválidos usa valores seguros.
- Próxima acción: validada como instrucción breve para el agente.
- Evaluación de sugerencia: validada como medición de calidad de IA, no como calificación del cliente.

Resultado dirigido: **35 pruebas, 0 fallos y 0 errores** (27 de Inteligencia Comercial/Conocimiento y 8 de IA). La regresión acotada de todos los módulos Chatroom terminó con **149 pruebas, 0 fallos y 0 errores**.

### Cómo probarlo desde Odoo

1. Ir a **Agente IA → Conocimiento para IA**.
2. Crear un registro, elegir **Documento PDF**, adjuntar un PDF con texto seleccionable y guardar.
3. Pulsar **Indexar manual**. El estado debe cambiar a **Indexado**, mostrando fragmentos y fecha.
4. Abrir **Agente IA → Probar conocimiento**, escribir una pregunta relacionada y pulsar **Consultar base local**.
5. Revisar **Fuentes encontradas**, tokens, caracteres y la vista previa del contexto. Si el PDF no aparece, revisar que esté indexado, activo y que la pregunta contenga términos del documento.
6. En una conversación, abrir **Asistente IA** o **Inteligencia IA** y elegir **Resumen de conversación**. El resultado debe mostrar **Resumen interno — No se envía**.
7. Para un texto que sí se podría enviar, elegir **Respuesta sugerida**. Solo esa opción muestra revisión, aprobación y envío.
8. **Evaluar calidad** significa indicar si la sugerencia fue útil, si el agente la editó o si no es segura; alimenta las métricas de calidad.

### Corrección aplicada al PDF

El módulo solo intentaba importar `pypdf`, aunque este servidor tenía instalado `PyPDF2`. Ahora acepta ambas librerías, valida que el archivo sea PDF, detecta PDFs protegidos y explica cuando el documento es un escaneo sin texto. El registro existente `PRUEBAPDF` fue reindexado y quedó persistido como **Indexado**, con 1 fragmento; además aparece como fuente en la recuperación local.

### Archivos de evidencia de esta ronda

- Pruebas de IA y PDF: `C:\Users\Bryan\Desktop\odoo19e\server\addons\qa_ai_targeted.log`
- Actualización de módulos: `C:\Users\Bryan\Desktop\odoo19e\server\addons\qa_ai_pdf_update.log`
- Regresión acotada final: `C:\Users\Bryan\Desktop\odoo19e\server\addons\qa_all_chatroom_modules_ai_final_scoped.log`
- Regresión posterior con resultados del Agente IA: `C:\Users\Bryan\Desktop\odoo19e\server\addons\qa_all_chatroom_modules_ai_agent_final.log`
- Prueba inicial con suite amplia (interrumpida por tiempo de ejecución, sin fallo de código): `C:\Users\Bryan\Desktop\odoo19e\server\addons\qa_ai_pdf_fix.log`

## 18. Agente IA: flujo de plan y resultados visibles

El flujo correcto es:

1. **Crear plan operativo** desde la conversación: crea una tarea en estado `Esperando aprobación`.
2. **Aprobar plan**: cambia a `Planificada` y registra quién aprobó y cuándo.
3. **Ejecutar**: procesa cada acción según su orden y sus permisos.
4. **Revisar resultado**: la tarea pasa a `Completada`, cada acción muestra su estado y el panel presenta un resultado legible.

En la prueba real de la base, la tarea 16 terminó correctamente con:

- Cliente clasificado: categoría `A`, score `83`.
- Intención identificada: `otro`.
- Respuesta preparada, **no enviada**, pendiente de revisión humana.

Antes de esta mejora solo se mostraba “Se completaron 3 acción(es)” y el detalle quedaba escondido en **Contexto técnico → Resultado técnico**. Ahora se conserva ese detalle técnico y se agrega **Resultado para el agente** tanto en la tarea como en el panel lateral. También se rellenó el resultado legible de la tarea demo existente.

La prueba del Agente IA terminó con **19 casos, 0 fallos y 0 errores**. La regresión acotada general posterior terminó con **149 casos, 0 fallos y 0 errores**.

Importante: `prepare_reply` prepara texto; no lo envía. Para enviar se requiere una acción explícita autorizada, y las acciones de cotización, cobro y envío mantienen aprobación y auditoría.

## 20. Agente interno con autonomía por situación

### Evolución operativa

La tarea del agente ahora muestra la decisión de autonomía, confianza evaluada, estado de verificación, próxima acción y si requiere intervención humana. Las situaciones que necesitan criterio se concentran en **Bandeja de excepciones**, con responsable, severidad, motivo y acción recomendada.

Al terminar una tarea, el sistema verifica referencias importantes en Odoo (oportunidad, cotización y enlace de pago), deja un resultado legible y propone el siguiente flujo: respuesta, seguimiento o cobranza. El botón **Crear siguiente tarea** permite continuar conservando el control y la trazabilidad.

El centro ejecutivo incorpora indicadores de excepciones abiertas, tareas autónomas, intervenciones humanas y tasa de autonomía.

El agente funciona dentro de Odoo y no requiere n8n. La autonomía se controla con **Políticas de autonomía**, que se aplican en este orden: canal directo, canales seleccionados, clientes seleccionados y política global de la empresa.

Cada política permite elegir **Asistente**, **Controlado** o **Autónomo**. En modo autónomo solo se ejecutan las acciones habilitadas y dentro de sus límites. Se pueden autorizar por separado respuestas, oportunidades, actividades, cotizaciones, pedidos, enlaces de pago y notificaciones de entrega. La confianza mínima, el límite diario de mensajes y el monto máximo se validan antes de ejecutar.

### Cómo probarlo

1. Ir a **Agente IA → Configuración → Políticas de autonomía**.
2. Crear una política para un canal o cliente de prueba.
3. Elegir **Autónomo** y habilitar únicamente respuestas, oportunidades y actividades.
4. Crear una tarea desde **Acciones guardadas** o desde el panel del chat.
5. Generar el plan. Si cumple la política quedará **Planificada**; si no, quedará **Esperando aprobación** o **Bloqueada**.
6. Ejecutar la tarea y revisar el resultado en la tarea y en **Evaluaciones de autonomía**.

La política no modifica la definición global de las herramientas: autoriza solamente la tarea concreta. Cada decisión queda registrada con política, cliente, conversación, acción, confianza, monto y motivo.

### Validación realizada

- Carga y actualización de `chatroom_ai_autonomy` en `nominaec19`: correcta.
- 13 pruebas de autonomía ejecutadas: **0 fallos, 0 errores**.
- Prioridad canal → cliente → global: validada.
- Tarea autónoma autorizada: queda planificada y libera solamente sus acciones autorizadas.
- Tarea con política controlada: queda esperando aprobación.
- Compilación Python de los cambios: correcta.

## 21. Conocimiento natural y creador guiado

La base de conocimiento no depende únicamente de PDF. El usuario puede crear
una ficha desde **Agente IA → Memoria y auditoría → Crear conocimiento** y
escribir la información como la explicaría a un compañero. Puede elegir
Texto natural, Preguntas frecuentes, Política o regla, Producto o servicio o
Procedimiento comercial.

Al pulsar **Crear y organizar**, el sistema guarda la fuente original, la
indexa localmente, genera resumen, puntos clave, preguntas y reglas detectadas
y deja el contenido estructurado para la recuperación contextual de la IA.
Este proceso es determinista y local: no envía la fuente a OpenAI ni consume
tokens. Los PDF con texto seleccionable siguen funcionando y también pasan
por la misma organización.

Los datos vivos de productos, empresa, clientes, RFM e inventario continúan
entrando mediante el **Perfil de conocimiento**. Así no se duplican tablas ni
se entrena un modelo cada vez que cambia un precio. Si cambia la fuente, la
versión vuelve a **Pendiente** para evitar mezclar información antigua con la
nueva.

### Ejemplo de carga

```
Somos una empresa implementadora de Odoo y desarrollamos personalizaciones.
La tarifa referencial es USD 20 por hora.
Para cotizar preguntamos alcance, usuarios, procesos y fecha objetivo.
Si el caso implica un descuento, debe revisarlo un responsable.
Pregunta: ¿Qué necesitan para preparar una propuesta?
Respuesta: Alcance, usuarios, procesos, integraciones y fecha objetivo.
```

La regresión integrada de conocimiento, autonomía, agente, ventas, pagos,
operaciones, RFM, estancamiento e inteligencia comercial terminó con **108
pruebas, 0 fallos y 0 errores**. Incluyó creación guiada desde texto,
organización local, PDF, consultas de fuentes, políticas de autonomía,
encadenamiento limitado y registro de excepciones.

### Complementos operativos recientes

- Cada tarea conserva las fuentes de conocimiento y los datos vivos utilizados, con versión y medición de contexto.
- El conocimiento puede retirarse temporalmente de la IA y volver a publicarse después de revisión.
- Los PDF escaneados muestran el estado OCR y ofrecen procesamiento local opcional cuando el entorno tiene las librerías instaladas.
- El simulador IA incluye escenarios de bienvenida, producto, cotización, pagos y quejas, con palabras esperadas y evaluación automática.
- La entrega simulada confirma que el texto no llamó a WhatsApp ni creó mensajes reales.
- Los modelos disponibles tienen una prueba de salud independiente para detectar endpoint, credenciales o disponibilidad.

La validación final de esta tanda terminó con **113 pruebas, 0 fallos y 0 errores**.

## 19. Biblioteca de acciones reutilizables del Agente IA

Se incorporó el modelo **Acciones guardadas** para que un usuario no técnico pueda reutilizar tareas sin escribir prompts desde cero.

### Alcances disponibles

- **Todos los chats activos:** crea tareas hasta el límite configurado.
- **Chats seleccionados:** aplica la acción a una selección concreta de conversaciones.
- **Clientes seleccionados:** busca sus chats activos y aplica la acción a cada uno.
- **Chat actual:** desde el panel lateral de una conversación se puede elegir una acción y aplicarla directamente.

### Ejemplos incluidos

1. Respuesta de bienvenida.
2. Responder con conocimiento de la empresa.
3. Clasificar clientes RFM/ABC.
4. Diagnóstico de conversación.
5. Seguimiento de oportunidad.
6. Reactivar cliente inactivo.
7. Convertir consulta en oportunidad.
8. Preparar cotización comercial.
9. Cobranza con enlace de pago, incluido PayPhone si está configurado.

Cada acción guarda su descripción, instrucciones, categoría, tipo de tarea, alcance, límite, ejemplo de uso y política de aprobación. Las acciones de venta, cotización, cobro y envío conservan aprobación humana y auditoría.

### Procedimiento recomendado

1. Entrar a **Agente IA → Operación diaria → Acciones guardadas**.
2. Abrir un ejemplo y revisar **Qué debe hacer** y **Seguridad y aplicación**.
3. Elegir el alcance: todos, chats o clientes seleccionados.
4. Ajustar la instrucción y el máximo de chats.
5. Pulsar **Aplicar acción**.
6. Revisar las tareas creadas; aprobar y ejecutar según corresponda.
7. Desde un chat también se puede abrir **Agente IA**, seleccionar la acción y pulsar **Aplicar al chat actual**.

La biblioteca no reemplaza las automatizaciones: las acciones guardadas son ejecuciones manuales y reutilizables; las automatizaciones se reservan para disparadores programados o eventos como conversación nueva, cotización pendiente, actividad vencida o factura vencida.

La ejecución sin filtro también intentó pruebas HTTP internas del núcleo de Odoo; esas pruebas requieren levantar el servidor HTTP durante la suite y no forman parte de la regresión de estos módulos. La suite acotada es la evidencia válida de esta entrega.
