"""Merge the former RFM category table into crm.rfm.segment.

The unified model keeps two explicit kinds of definition:
``category`` for score buckets and ``segment`` for customer audiences.
The old table is intentionally retained as an unused rollback source; all
live references are moved to the unified table.
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
    if not version or not _table_exists(cr, 'crm_rfm_category'):
        return

    # The new model has already been upgraded at this point, so its extra
    # columns are available even though the legacy category table remains.
    cr.execute(
        """
        SELECT id, name, code, sequence, active, score_min, score_max,
               color, is_at_risk, description
          FROM crm_rfm_category
         ORDER BY id
        """
    )
    category_rows = cr.fetchall()
    category_map = {}
    for row in category_rows:
        old_id, name, code, sequence, active, score_min, score_max, color, is_at_risk, description = row
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
            cr.execute(
                """
                UPDATE crm_rfm_segment
                   SET name = %s, active = %s, sequence = %s, color = %s,
                       score_min = %s, score_max = %s, description = %s,
                       is_at_risk = %s
                 WHERE id = %s
                """,
                (name, active, sequence, color, score_min, score_max,
                 description, is_at_risk, new_id),
            )
        else:
            cr.execute(
                """
                INSERT INTO crm_rfm_segment
                    (name, definition_type, code, active, sequence, color,
                     icon, category_id, use_score_filter, score_min,
                     score_max, max_days_since_sale, description, is_at_risk,
                     rule_logic, create_uid, create_date, write_uid, write_date)
                VALUES
                    (%s, 'category', %s, %s, %s, %s, 'fa-layer-group', NULL,
                     FALSE, %s, %s, 0, %s, %s, 'all', 1, NOW(), 1, NOW())
                RETURNING id
                """,
                (name, code, active, sequence, color, score_min, score_max,
                 description, is_at_risk),
            )
            new_id = cr.fetchone()[0]
        category_map[old_id] = new_id

    # Existing saved segments previously pointed to crm_rfm_category and/or
    # stored the same code in the redundant selection field.
    if _column_exists(cr, 'crm_rfm_segment', 'category_id'):
        cr.execute(
            "SELECT id, category_id FROM crm_rfm_segment "
            "WHERE definition_type = 'segment' AND category_id IS NOT NULL"
        )
        for segment_id, old_category_id in cr.fetchall():
            new_category_id = category_map.get(old_category_id)
            if new_category_id:
                cr.execute(
                    "UPDATE crm_rfm_segment SET category_id = %s WHERE id = %s",
                    (new_category_id, segment_id),
                )

    if _column_exists(cr, 'crm_rfm_segment', 'category'):
        cr.execute(
            "SELECT id, category FROM crm_rfm_segment "
            "WHERE definition_type = 'segment' AND category IS NOT NULL "
            "AND (category_id IS NULL OR category_id = 0)"
        )
        legacy_category_rows = cr.fetchall()
        cr.execute("SELECT id, code FROM crm_rfm_segment WHERE definition_type = 'category'")
        unified_category_rows = cr.fetchall()
        code_to_id = {code: new_id for new_id, code in unified_category_rows}
        for segment_id, code in legacy_category_rows:
            new_category_id = code_to_id.get(code)
            if new_category_id:
                cr.execute(
                    "UPDATE crm_rfm_segment SET category_id = %s WHERE id = %s",
                    (new_category_id, segment_id),
                )

    # Move known Many2one/Many2many references. These tables are optional
    # because the history and Chatroom modules can be installed separately.
    references = [
        ('res_partner', 'history_manual_category_id'),
        ('chatroom_campaign_rfm_category_rel', 'category_id'),
    ]
    for table, column in references:
        if not _table_exists(cr, table) or not _column_exists(cr, table, column):
            continue
        for old_id, new_id in category_map.items():
            cr.execute(
                'UPDATE "%s" SET "%s" = %%s WHERE "%s" = %%s' % (table, column, column),
                (new_id, old_id),
            )

    # Keep external IDs stable so existing XML references continue to point
    # to the same conceptual category after the model name changes.
    for old_id, new_id in category_map.items():
        cr.execute(
            """
            UPDATE ir_model_data
               SET model = 'crm.rfm.segment', res_id = %s
             WHERE model = 'crm.rfm.category' AND res_id = %s
            """,
            (new_id, old_id),
        )
