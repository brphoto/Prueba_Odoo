import json

from odoo import _, fields, models
from odoo.exceptions import UserError


class MarketingSocialAgentChat(models.Model):
    _inherit = 'marketing.social.agent.chat'

    analysis_mode = fields.Selection([
        ('local', 'Análisis local (sin tokens)'),
        ('provider', 'Proveedor IA configurado'),
    ], string='Modo de análisis', default='local', required=True, tracking=True,
        help='El modo local responde con las métricas guardadas. El proveedor IA interpreta el contexto y registra su consumo.')
    provider_model_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo IA',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
        help='Selecciona un modelo sincronizado; no es necesario escribir el identificador manualmente.')
    ai_model_used = fields.Char(string='Modelo utilizado', readonly=True)
    ai_input_tokens = fields.Integer(string='Tokens de entrada', readonly=True)
    ai_output_tokens = fields.Integer(string='Tokens de salida', readonly=True)
    ai_vehicle_count = fields.Integer(string='Vehículos consultados', readonly=True)
    ai_run_at = fields.Datetime(string='Última consulta IA', readonly=True)
    ai_error = fields.Text(string='Diagnóstico IA', readonly=True)

    def _ai_context_rows(self):
        rows = self._rows()
        context = []
        for publication, metric in rows[:40]:
            context.append({
                'id': publication.id,
                'titulo': publication.name,
                'red': publication.platform,
                'formato': publication.content_type,
                'fecha': fields.Datetime.to_string(publication.published_at),
                'alcance': metric.reach,
                'impresiones': metric.impressions,
                'reproducciones': metric.views,
                'me_gusta': metric.likes,
                'comentarios': metric.comments,
                'compartidos': metric.shares,
                'guardados': metric.saves,
                'interacciones': metric.total_interactions,
                'engagement': metric.engagement_rate,
                'calidad': metric.metric_status,
                'origen': metric.source,
                'detalle_proveedor': metric.provider_error or '',
            })
        return rows, context

    def _ai_vehicle_context(self):
        """Incluye el catálogo externo solo cuando su módulo está instalado."""
        if 'marketing.vehicle.listing' not in self.env:
            return []
        listings = self.env['marketing.vehicle.listing'].sudo().search([
            ('company_id', '=', self.company_id.id), ('active', '=', True),
        ], order='status, write_date desc, id desc', limit=40)
        return [{
            'id': listing.external_id,
            'vehiculo': listing.name,
            'marca': listing.brand or '',
            'modelo': listing.model or '',
            'version': listing.version or '',
            'año': listing.year,
            'kilometraje': listing.mileage,
            'precio': listing.price,
            'moneda': listing.currency or '',
            'ubicacion': listing.location or '',
            'estado': listing.status,
            'enlace': listing.url or '',
        } for listing in listings]

    def _ai_channel(self):
        Channel = self.env['chatroom.channel']
        channel = Channel.search([('company_id', '=', self.company_id.id)], limit=1)
        if channel:
            return channel
        # El método del motor solo necesita la compañía para aplicar límites,
        # credenciales y registrar el consumo. No se crea una conversación falsa.
        return Channel.new({'company_id': self.company_id.id})

    def _provider_answer(self, question):
        rows, context = self._ai_context_rows()
        vehicles = self._ai_vehicle_context()
        self.source_publication_ids = [(6, 0, [publication.id for publication, _metric in rows])]
        if not context and not vehicles:
            return _('No hay publicaciones con métricas en el período seleccionado. Sincroniza Meta o carga datos demo antes de consultar la IA.'), rows
        system = _(
            'Eres un analista de marketing. Responde en español claro y profesional. '
            'Usa exclusivamente el JSON entregado. No inventes métricas. Si una métrica '
            'tiene calidad «unavailable», dilo explícitamente y explica que no equivale '
            'a cero. Entrega una respuesta breve, una lectura ejecutiva y una acción recomendada. '
            'No envíes mensajes ni modifiques redes sociales.'
        )
        prompt = json.dumps({
            'pregunta': question,
            'filtro_red': self._platform_text(),
            'periodo_dias': self.period_days,
            'publicaciones': context,
            'vehiculos_catalogo': vehicles,
        }, ensure_ascii=False)
        channel = self._ai_channel()
        answer = channel._ai_chat_completion([
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': prompt},
        ], task_type='summary', model_id=self.provider_model_id.id if self.provider_model_id else None)
        events = self.env['chatroom.ai.usage.event'].sudo().search([
            ('company_id', '=', self.company_id.id),
        ], order='request_date desc, id desc', limit=1)
        if events:
            self.ai_model_used = events.model
            self.ai_input_tokens = events.input_tokens
            self.ai_output_tokens = events.output_tokens
        return answer, rows, len(vehicles)

    def action_generate_ai_summary(self):
        self.ensure_one()
        self.write({
            'draft_message': _('Genera un resumen ejecutivo del período: rendimiento por red, contenido destacado, calidad de métricas, riesgos y tres acciones recomendadas.'),
            'analysis_mode': 'provider',
        })
        return self.action_send_message()

    def action_send_message(self):
        self.ensure_one()
        if self.analysis_mode != 'provider':
            return super().action_send_message()
        question = (self.draft_message or '').strip()
        if not question:
            raise UserError(_('Escribe una pregunta antes de consultar la IA.'))
        next_sequence = max(self.chat_message_ids.mapped('sequence') or [0]) + 1
        self.env['marketing.social.agent.message'].create({
            'chat_id': self.id, 'sequence': next_sequence,
            'speaker': 'user', 'body': question,
        })
        try:
            provider_result = self._provider_answer(question)
            answer, rows = provider_result[:2]
            vehicle_count = provider_result[2] if len(provider_result) > 2 else 0
            source_summary = _('Respuesta IA calculada con %s publicación(es).') % len(rows)
            if rows:
                source_summary += ' ' + _('Fuentes: %s.') % ', '.join(
                    [publication.name for publication, _metric in rows[:5]])
            if vehicle_count:
                source_summary += ' ' + _('Catálogo: %s vehículo(s).') % vehicle_count
            self.env['marketing.social.agent.message'].create({
                'chat_id': self.id, 'sequence': next_sequence + 1,
                'speaker': 'agent', 'body': answer,
            })
            self.write({
                'draft_message': False, 'answer': answer,
                'source_summary': source_summary, 'state': 'answered',
                'ai_run_at': fields.Datetime.now(), 'ai_error': False,
                'ai_vehicle_count': vehicle_count,
            })
        except Exception as exc:
            self.write({
                'state': 'error', 'answer': False, 'ai_error': str(exc),
                'ai_run_at': fields.Datetime.now(),
            })
            raise UserError(_('No se pudo consultar la IA: %s') % exc) from exc
        return {
            'type': 'ir.actions.act_window', 'name': _('Agente de marketing'),
            'res_model': self._name, 'view_mode': 'form', 'res_id': self.id,
            'target': 'current',
        }
