"""Prepare legacy RFM XML-IDs before Odoo loads the new data files.

The old category model is intentionally no longer registered.  Therefore
``ir_model_data`` must point to the unified model before
``rfm_category_data.xml`` is parsed; doing this in post-migrate is too late.
"""


def _table_exists(cr, table):
    cr.execute("SELECT to_regclass(%s)", (table,))
    return bool(cr.fetchone()[0])


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return

    # Updating a parent view makes Odoo validate its existing inherited views
    # immediately. Patch the persisted legacy xpath first, otherwise the old
    # child view fails before its XML file gets a chance to update it.
    if _table_exists(cr, 'ir_ui_view') and _column_exists(cr, 'ir_ui_view', 'arch_db'):
        cr.execute(
            """
            UPDATE ir_ui_view
               SET arch_db = replace(
                   replace(arch_db::text, 'name="category"', 'name="category_id"'),
                   'name=' || chr(39) || 'category' || chr(39),
                   'name=' || chr(39) || 'category_id' || chr(39)
               )::jsonb
             WHERE model = 'crm.rfm.segment'
               AND arch_db::text LIKE '%category%'
            """
        )

    if not _table_exists(cr, 'crm_rfm_category'):
        return
    if not _table_exists(cr, 'crm_rfm_segment'):
        return

    # At the pre-migrate stage Odoo has not added the new columns yet. The
    # placeholder rows therefore use only the legacy segment columns; the
    # XML data loaded immediately afterwards fills definition_type and code.
    has_definition_type = _column_exists(cr, 'crm_rfm_segment', 'definition_type')

    cr.execute(
        """
        SELECT id, name, code, sequence, active, score_min, score_max,
               color, is_at_risk, description
          FROM crm_rfm_category
         ORDER BY id
        """
    )
    category_map = {}
    for row in cr.fetchall():
        old_id, name, code, sequence, active, score_min, score_max, color, is_at_risk, description = row
        existing = None
        if has_definition_type and _column_exists(cr, 'crm_rfm_segment', 'code'):
            cr.execute(
                """
                SELECT id
                  FROM crm_rfm_segment
                 WHERE definition_type = 'category' AND code = %s
                 LIMIT 1
                """,
                (code,),
            )
            existing = cr.fetchone()
        if existing:
            new_id = existing[0]
        else:
            cr.execute(
                """
                INSERT INTO crm_rfm_segment
                    (name, category, active, sequence, color, icon, category_id,
                     use_score_filter, score_min, score_max, max_days_since_sale,
                     description, rule_logic, create_uid, create_date,
                     write_uid, write_date)
                VALUES
                    (%s, %s, %s, %s, %s, 'fa-layer-group', NULL, FALSE,
                     %s, %s, 0, %s, 'all', 1, NOW(), 1, NOW())
                RETURNING id
                """,
                (name, code, active, sequence, color, score_min, score_max,
                 description),
            )
            new_id = cr.fetchone()[0]
        category_map[old_id] = new_id

    # This must happen before XML data is loaded. Otherwise env.ref() tries
    # to browse the removed crm.rfm.category model and aborts the upgrade.
    for old_id, new_id in category_map.items():
        cr.execute(
            """
            UPDATE ir_model_data
               SET model = 'crm.rfm.segment', res_id = %s
             WHERE model = 'crm.rfm.category' AND res_id = %s
            """,
            (new_id, old_id),
        )
