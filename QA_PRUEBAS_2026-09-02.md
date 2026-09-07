# QA y cierre técnico - 2026-09-02

## Alcance de esta tanda

- Revisión de formularios de IA, autonomía, conocimiento, operaciones,
  ejecuciones y marketing social.
- Corrección visual acotada: ancho disponible, campos largos, JSON,
  instrucciones, resultados y adaptación móvil.
- Conservación del chatter donde el modelo hereda `mail.thread`.
- Conservación de asistentes transitorios sin chatter, porque no tienen un
  registro persistente al cual asociarlo.
- Mantenimiento de demos y datos de prueba existentes.

## Cambios verificados

| Área | Resultado |
|---|---|
| Formularios IA y agente | Clases visuales consistentes y campos de texto legibles |
| Historial de automatizaciones | Ficha preparada para lectura de resumen, incidencias y tareas |
| Conocimiento | Mapa de memoria, contenido y análisis aprovechan el ancho disponible |
| Autonomía | Solicitudes y simulador mantienen flujo de revisión sin envío |
| Operaciones | Comprobaciones y playbooks mantienen historial y chatter persistente |
| Marketing social | Campañas, publicaciones, métricas, interacciones y alertas comparten estética |
| Móvil | Los grids de dos columnas pasan a una columna y los botones se ajustan |
| Modularidad | Perfiles de instalación documentados sin afirmar dependencias inexistentes |

## Pruebas funcionales disponibles en la base

Los demos existentes se conservan para revisión manual. Los flujos que deben
probarse desde la interfaz son:

1. Contacto demo -> conversación -> oportunidad -> formulario nativo.
2. Laboratorio local -> respuesta sin consumo ni envío real.
3. Laboratorio con proveedor -> modelo seleccionado -> tokens y costo local.
4. Conocimiento -> indexar -> organizar -> publicar -> consulta con fuentes.
5. Solicitud IA -> plan -> aprobación -> ejecución -> auditoría y resultado.
6. Petición de cotización -> `sale.order` nativa -> líneas, impuestos y PDF
   nativo de Ventas.
7. Petición de reunión -> `calendar.event` nativo -> actividad y enlace
   Discuss/video si están disponibles.
8. Confirmación de pago -> conector instalado -> enlace y registro de pago.
9. Automatización -> previsualizar alcance -> ejecutar -> historial de corrida
   y tareas generadas.
10. RFM/ABC -> histórico -> cálculo -> campaña NPS o reactivación por segmento.
11. Marketing -> importar CSV UTF-8 -> métricas -> engagement -> consulta del
    agente analítico.
12. Usuario agente/supervisor/administrador -> permisos de lectura, creación,
    aprobación y ejecución.

## Regresión automatizada

- Compilación Python de todos los módulos: `PY_COMPILE_OK`.
- Prueba enfocada de Chatroom WhatsApp: `CHATROOM_TEST_EXIT=0`.
- Regresión base anterior: 248 pruebas, 0 fallos y 0 errores.
- Pruebas dirigidas de agente, conocimiento, uso, calendario y ventas:
  ejecución correcta con `TARGETED_EXIT=0`.

La regresión global más reciente fue detenida de forma segura por duración
excesiva; no se presenta como una ejecución completa posterior a esta tanda.

## Validación externa pendiente

No se puede certificar desde una base local sin credenciales y servicios
externos:

- respuesta real de Meta/WhatsApp;
- consulta oficial de costos y facturación de OpenAI;
- PayPhone en ambiente de prueba;
- disponibilidad de Google Calendar/Meet;
- APIs reales de Instagram, Facebook y TikTok.

Estas integraciones conservan manejo de error, auditoría y modo seguro local.
La activación productiva debe hacerse después de una prueba E2E con cada
credencial del cliente.

## Cierre técnico adicional (2026-09-03)

Se completó una tanda enfocada en operación repetible y control financiero:

- Los modelos de proveedor permiten registrar tarifas manuales de entrada y salida por millón de tokens.
- Cada solicitud local calcula un costo estimado en USD solo cuando existe una tarifa configurada; nunca se presenta como costo oficial.
- El resumen local muestra solicitudes, tokens, costo estimado y base del cálculo. Incluye las solicitudes creadas en el mismo segundo de la actualización.
- Las acciones repetidas del laboratorio reutilizan la actividad y la reunión nativas ya creadas, evitando duplicados.
- Las ejecuciones de automatizaciones IA heredan chatter y actividades nativas para dejar trazabilidad.
- Se documentaron `pypdf` y `pdfminer.six` en `requirements.txt`; ambas dependencias están instaladas en el Python que ejecuta Odoo.

Validación final en `nominaec19`:

- Actualización de `chatroom_ai_usage` y `chatroom_ai_agent`: OK.
- Suite Odoo: 134 pruebas, 0 fallos y 0 errores.
- Compilación Python: OK.
- Parseo XML: OK.
- Puerto HTTP 8019 al finalizar: libre.

## Cierre de esta tanda (2026-09-03)

Se añadió una protección de producción para el orquestador:

- `chatroom.ai.task.orchestration_key` ahora tiene restricción única. Dos workers que reciban el mismo webhook no pueden crear dos tareas.
- Si la carrera ocurre entre la búsqueda y el alta, el orquestador recupera la tarea ya creada dentro de un savepoint y continúa sin duplicar el flujo.
- Las reuniones creadas desde una tarea llevan un marcador técnico en la descripción del evento nativo. Un reintento reutiliza el mismo `calendar.event` y la misma actividad `mail.activity`.
- Se rechazan ventanas de calendario inválidas donde la hora final no sea posterior a la inicial.

Validaciones ejecutadas después de estos cambios:

- Compilación Python de todo `Prueba_Odoo`: OK.
- Parseo XML de todo `Prueba_Odoo`: OK.
- Actualización Odoo en `nominaec19` de `chatroom_ai_agent`, `chatroom_calendar` y `chatroom_ai_usage`: OK.
- Pruebas dirigidas de agente y calendario: OK.
- Batería amplia de Chatroom, IA, conocimiento, ventas, operaciones, autonomía, WhatsApp, RFM/histórico/experiencia y marketing: OK.
- `git diff --check`: sin errores de espacios.
- Servicio HTTP 8019: detenido al finalizar.

El único aviso esperado de la batería es el intento protegido de enviar a WhatsApp externo; el entorno de pruebas bloquea solicitudes de red y por eso no se considera fallo funcional local.
