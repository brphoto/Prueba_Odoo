{
    'name': 'Chatroom Operaciones y Automatización',
    'summary': 'Panel de salud, playbooks de mensajes y demos QA',
    'description': '''Centro operativo modular para revisar la salud de Chatroom,
configurar playbooks de comunicación y generar escenarios DEMO QA.

El modo de playbook por defecto solo crea avisos internos. El envío automático
requiere una plantilla WhatsApp aprobada, permisos y activación explícita.''',
    'version': '19.0.1.0.7',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Discuss',
    'depends': [
        'chatroom_whatsapp', 'chatroom_ai_agent', 'chatroom_ai_usage',
        'chatroom_notifications', 'chatroom_ai_sales_fulfillment',
    ],
    'data': [
        'security/chatroom_ai_operations_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/chatroom_operations_metric_views.xml',
        'views/chatroom_operations_views.xml',
        'views/chatroom_operations_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'chatroom_ai_operations/static/src/chatroom_operations.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'icon': 'static/description/icon.svg',
}
