# -*- coding: utf-8 -*-
{
    'name': 'CRM - Gestión de Oportunidades Estancadas',
    'summary': 'Semáforo, capital atrapado, alertas y depuración parametrizable del pipeline.',
    'description': """
Gestión de Oportunidades Estancadas
====================================

Módulo independiente para detectar oportunidades que llevan demasiado tiempo
en una etapa, estimar el capital atrapado y ordenar la acción comercial.

La regla global se configura por empresa y cada etapa puede tener su propio
límite de días y cantidad mínima de actividades. Incluye semáforo, motivos,
score real/ficticia, alertas, escalamiento, vistas analíticas y un wizard de
depuración con aprobación explícita. No depende de WhatsApp ni de proveedores
de IA; si el agente IA está instalado, puede crear tareas supervisadas de
seguimiento como integración opcional.
""",
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Sales/CRM',
    'version': '19.0.1.0.1',
    'depends': ['crm', 'mail'],
    'data': [
        'security/crm_stagnation_security.xml',
        'security/ir.model.access.csv',
        'data/stagnation_config_data.xml',
        'data/ir_cron_data.xml',
        'views/crm_stagnation_config_views.xml',
        'views/crm_stage_views.xml',
        'views/crm_lead_views.xml',
        'views/crm_lead_purge_wizard_views.xml',
        'views/crm_stagnation_menus.xml',
    ],
    'installable': True,
    'application': False,
}
