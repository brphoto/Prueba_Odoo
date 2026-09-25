from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta

import logging
import random

_logger = logging.getLogger(__name__)

class PolizaPartner(models.Model):
    _name = 'poliza.partner'
    _description = 'Póliza de Seguro para Partner'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Nombre de la Póliza",
        compute="_compute_name",
        inverse="_inverse_name",
        store=True,
        help="Nombre de la póliza, se genera automáticamente a partir del número de póliza y el nombre del cliente."
    )

    @api.depends('numero_poliza', 'partner_id')
    def _compute_name(self):
        for rec in self:
            if rec.numero_poliza and rec.partner_id:
                rec.name = f"{rec.numero_poliza} - {rec.partner_id.name}"
            else:
                rec.name = "Póliza sin número o cliente"

    def _inverse_name(self):
        pass

    partner_id = fields.Many2one('res.partner', string="Cliente", required=True, ondelete='cascade')
    ramo_id = fields.Many2one('polizas.ramos', string="Ejecutivo", required=True)
    aseguradora_id = fields.Many2one('polizas.aseguradoras', string="Aseguradora", required=True)
    numero_poliza = fields.Char("Número de Póliza", required=True)
    fecha_inicio = fields.Date("Fecha Inicio Vigencia", required=True)
    fecha_fin = fields.Date("Fecha Fin Vigencia", compute="_compute_fecha_fin", inverse="_inverse_fecha", store=True)
    cuotas_enviadas = fields.Integer("Cuotas Enviadas", default=0)
    last_reminder_date = fields.Date("Último recordatorio enviado")
    poliza_type = fields.Many2one('poliza.type', string="Tipo de Poliza", required=True)
    prima_neta = fields.Float("Prima Neta")
    prima_total = fields.Float("Prima Total")
    tipo_pago = fields.Selection([
        ('contado', 'Contado'),
        ('cuotas', 'Cuotas'),
    ], string="Tipo de Pago", required=True)

    forma_pago = fields.Selection([
        ('3', '3 meses'),
        ('6', '6 meses'),
        ('8', '8 meses'),
        ('9', '9 meses'),
        ('10', '10 meses'),
    ], string="Forma de Pago")

    actividad_actual = fields.Char("Actividad del cliente (texto libre)")
    client_activity = fields.Many2one('res.partner.activity', string="Actividad del cliente")
    state = fields.Selection([
    ('draft', 'Borrador'),
    ('vigente', 'Vigente'),
    ('vencida', 'Vencida'),
    ('no_renovada', 'No Renovada'),
    ('renovada', 'Renovada'),  # ✅ nuevo estado
    ], string="Estado", default='draft')

    poliza_renovada_id = fields.Many2one('poliza.partner', string="Póliza Renovada")

    files_ids = fields.Many2many('ir.attachment', string="Archivos Adjuntos")
    file = fields.Binary("Archivo Adjunto")

    cuota_ids = fields.One2many('poliza.partner.cuota', 'poliza_id', string="Tabla de Cuotas")
    comision_broker = fields.Float(" %Comisión del Broker", help="Porcentaje de comisión del broker sobre la prima total")
    comision_broker_monto = fields.Float("Monto de Comisión del Broker", compute="_compute_comisiones", store=True)

    comision_executivo = fields.Float(" %Comisión del Ejecutivo", help="Porcentaje de comisión del ejecutivo sobre la prima total")
    comision_executivo_monto = fields.Float("Monto de Comisión del Ejecutivo", compute="_compute_comisiones", store=True)

    comision_cxc_id = fields.Many2one('comision.cxc', string="Comisión CXC", help="Referencia a la liquidación de comisiones CXC asociada a esta póliza")
    comision_cxp_id = fields.Many2one('comision.cxp', string="Comisión CXP", help="Referencia a la liquidación de comisiones CXP asociada a esta póliza")

    prima_neta = fields.Float("Prima Neta", help="Monto base sobre el cual se calculan las comisiones")

    partner_id = fields.Many2one('res.partner', string="Cliente")
    number_polizas = fields.Integer("Número Total de Pólizas", compute="_compute_number_polizas", store=True, help="Número total de pólizas registradas para este cliente")

    ramos_id = fields.Many2one('poliza.ramo', string="Ramo", help="Ramo de la póliza")
    comercial_id= fields.Many2one('res.users', string="Comercial", help="Usuario responsable de la póliza", compute="_compute_comercial_id", store=True,inverse="_inverse_comercial_id")

    @api.depends('partner_id')
    def _compute_comercial_id(self):
        for record in self:
            record.comercial_id = record.partner_id.user_id or self.env.user or False
    def _inverse_comercial_id(self):
        for record in self:
            record.comercial_id = record.comercial_id 

    def action_renovar_poliza(self):
        for rec in self:
            # if rec.state != 'vencida':
            #     raise UserError("Solo se pueden renovar pólizas vencidas.")

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
            })
            rec._copy_insurance_details_to(nueva_poliza)

            rec.write({'state': 'renovada'})

            rec.message_post(body=_("📄 La póliza ha sido renovada con la nueva póliza <a href='#' data-oe-model='poliza.partner' data-oe-id='%d'>%s</a>.") % (nueva_poliza.id, nueva_poliza.name))

    @api.depends('partner_id')
    def _compute_number_polizas(self):
        for rec in self:
            if rec.partner_id:
                polizas = self.search([('partner_id', '=', rec.partner_id.id)])
                rec.number_polizas = len(polizas)
            else:
                rec.number_polizas = 0

    @api.depends('prima_neta', 'comision_broker', 'comision_executivo')
    def _compute_comisiones(self):
        for rec in self:
            rec.comision_broker_monto = round(
                rec.prima_neta * (rec.comision_broker / 100), 2
            ) if rec.prima_neta and rec.comision_broker else 0.0

            rec.comision_executivo_monto = round(
                rec.prima_neta * (rec.comision_executivo / 100), 2
            ) if rec.prima_neta and rec.comision_executivo else 0.0

    def action_generar_cuotas(self):
        for rec in self:
            if rec.tipo_pago == 'cuotas' and rec.forma_pago and rec.fecha_inicio and rec.prima_total:
                rec.cuota_ids.unlink()
                cuotas = int(rec.forma_pago)
                monto = round(rec.prima_total / cuotas, 2)
                cuotas_creadas = []
                for i in range(cuotas):
                    fecha_pago = rec.fecha_inicio + relativedelta(days=i * 30)
                    cuota = self.env['poliza.partner.cuota'].create({
                        'poliza_id': rec.id,
                        'numero': i + 1,
                        'fecha_pago': fecha_pago,
                        'monto': monto,
                        'pagado': False,
                    })
                    cuotas_creadas.append(cuota)

                rec.message_post(
                    body=_("Se generó la tabla de cuotas de la póliza."),
                    subtype_xmlid="mail.mt_note",
                )

    @api.depends('fecha_inicio')
    def _compute_fecha_fin(self):
        for rec in self:
            rec.fecha_fin = rec.fecha_inicio + relativedelta(months=12) if rec.fecha_inicio else False

    def _inverse_fecha(self):
        pass

    def approve_poliza(self):
        for record in self:
            record.write({'state': 'vigente'})

            plantilla = self.env['polizas.recordatorio.template'].search([
                ('is_welcome', '=', True)
            ], limit=1)

            if not plantilla:
                continue

            mensaje = (plantilla.message or '').format(
                nombre=record.partner_id.name or '',
                numero_poliza=record.numero_poliza or '',
                #cuota_actual=cuota_actual,
                #total_cuotas=total_cuotas,
                tipo=record.poliza_type.name or '',
                ejecutivo=record.ramo_id.partner_id.name or '',
                ramo=record.ramo_id.name or '',
                comercial=record.comercial_id.name or '',
                fecha_inicio=record.fecha_inicio or '',
                fecha_fin=record.fecha_fin or '',
                aseguradora= record.aseguradora_id.name or '',
            )

            # Posteamos el mensaje en el chatter como nota
            record.message_post(
                body=mensaje,
                subject="Bienvenida - Póliza registrada",
                partner_ids=[record.partner_id.id],
                attachment_ids=[(4, adj.id) for adj in record.files_ids],
            )

    def cancel_poliza(self):
        self.write({'state': 'vencida'})

    def no_renovada_poliza(self):
        self.write({'state': 'no_renovada'})

    def set_draft(self):
        self.write({'state': 'draft'})

    @api.model
    def _send_followup_messages_polizas(self):
        today = fields.Date.today()
        polizas = self.search([
            ('tipo_pago', '=', 'cuotas'),
            ('forma_pago', '!=', False),
            ('fecha_inicio', '!=', False),
            ('state', '=', 'vigente'),
        ])

        frecuencia_map = {'3': 30, '6': 30, '9': 30, '10': 30,'8': 30}  # Mapeo de frecuencia de pago a días

        for poliza in polizas:
            if poliza.last_reminder_date == today:
                continue  # ya se envió hoy

            frecuencia_dias = frecuencia_map.get(poliza.forma_pago)
            total_cuotas = int(poliza.forma_pago or 0)
            if not frecuencia_dias or not total_cuotas:
                continue

            dias_transcurridos = (today - poliza.fecha_inicio).days
            if dias_transcurridos < 0:
                continue

            cuota_actual = (dias_transcurridos // frecuencia_dias) + 1
            if cuota_actual > total_cuotas or poliza.cuotas_enviadas >= cuota_actual:
                continue

            partner = poliza.partner_id
            if not partner:
                continue

            try:
                poliza.invalidate_recordset()
                poliza = self.browse(poliza.id)
                if poliza.last_reminder_date == today:
                    continue  # validación final antes de escribir
                poliza.write({
                    'last_reminder_date': today,
                    'cuotas_enviadas': cuota_actual
                })
            except Exception as e:
                _logger.warning(f"No se pudo bloquear póliza {poliza.id}: {e}")
                continue

            template = self.env['polizas.recordatorio.template'].search([
                ('forma_pago', '=', poliza.forma_pago),
            ], limit=1)

            if not template:
                continue

            mensaje = (template.message or '').format(
                nombre=partner.name or '',
                numero_poliza=poliza.numero_poliza or '',
                cuota_actual=cuota_actual,
                total_cuotas=total_cuotas,
                tipo=poliza.poliza_type.name or '',
                ejecutivo=poliza.ramo_id.partner_id.name or '',
                ramo=poliza.ramo_id.name or '',
                comercial=poliza.comercial_id.name or '',
                fecha_inicio=poliza.fecha_inicio or '',
                fecha_fin=poliza.fecha_fin or '',
                aseguradora=poliza.aseguradora_id.name or '',
                


            )

            poliza.message_post(
                body=mensaje,
                subject="Recordatorio de pago de cuota",
                author_id=self.env.user.id,
            )

            if partner.email and template:
                try:
                    self.env['mail.mail'].create({
                        'subject': _(f"Recordatorio de pago de cuota #{cuota_actual}"),
                        'body_html': f"<p>{mensaje}</p>",
                        'email_to': partner.email,
                        'auto_delete': True,
                    }).send()
                except Exception as e:
                    _logger.warning(f"Error enviando correo a {partner.name}: {str(e)}")


    @api.model
    def cron_recordatorio_dia_final(self):
        today = fields.Date.today()
        target_date = today + relativedelta(days=1)  # Un día antes de vencimiento  

        # Buscar pólizas vigentes que vencen mañana
        polizas = self.search([
            ('fecha_fin', '=', target_date),
            ('state', '=', 'vigente'),
        ])  

        for poliza in polizas:
            partner = poliza.partner_id
            template = self.env['polizas.recordatorio.template'].search([
                ('is_close', '=', True),
            ], limit=1) 

            if not template or not partner:
                continue    

            mensaje = (template.message or '').format(
                nombre=partner.name or '',
                numero_poliza=poliza.numero_poliza or '',
                #cuota_actual=cuota_actual,
                #total_cuotas=total_cuotas,
                tipo=poliza.poliza_type.name or '',
                ejecutivo=poliza.ramo_id.partner_id.name or '',
                ramo=poliza.ramo_id.name or '',
                comercial=poliza.comercial_id.name or '',
                fecha_inicio=poliza.fecha_inicio or '',
                fecha_fin=poliza.fecha_fin or '',
                aseguradora=poliza.aseguradora_id.name or '',
            )   

            poliza.message_post(
                body=_("⚠️ Recordatorio: La póliza vence mañana. Se registró el aviso en el chatter para %s.") % partner.name,
                subtype_xmlid="mail.mt_note"
            )
            _logger.info(f"[Día Antes Vencimiento] Aviso registrado para {partner.name}: {mensaje}")



           
    @api.model
    def cron_recordatorio_mes_antes(self):
        today = fields.Date.today()

        # Obtener días de recordatorio desde configuración
        days_reminder = int(
            self.env['ir.config_parameter'].sudo().get_param('polizas.days_reminder') or 20
        )
        target_date = today + relativedelta(days=days_reminder)

        # Buscar pólizas vigentes que vencen en X días
        polizas = self.search([
            ('fecha_fin', '=', target_date),
            ('state', '=', 'vigente'),
        ])

        # Obtener vendedores del equipo de ventas por defecto
        equipo = self.env['crm.team'].search([('use_opportunities', '=', True)], limit=1)
        vendedores = equipo.crm_team_member_ids.mapped('user_id') if equipo else self.env['res.users']

        for poliza in polizas:
            partner = poliza.partner_id
            template = self.env['polizas.recordatorio.template'].search([
                ('is_monthly', '=', True),
            ], limit=1)

            if not template or not partner:
                continue

            mensaje = (template.message or '').format(
                nombre=partner.name or '',
                numero_poliza=poliza.numero_poliza or '',
                fecha_fin=poliza.fecha_fin or '',
                tipo=poliza.poliza_type.name or '',
                ejecutivo=poliza.ramo_id.partner_id.name or '',
                ramo=poliza.ramo_id.name or '',
                cliente= partner.name or '',
                aseguradora=poliza.aseguradora_id.name or '',
                fecha_inicio=poliza.fecha_inicio or  '',
                fecha_final=poliza.fecha_fin or  '',
                comercial=poliza.comercial_id.name or  '',
            )

            # Registrar mensaje en el chatter
            poliza.message_post(
                body=_("Se registró recordatorio de fecha próxima de vencimiento para %s.") % partner.name,
                subtype_xmlid="mail.mt_note"
            )
            _logger.info(f"[Mes Antes] Aviso registrado para {partner.name}: {mensaje}")

            # 🧠 Asignar vendedor: si tiene uno, usarlo; si no, uno aleatorio del equipo por defecto
            vendedor = partner.user_id or (random.choice(vendedores) if vendedores else False)

            # Crear oportunidad CRM
            lead_vals = {
                'name': f'Seguimiento Renovacion: {partner.name}',
                'partner_id': partner.id,
                'user_id': vendedor.id if vendedor else False,
                'type': 'opportunity',
                'description': f"Recordatorio automático enviado por póliza {poliza.numero_poliza}.",
                #'planned_revenue': poliza.prima_neta or 0.0,
            }
            lead = self.env['crm.lead'].create(lead_vals)

            poliza.message_post(
                body=_("🎯 Se creó oportunidad CRM de seguimiento con ID <a href='#' data-oe-model='crm.lead' data-oe-id='%s'>%s</a>.") % (lead.id, lead.name),
                subtype_xmlid="mail.mt_note"
            )
            _logger.info(f"[CRM] Oportunidad creada: {lead.name} (ID: {lead.id})")


    @api.model
    def cron_mensaje_cumpleanos(self):
        today = fields.Date.today()

        partners = self.env['res.partner'].search([
            ('birthday', '!=', False)
        ])

        for partner in partners:
            if partner.birthday and partner.birthday.month == today.month and partner.birthday.day == today.day:
                polizas_vigentes = self.search([
                    ('partner_id', '=', partner.id),
                    ('state', '=', 'vigente'),
                ])
                if not polizas_vigentes:
                    continue

                template = self.env['polizas.recordatorio.template'].search([
                    ('is_birthday', '=', True),
                ], limit=1)
                if not template:
                    continue

                mensaje = (template.message or '').format(nombre=partner.name or '',cliente=partner.name or '',ramo=polizas_vigentes[0].ramo_id.name or '',numero_poliza=polizas_vigentes[0].numero_poliza or '',ejecutivo=polizas_vigentes[0].ramo_id.partner_id.name or '',fecha_inicio=polizas_vigentes[0].fecha_inicio.strftime('%d/%m/%Y') if polizas_vigentes[0].fecha_inicio else '',fecha_fin=polizas_vigentes[0].fecha_fin.strftime('%d/%m/%Y') if polizas_vigentes[0].fecha_fin else '',prima_total=polizas_vigentes[0].prima_total or '',comercial=polizas_vigentes[0].comercial_id.name or '',aseguradora=polizas_vigentes[0].aseguradora_id.name or '')

                partner.message_post(
                    body=mensaje,
                    subject="Mensaje de cumpleaños",
                    subtype_xmlid="mail.mt_note",
                )
                _logger.info(f"[Cumpleaños] Aviso registrado para {partner.name}: {mensaje}")

    @api.model
    def cron_cambiar_estado_vencida(self):
        today = fields.Date.today()

        polizas = self.search([
            ('fecha_fin', '<', today),
            ('state', '=', 'vigente'),
        ])

        for poliza in polizas:
            poliza.write({'state': 'vencida'})
            poliza.message_post(
            body=_("La póliza ha sido marcada como <b>VENCIDA</b> automáticamente el %s.") % today.strftime('%d/%m/%Y'),
            subtype_xmlid="mail.mt_note"
        )
            _logger.info(f"[Estado] Póliza {poliza.name} marcada como vencida automáticamente.")
class PolizaPartnerCuota(models.Model):
    _name = 'poliza.partner.cuota'
    _description = 'Cuotas de póliza diferida'

    poliza_id = fields.Many2one('poliza.partner', string="Póliza", ondelete='cascade')
    numero = fields.Integer("# Cuota")
    fecha_pago = fields.Date("Fecha de Pago")
    monto = fields.Float("Monto")
    pagado = fields.Boolean("¿Pagado?")


class PolizasAseguradoras(models.Model):
    _name = 'polizas.aseguradoras'
    _description = 'Aseguradora'

    name = fields.Char("Nombre", required=True)


class PolizaRamo(models.Model):
    _name = 'poliza.ramo'
    _description = 'Ramo de Aseguradora'

    name= fields.Char("Nombre", required=True)
    
class PolizasRamos(models.Model):
    _name = 'polizas.ramos'
    _description = 'Ramo de Aseguradora'

    name = fields.Char("Nombre", required=True)
    partner_id = fields.Many2one('res.partner', string="Ejecutivo de Póliza", ondelete='cascade')

    @api.model_create_multi
    def create(self, vals_list):
        """Create the partner associated with each ramo when necessary."""
        for vals in vals_list:
            if not vals.get('partner_id'):
                partner = self.env['res.partner'].create({
                    'name': vals.get('name', 'Nuevo Ramo'),
                    'is_company': False,
                })
                vals['partner_id'] = partner.id
        return super().create(vals_list)

    def action_create_partner_if_missing(self):
        """ Acción para crear partner si no existe """
        for rec in self:
            if not rec.partner_id:
                partner = self.env['res.partner'].create({
                    'name': rec.name,
                    'is_company': False,
                    #'company_type': 'individual',
                    #'customer_rank': 1,
                })
                rec.partner_id = partner.id

class PolizaType(models.Model):
    _name = 'poliza.type'
    _description = 'Tipo de Póliza'
    
    name = fields.Char("Nombre", required=True)
    description = fields.Text("Descripción")

class ResPartnerActivity(models.Model):
    _name = 'res.partner.activity'
    _description = 'Actividad del Cliente'

    name = fields.Char("Nombre", required=True)
    description = fields.Text("Descripción")
    def enviar_bienvenida(self):
        for rec in self:
            template = self.env.ref('polizas_partner.email_template_bienvenida', raise_if_not_found=False)
            if template:
                template.send_mail(rec.id, force_send=True)
    def verificar_cartera(self):
        for rec in self:
            if not rec.cuota_pagada:
                rec.message_post(body='Atención: Cuota pendiente para la póliza %s' % rec.name)

    def verificar_vencimiento(self):
        for rec in self:
            if rec.fecha_vencimiento:
                dias_restantes = (rec.fecha_vencimiento - fields.Date.today()).days
                if dias_restantes in [0, 1, 7]:
                    rec.message_post(body='La póliza %s está por vencer.' % rec.name)
    
