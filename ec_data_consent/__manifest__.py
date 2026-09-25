# -*- coding: utf-8 -*-
{
    'name': 'Ecuador - Protección de Datos Personales (LOPDP)',
    'version': '19.0.1.0.1',
    'category': 'Human Resources',
    'summary': 'Registro de consentimiento de tratamiento de datos personales conforme a la LOPDP',
    'description': """
Protección de Datos Personales - LOPDP (Ecuador)
==================================================

Registro de consentimientos de socios/contactos conforme a la Ley Orgánica de
Protección de Datos Personales de Ecuador:

* Catálogo de tipos de consentimiento (tratamiento de datos, comunicaciones,
  uso de imagen, u otros que la organización defina).
* Un registro por socio y tipo de consentimiento, con fecha de otorgamiento,
  versión de política aceptada, y quién lo registró.
* Revocación explícita: un consentimiento revocado queda con fecha de revocación,
  nunca se borra (trazabilidad exigida por la ley).
* Vista rápida por socio de todos sus consentimientos vigentes/revocados.
""",
    'author': 'ERP Financiero EC',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['base', 'contacts', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/data_consent_views.xml',
        'views/res_partner_views.xml',
        'data/consent_type_data.xml',
    ],
    'icon': '/ec_data_consent/static/description/icon.svg',
    'installable': True,
    'application': False,
    'auto_install': False,
}
