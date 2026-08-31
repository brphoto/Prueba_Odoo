# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatroom_ai_safety_profile = fields.Selection([
        ('supervised', 'Supervisado recomendado'),
        ('balanced', 'Equilibrado'),
        ('automatic', 'Automatico con limites'),
    ], string='Perfil de operacion IA', default='supervised',
       config_parameter='chatroom_ai_agent.safety_profile',
       help='Selecciona un punto de partida y luego puedes ajustar cualquier parametro.')

    chatroom_ai_agent_enabled = fields.Boolean(
        string='Activar automatizaciones del agente IA',
        config_parameter='chatroom_ai_agent.enabled',
        help='Permite que las automatizaciones creen y ejecuten tareas según sus reglas.',
    )
    chatroom_ai_production_orchestrator = fields.Boolean(
        string='Activar orquestador de producción',
        config_parameter='chatroom_ai_agent.production_orchestrator',
        help='Conecta cada mensaje entrante con una única ruta operativa. Usa los modelos nativos de Odoo y deja las acciones sensibles para aprobación humana.',
    )
    chatroom_ai_orchestrator_auto_reply = fields.Boolean(
        string='Permitir respuestas automáticas seguras',
        config_parameter='chatroom_ai_agent.orchestrator_auto_reply',
        help='En modo automático responde consultas de bajo riesgo usando la guardia de IA. Cotizaciones, reuniones, cobros y cambios siguen protegidos.',
    )
    chatroom_ai_agent_require_approval = fields.Boolean(
        string='Requerir aprobación para acciones sensibles', default=True,
        config_parameter='chatroom_ai_agent.require_approval',
        help='Las acciones que cambian datos o envían mensajes siempre conservan su aprobación propia.',
    )
    chatroom_ai_agent_event_orchestration = fields.Boolean(
        string='Crear tareas IA al recibir mensajes',
        config_parameter='chatroom_ai_agent.event_orchestration',
        help='Al recibir un mensaje crea y planifica la tarea de la automatización activa. En modo automático ejecuta únicamente acciones autorizadas; los envíos, cobros, cotizaciones y actividades conservan su aprobación.',
    )
    chatroom_ai_agent_commercial_router_enabled = fields.Boolean(
        string='Preparar automáticamente solicitudes comerciales',
        config_parameter='chatroom_ai_agent.commercial_router_enabled',
        help='Al recibir un mensaje crea un plan de cotización, reunión, producto, pago o consulta. En modo supervisado siempre espera aprobación humana.',
    )
    chatroom_ai_agent_ai_planning_enabled = fields.Boolean(
        string='Usar planificador externo de IA',
        config_parameter='chatroom_ai_agent.ai_planning_enabled',
        help='Si está activo, el agente puede consultar el proveedor configurado para proponer planes no deterministas. Desactivado usa los planes locales y ahorra tokens.',
    )
    chatroom_ai_agent_mode = fields.Selection([
        ('supervised', 'Supervisado: requiere aprobacion'),
        ('automatic', 'Automatico: ejecuta tareas autorizadas'),
        ('simulation', 'Simulacion: solo prepara planes'),
    ], string='Modo de operacion del agente', default='supervised',
        config_parameter='chatroom_ai_agent.mode',
        help='El modo supervisado es el recomendado. El automatico no elimina las aprobaciones propias de cobros y envios.')
    chatroom_ai_agent_max_tasks = fields.Integer(
        string='Máximo de tareas por ciclo', default=20,
        config_parameter='chatroom_ai_agent.max_tasks',
    )
    chatroom_ai_agent_max_actions = fields.Integer(
        string='Maximo de acciones por tarea', default=8,
        config_parameter='chatroom_ai_agent.max_actions',
    )
    chatroom_ai_agent_max_payment_amount = fields.Float(
        string='Límite de cobro automático', default=0.0,
        config_parameter='chatroom_ai_agent.max_payment_amount',
        help='0 desactiva el límite. Si un documento supera el valor, el agente lo bloquea para revisión humana.',
    )
    chatroom_ai_agent_quote_product_id = fields.Many2one(
        'product.product', string='Producto para cotizaciones IA',
        config_parameter='chatroom_ai_agent.quote_product_id',
        domain=[('sale_ok', '=', True)],
        help='Producto que el agente añadirá a una cotización cuando el cliente pida un presupuesto. Déjalo vacío para exigir selección humana.',
    )
    chatroom_ai_agent_quote_quantity = fields.Float(
        string='Cantidad predeterminada para cotizaciones IA', default=1.0,
        config_parameter='chatroom_ai_agent.quote_quantity',
        help='Cantidad que se añadirá al producto configurado en cada cotización preparada por el agente.',
    )
    chatroom_ai_agent_quote_hourly_rate = fields.Float(
        string='Tarifa por hora para cotizaciones IA', default=20.0,
        config_parameter='chatroom_ai_agent.quote_hourly_rate',
        help='Precio unitario aplicado cuando el cliente solicita horas de implementación o consultoría. '
             'Las demás ventas usan el precio nativo del producto en Odoo.',
    )

    chatroom_ai_safe_auto_reply = fields.Boolean(
        string='Aplicar guardia de seguridad a respuestas automaticas',
        default=True,
        config_parameter='chatroom_ai_agent.safe_auto_reply',
        help='Valida consentimiento, horario, frecuencia, confianza y necesidad de un humano antes de responder.',
    )
    chatroom_ai_auto_reply_min_confidence = fields.Float(
        string='Confianza minima para responder', default=0.80,
        config_parameter='chatroom_ai_agent.auto_reply_min_confidence',
        help='Valor entre 0 y 1. Si la IA no alcanza este nivel, deja una sugerencia para un agente.',
    )
    chatroom_ai_auto_reply_cooldown_minutes = fields.Integer(
        string='Espera entre respuestas automaticas (minutos)', default=15,
        config_parameter='chatroom_ai_agent.auto_reply_cooldown_minutes',
        help='Evita respuestas repetidas cuando llegan varios mensajes seguidos.',
    )
    chatroom_ai_auto_reply_daily_limit = fields.Integer(
        string='Maximo diario por conversacion', default=30,
        config_parameter='chatroom_ai_agent.auto_reply_daily_limit',
        help='0 bloquea las respuestas automaticas; usa un numero positivo para mantener un limite operativo.',
    )
    chatroom_ai_auto_reply_escalate_negative = fields.Boolean(
        string='Escalar quejas y urgencias a un humano', default=True,
        config_parameter='chatroom_ai_agent.auto_reply_escalate_negative',
        help='La IA prepara una respuesta, pero no la envia cuando detecta queja, sentimiento negativo o urgencia critica.',
    )
    chatroom_ai_auto_reply_allow_outside_hours = fields.Boolean(
        string='Permitir respuestas fuera del horario', default=False,
        config_parameter='chatroom_ai_agent.auto_reply_allow_outside_hours',
        help='Por defecto la IA respeta el horario de atencion configurado en Chatroom WhatsApp.',
    )

    @api.onchange('chatroom_ai_safety_profile')
    def _onchange_chatroom_ai_safety_profile(self):
        profiles = {
            'supervised': {
                'chatroom_ai_agent_mode': 'supervised',
                'chatroom_ai_agent_require_approval': True,
                'chatroom_ai_safe_auto_reply': True,
                'chatroom_ai_auto_reply_min_confidence': 0.80,
                'chatroom_ai_auto_reply_cooldown_minutes': 15,
                'chatroom_ai_auto_reply_daily_limit': 30,
                'chatroom_ai_auto_reply_escalate_negative': True,
                'chatroom_ai_auto_reply_allow_outside_hours': False,
                'chatroom_ai_agent_ai_planning_enabled': False,
            },
            'balanced': {
                'chatroom_ai_agent_mode': 'automatic',
                'chatroom_ai_agent_require_approval': True,
                'chatroom_ai_safe_auto_reply': True,
                'chatroom_ai_auto_reply_min_confidence': 0.75,
                'chatroom_ai_auto_reply_cooldown_minutes': 10,
                'chatroom_ai_auto_reply_daily_limit': 50,
                'chatroom_ai_auto_reply_escalate_negative': True,
                'chatroom_ai_auto_reply_allow_outside_hours': False,
                'chatroom_ai_agent_ai_planning_enabled': False,
            },
            'automatic': {
                'chatroom_ai_agent_mode': 'automatic',
                'chatroom_ai_agent_require_approval': False,
                'chatroom_ai_safe_auto_reply': True,
                'chatroom_ai_auto_reply_min_confidence': 0.90,
                'chatroom_ai_auto_reply_cooldown_minutes': 20,
                'chatroom_ai_auto_reply_daily_limit': 20,
                'chatroom_ai_auto_reply_escalate_negative': True,
                'chatroom_ai_auto_reply_allow_outside_hours': False,
                'chatroom_ai_agent_ai_planning_enabled': False,
            },
        }
        values = profiles.get(self.chatroom_ai_safety_profile)
        if values:
            for field_name, value in values.items():
                setattr(self, field_name, value)

    def action_open_ai_agent_control(self):
        return self.env.ref('chatroom_ai_agent.action_chatroom_ai_control').read()[0]
