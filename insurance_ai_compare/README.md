# Comparativo de seguros con IA

Para brokers que cotizan con varias aseguradoras: subes los PDF de las
cotizaciones y obtienes el cuadro comparativo, la recomendación para el cliente,
lo que cada aseguradora debería mejorar y el PDF listo para enviar.

**Principio:** la IA **lee** y **redacta**; Odoo **normaliza, calcula y arma el
PDF**; el asesor **revisa y aprueba**. Ninguna cifra del puntaje la calcula la IA.

## Flujo

1. **Pólizas → Comparativos IA → Comparativos → Nuevo.** Elige el cliente y el
   ramo (plantilla).
2. En **Cotizaciones**, agrega una línea por aseguradora y sube su PDF.
3. **Leer cotizaciones con IA.** La lectura corre en segundo plano (cola con
   cron), así que puedes seguir trabajando. De cada PDF se extraen:
   - prima neta y total, forma de pago y suma asegurada;
   - deducible;
   - coberturas, con su página de origen y una cita;
   - asistencias y exclusiones.
4. **Revisión.** Las coberturas dudosas (poca confianza o sin ubicar en el
   catálogo) aparecen resaltadas en cada cotización. Al corregirlas quedan como
   revisadas. Si un PDF es escaneado y no se puede leer, usa **Cargar datos a mano**.
5. **Puntaje (Odoo).** Precio, deducible, coberturas ponderadas, y asistencias
   más la calificación de servicio de la aseguradora, con los pesos de la
   plantilla. La oferta que no incluye una **cobertura obligatoria** queda
   descartada del ranking.
6. **Analizar con IA.** Genera:
   - ventajas y desventajas de cada oferta;
   - la recomendación para el perfil y las prioridades del cliente;
   - qué pedirle a cada aseguradora para mejorar (negociación);
   - una explicación simple para el cliente.

   La IA no puede recomendar una oferta descartada.
7. **Aprobar.** Queda registrado quién aprobó. Antes de aprobar, el PDF sale con
   la marca **BORRADOR**.
8. **Enviar por WhatsApp o email**, con el PDF para el cliente.
9. **Emitir póliza.** Crea la póliza con la aseguradora elegida, sus primas y
   las coberturas incluidas.

Hay dos PDF:
- **Para el cliente:** cuadro, recomendación, ventajas y desventajas, fuentes por
  página y nota legal.
- **Interno:** además, el detalle del puntaje y la negociación.

## Asesoría desde el chat

Para asesores (grupo *Comparativo de seguros / Asesor*), con ✨ o escribiendo `/`:

| Atajo | Qué hace |
|---|---|
| `/perfil` | Extrae de la conversación los datos del cliente definidos en la plantilla, sin inventar, y deja una nota interna con lo que falta |
| `/faltantes` | Redacta el mensaje que pide solo los datos que faltan |
| `/asesorar` | Recomienda coberturas según el perfil |
| `/explicar` | Explica al cliente el último comparativo |
| `/comparativo` | Crea el comparativo con el perfil ya cargado |

## Configuración

- **Plantillas y coberturas** (Pólizas → Configuración → Configuración del comparativo):
  - catálogo de coberturas por ramo, con **sinónimos** (cada aseguradora las
    llama distinto), importancia y obligatorias;
  - pesos del puntaje;
  - datos del cliente a recopilar;
  - instrucciones de extracción y nota legal.

  Se incluyen las plantillas **Vehículos livianos** y **General**.
- **Aseguradoras:** logo, **calificación de servicio (0-5)**, que es un dato del
  broker, y **pistas para leer sus cotizaciones**, que se agregan a la
  instrucción de la IA solo para sus PDFs.

## Protección de datos (LOPDP)

Nada se analiza con IA sin el consentimiento **«Asesoría de seguros con IA»**
vigente del cliente (módulo `ec_data_consent`). El comparativo lo avisa y ofrece
registrarlo. La exigencia se controla con el parámetro
`insurance_ai_compare.require_consent` (por defecto `True`).

## Seguridad y robustez

- Los PDF se entregan a la IA **como datos**: un texto escondido en una
  cotización no puede darle órdenes.
- Las respuestas de la IA deben ser JSON válido con las claves esperadas; si no
  lo son, se reintenta una vez explicando el error.
- Si falla la lectura de un documento, el error queda en esa cotización y las
  demás siguen.
- El consumo de IA de los análisis queda registrado como tipo **Documentos**
  (con *Chatroom IA - Modelos y Consumo*) y respeta los límites diarios.
- Acceso:
  - solo usuarios internos del grupo **Asesor**, y la configuración para
    **Administrador**;
  - reglas por empresa.

## Requisitos

`pypdf` (obligatorio) y `pdfplumber` (recomendado: conserva las tablas de
coberturas). El OCR para PDFs escaneados es opcional: `pdf2image`,
`pytesseract` y Tesseract.
