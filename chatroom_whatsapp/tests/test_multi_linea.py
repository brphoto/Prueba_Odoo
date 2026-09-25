# -*- coding: utf-8 -*-
"""Multi-línea: conversación por línea, aislamiento de agentes, plantillas
por WABA y webhooks de varias Apps de Meta."""
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


class _FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        return None


@tagged('post_install', '-at_install')
class TestMultiLinea(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.icp = cls.env['ir.config_parameter'].sudo()
        cls.icp.set_param('chatroom_whatsapp.access_token', 'token-general')
        cls.icp.set_param('chatroom_whatsapp.business_account_id', 'WABA-GENERAL')
        cls.agent_a = new_test_user(
            cls.env, login='agente_linea_a',
            groups='chatroom_whatsapp.group_chatroom_user,base.group_partner_manager')
        cls.agent_b = new_test_user(
            cls.env, login='agente_linea_b',
            groups='chatroom_whatsapp.group_chatroom_user,base.group_partner_manager')
        cls.supervisor = new_test_user(
            cls.env, login='supervisor_lineas', groups='chatroom_whatsapp.group_chatroom_supervisor')
        Number = cls.env['chatroom.whatsapp.number']
        cls.line_a = Number.create({
            'name': 'Ventas', 'phone_number_id': 'PNID-A',
            'member_ids': [(6, 0, cls.agent_a.ids)],
        })
        cls.line_b = Number.create({
            'name': 'Otra marca', 'phone_number_id': 'PNID-B',
            'business_account_id': 'WABA-B', 'access_token': 'token-b',
            'member_ids': [(6, 0, cls.agent_b.ids)],
        })

    def _inbound(self, wa_id, line):
        return self.env['chatroom.channel']._find_or_create_from_webhook(
            'whatsapp', wa_id, 'Cliente', meta_phone_number_id=line.phone_number_id)

    # -- Una conversación por línea -------------------------------------

    def test_default_mode_keeps_one_conversation_per_contact(self):
        first = self._inbound('593990000001', self.line_a)
        second = self._inbound('593990000001', self.line_b)
        self.assertEqual(first, second)
        self.assertEqual(second.whatsapp_number_id, self.line_b)

    def test_per_line_mode_separates_conversations(self):
        self.icp.set_param('chatroom_whatsapp.conversation_per_line', 'True')
        on_a = self._inbound('593990000002', self.line_a)
        on_b = self._inbound('593990000002', self.line_b)
        self.assertNotEqual(on_a, on_b)
        self.assertEqual(on_a.whatsapp_number_id, self.line_a)
        self.assertEqual(on_b.whatsapp_number_id, self.line_b)
        # El siguiente mensaje por A vuelve a la conversación de A, sin moverla.
        self.assertEqual(self._inbound('593990000002', self.line_a), on_a)
        self.assertEqual(on_a.whatsapp_number_id, self.line_a)

    def test_per_line_mode_start_conversation_uses_the_chosen_line(self):
        self.icp.set_param('chatroom_whatsapp.conversation_per_line', 'True')
        partner = self.env['res.partner'].create({'name': 'Cliente', 'phone': '+593990000003'})
        on_a = self._inbound('593990000003', self.line_a)
        channel_id = self.env['chatroom.channel'].action_start_conversation(
            partner.id, whatsapp_number_id=self.line_b.id)
        on_b = self.env['chatroom.channel'].browse(channel_id)
        self.assertNotEqual(on_a, on_b)
        self.assertEqual(on_b.whatsapp_number_id, self.line_b)

    def test_switching_back_to_one_conversation_prefers_the_same_line(self):
        """Si el modo estuvo activo y quedaron dos conversaciones, al
        desactivarlo cada mensaje sigue yendo a la de su línea."""
        self.icp.set_param('chatroom_whatsapp.conversation_per_line', 'True')
        on_a = self._inbound('593990000004', self.line_a)
        on_b = self._inbound('593990000004', self.line_b)
        self.icp.set_param('chatroom_whatsapp.conversation_per_line', 'False')
        self.assertEqual(self._inbound('593990000004', self.line_b), on_b)
        self.assertEqual(self._inbound('593990000004', self.line_a), on_a)

    # -- Aislamiento por línea ------------------------------------------

    def _channel_with_message(self, line, wa_id, body):
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': wa_id,
            'whatsapp_number_id': line.id, 'assigned_user_id': self.env.user.id,
        })
        message = self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound',
            'message_type': 'text', 'body': body,
        })
        return channel, message

    def test_agent_only_sees_conversations_and_messages_of_their_line(self):
        channel_a, message_a = self._channel_with_message(self.line_a, '593990000010', 'Hola ventas')
        channel_b, message_b = self._channel_with_message(self.line_b, '593990000011', 'Hola marca B')

        Channel = self.env['chatroom.channel'].with_user(self.agent_a)
        Message = self.env['chatroom.message'].with_user(self.agent_a)
        self.assertIn(channel_a, Channel.search([]))
        self.assertNotIn(channel_b, Channel.search([]))
        self.assertIn(message_a, Message.search([]))
        self.assertNotIn(message_b, Message.search([]))
        with self.assertRaises(AccessError):
            message_b.with_user(self.agent_a).read(['body'])

    def test_supervisor_sees_every_line(self):
        channel_a, message_a = self._channel_with_message(self.line_a, '593990000012', 'A')
        channel_b, message_b = self._channel_with_message(self.line_b, '593990000013', 'B')
        Message = self.env['chatroom.message'].with_user(self.supervisor)
        found = Message.search([('id', 'in', (message_a | message_b).ids)])
        self.assertEqual(found, message_a | message_b)

    def test_conversation_assigned_to_an_agent_is_visible_to_them(self):
        channel_b, message_b = self._channel_with_message(self.line_b, '593990000014', 'B')
        channel_b.assigned_user_id = self.agent_a
        self.assertEqual(message_b.with_user(self.agent_a).body, 'B')

    def test_agent_cannot_start_a_conversation_from_another_line(self):
        partner = self.env['res.partner'].create({'name': 'Cliente', 'phone': '+593990000015'})
        Channel = self.env['chatroom.channel'].with_user(self.agent_a)
        with self.assertRaisesRegex(UserError, 'no eres miembro'):
            Channel.action_start_conversation(partner.id, whatsapp_number_id=self.line_b.id)

    def test_agent_without_a_chosen_line_uses_their_own(self):
        self.icp.set_param('chatroom_whatsapp.conversation_per_line', 'True')
        partner = self.env['res.partner'].create({'name': 'Cliente', 'phone': '+593990000016'})
        channel_id = self.env['chatroom.channel'].with_user(
            self.agent_a).action_start_conversation(partner.id)
        self.assertEqual(self.env['chatroom.channel'].browse(channel_id).whatsapp_number_id, self.line_a)

    def test_line_picker_only_offers_the_agent_lines(self):
        Number = self.env['chatroom.whatsapp.number']
        open_line = Number.create({'name': 'Sin equipo', 'phone_number_id': 'PNID-OPEN'})
        offered = {line['id'] for line in Number.with_user(self.agent_a).get_available_lines()}
        self.assertIn(self.line_a.id, offered)
        self.assertIn(open_line.id, offered)
        self.assertNotIn(self.line_b.id, offered)
        offered = {line['id'] for line in Number.with_user(self.supervisor).get_available_lines()}
        self.assertIn(self.line_b.id, offered)

    # -- Plantillas por WABA --------------------------------------------

    def test_same_template_name_can_live_in_two_wabas(self):
        Template = self.env['chatroom.template']
        values = {'name': 'promo_multi', 'language': 'es', 'body': 'Hola {{1}}'}
        general = Template.create(values)
        other = Template.create(dict(values, business_account_id='WABA-B'))
        self.assertEqual(general.business_account_id, 'WABA-GENERAL')
        self.assertEqual(other.business_account_id, 'WABA-B')
        with mute_logger('odoo.sql_db'), self.assertRaises(Exception), self.env.cr.savepoint():
            Template.create(dict(values, business_account_id='WABA-B'))

    def test_sync_reads_every_waba_with_its_token(self):
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((url, kwargs['headers']['Authorization']))
            waba = url.split('/')[-2]
            return _FakeResponse({'data': [{
                'id': 'tpl-%s' % waba, 'name': 'bienvenida_multi', 'language': 'es',
                'status': 'APPROVED', 'category': 'UTILITY',
                'components': [{'type': 'BODY', 'text': 'Hola desde %s' % waba}],
            }]})

        Template = self.env['chatroom.template']
        with patch.object(type(Template), '_meta_request', MagicMock(side_effect=fake_request)):
            Template.action_sync_templates()

        self.assertEqual(
            sorted(calls),
            sorted([
                ('https://graph.facebook.com/v20.0/WABA-GENERAL/message_templates', 'Bearer token-general'),
                ('https://graph.facebook.com/v20.0/WABA-B/message_templates', 'Bearer token-b'),
            ]))
        synced = Template.search([('name', '=', 'bienvenida_multi')])
        self.assertEqual(sorted(synced.mapped('business_account_id')), ['WABA-B', 'WABA-GENERAL'])

    def test_one_failing_waba_does_not_block_the_others(self):
        def fake_request(method, url, **kwargs):
            if 'WABA-B' in url:
                raise requests.RequestException('token vencido')
            return _FakeResponse({'data': [{
                'id': 'tpl-ok', 'name': 'solo_general', 'language': 'es',
                'status': 'APPROVED', 'components': [{'type': 'BODY', 'text': 'Hola'}],
            }]})

        Template = self.env['chatroom.template']
        with patch.object(type(Template), '_meta_request', MagicMock(side_effect=fake_request)):
            result = Template.action_sync_templates()
        self.assertEqual(result['params']['type'], 'warning')
        self.assertIn('Otra marca', result['params']['message'])
        self.assertTrue(Template.search([('name', '=', 'solo_general')]))

    def test_send_wizard_only_accepts_templates_of_the_conversation_waba(self):
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593990000020',
            'whatsapp_number_id': self.line_b.id,
        })
        template = self.env['chatroom.template'].create({
            'name': 'otra_waba', 'language': 'es', 'body': 'Hola',
            'status': 'approved', 'business_account_id': 'WABA-GENERAL',
        })
        wizard = self.env['chatroom.send.template.wizard'].create({
            'channel_id': channel.id, 'template_id': template.id,
        })
        self.assertEqual(wizard.waba_id, 'WABA-B')
        with self.assertRaisesRegex(UserError, 'otra WABA'):
            wizard.action_send()

    # -- Webhooks de varias Apps ----------------------------------------

    def test_webhook_secrets_include_every_app(self):
        self.icp.set_param('chatroom_whatsapp.app_secret', 'secreto-general')
        self.line_b.app_secret = 'secreto-b'
        self.line_b.webhook_verify_token = 'verify-b'
        Number = self.env['chatroom.whatsapp.number']
        self.assertEqual(Number._get_webhook_secrets(), ['secreto-general', 'secreto-b'])
        self.assertIn('verify-b', Number._get_webhook_verify_tokens())


