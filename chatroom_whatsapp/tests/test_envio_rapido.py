# -*- coding: utf-8 -*-
"""Envío rápido de archivos: PDFs por URL local y adjuntos en segundo plano."""
import base64
from unittest.mock import patch

import requests

from odoo.tests import TransactionCase, tagged
from odoo.tools import config, mute_logger


class _Response:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError('HTTP %s' % self.status_code)


@tagged('post_install', '-at_install')
class TestEnvioRapido(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.access_token', 'token-qa')
        icp.set_param('chatroom_whatsapp.phone_number_id', 'PNID-QA')
        cls.channel = cls.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593990008000'})
        cls.pdf = {'name': 'cotizacion.pdf', 'mimetype': 'application/pdf',
                   'data': base64.b64encode(b'%PDF-1.4 prueba').decode()}

    def _patched(self, calls, fail_upload=False):
        def fake_request(method, url, **kwargs):
            calls.append(url)
            if url.endswith('/media'):
                if fail_upload:
                    raise requests.ConnectionError('sin red')
                return _Response({'id': 'MEDIA-%s' % len(calls)})
            return _Response({'messages': [{'id': 'wamid.%s' % len(calls)}]})
        Channel = type(self.env['chatroom.channel'])
        return (patch.object(Channel, '_meta_request', staticmethod(fake_request)),
                patch.object(Channel, '_check_can_send', lambda self: True))

    # -- PDF por URL local ----------------------------------------------

    def test_pdf_assets_use_the_local_server_behind_a_tunnel(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('report.url', False)
        icp.set_param('web.base.url', 'https://qzw3zbx9-8019.use2.devtunnels.ms')
        url = self.env['ir.actions.report']._get_report_url()
        self.assertTrue(url.startswith('http://127.0.0.1:') or url.startswith(
            'http://%s:' % config.get('http_interface')), url)
        self.assertTrue(url.endswith(':%s' % config.get('http_port')), url)

    def test_a_configured_report_url_is_respected(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('report.url', 'http://interno:9000')
        self.assertEqual(self.env['ir.actions.report']._get_report_url(), 'http://interno:9000')

    def test_a_local_base_url_is_used_as_is(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('report.url', False)
        icp.set_param('web.base.url', 'http://localhost:8019')
        self.assertEqual(self.env['ir.actions.report']._get_report_url(), 'http://localhost:8019')

    # -- Adjuntos en segundo plano --------------------------------------

    def test_attachments_are_queued_and_the_agent_does_not_wait(self):
        calls = []
        network, window = self._patched(calls)
        with network, window:
            message = self.channel.with_context(chatroom_async_media=True).action_send_message(
                body='Tu cotización', attachments=[self.pdf])
            self.assertEqual(calls, [], 'La pantalla no espera a Meta.')
            self.assertEqual(message.state, 'pending')
            self.assertTrue(message.media_queued)
            self.assertEqual(self.env['chatroom.channel']._cron_send_queued_media(), 1)
        self.assertEqual(message.state, 'sent')
        self.assertFalse(message.media_queued)
        self.assertTrue(message.wa_message_id.startswith('wamid.'))
        self.assertEqual(len(calls), 2, 'Una subida y un envío.')

    def test_a_failed_file_does_not_block_the_next_ones(self):
        calls = []
        network, window = self._patched(calls)
        with network, window:
            first, second = self.channel.with_context(chatroom_async_media=True).action_send_message(
                attachments=[self.pdf, dict(self.pdf, name='anexo.pdf')])
        network, window = self._patched([], fail_upload=True)
        with network, window, mute_logger('odoo.addons.chatroom_whatsapp.models.chatroom_channel'):
            self.env['chatroom.channel']._cron_send_queued_media()
        self.assertEqual((first.state, second.state), ('failed', 'failed'))
        self.assertFalse(first.media_queued or second.media_queued)

    def test_synchronous_mode_still_works(self):
        calls = []
        network, window = self._patched(calls)
        with network, window:
            message = self.channel.with_context(chatroom_async_media=False).action_send_message(
                attachments=[self.pdf])
        self.assertEqual(message.state, 'sent')
        self.assertEqual(len(calls), 2)
