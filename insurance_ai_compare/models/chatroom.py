# -*- coding: utf-8 -*-
"""Asesoría de seguros desde el chat: acciones de IA /perfil, /faltantes,
/asesorar, /explicar y /comparativo."""
from odoo import _, fields, models
from odoo.exceptions import UserError


class ChatroomAiQuickAction(models.Model):
    _inherit = 'chatroom.ai.quick.action'

    output_mode = fields.Selection(selection_add=[
        ('insurance_profile', 'Seguros: guardar el perfil del cliente'),
        ('insurance_compare', 'Seguros: crear comparativo'),
    ], ondelete={'insurance_profile': 'set default', 'insurance_compare': 'set default'})
    use_insurance = fields.Boolean(
        string='Perfil y comparativos de seguros',
        help='Agrega el perfil de riesgo del cliente, los datos que faltan y el último '
             'comparativo. Exige el consentimiento LOPDP del cliente.')
    insurance_template_id = fields.Many2one(
        'insurance.compare.template', string='Ramo',
        help='Vacío: el ramo del último perfil o comparativo del cliente.')


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    # ------------------------------------------------------------------
    # Contexto de seguros
    # ------------------------------------------------------------------
    def _insurance_template(self, action=None):
        self.ensure_one()
        if action and action.insurance_template_id:
            return action.insurance_template_id
        partner = self.partner_id
        if partner:
            profile = self.env['insurance.client.profile'].search(
                [('partner_id', '=', partner.id)], limit=1)
            if profile:
                return profile.template_id
            compare = self.env['insurance.compare'].search([('partner_id', '=', partner.id)], limit=1)
            if compare:
                return compare.template_id
        return self.env['insurance.compare.template'].search([], limit=1)

    def _insurance_check_consent(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('La conversación no tiene un contacto asociado.'))
        if not self.env['insurance.compare']._partner_has_consent(self.partner_id):
            raise UserError(_(
                'Falta el consentimiento «Asesoría de seguros con IA» (LOPDP) de %s. '
                'Regístralo en su ficha antes de analizar sus datos con IA.') % self.partner_id.name)

    def _insurance_context(self, template):
        """Perfil, checklist y último comparativo en texto para la IA."""
        self.ensure_one()
        profile = self.env['insurance.client.profile'].search([
            ('partner_id', '=', self.partner_id.id), ('template_id', '=', template.id)], limit=1)
        fields_list = template._profile_field_list()
        parts = [_('Ramo: %s.') % template.name]
        if fields_list:
            parts.append(_('Datos que se necesitan para cotizar:\n%s') % '\n'.join(
                '- %s' % label for _key, label in fields_list))
        if profile:
            parts.append(_('Perfil registrado del cliente:\n%s') % profile._as_prompt())
            if profile.missing_fields:
                parts.append(_('Datos que todavía faltan:\n%s') % profile.missing_fields)
        else:
            parts.append(_('Aún no hay perfil registrado: todos los datos están pendientes.'))
        compare = self.env['insurance.compare'].search([
            ('partner_id', '=', self.partner_id.id), ('template_id', '=', template.id),
            ('state', 'in', ('analyzed', 'approved', 'sent', 'won'))], limit=1)
        if compare:
            best = compare.recommended_offer_id
            summary = [_('Último comparativo %s:') % compare.name]
            for offer in compare._matrix_offers():
                summary.append(_('- %(insurer)s: prima %(premium).2f, puntaje %(score).1f%(extra)s') % {
                    'insurer': offer.insurer_id.name, 'premium': offer.premium_total,
                    'score': offer.score_total,
                    'extra': (_(' (descartada: %s)') % offer.disqualified_reason)
                    if offer.disqualified else ''})
            if best:
                summary.append(_('Recomendada: %s. %s') % (
                    best.insurer_id.name, compare.recommendation_reason or ''))
            if compare.client_explanation:
                summary.append(_('Explicación preparada: %s') % compare.client_explanation)
            parts.append('\n'.join(summary))
        return '\n\n'.join(parts)

    def _ai_quick_action_messages(self, action, draft_text=''):
        messages = super()._ai_quick_action_messages(action, draft_text)
        if action.use_insurance:
            self._insurance_check_consent()
            template = self._insurance_template(action)
            if template:
                messages[0]['content'] += '\n\n' + _(
                    'Contexto de seguros del cliente:\n%s') % self._insurance_context(template)
        return messages

    def _insurance_transcript(self, limit=40):
        self.ensure_one()
        messages = self.message_ids.filtered(lambda message: message.body).sorted('date')[-limit:]
        customer, advisor = _('Cliente'), _('Asesor')
        return '\n'.join('%s: %s' % (
            customer if message.direction == 'inbound' else advisor, message.body)
            for message in messages)

    # ------------------------------------------------------------------
    # /perfil: la IA completa el perfil de riesgo desde la conversación
    # ------------------------------------------------------------------
    def _ai_quick_action_run_insurance_profile(self, action, draft_text=''):
        self.ensure_one()
        self._insurance_check_consent()
        template = self._insurance_template(action)
        if not template:
            raise UserError(_('Crea primero una plantilla de comparativo (ramo).'))
        fields_list = template._profile_field_list()
        if not fields_list:
            raise UserError(_('La plantilla %s no tiene definidos los datos del cliente.') % template.name)
        service = self.env['chatroom.ai.service']
        system = '\n\n'.join([
            _('Eres asistente de un broker de seguros. Lees una conversación de WhatsApp y '
              'extraes SOLO los datos listados que el cliente haya dicho explícitamente. No '
              'deduzcas ni inventes: si un dato no aparece, usa null.'),
            _('Datos a buscar (clave: descripción):\n%s') % '\n'.join(
                '%s: %s' % item for item in fields_list),
            _('Devuelve ÚNICAMENTE un objeto JSON: {"datos": {clave: valor o null}, '
              '"prioridades": "qué valora el cliente o null", "resumen": "2-3 líneas"}'),
        ])
        data = service.complete_json([
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': _('Conversación:\n%s') % self._insurance_transcript()},
        ], required_keys=('datos',), task_type='classification', timeout=90)
        values = data.get('datos') if isinstance(data.get('datos'), dict) else {}
        allowed = {key for key, _label in fields_list}
        values = {key: value for key, value in values.items() if key in allowed}
        Profile = self.env['insurance.client.profile']
        profile = Profile.search([('partner_id', '=', self.partner_id.id),
                                  ('template_id', '=', template.id)], limit=1)
        if not profile:
            profile = Profile.create({'partner_id': self.partner_id.id,
                                      'template_id': template.id, 'channel_id': self.id})
        profile._merge_data(values)
        updates = {'channel_id': self.id}
        if data.get('resumen'):
            updates['summary'] = str(data['resumen']).strip()
        if data.get('prioridades'):
            updates['priorities'] = str(data['prioridades']).strip()
        profile.write(updates)
        found = [label for key, label in fields_list if values.get(key) not in (None, '', [], {})]
        note = _('Perfil de %(ramo)s actualizado (%(pct)d%% completo).\nDatos encontrados: %(found)s') % {
            'ramo': template.name, 'pct': profile.completion,
            'found': ', '.join(found) or _('ninguno nuevo')}
        if profile.missing_fields:
            note += '\n' + _('Faltan: %s') % ', '.join(profile.missing_fields.splitlines())
        self.action_post_internal_note('%s: %s' % (action.name, note))
        return {'mode': 'note', 'text': note, 'profile_id': profile.id}

    # ------------------------------------------------------------------
    # /comparativo: crea el comparativo con el perfil ya cargado
    # ------------------------------------------------------------------
    def _ai_quick_action_run_insurance_compare(self, action, draft_text=''):
        self.ensure_one()
        self._insurance_check_consent()
        template = self._insurance_template(action)
        if not template:
            raise UserError(_('Crea primero una plantilla de comparativo (ramo).'))
        profile = self.env['insurance.client.profile'].search([
            ('partner_id', '=', self.partner_id.id), ('template_id', '=', template.id)], limit=1)
        compare = self.env['insurance.compare'].create({
            'partner_id': self.partner_id.id,
            'template_id': template.id,
            'profile_id': profile.id or False,
            'channel_id': self.id,
        })
        return {'mode': 'action', 'action': compare._action_open_form(), 'compare_id': compare.id}
