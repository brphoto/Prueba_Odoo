from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta

class PolizaPartner(models.Model):
    _inherit = 'poliza.partner'
    _description = 'Agregación de póliza de seguro para Vehicles'

    vehicle_id = fields.Many2one('polizas.vehicles', string="Vehículo", ondelete='cascade')  # corregido
    model = fields.Char("Modelo")
    year = fields.Char("Año")
    plate = fields.Char("Placa")
    brand= fields.Char("Marca")

    def action_renovar_poliza(self):
        for rec in self:
            #if rec.state != 'vencida':
            #    raise UserError("Solo se pueden renovar pólizas vencidas.")

            nueva_fecha_inicio = rec.fecha_fin + relativedelta(days=1)
            nueva_fecha_fin = nueva_fecha_inicio + relativedelta(months=12)

            nueva_poliza = self.create({
                'partner_id': rec.partner_id.id,
                'ramo_id': rec.ramo_id.id,
                'aseguradora_id': rec.aseguradora_id.id,
                'numero_poliza': f"{rec.numero_poliza}/R",
                'fecha_inicio': nueva_fecha_inicio,
                'fecha_fin': nueva_fecha_fin,
                'poliza_type': rec.poliza_type.id,
                'tipo_pago': rec.tipo_pago,
                'forma_pago': rec.forma_pago,
                'prima_neta': rec.prima_neta,
                'prima_total': rec.prima_total,
                'state': 'draft',
                'poliza_renovada_id': rec.id,
                'comision_broker': rec.comision_broker,
                'comision_executivo': rec.comision_executivo,
                'model': rec.model,
                'year': rec.year,
                'plate': rec.plate,
                'brand': rec.brand,
            })
            rec._copy_insurance_details_to(nueva_poliza)

            rec.write({'state': 'renovada'})

            rec.message_post(body=_("📄 La póliza ha sido renovada con la nueva póliza <a href='#' data-oe-model='poliza.partner' data-oe-id='%d'>%s</a>.") % (nueva_poliza.id, nueva_poliza.name))





class Vehicle(models.Model):
    _name='polizas.vehicles'
    _description='Vehículos'

    name=fields.Char("Nombre", required=True)
    brand_id = fields.Many2one('polizas.vehicles.brand', string="Marca", required=True)
    model_id = fields.Many2one('polizas.vehicles.model', string="Modelo", required=True)

class VehicleBrand(models.Model):
    _name='polizas.vehicles.brand'
    _description = 'Marca de Vehículo'
    name=fields.Char("Nombre", required=True)

class VehicleModel(models.Model):
    _name='polizas.vehicles.model'
    _description = 'Modelo de Vehículo'
    name=fields.Char("Nombre", required=True)
    

class PolizaType(models.Model):
    _inherit = 'poliza.type'
    _description = 'Tipo de Póliza'
    
    is_vehicle = fields.Boolean("Es vehículo", default=False)

