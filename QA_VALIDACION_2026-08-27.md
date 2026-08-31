# Validación funcional de Chatroom y módulos comerciales

Fecha: 27 de agosto de 2026  
Base: `nominaec19`  
Odoo: 19 Enterprise  
Alcance: módulos Chatroom, IA, RFM, experiencia del cliente, estancamiento, pagos y ventas autónomas.

## Resultado ejecutivo

La batería focalizada de los módulos propios terminó con **175 pruebas, 0 fallas y 0 errores**.

También se verificó:

- `327` archivos XML analizados; `327` válidos.
- `122` archivos con formularios; los formularios de modelos operativos principales tienen chatter o herencia de chatter.
- Los formularios sin chatter corresponden principalmente a asistentes transitorios, paneles de solo lectura, configuraciones y reportes; no se añadió chatter artificial a esos casos.
- Odoo responde en `http://localhost:8019/web/login` con HTTP `200`.
- Los campos que habían producido errores de Owl existen actualmente: `usage_roles`, `operational_status` y `chatroom_ai_safety_profile`.
- El código funcional de los módulos Chatroom/CRM está en UTF-8 y se corrigieron cadenas mojibake detectadas en ventas autónomas, notificaciones, automatizaciones y sus vistas.

## Datos demo que quedan visibles

No se borró ningún dato. La base conserva ejemplos para revisar:

| Área | Datos visibles |
|---|---:|
| Contactos DEMO19 | 20 |
| Conversaciones | 54 |
| Mensajes | 139 |
| Tareas del agente IA | 48 |
| Sugerencias IA | 6 |
| Automatizaciones predefinidas | 6 |
| Playbooks de agente | 9 |
| Manuales/base de conocimiento | 26 |
| Eventos de ventas autónomas | 8 |
| Pedidos de venta | 23 |
| Segmentos RFM | 38 |
| Reglas RFM | 13 |

## Casos de prueba ejecutados

### 1. Base de conocimiento natural

Se probó el flujo con el siguiente contenido:

```text
Somos implementadores de Odoo.
Tarifa: USD 20 por hora.
Para cotizar necesitamos alcance, usuarios y fecha objetivo.
```

Resultado: el manual queda `Indexado` y `Organizado`; la prueba local recupera contexto y estima `317` tokens de entrada sin llamar a OpenAI. La organización genera contenido utilizable y preguntas frecuentes.

Para revisarlo en Odoo:

1. Abrir `Agente IA > Conocimiento`.
2. Crear conocimiento o usar el compositor.
3. Escribir la información en lenguaje natural.
4. Pulsar `Crear e indexar`.
5. Abrir `Probar conocimiento` y preguntar: `¿Cuál es la tarifa de implementación?`.
6. Revisar fuentes, contexto recuperado y tokens estimados.

### 2. Agente IA controlado

Se ejecutó un flujo completo en modo seguro:

1. Crear tarea sobre una conversación.
2. Generar plan.
3. Aprobar el plan.
4. Ejecutar tres acciones.
5. Revisar resultado y auditoría.

Resultado: estado `Completada`, `3` acciones finalizadas y resultado visible. Las acciones sensibles mantienen aprobación humana y no se envían mensajes automáticamente.

### 3. Automatizaciones y playbooks

Se verificó que las seis automatizaciones de ejemplo y los nueve playbooks estén cargados, con descripción e instrucción. Las automatizaciones de ejemplo están inactivas por seguridad.

Ejemplos para probar:

- Diagnóstico de conversación.
- Clasificación de cliente.
- Seguimiento de oportunidad.
- Preparación de respuesta.
- Conversión comercial protegida.
- Revisión de conversaciones.

El flujo recomendado es `Previsualizar alcance > Generar tarea > Aprobar > Ejecutar > Revisar auditoría`.

### 4. NPS, LTV y experiencia del cliente

Se dejaron seis respuestas demo visibles con puntuaciones `10, 9, 8, 6, 5 y 7`.

Clasificación esperada:

- Promotores: `10, 9`.
- Pasivos: `8, 7`.
- Detractores: `6, 5`.
- NPS demo global: `0,00`.

El snapshot del día queda actualizado con `6` respuestas, `2` promotores, `2` pasivos y `2` detractores. También se verificó el cálculo de LTV/RFM promedio.

Para revisarlo:

1. Abrir `Inteligencia Comercial > Experiencia del cliente > Respuestas NPS`.
2. Probar los filtros Promotores, Pasivos y Detractores.
3. Abrir `Panel NPS y LTV`.
4. Abrir un contacto DEMO19 y revisar su resumen comercial.

### 5. RFM y estancamiento

Las pruebas validan límites de clasificación, recalculo, segmentos, reglas, acciones de reactivación, alertas y seguimiento. Los datos actuales tienen segmentos y reglas configurables; el cálculo no depende de una categoría ABC fija y admite más catálogos parametrizados.

Para revisar un caso:

1. Abrir `Inteligencia Comercial > RFM`.
2. Abrir una categoría o segmento.
3. Revisar contactos, oportunidades y acciones.
4. Abrir una oportunidad con análisis de estancamiento.
5. Comprobar días en etapa, límite, riesgo y recomendación.

### 6. Ventas autónomas

Se validaron catálogo, carrito, bloqueo por inventario, bloqueo por cambio de precio, confirmación explícita, creación de cotización, escalamiento a humano y auditoría.

El comportamiento seguro esperado es:

1. El cliente consulta un producto.
2. La IA busca el producto en Odoo.
3. Se arma el carrito.
4. La IA solicita confirmación explícita.
5. Solo si cumple políticas se confirma; si no, se escala a un asesor.
6. El link de pago usa el conector instalado, incluido PayPhone cuando está configurado.

### 7. WhatsApp, pagos y UI

