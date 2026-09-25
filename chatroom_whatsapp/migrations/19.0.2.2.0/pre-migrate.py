# -*- coding: utf-8 -*-
"""Multi-línea: la unicidad pasa a incluir la línea (canales) y la WABA
(plantillas).

Las restricciones antiguas se reemplazan por índices únicos con otro
nombre (`_external_id_line_uniq`, `_name_language_waba_uniq`). Odoo crea
los nuevos al actualizar, pero no borra solo los viejos: si quedaran, la
base seguiría impidiendo una segunda conversación del mismo contacto en
otra línea, o la misma plantilla en otra WABA.
"""

OLD_CONSTRAINTS = (
    ('chatroom_channel', 'chatroom_channel_external_id_type_uniq'),
    ('chatroom_template', 'chatroom_template_name_language_uniq'),
)


def migrate(cr, version):
    if not version:
        return
    for table, name in OLD_CONSTRAINTS:
        cr.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}"')
        cr.execute("DELETE FROM ir_model_constraint WHERE name = %s", [name])
