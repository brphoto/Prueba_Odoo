import base64
import csv
import io

from odoo import _, fields, models
from odoo.exceptions import UserError

from .marketing_social_constants import PLATFORM_LABELS


class MarketingSocialImportWizard(models.TransientModel):
    _name = 'marketing.social.import.wizard'
    _description = 'Importador guiado de marketing social'

    file_data = fields.Binary(string='Archivo CSV', required=True)
    file_name = fields.Char(string='Nombre del archivo')
    import_type = fields.Selection([
        ('accounts', 'Cuentas'), ('publications', 'Publicaciones'),
        ('metrics', 'Métricas'), ('interactions', 'Interacciones'),
    ], string='Qué importar', required=True, default='publications')
    delimiter = fields.Selection([
        (',', 'Coma (,)'), (';', 'Punto y coma (;)'), ('\\t', 'Tabulador'),
    ], string='Separador', required=True, default=',')
    result_summary = fields.Text(string='Resultado', readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company)

    def _decode_rows(self):
        self.ensure_one()
        try:
            content = base64.b64decode(self.file_data).decode('utf-8-sig')
            delimiter = '\t' if self.delimiter == '\\t' else self.delimiter
            return list(csv.DictReader(io.StringIO(content), delimiter=delimiter))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise UserError(_('El archivo debe ser CSV UTF-8 válido: %s') % exc) from exc

    def _required(self, row, key, line_number):
        value = (row.get(key) or '').strip()
        if not value:
            raise UserError(_('Falta la columna «%s» en la línea %s.') % (key, line_number))
        return value

    def action_import(self):
        self.ensure_one()
        rows = self._decode_rows()
        if not rows:
            raise UserError(_('El CSV no contiene filas para importar.'))
        handlers = {
            'accounts': self._import_account,
            'publications': self._import_publication,
            'metrics': self._import_metric,
            'interactions': self._import_interaction,
        }
        created = 0
        for line_number, row in enumerate(rows, 2):
            handlers[self.import_type](row, line_number)
            created += 1
        self.result_summary = _('Se importaron %s fila(s) correctamente. Los datos quedaron disponibles para actualizar el centro de mando.') % created
        return {
            'type': 'ir.actions.act_window', 'name': _('Importar datos sociales'),
            'res_model': self._name, 'view_mode': 'form', 'res_id': self.id,
            'target': 'new',
        }

    def action_download_template(self):
        self.ensure_one()
        headers = {
            'accounts': 'name,platform,external_id,profile_url',
            'publications': 'name,external_id,account_external_id,published_at,content_type,caption,url',
            'metrics': 'external_id,snapshot_date,reach,impressions,views,likes,comments,shares,saves,clicks,leads,sales_amount',
            'interactions': 'external_id,publication_external_id,interaction_date,interaction_type,author_name,text,sentiment,intent,response_state',
        }[self.import_type]
        attachment = self.env['ir.attachment'].create({
            'name': 'plantilla_marketing_%s.csv' % self.import_type,
            'type': 'binary',
            'datas': base64.b64encode((headers + '\n').encode('utf-8')),
            'mimetype': 'text/csv',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def _import_account(self, row, line_number):
        Account = self.env['marketing.social.account']
        platform = self._required(row, 'platform', line_number).lower()
        if platform not in PLATFORM_LABELS:
            raise UserError(_('Red no válida en la línea %s. Usa: %s.') %
                            (line_number, ', '.join(PLATFORM_LABELS)))
        external_id = (row.get('external_id') or '').strip()
        domain = [('platform', '=', platform), ('company_id', '=', self.company_id.id)]
        if external_id:
            domain.append(('external_id', '=', external_id))
        account = Account.search(domain, limit=1)
        values = {
            'name': self._required(row, 'name', line_number), 'platform': platform,
            'external_id': external_id or False, 'profile_url': (row.get('profile_url') or '').strip(),
            'company_id': self.company_id.id,
        }
        if account:
            account.write(values)
        else:
            Account.create(values)

    def _find_publication(self, row, line_number):
        external_id = self._required(
            row, 'publication_external_id' if row.get('publication_external_id') is not None else 'external_id',
            line_number)
        publication = self.env['marketing.social.publication'].search([
            ('external_id', '=', external_id), ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not publication:
            raise UserError(_('No existe una publicación con ID externo «%s» en la línea %s.') %
                            (external_id, line_number))
        return publication

    def _find_account(self, row, line_number):
        platform = self._required(row, 'platform', line_number).lower()
        account = self.env['marketing.social.account'].search([
            ('platform', '=', platform), ('external_id', '=', self._required(row, 'account_external_id', line_number)),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not account:
            raise UserError(_('No existe la cuenta indicada en la línea %s. Importa primero las cuentas.') % line_number)
        return account

    def _import_publication(self, row, line_number):
        Publication = self.env['marketing.social.publication']
        account = self._find_account(row, line_number)
        external_id = self._required(row, 'external_id', line_number)
        values = {
            'name': self._required(row, 'name', line_number), 'external_id': external_id,
            'account_id': account.id, 'published_at': self._required(row, 'published_at', line_number),
            'content_type': (row.get('content_type') or 'post').strip(),
            'caption': (row.get('caption') or '').strip(), 'url': (row.get('url') or '').strip(),
        }
        publication = Publication.search([('external_id', '=', external_id), ('company_id', '=', self.company_id.id)], limit=1)
        if publication:
            publication.write(values)
        else:
            Publication.create(values)

    def _import_metric(self, row, line_number):
        publication = self._find_publication(row, line_number)
        values = {'publication_id': publication.id, 'snapshot_date': self._required(row, 'snapshot_date', line_number)}
        for field_name in ('reach', 'impressions', 'views', 'likes', 'comments', 'shares', 'saves', 'clicks', 'leads', 'sales_amount'):
            if row.get(field_name):
                try:
                    values[field_name] = float(row[field_name]) if field_name == 'sales_amount' else int(row[field_name])
                except ValueError as exc:
                    raise UserError(_('El valor de «%s» no es numérico en la línea %s.') % (field_name, line_number)) from exc
        Metric = self.env['marketing.social.metric.snapshot']
        metric = Metric.search([('publication_id', '=', publication.id), ('snapshot_date', '=', values['snapshot_date'])], limit=1)
        if metric:
            metric.write(values)
        else:
            Metric.create(values)

    def _import_interaction(self, row, line_number):
        publication = self._find_publication(row, line_number)
        values = {
            'publication_id': publication.id, 'interaction_type': (row.get('interaction_type') or 'comment').strip(),
            'author_name': (row.get('author_name') or '').strip(), 'external_id': (row.get('external_id') or '').strip(),
            'text': (row.get('text') or '').strip(), 'interaction_date': self._required(row, 'interaction_date', line_number),
            'sentiment': (row.get('sentiment') or 'neutral').strip(), 'intent': (row.get('intent') or 'other').strip(),
            'response_state': (row.get('response_state') or 'pending').strip(),
        }
        Interaction = self.env['marketing.social.interaction']
        interaction = Interaction.search([('external_id', '=', values['external_id']), ('company_id', '=', self.company_id.id)], limit=1) if values['external_id'] else self.env['marketing.social.interaction']
        if interaction:
            interaction.write(values)
        else:
            Interaction.create(values)
