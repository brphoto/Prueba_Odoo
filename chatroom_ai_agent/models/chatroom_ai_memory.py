# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class ChatroomAiMemory(models.Model):
    _name = 'chatroom.ai.memory'
    _description = 'Memoria empresarial del agente IA'
    _order = 'importance desc, last_used desc, id desc'

    name = fields.Char(string='Título', required=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', index=True, ondelete='cascade')
    channel_id = fields.Many2one('chatroom.channel', string='Conversación', index=True, ondelete='cascade')
    memory_type = fields.Selection([
        ('fact', 'Dato'), ('preference', 'Preferencia'),
        ('commitment', 'Compromiso'), ('outcome', 'Resultado'),
    ], string='Tipo', required=True, default='fact', index=True)
    content = fields.Text(string='Contenido', required=True)
    source = fields.Selection([
        ('conversation', 'Conversación'), ('sales', 'Ventas'),
        ('payment', 'Pagos'), ('manual', 'Manual'), ('agent', 'Agente IA'),
    ], string='Origen', required=True, default='agent')
    importance = fields.Selection([
        ('1', 'Baja'), ('2', 'Normal'), ('3', 'Alta'),
    ], string='Importancia', default='2', required=True)
    confidence = fields.Float(string='Confianza', default=1.0, help='Nivel de confianza del dato entre 0 y 1.')
    expires_at = fields.Datetime(string='Vigente hasta')
    source_ref = fields.Char(string='Referencia de origen', copy=False)
    active = fields.Boolean(default=True)
    last_used = fields.Datetime(string='Último uso', default=fields.Datetime.now)
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company, index=True)

    @api.model
    def remember(self, content, partner=False, channel=False, memory_type='fact', source='agent', importance='2'):
        content = (content or '').strip()
        if not content:
            return self.browse()
        domain = [('content', '=', content), ('active', '=', True)]
        if partner:
            domain.append(('partner_id', '=', partner.id if hasattr(partner, 'id') else partner))
        if channel:
            domain.append(('channel_id', '=', channel.id if hasattr(channel, 'id') else channel))
        memory = self.search(domain, limit=1)
        vals = {
            'name': content[:80], 'content': content, 'memory_type': memory_type,
            'source': source, 'importance': importance, 'last_used': fields.Datetime.now(),
            'partner_id': partner.id if hasattr(partner, 'id') else partner,
            'channel_id': channel.id if hasattr(channel, 'id') else channel,
        }
        if memory:
            memory.write(vals)
            return memory
        return self.create(vals)

    @api.model
    def get_context(self, partner=False, channel=False, limit=8):
        """Devuelve memoria vigente y relevante para inyectarla en el prompt."""
        partner_id = partner.id if hasattr(partner, 'id') else partner
        channel_id = channel.id if hasattr(channel, 'id') else channel
        domain = [('active', '=', True), '|', ('expires_at', '=', False), ('expires_at', '>=', fields.Datetime.now())]
        if partner_id or channel_id:
            domain += ['|', ('partner_id', '=', partner_id or 0), ('channel_id', '=', channel_id or 0)]
        records = self.sudo().search(domain, order='importance desc, last_used desc, id desc', limit=limit)
        # No escribimos en cada consulta IA: actualizar la fecha como máximo
        # una vez por hora evita escrituras innecesarias y bloqueos de fila.
        if records:
            cutoff = fields.Datetime.now() - timedelta(hours=1)
            records.filtered(lambda record: not record.last_used or record.last_used < cutoff).write({
                'last_used': fields.Datetime.now()
            })
        return '\n'.join('- %s' % record.content for record in records)
