# -*- coding: utf-8 -*-
from urllib.parse import urlparse

from odoo import models
from odoo.tools import config

LOCAL_HOSTS = ('localhost', '127.0.0.1', '::1')


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _get_report_url(self, layout=None):
        """URL con la que wkhtmltopdf descarga estilos y fuentes del propio Odoo.

        Sin `report.url`, Odoo usa la URL pública (`web.base.url`). Con un
        túnel o un dominio externo (lo habitual para recibir el webhook de
        WhatsApp), cada PDF sale a Internet y vuelve al mismo servidor: medido,
        un PDF que tarda ~5 s en local pasa a ~40 s y sale sin estilos si el
        túnel no responde. Si no se configuró `report.url` y la URL pública
        no es local, se usa la dirección local del propio servidor, que
        siempre es alcanzable desde él. Una `report.url` configurada a mano
        se respeta siempre.
        """
        if self.env['ir.config_parameter'].sudo().get_param('report.url'):
            return super()._get_report_url(layout=layout)
        url = super()._get_report_url(layout=layout)
        if not config.get('http_enable', True) or urlparse(url).hostname in LOCAL_HOSTS:
            return url
        interface = config.get('http_interface') or '127.0.0.1'
        if interface in ('0.0.0.0', '::', ''):
            interface = '127.0.0.1'
        return 'http://%s:%s' % (interface, config.get('http_port') or 8069)
