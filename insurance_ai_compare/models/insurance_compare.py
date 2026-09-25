# -*- coding: utf-8 -*-
import json
import logging
import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models, modules
from odoo.exceptions import UserError

from .insurance_template import normalize_text

_logger = logging.getLogger(__name__)

CONSENT_CODE = 'ASESORIA_IA'
# Límite de texto por documento que viaja a la IA (~15.000 tokens). Una
# cotización normal ocupa bastante menos; si un PDF trae anexos enormes se
# recorta y queda indicado en la oferta.
MAX_DOCUMENT_CHARS = 60000

COVERAGE_STATES = [
    ('yes', 'Incluida'),
    ('limited', 'Limitada'),
    ('no', 'No incluida'),
    ('unknown', 'Sin dato'),
]
COVERAGE_VALUE = {'yes': 1.0, 'limited': 0.5, 'no': 0.0, 'unknown': 0.0}
COVERAGE_ICON = {'yes': '✔', 'limited': '◐', 'no': '✘', 'unknown': '?'}


def to_number(value):
    """Convierte montos escritos de cualquier forma a float, o None.

    «$ 1.234,56», «1,234.56», «USD 850», 850 → número. Decide cuál es el
    separador decimal por su posición, como lo leería una persona.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r'[^0-9,.\-]', '', str(value))
    if not re.search(r'\d', text):
        return None
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')
    elif ',' in text:
        # Una sola coma con 1-2 decimales es decimal («850,50»); si no, miles («1,234»).
        head, _sep, tail = text.rpartition(',')
        if text.count(',') == 1 and len(tail) in (1, 2):
            text = '%s.%s' % (head, tail)
        else:
            text = text.replace(',', '')
    elif text.count('.') > 1:
        text = text.replace('.', '')
    elif '.' in text:
        # Un punto seguido de exactamente 3 dígitos es separador de miles
        # («1.234» en una prima): las primas no se expresan con 3 decimales.
        head, _sep, tail = text.partition('.')
        if len(tail) == 3 and head.lstrip('-') not in ('', '0'):
            text = head + tail
    try:
        return float(text)
    except ValueError:
        return None


def to_coverage_state(value):
    text = normalize_text(str(value or ''))
    if text in ('si', 'yes', 'incluida', 'incluido', 'true', 'cubre', 'amparado', 'x'):
        return 'yes'
    if text in ('limitada', 'limitado', 'parcial', 'limited', 'con limite', 'sublimite'):
        return 'limited'
    if text in ('no', 'excluida', 'excluido', 'false', 'no incluida', 'no cubre', 'no aplica'):
        return 'no'
    return 'unknown'


class InsuranceCompare(models.Model):
    _name = 'insurance.compare'
    _description = 'Comparativo de cotizaciones de seguros'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True,
                       default=lambda self: _('Nuevo'))
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    partner_id = fields.Many2one('res.partner', string='Cliente', required=True, tracking=True, index=True)
    template_id = fields.Many2one(
        'insurance.compare.template', string='Ramo / plantilla', required=True, tracking=True,
        default=lambda self: self.env['insurance.compare.template'].search([], limit=1))
    profile_id = fields.Many2one(
        'insurance.client.profile', string='Perfil del cliente',
        domain="[('partner_id', '=', partner_id), ('template_id', '=', template_id)]")
    profile_summary = fields.Text(related='profile_id.summary', string='Resumen del perfil')
    profile_missing = fields.Text(related='profile_id.missing_fields', string='Datos que faltan')
    priorities = fields.Text(
        string='Qué valora el cliente', tracking=True,
        help='Se usa en el análisis y en la recomendación. Si hay perfil, se toma de ahí.')
    lead_id = fields.Many2one('crm.lead', string='Oportunidad', index=True)
    channel_id = fields.Many2one('chatroom.channel', string='Conversación')
    advisor_id = fields.Many2one(
        'res.users', string='Asesor', default=lambda self: self.env.user, tracking=True)

    state = fields.Selection([
        ('draft', 'Preparación'),
        ('extracting', 'Leyendo cotizaciones'),
        ('review', 'Revisión'),
        ('analyzed', 'Analizado'),
        ('approved', 'Aprobado'),
        ('sent', 'Enviado al cliente'),
        ('won', 'Póliza emitida'),
        ('lost', 'Perdido'),
    ], string='Estado', default='draft', required=True, tracking=True, index=True)

    offer_ids = fields.One2many('insurance.compare.offer', 'compare_id', string='Cotizaciones')
    offer_count = fields.Integer(compute='_compute_counts')
    review_count = fields.Integer(compute='_compute_counts', string='Datos por revisar')
    pending_count = fields.Integer(compute='_compute_counts', string='En lectura')

    recommended_offer_id = fields.Many2one(
        'insurance.compare.offer', string='Opción recomendada', tracking=True,
        domain="[('compare_id', '=', id), ('disqualified', '=', False)]")
    ai_recommended_offer_id = fields.Many2one(
        'insurance.compare.offer', string='Recomendada por la IA', readonly=True)
    recommendation_reason = fields.Text(string='Por qué se recomienda')
    analysis_summary = fields.Text(string='Análisis general')
    client_explanation = fields.Text(
        string='Explicación para el cliente',
        help='Texto en lenguaje simple para enviar al cliente por WhatsApp o email.')
    negotiation_notes = fields.Text(
        string='Negociación (interno)',
        help='Qué pedirle a cada aseguradora para mejorar su oferta. No sale en el PDF del cliente.')
    analyzed_at = fields.Datetime(string='Analizado el', readonly=True)
    approved_by_id = fields.Many2one('res.users', string='Aprobado por', readonly=True, tracking=True)
    approved_at = fields.Datetime(string='Aprobado el', readonly=True)
    chosen_offer_id = fields.Many2one('insurance.compare.offer', string='Opción elegida', readonly=True)
    policy_id = fields.Many2one('poliza.partner', string='Póliza emitida', readonly=True)
    consent_ok = fields.Boolean(compute='_compute_consent_ok', string='Consentimiento LOPDP')
    matrix_html = fields.Html(compute='_compute_matrix_html', sanitize=False, string='Cuadro comparativo')
    offers_analysis_html = fields.Html(
        compute='_compute_offers_analysis_html', sanitize=False, string='Ventajas y desventajas')
    legal_note = fields.Text(related='template_id.legal_note')

    # ------------------------------------------------------------------
    # Creación y datos derivados
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('insurance.compare') or _('Nuevo')
        records = super().create(vals_list)
        for record in records:
            if not record.profile_id and record.partner_id and record.template_id:
                record.profile_id = self.env['insurance.client.profile'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('template_id', '=', record.template_id.id),
                ], limit=1)
            if not record.priorities and record.profile_id.priorities:
                record.priorities = record.profile_id.priorities
        return records

    @api.depends('offer_ids.state', 'offer_ids.review_count')
    def _compute_counts(self):
        for compare in self:
            compare.offer_count = len(compare.offer_ids)
            compare.review_count = sum(compare.offer_ids.mapped('review_count'))
            compare.pending_count = len(compare.offer_ids.filtered(
                lambda offer: offer.state in ('queued', 'processing')))

    @api.depends('partner_id')
    def _compute_consent_ok(self):
        for compare in self:
            compare.consent_ok = compare._has_consent()

    def _has_consent(self):
        self.ensure_one()
        return self._partner_has_consent(self.partner_id)

    @api.model
    def _partner_has_consent(self, partner):
        """Consentimiento LOPDP «Asesoría de seguros con IA» vigente.

        Se acepta el del contacto o el de su empresa. sudo solo para consultar:
        el asesor debe poder verificarlo aunque no pueda editar consentimientos.
        """
        required = self.env['ir.config_parameter'].sudo().get_param(
            'insurance_ai_compare.require_consent', 'True')
        if str(required).lower() in ('false', '0', 'no'):
            return True
        if not partner:
            return False
        consent = self.env['ec.data.consent'].sudo()
        return any(consent.has_active_consent(candidate.id, CONSENT_CODE)
                   for candidate in (partner | partner.commercial_partner_id))

    def _check_consent(self):
        for compare in self:
            if not compare._has_consent():
                raise UserError(_(
                    'El cliente %s no tiene registrado el consentimiento «Asesoría de seguros '
                    'con IA» (LOPDP). Regístralo antes de analizar sus datos con IA.')
                    % compare.partner_id.display_name)

    def _action_open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'insurance.compare',
            'res_id': self.id, 'view_mode': 'form', 'views': [(False, 'form')],
            'target': 'current',
        }

    def action_register_consent(self):
        """Abre el alta del consentimiento ya completado para este cliente."""
        self.ensure_one()
        consent_type = self.env.ref('insurance_ai_compare.consent_type_asesoria_ia')
        return {
            'type': 'ir.actions.act_window', 'name': _('Registrar consentimiento'),
            'res_model': 'ec.data.consent', 'view_mode': 'form', 'target': 'new',
            'views': [(False, 'form')],
            'context': {'default_partner_id': self.partner_id.id,
                        'default_consent_type_id': consent_type.id},
        }

    # ------------------------------------------------------------------
    # Lectura de cotizaciones (en segundo plano)
    # ------------------------------------------------------------------
    def action_extract(self):
        """Encola la lectura de las cotizaciones y la lanza en segundo plano."""
        for compare in self:
            compare._check_consent()
            offers = compare.offer_ids.filtered(lambda offer: offer.state in ('draft', 'error'))
            if not offers:
                raise UserError(_('Sube al menos una cotización en PDF que no se haya leído todavía.'))
            missing_file = offers.filtered(lambda offer: not offer.document)
            if missing_file:
                raise UserError(_('Falta el PDF de: %s') % ', '.join(
                    missing_file.mapped(lambda offer: offer.insurer_id.name or _('cotización sin aseguradora'))))
            offers.write({'state': 'queued', 'error_message': False})
            compare.state = 'extracting'
            compare.message_post(body=_('Se encolaron %s cotización(es) para leerlas con IA.') % len(offers))
        cron = self.env.ref('insurance_ai_compare.ir_cron_insurance_extract', raise_if_not_found=False)
        if cron:
            cron._trigger()
        return True

    def action_refresh(self):
        return True

    @api.model
    def _cron_process_offers(self, limit=5):
        """Lee cotizaciones en cola. Cada una se confirma por separado: si una
        falla, las demás siguen y el error queda en la oferta."""
        offers = self.env['insurance.compare.offer'].search(
            [('state', '=', 'queued')], order='id', limit=limit)
        for offer in offers:
            offer._process_extraction()
            if not modules.module.current_test:
                self.env.cr.commit()
        remaining = self.env['insurance.compare.offer'].search_count([('state', '=', 'queued')])
        if remaining:
            cron = self.env.ref('insurance_ai_compare.ir_cron_insurance_extract', raise_if_not_found=False)
            if cron:
                cron._trigger()
        return len(offers)

    def _after_extraction(self):
        for compare in self:
            if compare.state != 'extracting' or compare.pending_count:
                continue
            if compare.offer_ids.filtered(lambda offer: offer.state == 'extracted'):
                compare.state = 'review'
                compare.action_compute_scores()
                compare.message_post(body=_(
                    'Cotizaciones leídas. Revisa los datos marcados antes de analizar.'))
            else:
                compare.state = 'draft'

    # ------------------------------------------------------------------
    # Puntaje: lo calcula Odoo, no la IA
    # ------------------------------------------------------------------
    def action_compute_scores(self):
        for compare in self:
            compare._compute_scores()
        return True

    def _compute_scores(self):
        self.ensure_one()
        template = self.template_id
        offers = self.offer_ids.filtered(lambda offer: offer.state in ('extracted', 'manual'))
        required = template.coverage_ids.filtered('required')
        for offer in offers:
            reasons = []
            if not offer.premium_total:
                reasons.append(_('sin prima total'))
            states = offer._coverage_states()
            for coverage in required:
                if states.get(coverage.id, 'unknown') not in ('yes', 'limited'):
                    reasons.append(_('no incluye %s') % coverage.name)
            offer.disqualified = bool(reasons)
            offer.disqualified_reason = ', '.join(reasons)
        eligible = offers.filtered(lambda offer: not offer.disqualified)

        prices = [offer.premium_total for offer in eligible if offer.premium_total]
        deductibles = [offer.deductible_amount for offer in eligible if offer.deductible_known]
        services = [len(offer._assistance_list()) for offer in eligible]
        max_services = max(services) if services else 0
        coverage_weight = sum(template.coverage_ids.mapped('weight'))

        for offer in offers:
            price = (100.0 * min(prices) / offer.premium_total) if prices and offer.premium_total else 0.0
            if not offer.deductible_known:
                deductible = 50.0
            elif len(set(deductibles)) <= 1:
                deductible = 100.0
            else:
                low, high = min(deductibles), max(deductibles)
                deductible = 100.0 * (high - offer.deductible_amount) / (high - low)
            states = offer._coverage_states()
            coverage = (100.0 * sum(
                item.weight * COVERAGE_VALUE[states.get(item.id, 'unknown')]
                for item in template.coverage_ids) / coverage_weight) if coverage_weight else 100.0
            assistances = len(offer._assistance_list())
            service = 50.0 * (assistances / max_services if max_services else 0.5)
            service += 50.0 * ((offer.insurer_id.service_score or 0.0) / 5.0)
            weights = (template.weight_price, template.weight_deductible,
                       template.weight_coverage, template.weight_service)
            total = (price * weights[0] + deductible * weights[1]
                     + coverage * weights[2] + service * weights[3]) / (sum(weights) or 1.0)
            offer.write({
                'score_price': round(price, 1), 'score_deductible': round(deductible, 1),
                'score_coverage': round(coverage, 1), 'score_service': round(service, 1),
                'score_total': round(total, 1),
            })
        ranked = eligible.sorted(lambda offer: (-offer.score_total, offer.premium_total or 0.0))
        for position, offer in enumerate(ranked, start=1):
            offer.rank = position
        (offers - eligible).write({'rank': 0})
        if not self.recommended_offer_id or self.recommended_offer_id.disqualified:
            self.recommended_offer_id = ranked[:1]
        return ranked

    # ------------------------------------------------------------------
    # Análisis de la IA
    # ------------------------------------------------------------------
    def action_analyze(self):
        for compare in self:
            compare._check_consent()
            offers = compare.offer_ids.filtered(lambda offer: offer.state in ('extracted', 'manual'))
            if len(offers) < 2:
                raise UserError(_('Se necesitan al menos dos cotizaciones leídas para comparar.'))
            compare._compute_scores()
            data = compare._ai_analysis(offers)
            compare._apply_analysis(data, offers)
        return True

    def _analysis_payload(self, offers):
        self.ensure_one()
        rows = []
        for offer in offers.sorted(lambda offer: (offer.disqualified, offer.rank or 999)):
            states = offer._coverage_states()
            rows.append({
                'aseguradora': offer.insurer_id.name,
                'prima_total': offer.premium_total,
                'prima_neta': offer.premium_net,
                'forma_pago': offer.payment_terms or None,
                'suma_asegurada': offer.sum_insured or None,
                'deducible': offer.deductible_text or None,
                'coberturas': {
                    coverage.name: dict(COVERAGE_STATES)[states.get(coverage.id, 'unknown')]
                    for coverage in self.template_id.coverage_ids},
                'otras_coberturas': offer.line_ids.filtered(lambda line: not line.coverage_id).mapped('name'),
                'asistencias': offer._assistance_list(),
                'exclusiones': [item for item in (offer.exclusions or '').splitlines() if item.strip()],
                'calificacion_servicio': offer.insurer_id.service_score,
                'puntaje_total': offer.score_total,
                'puesto': offer.rank or None,
                'descartada': offer.disqualified_reason or None,
            })
        return rows

    def _ai_analysis(self, offers):
        self.ensure_one()
        service = self.env['chatroom.ai.service']
        profile = self.profile_id._as_prompt() if self.profile_id else _('Sin perfil registrado.')
        priorities = self.priorities or _('No indicadas.')
        system = '\n\n'.join([
            _('Eres un analista de seguros de un broker. Comparas cotizaciones de distintas '
              'aseguradoras para el mismo cliente y explicas con claridad, sin tecnicismos '
              'innecesarios. Responde en español.'),
            _('El puntaje y el ranking los calculó el sistema con los pesos del broker. Puedes '
              'recomendar otra opción solo si el perfil o las prioridades del cliente lo '
              'justifican, y en ese caso explica por qué. No inventes datos que no estén en '
              'las cotizaciones.'),
            _('Devuelve ÚNICAMENTE un objeto JSON con esta forma: {"recomendacion": '
              '{"aseguradora": "nombre exacto", "motivo": "texto"}, "resumen": "texto", '
              '"ofertas": [{"aseguradora": "nombre exacto", "ventajas": ["..."], '
              '"desventajas": ["..."], "mejorar": ["qué debería ofrecer para ser la mejor '
              'opción"]}], "explicacion_cliente": "texto breve para el cliente"}'),
        ])
        user = '\n\n'.join([
            _('Ramo: %s') % self.template_id.name,
            _('Perfil del cliente:\n%s') % profile,
            _('Prioridades del cliente: %s') % priorities,
            _('Cotizaciones (datos revisados por el asesor):\n%s') % json.dumps(
                self._analysis_payload(offers), ensure_ascii=False, indent=1),
        ])
        return service.complete_json(
            [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            required_keys=('recomendacion', 'ofertas'), timeout=180)

    def _apply_analysis(self, data, offers):
        self.ensure_one()

        def find(name):
            wanted = normalize_text(name)
            if not wanted:
                return offers.browse()
            for offer in offers:
                insurer = normalize_text(offer.insurer_id.name)
                if insurer and (insurer == wanted or insurer in wanted or wanted in insurer):
                    return offer
            return offers.browse()

        def as_lines(value):
            if isinstance(value, str):
                value = [value]
            return '\n'.join('• %s' % str(item).strip() for item in (value or []) if str(item).strip())

        negotiation = []
        for item in data.get('ofertas') or []:
            if not isinstance(item, dict):
                continue
            offer = find(item.get('aseguradora'))
            if not offer:
                continue
            offer.write({
                'advantages': as_lines(item.get('ventajas')),
                'disadvantages': as_lines(item.get('desventajas')),
                'improvements': as_lines(item.get('mejorar')),
            })
            if offer.improvements:
                negotiation.append('%s:\n%s' % (offer.insurer_id.name, offer.improvements))
        recommendation = data.get('recomendacion') or {}
        if not isinstance(recommendation, dict):
            recommendation = {'aseguradora': str(recommendation)}
        chosen = find(recommendation.get('aseguradora'))
        values = {
            'ai_recommended_offer_id': chosen.id or False,
            'recommendation_reason': str(recommendation.get('motivo') or '').strip(),
            'analysis_summary': str(data.get('resumen') or '').strip(),
            'client_explanation': str(data.get('explicacion_cliente') or '').strip(),
            'negotiation_notes': '\n\n'.join(negotiation),
            'analyzed_at': fields.Datetime.now(),
            'state': 'analyzed',
        }
        # La IA propone; si su opción está descartada por reglas del broker se
        # mantiene la del ranking y queda anotado.
        if chosen and not chosen.disqualified:
            values['recommended_offer_id'] = chosen.id
        elif chosen:
            values['recommendation_reason'] = _(
                'La IA sugirió %(ia)s, pero está descartada (%(reason)s). Se mantiene la '
                'opción mejor puntuada.\n\n%(motivo)s') % {
                    'ia': chosen.insurer_id.name, 'reason': chosen.disqualified_reason,
                    'motivo': values['recommendation_reason']}
        self.write(values)
        self.message_post(body=_('Análisis de IA listo. Revísalo y apruébalo antes de enviarlo.'))

    # ------------------------------------------------------------------
    # Aprobación, PDF, envío y cierre
    # ------------------------------------------------------------------
    def action_approve(self):
        for compare in self:
            if compare.state not in ('review', 'analyzed'):
                raise UserError(_('Solo se aprueba un comparativo revisado o analizado.'))
            if not compare.recommended_offer_id:
                raise UserError(_('Elige la opción recomendada antes de aprobar.'))
            if compare.recommended_offer_id.disqualified:
                raise UserError(_('La opción recomendada está descartada: %s') %
                                compare.recommended_offer_id.disqualified_reason)
            compare.write({'state': 'approved', 'approved_by_id': self.env.user.id,
                           'approved_at': fields.Datetime.now()})
            compare.message_post(body=_('Comparativo aprobado por %s.') % self.env.user.name)
        return True

    def action_back_to_review(self):
        self.write({'state': 'review', 'approved_by_id': False, 'approved_at': False})
        return True

    def action_mark_lost(self):
        self.write({'state': 'lost'})
        return True

    def _check_approved(self):
        for compare in self:
            if compare.state not in ('approved', 'sent', 'won'):
                raise UserError(_('Aprueba el comparativo antes de enviarlo al cliente.'))

    def action_print_client(self):
        return self.env.ref('insurance_ai_compare.action_report_insurance_compare_client').report_action(self)

    def action_print_internal(self):
        return self.env.ref('insurance_ai_compare.action_report_insurance_compare_internal').report_action(self)

    def _get_channel(self):
        self.ensure_one()
        if self.channel_id:
            return self.channel_id
        channel_id = self.env['chatroom.channel'].action_start_conversation(self.partner_id.id)
        self.channel_id = channel_id
        return self.channel_id

    def action_send_whatsapp(self):
        self.ensure_one()
        self._check_approved()
        channel = self._get_channel()
        channel._send_report_as_message(
            'insurance_ai_compare.action_report_insurance_compare_client', self.id,
            '%s.pdf' % (self.name or 'comparativo').replace('/', '-'))
        if self.client_explanation:
            try:
                channel.action_send_text(self.client_explanation)
            except UserError as exc:
                # Fuera de la ventana de 24 h WhatsApp solo admite plantillas:
                # el PDF ya salió o falló con su propio mensaje.
                _logger.info('No se envió la explicación del comparativo: %s', exc)
        if self.state == 'approved':
            self.state = 'sent'
        self.message_post(body=_('Comparativo enviado por WhatsApp.'))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Enviado'), 'type': 'success',
            'message': _('El comparativo se envió por WhatsApp a %s.') % self.partner_id.name}}

    def action_send_email(self):
        self.ensure_one()
        self._check_approved()
        template = self.env.ref('insurance_ai_compare.mail_template_insurance_compare')
        return {
            'type': 'ir.actions.act_window', 'res_model': 'mail.compose.message',
            'view_mode': 'form', 'views': [(False, 'form')], 'target': 'new',
            'context': {
                'default_model': 'insurance.compare', 'default_res_ids': self.ids,
                'default_template_id': template.id, 'default_composition_mode': 'comment',
                'mark_compare_as_sent': True,
            },
        }

    def _message_post_after_hook(self, message, msg_vals):
        # Al enviar por email desde el asistente, el comparativo pasa a «Enviado».
        if self.env.context.get('mark_compare_as_sent'):
            self.filtered(lambda compare: compare.state == 'approved').write({'state': 'sent'})
        return super()._message_post_after_hook(message, msg_vals)

    def action_create_policy(self):
        self.ensure_one()
        self._check_approved()
        return {
            'type': 'ir.actions.act_window', 'name': _('Emitir póliza'),
            'res_model': 'insurance.policy.wizard', 'view_mode': 'form', 'target': 'new',
            'views': [(False, 'form')],
            'context': {'default_compare_id': self.id,
                        'default_offer_id': self.recommended_offer_id.id},
        }

    # ------------------------------------------------------------------
    # Cuadro comparativo en pantalla
    # ------------------------------------------------------------------
    @api.depends('offer_ids.line_ids.state', 'offer_ids.score_total', 'offer_ids.rank',
                 'offer_ids.premium_total', 'recommended_offer_id')
    def _compute_matrix_html(self):
        for compare in self:
            compare.matrix_html = compare._render_matrix()

    @api.depends('offer_ids.advantages', 'offer_ids.disadvantages', 'offer_ids.rank')
    def _compute_offers_analysis_html(self):
        for compare in self:
            blocks = []
            for offer in compare._matrix_offers().filtered(
                    lambda item: item.advantages or item.disadvantages):
                blocks.append(Markup(
                    '<div class="o_insurance_offer_card"><h5>%s%s</h5>'
                    '<div class="o_insurance_pros"><strong>%s</strong><pre>%s</pre></div>'
                    '<div class="o_insurance_cons"><strong>%s</strong><pre>%s</pre></div></div>') % (
                    offer.insurer_id.name or '',
                    Markup(' <span class="badge text-bg-primary">#%s</span>') % offer.rank if offer.rank else '',
                    _('Ventajas'), offer.advantages or '—',
                    _('Desventajas'), offer.disadvantages or '—'))
            compare.offers_analysis_html = Markup('<div class="o_insurance_offer_cards">%s</div>') %                 Markup('').join(blocks) if blocks else False

    def _matrix_offers(self):
        self.ensure_one()
        return self.offer_ids.filtered(
            lambda offer: offer.state in ('extracted', 'manual')
        ).sorted(lambda offer: (offer.disqualified, offer.rank or 999))

    def _render_matrix(self):
        self.ensure_one()
        offers = self._matrix_offers()
        if not offers:
            return Markup('<p class="text-muted">%s</p>') % _(
                'El cuadro aparece cuando se leen las cotizaciones.')
        currency = self.currency_id

        def money(value):
            return escape(currency.format(value)) if value else Markup('<span class="text-muted">—</span>')

        # _() fuera del generador: el generador no tiene self para saber el idioma.
        discarded = Markup(' <span class="badge text-bg-danger">%s</span>') % _('Descartada')
        head = Markup('').join(
            Markup('<th class="%s">%s%s</th>') % (
                'o_insurance_best' if offer == self.recommended_offer_id else '',
                offer.insurer_id.name or '',
                Markup(' <span class="badge text-bg-primary">#%s</span>') % offer.rank if offer.rank
                else discarded)
            for offer in offers)
        rows = [
            (_('Prima total'), [money(offer.premium_total) for offer in offers]),
            (_('Prima neta'), [money(offer.premium_net) for offer in offers]),
            (_('Forma de pago'), [escape(offer.payment_terms or '—') for offer in offers]),
            (_('Suma asegurada'), [money(offer.sum_insured) for offer in offers]),
            (_('Deducible'), [escape(offer.deductible_text or '—') for offer in offers]),
        ]
        for coverage in self.template_id.coverage_ids:
            cells = []
            for offer in offers:
                line = offer.line_ids.filtered(lambda item: item.coverage_id == coverage)[:1]
                state = line.state if line else 'unknown'
                detail = line.limit_text or '' if line else ''
                cells.append(Markup('<span class="o_insurance_cov o_insurance_cov_%s" title="%s">%s</span> %s') % (
                    state, dict(COVERAGE_STATES)[state], COVERAGE_ICON[state], detail))
            label = coverage.name + (' *' if coverage.required else '')
            rows.append((label, cells))
        rows.append((_('Asistencias'), [str(len(offer._assistance_list())) for offer in offers]))
        rows.append((_('Puntaje (0-100)'), [
            Markup('<strong>%s</strong>') % ('%.1f' % offer.score_total) for offer in offers]))
        body = Markup('').join(
            Markup('<tr><th>%s</th>%s</tr>') % (label, Markup('').join(
                Markup('<td class="%s">%s</td>') % (
                    'o_insurance_best' if offer == self.recommended_offer_id else '', cell)
                for offer, cell in zip(offers, cells)))
            for label, cells in rows)
        return Markup(
            '<div class="o_insurance_matrix_wrap"><table class="table table-sm o_insurance_matrix">'
            '<thead><tr><th></th>%s</tr></thead><tbody>%s</tbody></table>'
            '<small class="text-muted">%s</small></div>') % (
            head, body, _('✔ incluida · ◐ limitada · ✘ no incluida · ? sin dato · * obligatoria'))


class InsuranceCompareOffer(models.Model):
    _name = 'insurance.compare.offer'
    _description = 'Cotización de una aseguradora'
    _order = 'compare_id, rank, id'
    _rec_name = 'insurer_id'

    compare_id = fields.Many2one('insurance.compare', string='Comparativo', required=True,
                                 ondelete='cascade', index=True)
    company_id = fields.Many2one(related='compare_id.company_id', store=True)
    currency_id = fields.Many2one(related='compare_id.currency_id')
    compare_template_id = fields.Many2one(related='compare_id.template_id')
    insurer_id = fields.Many2one('polizas.aseguradoras', string='Aseguradora', required=True)
    document = fields.Binary(string='Cotización (PDF)', attachment=True)
    document_name = fields.Char(string='Archivo')
    state = fields.Selection([
        ('draft', 'Por leer'),
        ('queued', 'En cola'),
        ('processing', 'Leyendo'),
        ('extracted', 'Leída'),
        ('manual', 'Cargada a mano'),
        ('error', 'Error'),
    ], string='Estado', default='draft', required=True, index=True)
    error_message = fields.Text(string='Error', readonly=True)
    page_count = fields.Integer(string='Páginas', readonly=True)
    truncated = fields.Boolean(string='Documento recortado', readonly=True)
    extracted_json = fields.Text(string='Datos extraídos (JSON)', readonly=True)
    confidence = fields.Float(string='Confianza', readonly=True)

    premium_net = fields.Monetary(string='Prima neta')
    premium_total = fields.Monetary(string='Prima total')
    payment_terms = fields.Char(string='Forma de pago')
    installments = fields.Integer(string='Cuotas')
    valid_until = fields.Date(string='Válida hasta')
    sum_insured = fields.Monetary(string='Suma asegurada')
    deductible_text = fields.Char(string='Deducible')
    deductible_amount = fields.Monetary(string='Deducible (monto)')
    deductible_known = fields.Boolean(string='Deducible conocido')
    assistances = fields.Text(string='Asistencias', help='Una por línea.')
    exclusions = fields.Text(string='Exclusiones relevantes', help='Una por línea.')

    line_ids = fields.One2many('insurance.compare.line', 'offer_id', string='Coberturas')
    review_count = fields.Integer(compute='_compute_review_count', string='Por revisar', store=True)

    score_price = fields.Float(string='Puntaje precio', readonly=True)
    score_deductible = fields.Float(string='Puntaje deducible', readonly=True)
    score_coverage = fields.Float(string='Puntaje coberturas', readonly=True)
    score_service = fields.Float(string='Puntaje servicio', readonly=True)
    score_total = fields.Float(string='Puntaje', readonly=True)
    rank = fields.Integer(string='Puesto', readonly=True)
    disqualified = fields.Boolean(string='Descartada', readonly=True)
    disqualified_reason = fields.Char(string='Motivo del descarte', readonly=True)

    advantages = fields.Text(string='Ventajas')
    disadvantages = fields.Text(string='Desventajas')
    improvements = fields.Text(string='Qué debería mejorar', help='Para negociar con la aseguradora.')

    @api.depends('line_ids.needs_review', 'line_ids.reviewed')
    def _compute_review_count(self):
        for offer in self:
            offer.review_count = len(offer.line_ids.filtered(
                lambda line: line.needs_review and not line.reviewed))

    @api.onchange('document_name')
    def _onchange_document_name(self):
        if self.document_name and not self.insurer_id:
            guess = normalize_text(self.document_name)
            for insurer in self.env['polizas.aseguradoras'].search([]):
                name = normalize_text(insurer.name)
                if name and name in guess:
                    self.insurer_id = insurer
                    break

    def _coverage_states(self):
        """{cobertura del catálogo: estado} con el mejor estado si se repite."""
        self.ensure_one()
        order = {'yes': 3, 'limited': 2, 'no': 1, 'unknown': 0}
        states = {}
        for line in self.line_ids.filtered('coverage_id'):
            current = states.get(line.coverage_id.id, 'unknown')
            if order[line.state] > order[current]:
                states[line.coverage_id.id] = line.state
        return states

    def _assistance_list(self):
        self.ensure_one()
        return [item.strip(' •-') for item in (self.assistances or '').splitlines() if item.strip(' •-')]

    def action_mark_manual(self):
        """Carga manual: el asesor completa los datos sin IA."""
        self.write({'state': 'manual', 'error_message': False})
        self.compare_id.filtered(lambda compare: compare.state in ('draft', 'extracting')).write(
            {'state': 'review'})
        return True

    def action_retry(self):
        self.write({'state': 'draft', 'error_message': False})
        return self.compare_id.action_extract()

    def action_open(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'insurance.compare.offer',
                'res_id': self.id, 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'new'}

    # ------------------------------------------------------------------
    # Extracción
    # ------------------------------------------------------------------
    def _process_extraction(self):
        self.ensure_one()
        self.write({'state': 'processing'})
        try:
            with self.env.cr.savepoint():
                data = self._extract_with_ai()
                self._apply_extraction(data)
        except Exception as exc:  # noqa: BLE001 - el error queda en la oferta
            _logger.warning('No se pudo leer la cotización %s: %s', self.id, exc)
            message = exc.args[0] if isinstance(exc, UserError) and exc.args else str(exc)
            self.write({'state': 'error', 'error_message': message})
        self.compare_id._after_extraction()

    def _extraction_messages(self):
        self.ensure_one()
        service = self.env['chatroom.ai.service']
        pages = service.extract_pdf_pages(self.document)
        if not any(page.strip() for page in pages):
            raise UserError(_(
                'El PDF no tiene texto legible (parece escaneado) y el OCR no está disponible. '
                'Pide la cotización en PDF digital o carga los datos a mano.'))
        text = service.wrap_document(self.document_name or self.insurer_id.name, pages)
        truncated = len(text) > MAX_DOCUMENT_CHARS
        if truncated:
            text = text[:MAX_DOCUMENT_CHARS] + '\n[... documento recortado ...]\n</documento>'
        self.write({'page_count': len(pages), 'truncated': truncated})
        template = self.compare_id.template_id
        catalog = '\n'.join('- %s%s' % (coverage.name, (' (también: %s)' % ', '.join(
            item.strip() for item in re.split(r'[\n,;]+', coverage.synonyms or '') if item.strip()))
            if coverage.synonyms else '') for coverage in template.coverage_ids)
        system = '\n\n'.join(filter(None, [
            _('Eres un analista de seguros. Extraes datos de la cotización de una aseguradora '
              'de forma exacta, sin interpretar ni completar lo que no está escrito.'),
            service.document_guard(),
            _('Ramo: %s.') % template.name,
            _('Coberturas del catálogo (usa el nombre exacto del catálogo en "catalogo" cuando '
              'corresponda; si una cobertura no está en el catálogo, deja "catalogo" en null):\n%s')
            % catalog if catalog else '',
            template.extraction_instructions or '',
            (_('Cómo presenta sus cotizaciones %s: %s') % (
                self.insurer_id.name, self.insurer_id.ai_extraction_hint))
            if self.insurer_id.ai_extraction_hint else '',
            _('Devuelve ÚNICAMENTE un objeto JSON con esta forma (null si el dato no aparece): '
              '{"prima_neta": número, "prima_total": número, "forma_pago": "texto", '
              '"cuotas": entero, "vigencia_hasta": "AAAA-MM-DD", "suma_asegurada": número, '
              '"deducible": {"texto": "como aparece", "monto": número}, '
              '"coberturas": [{"nombre": "como aparece", "catalogo": "nombre del catálogo o '
              'null", "incluida": "si|limitada|no", "limite": "texto del límite o null", '
              '"deducible": "texto o null", "pagina": entero, "cita": "frase corta del '
              'documento", "confianza": 0.0-1.0}], "asistencias": ["..."], '
              '"exclusiones": ["..."], "confianza": 0.0-1.0}'),
        ]))
        return [{'role': 'system', 'content': system},
                {'role': 'user', 'content': _('Cotización de %s:\n%s') % (self.insurer_id.name, text)}]

    def _extract_with_ai(self):
        self.ensure_one()
        return self.env['chatroom.ai.service'].complete_json(
            self._extraction_messages(), required_keys=('coberturas', 'prima_total'), timeout=180)

    def _apply_extraction(self, data):
        self.ensure_one()
        template = self.compare_id.template_id
        deductible = data.get('deductible') or data.get('deducible') or {}
        if not isinstance(deductible, dict):
            deductible = {'texto': str(deductible), 'monto': deductible}
        deductible_amount = to_number(deductible.get('monto'))
        valid_until = data.get('vigencia_hasta')
        try:
            valid_until = fields.Date.to_date(valid_until) if valid_until else False
        except (TypeError, ValueError):
            valid_until = False
        lines = []
        for item in data.get('coberturas') or []:
            if not isinstance(item, dict) or not str(item.get('nombre') or '').strip():
                continue
            name = str(item.get('nombre')).strip()
            coverage = template._match_coverage(item.get('catalogo'), name)
            try:
                confidence = max(0.0, min(1.0, float(item.get('confianza'))))
            except (TypeError, ValueError):
                confidence = 0.5
            try:
                page = int(item.get('pagina') or 0)
            except (TypeError, ValueError):
                page = 0
            lines.append((0, 0, {
                'name': name[:250],
                'coverage_id': coverage.id or False,
                'state': to_coverage_state(item.get('incluida')),
                'limit_text': str(item.get('limite') or '')[:250] or False,
                'deductible_text': str(item.get('deducible') or '')[:250] or False,
                'source_page': page,
                'source_text': str(item.get('cita') or '')[:500] or False,
                'confidence': confidence,
            }))

        def as_text(value):
            if isinstance(value, str):
                value = [value]
            return '\n'.join(str(item).strip() for item in (value or []) if str(item).strip())

        try:
            overall = max(0.0, min(1.0, float(data.get('confianza'))))
        except (TypeError, ValueError):
            overall = 0.0
        installments = to_number(data.get('cuotas'))
        self.line_ids.unlink()
        self.write({
            'state': 'extracted',
            'error_message': False,
            'extracted_json': json.dumps(data, ensure_ascii=False, indent=1),
            'confidence': overall,
            'premium_net': to_number(data.get('prima_neta')) or 0.0,
            'premium_total': to_number(data.get('prima_total')) or 0.0,
            'payment_terms': str(data.get('forma_pago') or '')[:250] or False,
            'installments': int(installments) if installments else 0,
            'valid_until': valid_until,
            'sum_insured': to_number(data.get('suma_asegurada')) or 0.0,
            'deductible_text': str(deductible.get('texto') or '')[:250] or False,
            'deductible_amount': deductible_amount or 0.0,
            'deductible_known': deductible_amount is not None,
            'assistances': as_text(data.get('asistencias')),
            'exclusions': as_text(data.get('exclusiones')),
            'line_ids': lines,
        })


class InsuranceCompareLine(models.Model):
    _name = 'insurance.compare.line'
    _description = 'Cobertura en una cotización'
    _order = 'offer_id, sequence, id'

    offer_id = fields.Many2one('insurance.compare.offer', string='Cotización', required=True,
                               ondelete='cascade', index=True)
    compare_id = fields.Many2one(related='offer_id.compare_id', store=True, index=True)
    sequence = fields.Integer(related='coverage_id.sequence', store=True)
    name = fields.Char(string='Como aparece en la cotización', required=True)
    coverage_id = fields.Many2one(
        'insurance.coverage', string='Cobertura del catálogo',
        domain="[('template_id', '=', parent.compare_template_id)]")
    state = fields.Selection(COVERAGE_STATES, string='Estado', default='unknown', required=True)
    limit_text = fields.Char(string='Límite')
    deductible_text = fields.Char(string='Deducible')
    source_page = fields.Integer(string='Página')
    source_text = fields.Char(string='Cita del documento')
    confidence = fields.Float(string='Confianza', default=1.0)
    needs_review = fields.Boolean(compute='_compute_needs_review', store=True, string='Revisar')
    reviewed = fields.Boolean(string='Revisada')

    @api.depends('confidence', 'coverage_id', 'state')
    def _compute_needs_review(self):
        for line in self:
            line.needs_review = (line.confidence < 0.7 or not line.coverage_id
                                 or line.state == 'unknown')

    def write(self, vals):
        # Una corrección humana cuenta como revisión.
        if {'coverage_id', 'state', 'limit_text', 'deductible_text'} & set(vals) \
                and 'reviewed' not in vals and not self.env.context.get('insurance_ai_writing'):
            vals = dict(vals, reviewed=True)
        return super().write(vals)
