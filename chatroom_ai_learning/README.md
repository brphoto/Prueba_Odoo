# Chatroom IA - Aprendizaje y autonomía

La IA atiende sola **solo donde demostró acierto** y deja la conversación a una
persona cuando corresponde. Todo se configura en *Ajustes › Chatroom WhatsApp ›
IA: aprendizaje y autonomía* y se revisa en *Chatroom › Agente IA › Aprendizaje y
autonomía*.

| Pieza | Qué hace |
|---|---|
| **Modo sombra** | Cuando una persona responde, la IA redacta a ciegas (sin ver esa respuesta) y un juez compara. Nunca envía nada. Muestreo y tope diario configurables. |
| **Aprende de las correcciones** | Si la persona editó el borrador o la IA se equivocó en sombra, la respuesta humana queda como *ejemplo aprobado* y se inyecta en el prompt ante mensajes parecidos. |
| **Autonomía por niveles** | Cada tipo de conversación (consulta, venta, soporte, queja, otro; opcionalmente por línea) empieza *supervisado*. Pasa a *automático* con N evaluaciones y ≥ 90 % de acierto sin respuestas inseguras; vuelve a supervisado si el acierto baja del 80 % o ante **una** respuesta no segura. *Queja* empieza en «Siempre una persona». Un administrador puede fijar el nivel a mano. |
| **Reglas de traspaso** | Palabras (pedir una persona, siniestro, reembolso, temas legales) o evaluación de la IA (reclamo, cliente molesto, urgencia, poca confianza). Pausan la IA, avisan al responsable, a la línea o a los administradores, dejan un resumen y, opcionalmente, avisan al cliente. |
| **Reactivación** | Si la persona ya respondió y pasaron N horas sin actividad, la IA vuelve a atender. Nunca tras una respuesta marcada como no segura. |
| **Memoria del cliente** | Al terminar una conversación, con consentimiento (`ec_data_consent`), la IA propone datos estables. Los de confianza alta se guardan; los demás quedan en *Memorias propuestas* para revisión. |
| **Pruebas de regresión** | Batería de casos (se crean desde cualquier evaluación). Se ejecuta a diario; si la aprobación baja del mínimo, **toda la autonomía se congela** hasta que vuelvan a pasar. |

Tareas programadas: evaluar en sombra, recalcular niveles, reactivar IA,
extraer memoria y ejecutar las pruebas.
