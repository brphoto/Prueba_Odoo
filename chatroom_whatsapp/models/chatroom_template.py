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
    variable_mapping_ids = fields.One2many(
        'chatroom.template.variable', 'template_id', string='Campos de variables',
        copy=True)

    _name_language_uniq = models.Constraint(
        'unique(name, language)',
        "Ya existe una plantilla con ese nombre e idioma.",
    )

    @api.depends('body')
    def _compute_variable_count(self):
        for rec in self:
            numbers = [int(value) for value in VARIABLE_RE.findall(rec.body or '')]
            rec.variable_count = max(numbers, default=0)

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
        de la cuenta de WhatsApp Business configurada y las guarda/actualiza
        localmente."""
        token, waba_id, api_version = self._get_meta_waba_credentials()
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
            }
            existing = self.search([
                ('name', '=', tmpl.get('name')),
                ('language', '=', tmpl.get('language')),
            ], limit=1)
            if existing:
                existing.write(vals)
                updated += 1
            else:
                vals.update({'name': tmpl.get('name'), 'language': tmpl.get('language')})
                self.create(vals)
                created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Plantillas sincronizadas"),
                'message': _("%(created)s nuevas, %(updated)s actualizadas.") % {
                    'created': created, 'updated': updated},
                'type': 'success',
            },
        }

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

        token, waba_id, api_version = self._get_meta_waba_credentials()
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
