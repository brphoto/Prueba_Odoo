# Validación técnica de Chatroom IA y módulos comerciales

Fecha: 2 de septiembre de 2026  
Base: `nominaec19`  
Odoo: 19 Enterprise

## Alcance validado

- Cotizaciones nativas de Odoo con varias líneas y cantidades independientes.
- Tarifa configurada para horas: USD 20 en la demostración.
- Precio nativo de Odoo para productos normales.
- Separación de solicitudes nuevas para evitar mezclar productos de conversaciones anteriores.
- PDF estándar de Ventas (`sale.action_report_saleorder`) y adjunto al documento nativo.
- Actividades de Odoo, reuniones de Calendario y trazabilidad en chatter.
- Selector de modelos, sincronización, resumen local y campos opcionales que habían provocado errores de Owl.
- Centro de salud y preparación con comprobaciones persistentes, recomendaciones y estado por empresa.
- Lote DEMO QA persistente para revisar seis escenarios comerciales y tres playbooks seguros.
- Historial persistente de ejecuciones de playbooks de comunicación, con Chatter, métricas de procesados/avisos/envíos/bloqueos/errores y separación por empresa.

## Resultados

- Regresión completa de los módulos comerciales, IA, WhatsApp, RFM, automatizaciones, ventas y experiencia de cliente: **correcta, 0 fallos, 0 errores**.
- Pruebas focalizadas de agente, laboratorio IA y consumo: **correctas, 0 fallos, 0 errores**.
- Prueba focalizada de WhatsApp y creación de contactos: **32 casos, 0 fallos y 0 errores**.
- Validación estática: **457 archivos Python y 339 XML** revisados correctamente.
- Los módulos funcionales revisados no tienen problemas de sintaxis ni XML. Se mantienen 11 archivos XML con BOM UTF-8 dentro del módulo independiente de nómina; no se modificaron porque no pertenecen a esta tanda de Chatroom.
- Proveedor IA: endpoint `https://api.openai.com/v1`, modelo `gpt-4.1`, consulta mínima respondida correctamente.

## Mejoras de usabilidad aplicadas en esta tanda

- Se añadió una capa visual común para los formularios largos de tareas IA, automatizaciones, playbooks, configuración, laboratorio, modelos, fondos y consumo. Los campos extensos ahora ocupan el ancho disponible y dejan de comprimirse en columnas estrechas.
- El laboratorio muestra accesos directos a los documentos nativos creados: cotización, actividad y reunión. Así se puede comprobar el resultado sin buscarlo manualmente en otro menú.
- El laboratorio permite abrir el historial completo de cotizaciones de una prueba en una ventana Odoo: cada solicitud conserva su presupuesto, PDF estándar, operación, importes y líneas; las ampliaciones quedan diferenciadas de las cotizaciones nuevas.
- Las automatizaciones del agente ahora guardan un historial por ejecución, con origen manual o automático, fecha, canales revisados, tareas creadas, canales omitidos e incidencias. Desde la automatización se puede abrir la lista de ejecuciones y, desde cada ejecución, sus tareas generadas.
- El historial de automatizaciones usa permisos propios y mantiene la trazabilidad sin mezclarla con la configuración: facilita comprobar qué ocurrió después de pulsar «Ejecutar ahora» y detectar reintentos o ejecuciones sin alcance.
- El historial separa ahora tareas ya existentes de canales con incidencia y conserva el detalle de los omitidos. Esto permite distinguir una protección contra duplicados de un error real del procesamiento.
- Las notificaciones de previsualización y ejecución de automatizaciones fueron normalizadas a español con tildes y mensajes claros, manteniendo una prueba que protege ese texto para evitar regresiones.
- Las tareas del agente muestran el documento generado y permiten abrirlo desde el resultado cuando la acción produjo un registro nativo.
- La creación de oportunidades desde WhatsApp reutiliza una oportunidad activa del cliente cuando corresponde, ancla la conversación mediante `pinned_lead_id` y completa teléfono/correo únicamente cuando están vacíos. Las oportunidades nuevas conservan además el contexto de la conversación para que el seguimiento comercial no pierda información.
- Los contactos creados desde Chatroom heredan el idioma de la sesión del usuario conectado; si una integración o el usuario indica otro idioma explícitamente, ese valor se conserva. Se añadieron pruebas para ambos casos.
- El menú diferencia ahora el `Resumen ejecutivo` visual de la `Cola operativa`, evitando presentar una lista técnica como si fuera un centro de mando.
- Se reforzó la compatibilidad visual del asistente inicial, el creador de conocimiento y el laboratorio con la misma capa de formularios estándar.
- Las columnas principales de consumo y costos quedaron rotuladas en español para que la lectura no dependa de las etiquetas técnicas del modelo.
- Se conservaron los flujos nativos de Odoo para `sale.order`, `mail.activity` y `calendar.event`, incluyendo su chatter, reportes y permisos.
- Se añadió **Agente IA > Operaciones > Salud y preparación**: doce comprobaciones locales persistentes con estado, detalle, recomendación y última revisión. El panel operativo muestra el resumen de correctas y pendientes.
- Se dejó en la base un lote **DEMO QA** persistente y claramente marcado: seis conversaciones/escenarios, datos comerciales de demostración y tres automatizaciones desactivadas. Es seguro para revisar la UX y no envía mensajes.
- La actualización real de módulos terminó correctamente; la suite focalizada de Operaciones ejecutó 7 casos contabilizados (9 líneas de ejecución) sin fallos y la regresión completa actualizada ejecutó **248 tests con 0 fallos y 0 errores**.
- En la comprobación persistente posterior quedaron **12 checks**, **11 correctos**, **1 en advertencia**, **0 errores**. La advertencia corresponde a WhatsApp sin credenciales completas en el entorno de prueba; no es un fallo de código.
- Se actualizó de forma controlada el conjunto de **32 módulos Chatroom, CRM, KPI y Marketing** instalados en la base; no se detectaron errores de instalación, ParseError ni ValidationError. La regresión finalizó con **248 tests, 0 fallos y 0 errores**.
- Se corrigió además la consistencia de columnas obligatorias heredadas de `purchase_stock` y CRM en la base de prueba: `res.partner.group_rfq`, `res.partner.group_on` y `crm.stage.stagnation_max_days` quedaron con sus valores estándar por defecto. No había nulos que eliminar y no se borraron registros.
- Se regeneraron los seis escenarios DEMO QA de forma idempotente y se ejecutaron los tres playbooks demo en modo seguro: **3 ejecuciones completadas, 7 canales procesados, 7 avisos internos, 0 envíos externos y 0 errores**.

