from odoo import models, fields

class RecordatorioTempolate(models.Model):
    _name = 'polizas.recordatorio.template'
    _description = 'Plantilla de Mensaje para Seguimiento CRM'

    name = fields.Char("Nombre")
    forma_pago = fields.Selection([
        ('3', '3 meses'),
        ('6', '6 meses'),
        ('9', '9 meses'),
        ('8', '8 meses'),
        ('10', '10 meses'),
    ], string="Forma de Pago")
    message = fields.Text("Mensaje")

    is_welcome = fields.Boolean("Es Bienvenida", default=False, help="Indica si es un mensaje de bienvenida para nuevos clientes.")
    is_birthday = fields.Boolean("Es Cumpleaños", default=False, help="Indica si es un mensaje de cumpleaños para clientes.")
    is_close = fields.Boolean("Es Final de Vigencia", default=False, help="Indica si es un mensaje de final de vigencia para clientes.")
    is_monthly = fields.Boolean("Es Recordatorio Mes Previo de Cierre", default=False, help="Indica si es un mensaje de recordatorio mensual para clientes antes del cierre de la póliza.")
    is_installment = fields.Boolean("¿Es mensaje de cuotas generadas?") 
    is_renewal = fields.Boolean("¿Es mensaje de renovación?")
    #stage_id = fields.Many2one("crm.stage", string="Fase CRM")