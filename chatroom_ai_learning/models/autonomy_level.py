# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .ai_evaluation import RATED_VERDICTS
from .learning_utils import CATEGORIES


def learning_param(env, key, default):
    value = env['ir.config_parameter'].sudo().get_param('chatroom_ai_learning.%s' % key)
    if value in (None, False, ''):
        return default
    if isinstance(default, bool):
        return str(value).strip().lower() in ('1', 'true', 'yes', 'on')
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


class ChatroomAiAutonomyLevel(models.Model):
    """Qué puede responder la IA sola, por tipo de conversación.

    Cada tipo empieza supervisado y gana autonomía con datos: suficientes
    evaluaciones y un acierto alto sin ninguna respuesta insegura. La pierde
    sola si baja la calidad o alguien marca una respuesta como no segura.
    """
    _name = 'chatroom.ai.autonomy.level'
    _description = 'Nivel de autonomía de la IA'
    _inherit = ['mail.thread']
    _order = 'category, line_id'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', string='Empresa', required=True,
                                 default=lambda self: self.env.company, index=True)
    category = fields.Selection(CATEGORIES, string='Tipo de conversación', required=True, index=True)
    line_id = fields.Many2one('chatroom.whatsapp.number', string='Línea', ondelete='cascade',
                              help='Vacío: aplica a todas las líneas sin un nivel propio.')
    state = fields.Selection([
        ('supervised', 'Supervisado'),
        ('automatic', 'Automático'),
        ('blocked', 'Siempre una persona'),
    ], string='Nivel', default='supervised', required=True, tracking=True, index=True)
    locked = fields.Boolean(
        string='Fijado a mano', tracking=True,
        help='El nivel no cambia solo con las métricas; lo decide un administrador.')
    sample_count = fields.Integer(string='Evaluaciones', readonly=True)
    success_rate = fields.Float(string='Acierto (%)', readonly=True)
    unsafe_count = fields.Integer(string='No seguras', readonly=True)
    escalated_count = fields.Integer(string='Derivadas', readonly=True)
    progress = fields.Float(string='Avance hacia automático (%)', readonly=True)
    status_note = fields.Char(string='Situación', readonly=True)
    last_change = fields.Datetime(string='Último cambio', readonly=True)

    _category_line_uniq = models.UniqueIndex(
        '(company_id, category, COALESCE(line_id, 0))',
        'Ya existe un nivel para ese tipo de conversación y línea.',
    )

    @api.depends('category', 'line_id')
    def _compute_name(self):
        labels = dict(CATEGORIES)
        for level in self:
            level.name = '%s%s' % (labels.get(level.category, ''),
                                   ' · %s' % level.line_id.name if level.line_id else '')

    # ------------------------------------------------------------------
    @api.model
    def _for(self, category, line=None, company=None):
        category = category or 'otro'
        company = company or self.env.company
        base = [('company_id', '=', company.id), ('category', '=', category)]
        level = self.search(base + [('line_id', '=', line.id)], limit=1) if line else self.browse()
        level = level or self.search(base + [('line_id', '=', False)], limit=1)
        if not level:
            level = self.create({'category': category, 'company_id': company.id})
        return level

    @api.model
    def _thresholds(self):
        env = self.env
        return {
            'window': max(learning_param(env, 'window', 50), 5),
            'min_samples': max(learning_param(env, 'min_samples', 30), 1),
            'promote': learning_param(env, 'promote_rate', 90.0),
            'demote': learning_param(env, 'demote_rate', 80.0),
        }

    def _metrics(self):
        self.ensure_one()
        thresholds = self._thresholds()
        domain = [('company_id', '=', self.company_id.id), ('category', '=', self.category),
                  ('state', '=', 'done')]
        if self.line_id:
            domain.append(('line_id', '=', self.line_id.id))
        Evaluation = self.env['chatroom.ai.evaluation'].sudo()
        rated = Evaluation.search(domain + [('verdict', 'in', RATED_VERDICTS)],
                                  order='create_date desc, id desc', limit=thresholds['window'])
        good = len(rated.filtered(lambda item: item.verdict == 'good'))
        return {
            'samples': len(rated),
            'rate': 100.0 * good / len(rated) if rated else 0.0,
            'unsafe': len(rated.filtered(lambda item: item.verdict == 'unsafe')),
            'escalated': Evaluation.search_count(domain + [('verdict', '=', 'escalated')]),
        }

    def _apply_rules(self):
        """Recalcula métricas y sube o baja de nivel según los umbrales."""
        thresholds = self._thresholds()
        for level in self:
            metrics = level._metrics()
            progress = min(100.0, 100.0 * metrics['samples'] / thresholds['min_samples'])
            values = {'sample_count': metrics['samples'], 'success_rate': round(metrics['rate'], 1),
                      'unsafe_count': metrics['unsafe'], 'escalated_count': metrics['escalated'],
                      'progress': round(progress, 1)}
            new_state, reason = level.state, False
            if not level.locked and level.state != 'blocked':
                if level.state == 'supervised':
                    if (metrics['samples'] >= thresholds['min_samples']
                            and metrics['rate'] >= thresholds['promote'] and not metrics['unsafe']):
                        new_state = 'automatic'
                        reason = _('Ganó autonomía: %(rate).0f%% de acierto en %(n)s evaluaciones sin '
                                   'respuestas inseguras.') % {'rate': metrics['rate'], 'n': metrics['samples']}
                elif metrics['unsafe']:
                    new_state = 'supervised'
                    reason = _('Vuelve a supervisado: hay %s respuesta(s) marcadas como no seguras.') % metrics['unsafe']
                elif metrics['samples'] >= thresholds['min_samples'] // 2 and metrics['rate'] < thresholds['demote']:
                    new_state = 'supervised'
                    reason = _('Vuelve a supervisado: el acierto bajó a %.0f%%.') % metrics['rate']
            values['status_note'] = level._status_note(new_state, metrics, thresholds)
            if new_state != level.state:
                values.update(state=new_state, last_change=fields.Datetime.now())
            level.write(values)
            if reason:
                level.message_post(body=reason)
                level._notify_managers(reason)
        return True

    def _status_note(self, state, metrics, thresholds):
        if self.locked:
            return _('Fijado a mano por un administrador.')
        if state == 'blocked':
            return _('Siempre lo atiende una persona.')
        if state == 'automatic':
            return _('Responde sola: %.0f%% de acierto.') % metrics['rate']
        missing = thresholds['min_samples'] - metrics['samples']
        if missing > 0:
            return _('Faltan %s evaluaciones para decidir.') % missing
        if metrics['unsafe']:
            return _('Tiene respuestas no seguras recientes.')
        return _('Acierto %(rate).0f%%: necesita %(need).0f%%.') % {
            'rate': metrics['rate'], 'need': thresholds['promote']}

    def _notify_managers(self, message):
        if 'chatroom.notification' not in self.env:
            return
        group = self.env.ref('chatroom_whatsapp.group_chatroom_manager', raise_if_not_found=False)
        for user in (group.user_ids if group else self.env['res.users']):
            self.env['chatroom.notification'].sudo().create_deduplicated({
                'name': _('Autonomía de la IA: %s') % self.name,
                'message': message,
                'notification_type': 'ai',
                'priority': '1',
                'user_id': user.id,
                'res_model': self._name,
                'res_id': self.id,
                'dedupe_key': 'ai-level:%s:%s:%s' % (self.id, self.state, user.id),
            })

    def allows_automatic(self):
        self.ensure_one()
        return self.state == 'automatic' and not learning_param(self.env, 'autonomy_frozen', False)

    def supervision_reason(self):
        self.ensure_one()
        if learning_param(self.env, 'autonomy_frozen', False):
            return _('La autonomía está congelada porque las pruebas de regresión no pasaron.')
        if self.state == 'blocked':
            return _('Los casos de tipo «%s» siempre los atiende una persona.') % self.name
        return _('Tipo «%(name)s» en modo supervisado: %(note)s') % {
            'name': self.name, 'note': self.status_note or _('aún sin datos suficientes')}

    # Acciones del administrador ----------------------------------------
    def _set_state(self, state, locked):
        self.write({'state': state, 'locked': locked, 'last_change': fields.Datetime.now()})
        for level in self:
            level.message_post(body=_('Nivel cambiado a mano a «%s».') % dict(
                self._fields['state'].selection)[state])
        return True

    def action_set_automatic(self):
        return self._set_state('automatic', True)

    def action_set_supervised(self):
        return self._set_state('supervised', True)

    def action_set_blocked(self):
        return self._set_state('blocked', True)

    def action_unlock(self):
        self.write({'locked': False})
        return self._apply_rules()

    def action_recompute(self):
        return self._apply_rules()

    @api.model
    def _cron_update_levels(self):
        self.search([])._apply_rules()
        return True