## Criterio de operación

La interfaz separa tres niveles para reducir errores de uso: el resumen para decidir, la cola para revisar tareas y las fichas nativas para editar documentos. Las acciones que crean o envían información siguen pasando por permisos y aprobación humana cuando corresponde.

La consulta real fue revertida al finalizar: no envió WhatsApp, no creó ventas y no dejó consumo persistente.

El agente también revalida la autorización de cada herramienta justo antes de ejecutarla: debe estar activa y el usuario debe pertenecer al grupo configurado. Esto evita que una edición manual del plan salte las restricciones de seguridad.

## Pruebas de cotización

Con una solicitud de `2 horas de Servicio A y 3 unidades de Producto B`, el sistema genera un `sale.order` nativo con:

| Línea | Cantidad | Precio unitario |
| --- | ---: | ---: |
| Servicio A | 2 | USD 20 |
| Producto B | 3 | Precio nativo de Odoo |

Una solicitud posterior solo usa sus productos actuales. Para ampliar una cotización existente debe indicarse expresamente, por ejemplo: “agrega también 2 unidades de Producto B a la cotización anterior”.

## Advertencia de restauración

La base contiene algunas referencias a adjuntos cuyo archivo físico no está presente en el filestore. Odoo registra `FileNotFoundError` al intentar leerlos, pero no provocaron fallos en la regresión. La solución correcta es restaurar el filestore que corresponde a `nominaec19` junto con la base, o depurar esos adjuntos huérfanos en una tarea de mantenimiento separada. No se eliminaron datos automáticamente.

## Estado del servicio

El servicio de Odoo en el puerto 8019 quedó detenido después de las pruebas.

## Guía de revisión del lote DEMO QA

1. Abre **Agente IA > Operaciones > Salud y preparación** y pulsa **Comprobar todo**. Revisa qué capacidades están correctas y qué requiere configuración.
2. Abre **Agente IA > Operaciones > Demos QA** para conocer el flujo seguro de generación. No se deben borrar los registros DEMO QA.
3. Revisa las conversaciones con nombre `DEMO QA - ...`: cada una representa un punto del ciclo comercial y puede abrirse desde el módulo de WhatsApp.
4. Revisa **Automatizaciones IA** y filtra por `DEMO QA - ...`; están inactivas y sirven para probar alcance, ejecución manual, aprobación e historial.
5. Para un flujo real, configura primero credenciales, catálogo y permisos. La aprobación humana debe permanecer activa antes de permitir cotizaciones, pagos, reuniones o mensajes.

Estas comprobaciones distinguen preparación local de conexión efectiva: que un conector aparezca como disponible no significa que una credencial externa haya sido validada. Las pruebas con proveedores se ejecutan únicamente de forma explícita.
