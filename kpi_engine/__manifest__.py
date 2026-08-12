# -*- coding: utf-8 -*-
{
    'name': "Motor de KPI compartido",

    'summary': """
        Modelo abstracto de "objetivo de KPI" (kpi.target.mixin), compartido
        por chatroom_whatsapp y crm_customer_intelligence: ninguno de los
        dos depende del otro, pero los dos necesitaban la misma lógica de
        alcance/período/objetivo y la tenían duplicada byte a byte.""",

    'description': """
Motor de KPI compartido
==========================
Ninguno de los dos módulos que definen KPIs (``chatroom_whatsapp`` con
``chatroom.kpi.definition`` y ``crm_customer_intelligence`` con
``crm.kpi.definition``) depende del otro, así que no podían compartir
código directamente: cada uno tenía su propia copia, byte a byte
idéntica, del modelo "objetivo de KPI" (alcance, período, validación de
fechas, `is_current_period()`).

Este módulo saca esa parte -la que de verdad era una copia exacta, sin
ninguna diferencia de negocio entre los dos- a un ``AbstractModel``
(``kpi.target.mixin``) del que ambos heredan. Los modelos concretos
(``crm.kpi.target``, ``chatroom.kpi.target``) siguen viviendo donde
estaban, con el mismo nombre de tabla y los mismos datos: solo cambia
de dónde viene la definición de los campos y métodos comunes.

Los modelos de *definición* de KPI (``crm.kpi.definition`` /
``chatroom.kpi.definition``) y de *histórico* (snapshot) se dejaron
sin tocar: a pesar de tener una forma parecida, representan el período
de análisis de manera distinta (días arbitrarios en Chatroom vs.
períodos con categoría RFM en CRM) y forzar ahí un modelo común
hubiera significado rediseñar el período de uno de los dos módulos,
no simplemente ordenar código duplicado.
    """,

    'author': "Bryan Cando",
    'website': "https://github.com/brphoto/Prueba_Odoo",
    'license': 'LGPL-3',

    'category': 'Hidden/Tools',
    'version': '19.0.1.0.0',

    'depends': ['base'],

    'data': [],

    'demo': [],

    'installable': True,
    'application': False,
    'auto_install': False,
}
