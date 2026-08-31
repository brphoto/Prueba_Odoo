# Chatroom - Puente IA nativa de Odoo

Módulo opcional para Odoo Enterprise. Conecta el desarrollo de Chatroom con
`ai.agent` sin hacer que los módulos principales dependan de la aplicación IA
nativa.

## Qué hace

- Crea o selecciona un agente nativo de Odoo.
- Consulta el contexto local de Chatroom (empresa, productos y conocimiento publicado).
- Permite probar respuestas nativas sin enviar mensajes a WhatsApp.
- Registra archivos de Odoo como fuentes del agente nativo.
- Deja trazabilidad en el chatter y conserva el motor actual como respaldo.

## Qué no hace todavía

No reemplaza automáticamente el proveedor OpenAI del Chatroom ni envía mensajes
externos. El cambio del motor conversacional debe pasar por un adaptador
explícito, con permisos, auditoría y fallback.

## Instalación

Instalar después de `ai`, `chatroom_ai_usage`, `chatroom_ai_knowledge` y
`chatroom_ai_agent`. No instalar en Community; el módulo `ai` es una dependencia
Enterprise.
