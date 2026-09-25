# -*- coding: utf-8 -*-
import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

VARIABLE_RE = re.compile(r'\{\{\s*(\d+)\s*\}\}')


class ChatroomTemplate(models.Model):
    """Plantilla de mensaje de WhatsApp (HSM) aprobada por Meta.

    Fuera de la ventana de 24h desde el último mensaje del cliente, la
    Cloud API solo permite iniciar conversación con una de estas
    plantillas pre-aprobadas."""
    _name = 'chatroom.template'
    _description = "Plantilla de WhatsApp (HSM)"
    _inherit = ['chatroom.meta.mixin']
    _order = 'name, language'
    _rec_name = 'name'

    name = fields.Char(required=True, index=True)
    language = fields.Char(
        required=True, default='es',
        help="Código de idioma tal como está registrado en Meta, ej: es, es_MX, en_US")
    category = fields.Selection(
        [('marketing', "Marketing"),
         ('utility', "Utilidad"),
         ('authentication', "Autenticación")],
        default='utility')
    status = fields.Selection(
        [('draft', "Borrador"),
         ('approved', "Aprobada"),
         ('pending', "Pendiente"),
         ('rejected', "Rechazada"),
         ('paused', "Pausada"),
         ('disabled', "Deshabilitada")],
        default='draft', required=True)
    waba_template_id = fields.Char(string="ID en Meta", copy=False)
    business_account_id = fields.Char(
        string="WABA", index=True,
        default=lambda self: self._default_business_account_id(),
        help="WhatsApp Business Account donde vive la plantilla. Cada WABA tiene "
             "su propio catálogo: una plantilla solo puede enviarse por los "
             "números de su WABA. Por defecto, la WABA general de Ajustes.")
    last_synced_at = fields.Datetime(
        string="Última sincronización", readonly=True, copy=False)
    header_type = fields.Selection(
        [('none', "Ninguno"),
         ('text', "Texto"),
         ('image', "Imagen"),
         ('document', "Documento"),
         ('video', "Video")],
        default='none')
    header_text = fields.Char()
    body = fields.Text(
        required=True,
        help="Texto de la plantilla tal como fue aprobado, con variables "
             "en formato {{1}}, {{2}}, ...")
    footer_text = fields.Char()
    variable_count = fields.Integer(compute='_compute_variable_count')
    example_values = fields.Text(
        string='Valores de ejemplo',
        help='Escribe un valor por línea para revisar cómo quedará el mensaje.')
    preview_body = fields.Text(string='Vista previa', compute='_compute_preview_body')
    variable_mapping_ids = fields.One2many(
        'chatroom.template.variable', 'template_id', string='Campos de variables',
        copy=True)

    # El mismo nombre e idioma puede existir en varias WABAs (una por marca
    # o por cliente). Reemplaza a name_language_uniq (ver migrations/19.0.2.2.0).
    _name_language_waba_uniq = models.UniqueIndex(
        "(name, language, COALESCE(business_account_id, ''))",
        "Ya existe una plantilla con ese nombre e idioma en esa WABA.",
    )

    @api.model
    def _default_business_account_id(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_whatsapp.business_account_id') or False

    @api.model
    def _get_waba_accounts(self):
        """Todas las WABAs configuradas con el token con que se consultan.

        La general de Ajustes y la de cada línea activa que tenga una
        propia. Una línea sin token propio usa el general (caso típico:
        un mismo System User con acceso a varias WABAs).

        :return: lista de dicts ``waba_id``, ``token``, ``api_version`` y
            ``label``, sin WABAs repetidas.
        """
        icp = self.env['ir.config_parameter'].sudo()
        general_token = icp.get_param('chatroom_whatsapp.access_token')
        api_version = icp.get_param('chatroom_whatsapp.graph_api_version', 'v20.0')
        accounts = {}
        general_waba = icp.get_param('chatroom_whatsapp.business_account_id')
        if general_waba and general_token:
            accounts[general_waba] = {
                'waba_id': general_waba, 'token': general_token,
                'api_version': api_version, 'label': _('WABA general'),
            }
        for number in self.env['chatroom.whatsapp.number'].sudo().search([
                ('business_account_id', '!=', False)]):
            token = number.access_token or general_token
            if number.business_account_id in accounts or not token:
                continue
            accounts[number.business_account_id] = {
                'waba_id': number.business_account_id, 'token': token,
                'api_version': api_version, 'label': number.name,
            }
        return list(accounts.values())

    def _get_waba_credentials_for(self, waba_id):
        """Token, WABA y versión para hablar con una WABA concreta."""
        if not waba_id:
            return self._get_meta_waba_credentials()
        for account in self._get_waba_accounts():
            if account['waba_id'] == waba_id:
                return account['token'], account['waba_id'], account['api_version']
        raise UserError(_(
            "La WABA %s no está configurada: ponla en Ajustes o en una Línea "
            "de WhatsApp activa, con su token si es distinto del general.") % waba_id)

    @api.depends('body')
    def _compute_variable_count(self):
        for rec in self:
            numbers = [int(value) for value in VARIABLE_RE.findall(rec.body or '')]
            rec.variable_count = max(numbers, default=0)

    @api.depends('body', 'example_values')
    def _compute_preview_body(self):
        for record in self:
            values = (record.example_values or '').splitlines()
            def replace(match):
                number = int(match.group(1))
                return values[number - 1].strip() if number <= len(values) else match.group(0)
            record.preview_body = VARIABLE_RE.sub(replace, record.body or '')

    def action_validate_template(self):
        for record in self:
            numbers = sorted({int(value) for value in VARIABLE_RE.findall(record.body or '')})
            expected = list(range(1, max(numbers, default=0) + 1))
            if numbers != expected:
                raise UserError(_(
                    'Las variables deben ser consecutivas desde {{1}}. Detectadas: %s') % numbers)
            if record.variable_count and len(record.variable_mapping_ids) < record.variable_count:
                raise UserError(_('Detecta y configura todos los campos de variables antes de enviar.'))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Plantilla válida'),
            'message': _('La estructura y las variables están listas para revisión o envío.'),
            'type': 'success',
        }}

    def action_detect_variables(self):
        for record in self:
            numbers = sorted({int(value) for value in VARIABLE_RE.findall(record.body or '')})
            existing = {line.sequence: line for line in record.variable_mapping_ids}
            for number in numbers:
                if number not in existing:
                    self.env['chatroom.template.variable'].create({
                        'template_id': record.id,
                        'sequence': number,
                        'label': _('Variable %s') % number,
                    })
            record.variable_mapping_ids.filtered(
                lambda line: line.sequence not in numbers).unlink()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def get_variable_values(self, channel):
        self.ensure_one()
        mapping = {line.sequence: line for line in self.variable_mapping_ids}
        return [
            mapping[number].resolve_value(channel) if number in mapping else ''
            for number in range(1, self.variable_count + 1)
        ]

    @api.model
    def action_sync_templates(self):
        """Trae desde Meta el catálogo de plantillas aprobadas/pendientes
        de cada WABA configurada (la general y la de cada línea que viva en
        otra) y las guarda/actualiza localmente, cada una con su WABA.

        Una WABA que falla no impide sincronizar las demás: se informa al
        final. Solo si fallan todas se lanza el error."""
        accounts = self._get_waba_accounts()
        if not accounts:
            # Mismo mensaje de siempre cuando no hay nada configurado.
            self._get_meta_waba_credentials()
        created = updated = 0
        failures = []
        for account in accounts:
            try:
                account_created, account_updated = self._sync_waba_templates(account)
            except UserError as exc:
                failures.append('%s: %s' % (account['label'], exc.args[0] if exc.args else exc))
                continue
            created += account_created
            updated += account_updated
        if failures and len(failures) == len(accounts):
            raise UserError('\n'.join(failures))
        message = _("%(created)s nuevas, %(updated)s actualizadas.") % {
            'created': created, 'updated': updated}
        if failures:
            message += ' ' + _('No se pudo sincronizar: %s') % '; '.join(failures)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Plantillas sincronizadas"),
                'message': message,
                'type': 'warning' if failures else 'success',
            },
        }

    @api.model
    def _sync_waba_templates(self, account):
        """Sincroniza las plantillas de una WABA. Devuelve (creadas, actualizadas)."""
        token, waba_id, api_version = account['token'], account['waba_id'], account['api_version']
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://graph.facebook.com/{api_version}/{waba_id}/message_templates"
        params = {"limit": 100}

        templates_data = []
        try:
            while url:
                response = self._meta_request('GET', url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                templates_data += data.get('data', [])
                url = (data.get('paging') or {}).get('next')
                params = {}
        except requests.RequestException as exc:
            _logger.error("Error sincronizando plantillas de WhatsApp: %s", exc)
            raise UserError(_("No se pudo sincronizar con Meta: %s") % exc)

        created, updated = 0, 0
        synced_at = fields.Datetime.now()
        # Un indice de lo que ya existe en UNA consulta. Antes se buscaba
        # por plantilla: una cuenta con 200 plantillas aprobadas eran 200
        # SELECT antes de escribir nada.
        #
        # Las plantillas anteriores a las WABAs por línea no tienen WABA:
        # se tratan como de la general y se completan al actualizarlas.
        general_waba = self._default_business_account_id()
        known = {
            (record.name, record.language, record.business_account_id or general_waba): record
            for record in self.search([
                ('name', 'in', [t.get('name') for t in templates_data if t.get('name')]),
            ])
        } if templates_data else {}
        for tmpl in templates_data:
            components = tmpl.get('components', [])
            body_component = next((c for c in components if c.get('type') == 'BODY'), {})
            header_component = next((c for c in components if c.get('type') == 'HEADER'), {})
            footer_component = next((c for c in components if c.get('type') == 'FOOTER'), {})
            status = (tmpl.get('status') or 'pending').lower()
            if status not in dict(self._fields['status'].selection):
                status = 'pending'
            category = (tmpl.get('category') or '').lower() or False
            if category not in dict(self._fields['category'].selection):
                category = 'utility'
            header_type = (header_component.get('format') or 'none').lower()
            if header_type not in dict(self._fields['header_type'].selection):
                header_type = 'none'
            vals = {
                'waba_template_id': tmpl.get('id'),
                'category': category,
                'status': status,
                'body': body_component.get('text') or '',
                'header_type': header_type,
                'header_text': header_component.get('text'),
                'footer_text': footer_component.get('text'),
                'last_synced_at': synced_at,
                'business_account_id': waba_id,
            }
            key = (tmpl.get('name'), tmpl.get('language'), waba_id)
            existing = known.get(key, self.browse())
            if existing:
                existing.write(vals)
                updated += 1
            else:
                vals.update({'name': tmpl.get('name'), 'language': tmpl.get('language')})
                # Se alimenta el indice: si Meta repite el mismo par
                # nombre/idioma en la respuesta, la segunda vuelta
                # actualiza en vez de crear un duplicado, que es lo que
                # hacia la busqueda original.
                known[key] = self.create(vals)
                created += 1
        return created, updated

    def action_submit_to_meta(self):
        """Submit a locally prepared text template to Meta for approval."""
        self.ensure_one()
        if self.waba_template_id:
            raise UserError(_("Esta plantilla ya fue enviada a Meta."))
        if not self.name or not self.language or not self.category or not self.body:
            raise UserError(_(
                "Completa nombre, idioma, categoría y cuerpo antes de enviar "
                "la plantilla a Meta."))
        if self.header_type not in (False, 'none', 'text'):
            raise UserError(_(
                "Para crear la plantilla desde Odoo usa un encabezado sin "
                "contenido o de texto. Los encabezados multimedia requieren "
                "ejemplos gestionados desde Meta."))

        token, waba_id, api_version = self._get_waba_credentials_for(self.business_account_id)
        components = [{'type': 'BODY', 'text': self.body}]
        if self.header_type == 'text':
            if not self.header_text:
                raise UserError(_("Escribe el texto del encabezado."))
            components.insert(0, {
                'type': 'HEADER', 'format': 'TEXT', 'text': self.header_text,
            })
        if self.footer_text:
            components.append({'type': 'FOOTER', 'text': self.footer_text})

        url = f"https://graph.facebook.com/{api_version}/{waba_id}/message_templates"
        response = self._meta_request(
            'POST', url,
            headers={'Authorization': f'Bearer {token}'},
            json={
                'name': self.name,
                'language': self.language,
                'category': self.category.upper(),
                'components': components,
            },
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            detail = ''
            try:
                detail = response.json().get('error', {}).get('message', '')
            except (ValueError, AttributeError):
                pass
            raise UserError(_("Meta rechazó la plantilla: %s") % (detail or exc))

        data = response.json()
        self.write({
            'waba_template_id': data.get('id'),
            'status': (data.get('status') or 'pending').lower(),
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Plantilla enviada"),
                'message': _("Meta la dejó pendiente de aprobación."),
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }
