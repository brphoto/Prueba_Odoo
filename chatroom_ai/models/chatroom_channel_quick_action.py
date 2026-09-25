# -*- coding: utf-8 -*-
import json
import re

from odoo import _, fields, models
from odoo.exceptions import UserError

VALID_INTENTS = ('consulta', 'venta', 'soporte', 'queja', 'otro')


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    # ------------------------------------------------------------------
    # Contexto por acción
    # ------------------------------------------------------------------
    def _ai_sources(self):
        """Fuentes de contexto que pidió la acción en curso.

        Sin acción (flujos anteriores: guardia automática, agente, etc.) se
        usan todas, como siempre. Las extensiones que agregan contexto
        (memoria, conocimiento) consultan este diccionario antes de hacerlo.
        """
        return self.env.context.get('chatroom_ai_sources') or {}

    def _ai_history_limit(self):
        override = self.env.context.get('chatroom_ai_history')
        if override:
            return max(2, min(int(override), 30))
        return super()._ai_history_limit()

    def _ai_last_inbound_text(self):
        self.ensure_one()
        message = self.message_ids.filtered(
            lambda m: m.direction == 'inbound' and m._ai_text()).sorted('date')[-1:]
        return message._ai_text() if message else ''

    def _ai_quick_action_catalog(self):
        """Productos relacionados con lo que pregunta el cliente, con precio
        y disponibilidad leídos en este momento (nunca aprendidos)."""
        self.ensure_one()
        words = [w for w in re.findall(r'\w{4,}', self._ai_last_inbound_text().lower())][:8]
        rows, seen = [], set()
        for word in words:
            for row in self.search_products(word, self.id):
                if row['id'] in seen:
                    continue
                seen.add(row['id'])
                rows.append(row)
            if len(rows) >= 6:
                break
        if not rows:
            return ''
        lines = ['- %s | precio: %.2f %s | %s' % (
            row['name'], row['list_price'] or 0.0, row['currency_symbol'] or '', row['stock_label'])
            for row in rows[:6]]
        return 'Catálogo relacionado (datos vivos de Odoo):\n%s' % '\n'.join(lines)

    def _ai_quick_action_customer_history(self):
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        if not partner:
            return ''
        lines = []
        if 'sale.order' in self.env:
            orders = self.env['sale.order'].search([
                ('partner_id', 'child_of', partner.id)], order='date_order desc', limit=3)
            for order in orders:
                lines.append('- Pedido %s (%s): %.2f %s, estado %s' % (
                    order.name, fields.Date.to_string(order.date_order.date()) if order.date_order else '',
                    order.amount_total, order.currency_id.symbol or '',
                    dict(order._fields['state']._description_selection(self.env)).get(order.state, order.state)))
        if 'account.move' in self.env:
            invoices = self.env['account.move'].search([
                ('partner_id', 'child_of', partner.id), ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial')),
            ], order='invoice_date_due asc', limit=3)
            for invoice in invoices:
                lines.append('- Factura pendiente %s: %.2f %s, vence %s' % (
                    invoice.name, invoice.amount_residual, invoice.currency_id.symbol or '',
                    fields.Date.to_string(invoice.invoice_date_due) or '-'))
        if not lines:
            return ''
        return 'Historial comercial del cliente:\n%s' % '\n'.join(lines)

    def _ai_quick_action_messages(self, action, draft_text=''):
        self.ensure_one()
        system_parts = [action._render_instruction(self, draft_text)]
        if action.use_catalog:
            catalog = self._ai_quick_action_catalog()
            if catalog:
                system_parts.append(catalog)
        if action.use_customer_history:
            history = self._ai_quick_action_customer_history()
            if history:
                system_parts.append(history)
        channel = self.with_context(
            chatroom_ai_sources={'knowledge': action.use_knowledge, 'memory': action.use_memory},
            chatroom_ai_history=action.history_messages or False,
        )
        messages = channel._ai_build_conversation(extra_system='\n\n'.join(system_parts))
        if action.output_mode == 'rewrite':
            messages.append({'role': 'user', 'content': _(
                'Reescribe este borrador del agente siguiendo las instrucciones:\n%s') % draft_text})
        return messages

    # ------------------------------------------------------------------
    # API del panel y del compositor
    # ------------------------------------------------------------------
    def get_ai_quick_actions(self):
        self.ensure_one()
        return self.env['chatroom.ai.quick.action']._available_for(self)._to_ui()

    def action_ai_run_quick_action(self, action_id, draft_text=False, model_id=None):
        """Ejecuta una acción rápida y devuelve lo que la interfaz debe mostrar.

        :return: dict con ``mode`` y, según el modo, ``suggestion`` (borrador
            auditable), ``text`` (texto para el compositor), ``summary`` o
            ``intent``.
        """
        self.ensure_one()
        action = self.env['chatroom.ai.quick.action'].browse(int(action_id)).exists()
        if not action or not action._is_available_for(self):
            raise UserError(_('Esa acción de IA no está disponible en esta conversación.'))
        draft_text = (draft_text or '').strip()
        if action.output_mode == 'rewrite' and not draft_text:
            raise UserError(_('Escribe primero un borrador en el mensaje para que la IA lo mejore.'))
        if self.ai_paused and action.output_mode in ('reply', 'rewrite'):
            raise UserError(_(
                'La IA está pausada en esta conversación. Reactívala desde el control '
                'de la conversación después de revisar el caso.'))
        # Modos que no esperan texto de la IA (por ejemplo, crear una tarea
        # del agente) los resuelve su propio método.
        direct = getattr(self, '_ai_quick_action_run_%s' % action.output_mode, None)
        if direct:
            action.sudo().write({'use_count': action.use_count + 1, 'last_used': fields.Datetime.now()})
            return direct(action, draft_text)
        if not model_id and 'model_id' in action._fields and action.model_id:
            model_id = action.model_id.id
        task_type = 'classification' if action.output_mode == 'intent' else (
            'summary' if action.output_mode in ('summary', 'note') else 'reply')
        text = self._ai_chat_completion(
            self._ai_quick_action_messages(action, draft_text),
            task_type=task_type, model_id=model_id) or ''
        action.sudo().write({'use_count': action.use_count + 1, 'last_used': fields.Datetime.now()})
        return getattr(self, '_ai_quick_action_output_%s' % action.output_mode)(action, text.strip())

    def _ai_quick_action_output_reply(self, action, text):
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(self, text)
        suggestion.quick_action_id = action.id
        return {'mode': 'reply', 'suggestion': self._ai_suggestion_payload(suggestion)}

    def _ai_quick_action_output_rewrite(self, action, text):
        return {'mode': 'rewrite', 'text': text}

    def _ai_quick_action_output_note(self, action, text):
        self.action_post_internal_note('%s: %s' % (action.name, text))
        return {'mode': 'note', 'text': text}

    def _ai_quick_action_output_summary(self, action, text):
        self.ai_summary = text
        return {'mode': 'summary', 'summary': text}

    def _ai_quick_action_output_intent(self, action, text):
        intent = False
        try:
            intent = json.loads(text).get('intent')
        except (ValueError, AttributeError):
            match = re.search(r'\b(%s)\b' % '|'.join(VALID_INTENTS), text.lower())
            intent = match.group(1) if match else False
        valid = dict(self._fields['ai_intent'].selection)
        self.ai_intent = intent if intent in valid else 'otro'
        return {'mode': 'intent', 'intent': self.ai_intent}
