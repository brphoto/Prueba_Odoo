# -*- coding: utf-8 -*-
"""Lo que el agente hace además de escribir: botones de WhatsApp para elegir
un dato, la foto del producto que recomienda, la cotización con enlace para
aceptar y pagar, la cita en el calendario y el borrador en el chat."""
import logging
import re
import unicodedata
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models

from odoo.addons.chatroom_ai_learning.models.learning_utils import normalize
from .chatroom import DRAFT_CACHE, LOCAL_CACHE
from .playbook import load_data

_logger = logging.getLogger(__name__)

WEEKDAYS = {'lunes': 0, 'martes': 1, 'miercoles': 2, 'jueves': 3, 'viernes': 4, 'sabado': 5, 'domingo': 6}
MONTHS = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
          'septiembre': 9, 'setiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12}
HOUR_RE = re.compile(r'\b(?:a las |a la |las )?(\d{1,2})(?:[:h.](\d{2}))?\s*(am|pm|hrs|h)?\b')
DATE_RE = re.compile(r'\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b')
DAY_MONTH_RE = re.compile(r'\b(\d{1,2}) de (%s)\b' % '|'.join(MONTHS))


def _fold(text):
    """Minúsculas y sin tildes, pero conservando «:» y «/» (horas y fechas)."""
    text = unicodedata.normalize('NFKD', (text or '').lower())
    text = ''.join(char for char in text if not unicodedata.combining(char))
    for old, new in (('p.m.', 'pm'), ('a.m.', 'am'), ('p. m.', 'pm'), ('a. m.', 'am'),
                     (' de la tarde', ' pm'), (' de la noche', ' pm')):
        text = text.replace(old, new)
    return text