Se cargaron las vistas y pruebas de WhatsApp, plantillas, mensajes, enlaces de pago, PayPhone, calendario, notificaciones y paneles. Los tests no hacen envíos externos reales: las llamadas a Meta/OpenAI/PayPhone están simuladas o protegidas para no generar cobros ni mensajes a clientes.

Para una validación real posterior se requiere activar credenciales de prueba y revisar explícitamente:

- envío Meta/WhatsApp;
- creación y retorno de link PayPhone;
- respuesta real del proveedor IA;
- costos reportados por OpenAI Platform.

### 8. Laboratorio de conversación IA

Se incorporó un chat de prueba multi-turno en `chatroom_ai_usage`. Permite escribir como cliente y recibir respuestas dentro de la misma sesión, sin crear mensajes reales de WhatsApp.

- **Modo local:** respuestas deterministas para validar el flujo, el conocimiento comercial y la interfaz sin llamadas externas, tokens ni costo.
- **Modo proveedor IA:** utiliza el modelo seleccionado del catálogo configurado, registra tokens y consumo, pero mantiene la conversación aislada y no envía WhatsApp.
- **Trazabilidad:** conserva cada turno, resultado, modelo, tokens, evaluación y chatter.

Se dejó una demo persistente visible: `Laboratorio demo - conversación IA`, con seis turnos de ejemplo y contexto de un contacto DEMO19.

Para probarlo:

1. Abrir `Agente IA > Consumo de IA > Calidad y pruebas > Laboratorio de conversación IA`.
2. Crear una prueba o abrir la demo persistente.
3. Elegir una conversación de referencia y comenzar en **Modo local**.
4. Enviar `Hola`, `¿Cuál es la tarifa por hora?` y `¿Qué productos tienen?`.
5. Para probar OpenAI, cambiar a **Proveedor IA**, seleccionar el modelo y enviar un turno. Esta opción sí consume tokens.

La prueba automatizada del laboratorio terminó con `23/23` casos correctos; la regresión focalizada de la solución terminó con `177/177` casos correctos.

### 9. Centro de mando de marketing social

Se incorporó el módulo independiente `marketing_command_center`, sin dependencia de Chatroom. Centraliza cuentas de Instagram, Facebook, TikTok, YouTube y LinkedIn; campañas, publicaciones, métricas por fecha, comentarios/interacciones y un agente analítico consultable en lenguaje natural.

El dashboard calcula publicaciones, alcance, impresiones, reproducciones, interacciones, engagement, comentarios pendientes, oportunidades atribuidas, ventas atribuidas y contenido destacado. Incluye gráficos/listas nativas de Odoo, chatter en los formularios, permisos de usuario/administrador y datos demo persistentes.

La demo persistente contiene 4 cuentas, 12 publicaciones, 12 snapshots de métricas y 12 interacciones. También se dejó la sesión `Demo - analista de redes` con cuatro consultas y sus respuestas para revisar el flujo.

Consultas probadas: mejor publicación, tendencia, comentarios pendientes, alcance y reproducciones. La respuesta se calcula localmente sobre los snapshots guardados, por lo que esta función no consume tokens. Los conectores de cada red quedan desacoplados para poder agregarlos después con sus permisos y APIs correspondientes.

La prueba específica del módulo terminó con `8/8` casos correctos, sin fallos ni errores. La regresión previa de la solución terminó con `177/177` casos correctos y el laboratorio IA con `23/23`.

La versión `19.0.1.0.2` añade filtros por red, comparación con el período anterior, variaciones de alcance/interacciones/engagement, alertas configurables con resolución, importación guiada de CSV UTF-8 por compañía, plantillas descargables y fuentes de publicaciones consultadas por el agente. El importador actualiza registros por identificador externo y valida dependencias, fechas y valores numéricos antes de guardar.

Para usarlo: abrir `Marketing > Centro de mando`, pulsar `Cargar datos demo` solo si se desea regenerar el escenario, luego `Actualizar indicadores`; para conversar, abrir `Marketing > Agente de marketing` y escribir una pregunta natural.

## Advertencias conocidas

Odoo informa módulos heredados no instalables que no forman parte de la solución actual:

`novocentro_rfm_analysis`, `whatsapp_connector`, `whatsapp_connector_crm`, `whatsapp_connector_sale`, `whatsapp_connector_send_account`, `whatsapp_connector_send_crm`, `whatsapp_connector_send_purchase`, `whatsapp_connector_send_sale`, `whatsapp_connector_send_stock` y `whatsapp_connector_template_base`.

La prueba global de todos los módulos instalados de la base se detuvo por superar el tiempo debido a módulos externos de nómina. La prueba focalizada de nuestros 22 módulos y sus dependencias terminó correctamente con 175/175 casos.

La regresión final posterior al laboratorio terminó con `177/177` casos correctos; la prueba específica de `chatroom_ai_usage` terminó con `23/23`.

## Siguiente revisión manual recomendada

Usar el menú de Odoo y comprobar especialmente:

1. `Agente IA > Tareas` y abrir una tarea completada.
2. `Agente IA > Conocimiento` y ejecutar la prueba local.
3. `Agente IA > Automatizaciones IA` y previsualizar una automatización inactiva.
4. `Chatroom > Conversaciones` y abrir un contacto DEMO19.
5. `Inteligencia Comercial > RFM` y abrir un segmento.
6. `Inteligencia Comercial > Experiencia del cliente` y revisar las seis respuestas NPS.
7. `Ventas autónomas` y revisar eventos, bloqueos y escalamiento.
8. `Consumo de IA` para revisar tokens locales; el costo oficial requiere sincronización o carga de datos de OpenAI Platform, porque OpenAI no expone el saldo de fondos mediante una llamada estándar de uso de modelos.
