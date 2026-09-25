# Chatroom Agente IA Operativo

Orquestación de tareas, herramientas, memoria y automatizaciones IA con aprobación humana.

## Panel del agente en el chat (19.0.1.1)

El **Agente IA** no redacta mensajes (eso lo hace el *Asistente IA*): prepara
**acciones en Odoo** a partir de la conversación, como la oportunidad, la
cotización, una actividad o el link de pago, y las deja **por aprobar**.

- **Compacto por defecto**: el panel se abre solo cuando la conversación tiene
  una tarea por aprobar, y el encabezado lo avisa con la etiqueta *Por aprobar*.
- **Tarea primero**: *Revisar y aprobar* abre la tarea en un diálogo.
- **Un solo selector** de qué preparar: la atención sugerida por la ruta
  detectada, el plan completo o una acción guardada. Se lanza con *Preparar*.
- **Contadores reales**: *por aprobar* y *en curso* cuentan solo las tareas que
  el usuario puede ver, no las de toda la empresa ni las de otras líneas.
- **Preferencia por usuario** (*Mis preferencias → Chatroom*): compacto, siempre
  abierto u oculto. El enlace *Ocultar panel* lo oculta al instante.
- **Autonomía**: una política autónoma autoriza la tarea concreta
  (*Autorizada por política*) sin rebajar la marca de aprobación de las
  herramientas. Ese campo solo lo escribe el servidor, nunca un usuario.
- **Acciones de IA**: el modo *Tarea del agente* permite lanzar el agente desde
  el botón ✨ o con un atajo, por ejemplo `/vender`.
