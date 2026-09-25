# -*- coding: utf-8 -*-
{
    'name': 'Chatroom IA - Agente de atención',
    'summary': 'Agente configurable (identidad, instrucciones, guiones y conocimiento) que responde solo desde el inicio',
    'description': '''
Agente de atención para cualquier negocio, configurado sin código:

* Perfil del agente: identidad, objetivo, tono, instrucciones y límites; uno
  general o uno por línea de WhatsApp.
* Guiones: qué datos reunir según lo que necesita el cliente y qué hacer al
  completarlos (seguir, crear oportunidad o pasar a una persona).
* Responde solo desde el primer día lo que está respaldado por el
  conocimiento publicado; lo demás queda para aprobación.
* Vacíos de conocimiento: lo que la IA no supo responder se junta, se
  captura la respuesta del equipo y se publica con un clic.
* Probador del agente: conversación simulada con el mismo proceso que
  producción; se guarda como caso de prueba o se corrige para que aprenda.
''',
    'version': '19.0.1.6.0',
    'category': 'Productivity/Discuss',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'icon': '/chatroom_ai_agent_profile/static/description/icon.svg',
    'depends': ['chatroom_ai_learning', 'chatroom_ai_knowledge'],
    'data': [
        'security/ir.model.access.csv',
        'security/profile_security.xml',
        'data/profile_data.xml',
        'data/ir_cron_data.xml',
        'views/history_import_views.xml',
        'views/event_views.xml',
        'views/inbox_views.xml',
        'views/profile_views.xml',
        'views/gap_views.xml',
        'views/simulator_views.xml',
        'views/ai_center_views.xml',
        'views/menu.xml',
    ],
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_backend': [
            'chatroom_ai_agent_profile/static/src/profile_assistant.js',
            'chatroom_ai_agent_profile/static/src/profile_assistant.xml',
            'chatroom_ai_agent_profile/static/src/chat_list.js',
            'chatroom_ai_agent_profile/static/src/chat_list.xml',
            'chatroom_ai_agent_profile/static/src/agent_profile.scss',
            'chatroom_ai_agent_profile/static/src/ai_center/ai_center.js',
            'chatroom_ai_agent_profile/static/src/ai_center/ai_center.xml',
            'chatroom_ai_agent_profile/static/src/ai_center/ai_center.scss',
            'chatroom_ai_agent_profile/static/src/composer_draft.js',
            'chatroom_ai_agent_profile/static/src/composer_draft.xml',
        ],
        'web.assets_tests': [
            'chatroom_ai_agent_profile/static/tests/tours/profile_tour.js',
        ],
    },
    'installable': True,
    'application': False,
}
