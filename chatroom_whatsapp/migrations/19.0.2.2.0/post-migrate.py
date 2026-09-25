# -*- coding: utf-8 -*-
"""Las plantillas anteriores a las WABAs por línea eran todas de la WABA
general de Ajustes: se les asigna, para que el asistente de envío las siga
ofreciendo en las conversaciones de esa WABA."""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE chatroom_template
           SET business_account_id = (
                   SELECT value FROM ir_config_parameter
                    WHERE key = 'chatroom_whatsapp.business_account_id')
         WHERE business_account_id IS NULL
           AND EXISTS (SELECT 1 FROM ir_config_parameter
                        WHERE key = 'chatroom_whatsapp.business_account_id'
                          AND value IS NOT NULL AND value != '')
    """)
