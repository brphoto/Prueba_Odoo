"""Deactivate obsolete category/segment UI artifacts after catalog unification."""


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        """
        UPDATE ir_ui_view
           SET active = FALSE
         WHERE id IN (
             SELECT res_id
               FROM ir_model_data
              WHERE model = 'ir.ui.view'
                AND module = 'crm_customer_intelligence'
                AND name IN (
                    'view_crm_rfm_category_list',
                    'view_crm_rfm_category_form',
                    'view_crm_rfm_segment_list_automation'
                )
         )
        """
    )
