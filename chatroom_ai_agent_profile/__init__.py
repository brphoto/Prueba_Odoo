# -*- coding: utf-8 -*-
from . import models

# Menús de otros módulos que este módulo mueve a «Avanzado».
MOVED_MENUS = ('chatroom_ai_agent.menu_chatroom_ai_operation', 'chatroom_ai_agent.menu_chatroom_ai_configuration',
               'chatroom_ai_agent.menu_chatroom_ai_governance', 'chatroom_ai_learning.menu_ai_learning_root')


def uninstall_hook(env):
    """Devuelve los menús movidos a «Agente IA» antes de borrar «Avanzado»."""
    root = env.ref('chatroom_ai_agent.menu_chatroom_ai_agent', raise_if_not_found=False)
    for xmlid in MOVED_MENUS:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu and root:
            menu.parent_id = root
