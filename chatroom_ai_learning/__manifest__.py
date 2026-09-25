# -*- coding: utf-8 -*-
{
    'name': 'Chatroom IA - Aprendizaje y autonomía',
    'summary': 'La IA aprende del equipo y responde sola solo donde demostró acierto',
    'description': '''
Agente que opera solo de forma segura:

* Modo sombra: la IA redacta en silencio y se compara con lo que responde el equipo.
* Aprende de las correcciones: las respuestas del equipo se usan como ejemplos.
* Autonomía por niveles: cada tipo de conversación responde solo cuando lo ganó
  con datos, y vuelve a supervisado si baja la calidad.
* Reglas de traspaso: reclamos, siniestros, pagos o pedido de una persona pausan
  la IA, avisan al responsable y dejan un resumen.
* Memoria automática del cliente, con consentimiento.
* Pruebas de regresión que congelan la autonomía si la IA empeora.
''',
    'version': '19.0.1.2.0',
    'category': 'Productivity/Discuss',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'icon': '/chatroom_ai_learning/static/description/icon.svg',
    'depends': ['chatroom_ai', 'chatroom_ai_agent'],
    'data': [
        'security/ir.model.access.csv',
        'security/learning_security.xml',
        'data/ir_cron_data.xml',
        'data/autonomy_level_data.xml',
        'data/handoff_rule_data.xml',
        'data/eval_case_data.xml',
        'views/learning_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'chatroom_ai_learning/static/src/learning_assistant.js',
            'chatroom_ai_learning/static/src/learning_assistant.xml',
        ],
        'web.assets_tests': [
            'chatroom_ai_learning/static/tests/tours/learning_tour.js',
        ],
    },
    'installable': True,
    'application': False,
}
