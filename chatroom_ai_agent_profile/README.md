# Chatroom IA - Agente de atención

Agente de WhatsApp para **cualquier negocio**, configurado sin código y sin n8n:
todo corre dentro de Odoo.

## Cómo se pone en marcha

1. **Agente IA › Agente de atención › Perfil y guiones**: completa *Qué hace la
   empresa*, el objetivo, el tono, qué debe hacer y qué no debe hacer nunca.
2. **Base de conocimiento**: carga y publica textos o PDF (horarios, productos,
   políticas, preguntas frecuentes). Los datos de la empresa, los productos y la
   ficha del cliente se leen en vivo desde Odoo.
3. **Guiones**: define qué datos reunir según lo que necesita el cliente
   (cotización, soporte, reserva…) y qué hacer al completarlos: seguir, crear
   una oportunidad o pasar a una persona.
4. **Probar agente**: conversa como si fueras el cliente. Usa el mismo proceso
   que producción y muestra qué haría (enviar sola, dejar para aprobar o pasar a
   una persona), por qué y qué información usó. Corrige una respuesta (queda
   como ejemplo) o guárdala como caso de prueba.
5. El recuadro de preparación del perfil indica qué falta. Cuando está listo:
   **Activar respuesta automática**.

## Qué responde sola desde el primer día

Mientras un tipo de conversación está supervisado, la IA envía sola solo lo que:

* está respaldado por la información publicada, o solo pide datos del guion, o
  es un saludo o un cierre;
* tiene la confianza mínima del perfil (85 % por defecto);
* no menciona cifras (precios, plazos, cantidades) que no estén en la
  información entregada.

Lo demás queda como borrador para aprobar. Nunca aplica a tipos bloqueados
(por ejemplo, quejas), a niveles fijados a mano ni con la autonomía congelada
por las pruebas. Con el tiempo cada tipo gana autonomía completa con datos
(módulo *Aprendizaje y autonomía*).

## La base de conocimiento crece sola

Cuando el cliente pregunta algo que no está en la información, la IA no lo
inventa: avisa que lo consulta y registra un **vacío de conocimiento**. La
respuesta que da el equipo en esa conversación queda propuesta; al publicarla
pasa a la base de conocimiento y como ejemplo aprobado.

## Operación diaria

* **Cola de respuestas** (Chatroom WhatsApp › Ajustes): la IA responde unos
  segundos después del último mensaje del cliente (6 s por defecto, máximo 20 s
  desde el primero), una sola vez a todo lo que escribió, con «escribiendo…» en
  WhatsApp. La cola vive en la base: sobrevive a reinicios y reintenta 3 veces.
* **Audios e imágenes**: los audios se transcriben y las imágenes se describen
  con el mismo proveedor; la IA y el asesor leen el texto bajo el adjunto.
* **Búsqueda en el conocimiento**: sin tildes ni plurales, con sinónimos del
  negocio (pestaña *Búsqueda en el conocimiento*) y por significado
  (embeddings), que se preparan al indexar.
* **Aprender de chats anteriores**: guarda lo que el equipo ya respondió como
  ejemplos y propone preguntas frecuentes (sin datos personales) para publicar.
* **Tablero**: respondidas solas, para aprobar, traspasos y sus motivos,
  seguimientos, tiempo de respuesta y costo o tokens.
* **Guiones que terminan en acción**: cotización en borrador o tarea para el
  equipo, además de pasar la conversación.
* **Seguimiento**: un recordatorio si el cliente deja un guion a medias, dentro
  de la ventana de 24 h.
* **Modelo del verificador**: se puede asignar un modelo más rápido a la tarea
  «clasificación» en Ajustes de IA.