@tagged('post_install', '-at_install')
class TestMultiLineaWebhookHttp(HttpCase):

    def setUp(self):
        super().setUp()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.app_secret', 'secreto-general')
        icp.set_param('chatroom_whatsapp.webhook_verify_token', 'verify-general')
        self.env['chatroom.whatsapp.number'].create({
            'name': 'App B', 'phone_number_id': 'PNID-HTTP',
            'app_secret': 'secreto-b', 'webhook_verify_token': 'verify-b',
        })

    def _post(self, secret):
        body = json.dumps({'object': 'whatsapp_business_account', 'entry': []}).encode()
        signature = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.url_open(
            '/chatroom_whatsapp/webhook', data=body,
            headers={'Content-Type': 'application/json', 'X-Hub-Signature-256': signature})

    def test_post_signed_by_a_line_app_is_accepted(self):
        self.assertEqual(self._post('secreto-b').status_code, 200)
        self.assertEqual(self._post('secreto-general').status_code, 200)

    @mute_logger('odoo.addons.chatroom_whatsapp.controllers.whatsapp_webhook')
    def test_post_with_unknown_secret_is_rejected(self):
        self.assertEqual(self._post('secreto-falso').status_code, 403)

    @mute_logger('odoo.addons.chatroom_whatsapp.controllers.whatsapp_webhook')
    def test_verify_accepts_the_token_of_a_line_app(self):
        base = '/chatroom_whatsapp/webhook?hub.mode=subscribe&hub.challenge=123&hub.verify_token='
        self.assertEqual(self.url_open(base + 'verify-b').text, '123')
        self.assertEqual(self.url_open(base + 'verify-general').text, '123')
        self.assertEqual(self.url_open(base + 'otro').status_code, 403)
