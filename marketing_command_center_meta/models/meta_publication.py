from odoo import _, fields, models
from odoo.exceptions import UserError

from .meta_api import MetaGraphError


class MarketingMetaPublication(models.Model):
    _inherit = 'marketing.social.publication'

    meta_edit_capability = fields.Selection([
        ('available', 'Edición Facebook disponible'),
        ('unsupported', 'Edición no disponible para esta red'),
        ('unknown', 'Requiere validación'),
    ], string='Capacidad de edición Meta', default='unknown', readonly=True)

    def _meta_page_for_publication(self):
        self.ensure_one()
        Page = self.env['marketing.meta.page']
        account = self.account_id
        return Page.search([
            ('active', '=', True),
            '|', ('social_account_id', '=', account.id),
            ('instagram_social_account_id', '=', account.id),
        ], limit=1)

    def action_push_edit_to_meta(self):
        """Push an approved caption draft only where Meta supports it."""
        for record in self:
            if not record.draft_caption:
                raise UserError(_('Primero prepara y guarda un borrador de edición.'))
            if record.platform != 'facebook':
                record.write({
                    'edit_state': 'error',
                    'meta_edit_capability': 'unsupported',
                    'edit_last_error': _('La API estándar de Instagram permite publicar y consultar medios, pero no editar el texto de una publicación ya publicada en este flujo.'),
                })
                raise UserError(record.edit_last_error)
            page = record._meta_page_for_publication()
            if not page:
                raise UserError(_('No se encontró la página Meta vinculada a esta publicación.'))
            try:
                page._client().mutate(record.external_id, {'message': record.draft_caption})
            except MetaGraphError as error:
                record.write({
                    'edit_state': 'error', 'meta_edit_capability': 'available',
                    'edit_last_error': str(error),
                })
                raise UserError(str(error)) from error
            record.write({
                'caption': record.draft_caption,
                'name': (record.draft_caption or record.name)[:120],
                'edit_state': 'synced',
                'meta_edit_capability': 'available',
                'edit_synced_at': fields.Datetime.now(),
                'edit_last_error': False,
            })
            record.message_post(body=_('La edición fue sincronizada con la publicación de Facebook.'))
        return True

    def action_check_meta_edit_capability(self):
        for record in self:
            if record.platform != 'facebook':
                record.write({'meta_edit_capability': 'unsupported'})
                continue
            page = record._meta_page_for_publication()
            if not page:
                record.write({'meta_edit_capability': 'unknown'})
                continue
            try:
                page._client().request(record.external_id, {'fields': 'id,message'})
            except MetaGraphError as error:
                record.write({'meta_edit_capability': 'unknown', 'edit_last_error': str(error)})
            else:
                record.write({'meta_edit_capability': 'available', 'edit_last_error': False})
        return True
