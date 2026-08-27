from odoo import fields, models


class MarketingSocialAgentMessage(models.Model):
    _name = 'marketing.social.agent.message'
    _description = 'Mensaje del agente de marketing'
    _order = 'sequence, id'

    chat_id = fields.Many2one(
        'marketing.social.agent.chat', string='Sesión', required=True,
        ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    speaker = fields.Selection([
        ('user', 'Marketing'), ('agent', 'Agente'),
    ], string='Interlocutor', required=True)
    body = fields.Text(string='Mensaje', required=True)
    message_date = fields.Datetime(string='Fecha', default=fields.Datetime.now, required=True)
