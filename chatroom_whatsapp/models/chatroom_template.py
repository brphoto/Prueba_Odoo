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
         ('authentication', "Autenticación")])
    status = fields.Selection(
        [('approved', "Aprobada"),
         ('pending', "Pendiente"),
         ('rejected', "Rechazada"),
         ('paused', "Pausada"),
         ('disabled', "Deshabilitada")],
        default='pending')
    waba_template_id = fields.Char(string="ID en Meta", copy=False)
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

    _name_language_uniq = models.Constraint(
        'unique(name, language)',
        "Ya existe una plantilla con ese nombre e idioma.",
    )

    @api.depends('body')
    def _compute_variable_count(self):
        for rec in self:
            rec.variable_count = len(set(VARIABLE_RE.findall(rec.body or '')))

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
                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                templates_data += data.get('data', [])
                url = (data.get('paging') or {}).get('next')
                params = {}
        except requests.RequestException as exc:
            _logger.error("Error sincronizando plantillas de WhatsApp: %s", exc)
            raise UserError(_("No se pudo sincronizar con Meta: %s") % exc)

        created, updated = 0, 0
        for tmpl in templates_data:
            components = tmpl.get('components', [])
            body_component = next((c for c in components if c.get('type') == 'BODY'), {})
            header_component = next((c for c in components if c.get('type') == 'HEADER'), {})
            footer_component = next((c for c in components if c.get('type') == 'FOOTER'), {})
            vals = {
                'waba_template_id': tmpl.get('id'),
                'category': (tmpl.get('category') or '').lower() or False,
                'status': (tmpl.get('status') or 'pending').lower(),
                'body': body_component.get('text') or '',
                'header_type': (header_component.get('format') or 'none').lower(),
                'header_text': header_component.get('text'),
                'footer_text': footer_component.get('text'),
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