def parse_when(text, now):
    """Fecha y hora locales de «mañana a las 3 pm», «martes 10:30», «15/05 16h»...

    Devuelve ``None`` si no hay día y hora claros: en ese caso una persona agenda.
    """
    folded = _fold(text)
    plain = re.sub(r'\bpasado manana\b', 'pasadomanana', normalize(folded))
    day = None
    if 'pasadomanana' in plain:
        day = now.date() + timedelta(days=2)
    elif (re.search(r'\bmanana\b', plain) and not re.search(r'\b(en|por|de) la manana\b', plain)) \
            or re.search(r'(?<!la )\bmanana (a|en|por)\b', plain):
        day = now.date() + timedelta(days=1)
    elif re.search(r'\bhoy\b', plain):
        day = now.date()
    match = DATE_RE.search(folded)
    if match:
        year = int(match.group(3)) if match.group(3) else now.year
        year = year + 2000 if year < 100 else year
        try:
            day = datetime(year, int(match.group(2)), int(match.group(1))).date()
        except ValueError:
            day = None
    match = DAY_MONTH_RE.search(folded)
    if match:
        try:
            day = datetime(now.year, MONTHS[match.group(2)], int(match.group(1))).date()
            if day < now.date():
                day = day.replace(year=now.year + 1)
        except ValueError:
            day = None
    if day is None:
        for name, weekday in WEEKDAYS.items():
            if re.search(r'\b%s\b' % name, plain):
                day = now.date() + timedelta(days=(weekday - now.weekday()) % 7 or 7)
                break
    if day is None:
        return None
    # La hora: se quita la fecha para no confundir «15/05» con las 15.
    rest = DAY_MONTH_RE.sub(' ', DATE_RE.sub(' ', folded))
    hour = minute = None
    for match in HOUR_RE.finditer(rest):
        value = int(match.group(1))
        suffix = (match.group(3) or '').replace(' ', '')
        if value > 23 or (not suffix and not match.group(2) and 'las' not in match.group(0)):
            continue
        hour, minute = value, int(match.group(2) or 0)
        if suffix == 'pm' and hour < 12:
            hour += 12
        elif suffix == 'am' and hour == 12:
            hour = 0
        elif suffix != 'am' and 1 <= hour <= 7:
            hour += 12  # «a las 3» en horario de atención es por la tarde
        break
    if hour is None or minute > 59:
        return None
    return datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    ai_cards_sent = fields.Char(string='Productos ya mostrados', copy=False,
                                help='Fotos de producto ya enviadas en esta conversación (no se repiten).')

    # ------------------------------------------------------------------
    # Botones para elegir el dato que pide el guion
    # ------------------------------------------------------------------
    @api.model
    def _ai_parse_draft_extras(self, raw):
        extras = super()._ai_parse_draft_extras(raw)
        match = re.search(r'\{.*\}', raw or '', re.DOTALL)
        asked = ''
        if match:
            found = re.search(r'"pregunta_dato"\s*:\s*"([^"]*)"', match.group(0))
            asked = found.group(1).strip() if found else ''
        extras['asked_key'] = asked[:60]
        return extras

    def _ai_reply_options(self, draft):
        """Opciones del dato que la respuesta le pide al cliente (o [])."""
        if len(self) != 1 or not draft or not self.ai_playbook_id or self.ai_playbook_done:
            return []
        return self.ai_playbook_id._options_for(load_data(self.ai_playbook_data), draft.get('asked_key') or '',
                                                draft.get('reply') or '')

    def _ai_deliver_guarded_reply(self, reply, confidence, intent=False, reason=False):
        draft = self.env.cr.cache.get(DRAFT_CACHE, {}).get(self.id) if len(self) == 1 else None
        channel = self
        if draft and draft.get('reply') == reply:
            # El modelo dijo qué dato pide: manda eso, aunque no tenga opciones.
            channel = self.with_context(chatroom_ai_options=self._ai_reply_options(draft))
        result = super(ChatroomChannel, channel)._ai_deliver_guarded_reply(
            reply, confidence, intent=intent, reason=reason)
        if (isinstance(result, dict) and result.get('status') == 'sent' and len(self) == 1
                and self.id not in self.env.cr.cache.get(LOCAL_CACHE, set())):
            self._ai_send_product_cards(reply)
        return result

    def action_send_text(self, body, reply_to_id=False):
        options = self.env.context.get('chatroom_ai_options')
        if ('chatroom_ai_options' not in self.env.context and len(self) == 1 and self.ai_playbook_id
                and not self.ai_playbook_done and self.env.context.get('chatroom_ai_generated')):
            # Borrador aprobado desde la bandeja o un seguimiento: se reconoce
            # el dato que pide por lo que dice el texto.
            options = self.ai_playbook_id._options_for(load_data(self.ai_playbook_data), '', body)
        if options and len(self) == 1 and self.env.context.get('chatroom_ai_generated') \
                and self.channel_type == 'whatsapp':
            try:
                with self.env.cr.savepoint():
                    if len(options) <= 3:
                        return self.action_send_interactive_buttons(body, options)
                    rows = [{'id': 'opt_%s' % index, 'title': option[:24]} for index, option in enumerate(options)]
                    return self._send_interactive_list(
                        body, _('Elegir'), rows, '\n'.join([body] + ['• %s' % option for option in options]))
            except Exception as exc:  # noqa: BLE001 - sin botones sale como texto con las opciones
                _logger.info('No se enviaron las opciones como botones en %s: %s', self.id, exc)
                body = '%s\n%s' % (body, '\n'.join('• %s' % option for option in options))
        return super(ChatroomChannel, self.with_context(chatroom_ai_options=False)).action_send_text(
            body, reply_to_id=reply_to_id)

    # ------------------------------------------------------------------
    # Foto del producto recomendado
    # ------------------------------------------------------------------
    def _ai_products_in_reply(self, reply, limit=2):
        text = ' %s ' % normalize(reply)
        if len(text.strip()) < 4 or 'product.product' not in self.env:
            return self.env['product.product']
        Product = self.env['product.product'].sudo()
        company = self.company_id or self.env.company
        candidates = Product.search([('sale_ok', '=', True), ('product_tmpl_id.image_1920', '!=', False),
                                     '|', ('company_id', '=', False), ('company_id', '=', company.id)], limit=300)
        # El nombre más largo primero: «Silla ergonómica Pro» antes que «Silla».
        found = Product.browse()
        for product in candidates.sorted(lambda item: -len(item.name or '')):
            name = normalize(product.name)
            if len(name) >= 4 and ' %s ' % name in text and not any(
                    name in normalize(other.name) for other in found):
                found |= product
            if len(found) >= limit:
                break
        return found

    def _ai_send_product_cards(self, reply):
        self.ensure_one()
        profile = self._ai_agent_profile()
        if not profile or not profile.send_product_images or self.channel_type != 'whatsapp':
            return 0
        shown = {int(item) for item in (self.ai_cards_sent or '').split(',') if item.isdigit()}
        sent = 0
        for product in self._ai_products_in_reply(reply):
            if product.id in shown:
                continue
            try:
                with self.env.cr.savepoint():
                    self.with_context(chatroom_ai_generated=True).action_send_product(product.id)
                shown.add(product.id)
                sent += 1
            except Exception as exc:  # noqa: BLE001 - la foto es un extra
                _logger.info('No se envió la foto de %s en %s: %s', product.display_name, self.id, exc)
        if sent:
            self.sudo().ai_cards_sent = ','.join(str(item) for item in sorted(shown))
        return sent

    # ------------------------------------------------------------------
    # Cierre del guion con acciones reales
    # ------------------------------------------------------------------
    def _ai_playbook_action(self, playbook, data, summary):
        """Hace la acción del guion; devuelve el texto a enviar tras el cierre."""
        if playbook.on_complete == 'send_quote':
            return self._ai_playbook_send_quote(playbook, data, summary)
        if playbook.on_complete == 'meeting':
            return self._ai_playbook_meeting(playbook, data, summary)
        return super()._ai_playbook_action(playbook, data, summary)

    def _ai_playbook_send_quote(self, playbook, data, summary):
        order = self._ai_playbook_quote(playbook, data, summary)
        if not order or order._name != 'sale.order' or not order.order_line or order.amount_total <= 0:
            return ''
        try:
            with self.env.cr.savepoint():
                order = order.sudo()
                order._portal_ensure_token()
                url = '%s%s' % (order.get_base_url(), order.get_portal_url())
                if hasattr(order, 'action_quotation_sent'):
                    order.action_quotation_sent()
        except Exception as exc:  # noqa: BLE001 - queda en borrador para el equipo
            _logger.info('No se preparó el enlace de la cotización en %s: %s', self.id, exc)
            return ''
        self.sudo().action_post_internal_note(
            _('Cotización %(order)s enviada al cliente con enlace para aceptar y pagar.') % {'order': order.name})
        return _('Aquí está tu cotización %(order)s por %(amount)s. Puedes revisarla, aceptarla y pagarla en '
                 'línea: %(url)s') % {
            'order': order.name, 'url': url,
            'amount': '%s %.2f' % (order.currency_id.symbol or order.currency_id.name, order.amount_total)}

    def _ai_meeting_tz(self):
        icp = self.env['ir.config_parameter'].sudo()
        # La cola responde como usuario del sistema (sin zona horaria): «mañana»
        # es el del negocio, no el de UTC.
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        name = icp.get_param('chatroom_whatsapp.business_hours_tz') or self.assigned_user_id.tz \
            or self.whatsapp_number_id.member_ids[:1].tz or self.env.user.tz or (admin and admin.tz) \
            or self.env.company.partner_id.tz or 'UTC'
        try:
            return pytz.timezone(name)
        except pytz.UnknownTimeZoneError:
            return pytz.utc

    def _ai_playbook_meeting(self, playbook, data, summary):
        field = playbook.field_ids.filtered(lambda item: 'fecha' in item.key or 'hora' in item.key)[:1]
        when_text = ' '.join(data.get(item.key) or '' for item in field) if field else ' '.join(
            str(value) for value in data.values())
        tz = self._ai_meeting_tz()
        now_local = fields.Datetime.now().replace(tzinfo=pytz.utc).astimezone(tz).replace(tzinfo=None)
        start_local = parse_when(when_text, now_local)
        if not start_local or start_local < now_local or 'calendar.event' not in self.env:
            self._ai_playbook_activity(playbook, summary)
            return ''
        start = tz.localize(start_local).astimezone(pytz.utc).replace(tzinfo=None)
        user = self.assigned_user_id or self.whatsapp_number_id.member_ids[:1] or self.env.user
        try:
            with self.env.cr.savepoint():
                event = self.env['calendar.event'].sudo().create({
                    'name': '%s: %s' % (playbook.name, self.partner_id.name or self.display_name),
                    'start': start, 'stop': start + timedelta(hours=1), 'user_id': user.id,
                    'partner_ids': [(6, 0, (user.partner_id | self.partner_id).ids)], 'description': summary,
                })
        except Exception as exc:  # noqa: BLE001 - sin calendario, tarea para el equipo
            _logger.info('No se creó la cita del guion en %s: %s', self.id, exc)
            self._ai_playbook_activity(playbook, summary)
            return ''
        self.sudo().action_post_internal_note(_('Cita agendada: %(name)s, %(when)s.') % {
            'name': event.name, 'when': start_local.strftime('%d/%m/%Y %H:%M')})
        return _('Listo, te agendé para el %(day)s a las %(hour)s. Te confirmamos por aquí cualquier cambio.') % {
            'day': start_local.strftime('%d/%m/%Y'), 'hour': start_local.strftime('%H:%M')}

    # ------------------------------------------------------------------
    # Borrador de la IA en el chat
    # ------------------------------------------------------------------
    def _ai_pending_suggestions(self):
        self.ensure_one()
        return self.env['chatroom.ai.suggestion'].search([
            ('channel_id', '=', self.id), ('state', 'in', ('draft', 'approved')), ('quick_action_id', '=', False),
        ], order='create_date desc, id desc')

    def get_ai_pending_draft(self):
        """Lo que la IA propone responder: se escribe en el cuadro del chat."""
        self.ensure_one()
        suggestion = self._ai_pending_suggestions()[:1]
        if not suggestion or not (suggestion.suggested_text or '').strip():
            return False
        return {'id': suggestion.id, 'text': suggestion.suggested_text.strip(),
                'reason': suggestion.safety_reason or ''}

    def action_ai_discard_draft(self):
        self.ensure_one()
        self._ai_pending_suggestions().action_discard()
        return True

    def _ai_learn_from_human_reply(self, message):
        super()._ai_learn_from_human_reply(message)
        # La persona ya respondió: los borradores que quedaban no se deben enviar.
        leftovers = self._ai_pending_suggestions()
        if leftovers:
            leftovers.sudo().write({'state': 'rejected', 'rejection_reason': _('Respondió una persona.')})
