# -*- coding: utf-8 -*-
"""Centro de IA, autonomía en un control, plantillas, información en un paso,
carga desde la web, borrador en el chat, resumen diario, preguntas a los datos,
botones de WhatsApp y cierres con acciones reales."""
import base64
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.chatroom_whatsapp.models.chatroom_channel import ChatroomChannel as BaseChannel
from ..models.chatroom_actions import parse_when
from ..models.web_import import check_public_url, page_text
from .common import AgentMixin, draft_json, setup_agent

PNG = base64.b64encode(base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='))
PAGE = """<html><head><title>Preguntas frecuentes</title><script>var x = 1;</script></head><body>
<nav>Inicio | Tienda</nav><h1>Preguntas frecuentes</h1>
<p>Hacemos envíos a todo el país en 48 horas, el costo es de 5 dólares.</p>
<p>Aceptamos transferencia, tarjeta de crédito y efectivo contra entrega.</p>
<a href="/envios">Envíos</a><a href="https://otro-sitio.com/x">Fuera</a><a href="/logo.png">Logo</a>
<footer>Todos los derechos reservados</footer></body></html>"""
PAGE_2 = """<html><head><title>Envíos</title></head><body>
<p>Los envíos a Galápagos tardan 5 días hábiles y cuestan 20 dólares adicionales.</p></body></html>"""


def with_asked(reply, asked, **kwargs):
    data = json.loads(draft_json(reply, **kwargs))
    data['pregunta_dato'] = asked
    return json.dumps(data)


@tagged('post_install', '-at_install')
class TestAiCenter(AgentMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile, cls.knowledge = setup_agent(cls.env)
        cls.agent = cls.env['res.users'].create({
            'name': 'Asesora Centro', 'login': 'asesora_centro_test',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])]})
        cls.partner = cls.env['res.partner'].create({'name': 'Irene Mora'})
        cls.icp = cls.env['ir.config_parameter'].sudo()

    # ------------------------------------------------------------------
    # Autonomía en un control
    # ------------------------------------------------------------------
    def test_autonomy_mode_sets_everything_at_once(self):
        self.profile.autonomy_mode = 'prudent'
        self.assertFalse(self.profile.bootstrap_autonomy)
        self.assertEqual(self.icp.get_param('chatroom_ai_agent.require_approval'), 'True')
        self.assertEqual(self.icp.get_param('chatroom_ai_learning.graduated_autonomy'), 'False')
        self.assertIn('aprueba todo', self.profile.autonomy_help)
        data = self.profile.action_set_autonomy_mode('autonomous')
        self.assertEqual(data['profile']['autonomy_mode'], 'autonomous')
        self.assertTrue(self.profile.bootstrap_autonomy and self.profile.verify_before_send)
        self.assertEqual(self.icp.get_param('chatroom_ai_agent.require_approval'), 'False')
        self.assertEqual(self.icp.get_param('chatroom_whatsapp.ai_require_approval'), 'False')
        self.profile.autonomy_mode = 'balanced'
        self.assertEqual((self.profile.cost_mode, self.profile.bootstrap_min_confidence), ('balanced', 0.85))
        self.assertEqual(self.icp.get_param('chatroom_ai_agent.require_approval'), 'True')
        with self.assertRaises(UserError):
            self.profile.action_set_autonomy_mode('loco')

    def test_prudent_mode_drafts_even_backed_answers(self):
        self.profile.autonomy_mode = 'prudent'
        channel = self._channel('¿Cuál es el horario de atención?')
        with self._ai(draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')), self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'awaiting_approval')
        sender.assert_not_called()

    # ------------------------------------------------------------------
    # Plantillas
    # ------------------------------------------------------------------
    def test_template_fills_profile_playbooks_with_buttons_and_checklist(self):
        old = self.env.ref('chatroom_ai_agent_profile.playbook_support')
        self.profile.action_apply_template('clinic')
        self.assertEqual(self.profile.business_template, 'clinic')
        self.assertIn('agendamiento', self.profile.role)
        self.assertIn('diagnósticos', self.profile.restrictions)
        self.assertFalse(old.active, 'Los guiones anteriores se archivan, no se borran.')
        playbook = self.profile.playbook_ids.filtered('active')
        self.assertEqual((playbook.code, playbook.on_complete), ('cita', 'meeting'))
        first = playbook.field_ids.filtered(lambda field: field.key == 'primera_vez')
        self.assertEqual(first._option_list(), ['Sí', 'No'])
        self.assertIn('opciones: Sí / No', playbook._prompt_block())
        checklist = self.env['ai.knowledge.base'].search([('name', 'ilike', 'Completa esta información')])
        self.assertEqual(checklist.publication_state, 'draft', 'La lista no se publica: es para completar.')
        self.profile.action_apply_template('clinic')  # aplicar dos veces no duplica
        self.assertEqual(len(self.profile.with_context(active_test=False).playbook_ids.filtered(
            lambda item: item.code == 'cita')), 1)
        self.assertEqual(self.env['ai.knowledge.base'].search_count([('name', 'ilike', 'Completa esta información')]), 1)
        self.assertEqual(self.profile.restrictions.count('diagnósticos'), 1)

    def test_setup_wizard_with_template(self):
        wizard = self.env['chatroom.ai.agent.setup'].create({
            'profile_id': self.profile.id, 'business_template': 'restaurant',
            'business_description': 'Restaurante de comida típica en Quito, con servicio a domicilio.'})
        self.assertIn('Reserva de mesa', wizard.template_playbooks)
        wizard.action_next()
        self.assertEqual(self.profile.business_template, 'restaurant')
        self.assertEqual(set(self.profile.playbook_ids.filtered('active').mapped('code')), {'reserva', 'pedido'})
        wizard.write({'step': 'launch', 'autonomy_mode': 'prudent'})
        with patch.object(type(self.profile), 'action_enable_auto_reply', return_value=True):
            wizard.action_activate()
        self.assertEqual(self.profile.autonomy_mode, 'prudent')

    # ------------------------------------------------------------------
    # Información en un paso y carga desde la web
    # ------------------------------------------------------------------
    def test_quick_knowledge_is_used_right_away(self):
        self.profile.action_quick_knowledge('Garantía', 'Todas las sillas tienen garantía de 2 años por defectos.')
        record = self.env['ai.knowledge.base'].search([('name', '=', 'Garantía')])
        self.assertEqual((record.state, record.publication_state), ('indexed', 'published'))
        context = self.env['ai.knowledge.base'].get_sales_context_details(False, query='garantía de las sillas')
        self.assertIn('2 años', context['context'])
        with self.assertRaises(UserError):
            self.profile.action_quick_knowledge('Vacío', '   ')

    def test_publish_now_button(self):
        record = self.env['ai.knowledge.base'].create({
            'name': 'Devoluciones', 'source_type': 'text', 'publication_state': 'draft',
            'source_text': 'Aceptamos devoluciones dentro de los 30 días con factura.'})
        action = record.action_index_and_publish()
        self.assertEqual((record.state, record.publication_state), ('indexed', 'published'))
        self.assertEqual(action['params']['type'], 'success')

    def test_web_import_only_public_sites(self):
        for url in ('ftp://ejemplo.com', 'http://localhost:8069/web', 'http://127.0.0.1/', 'http://10.0.0.5/',
                    'http://169.254.169.254/latest/meta-data'):
            with self.assertRaises(UserError, msg=url):
                check_public_url(url)

    def test_web_import_accents_and_same_page_twice(self):
        """Web real de un cliente: sin charset en la cabecera y con enlace a sí misma por http."""
        from ..models.web_import import decode_html, page_key
        raw = '<html><body><p>Protegemos tu tranquilidad – gastos médicos</p></body></html>'.encode('utf-8')
        self.assertIn('tranquilidad – gastos médicos', decode_html(raw, 'text/html'))
        self.assertIn('Ã', raw.decode('latin-1'), 'Lo que pasaba antes.')
        self.assertNotIn('Ã', decode_html(raw, 'text/html'))
        self.assertEqual(page_key('http://www.ejemplo.com'), page_key('https://ejemplo.com/'))
        home = ('<html><head><title>Inicio</title></head><body><p>Somos un bróker de seguros con 15 años de '
                'experiencia en Ecuador.</p><a href="http://www.ejemplo.com">Inicio</a></body></html>')
        Wizard = type(self.env['chatroom.ai.web.import'])
        with patch('odoo.addons.chatroom_ai_agent_profile.models.web_import.check_public_url',
                   side_effect=lambda url: url), \
                patch.object(Wizard, '_fetch', autospec=True, side_effect=lambda _self, url: (url, home)):
            wizard = self.env['chatroom.ai.web.import'].create({'url': 'https://www.ejemplo.com/'})
            wizard.action_import()
        self.assertIn('1 página(s)', wizard.result)

    def test_page_text_keeps_content_and_same_site_links(self):
        title, text, links = page_text(PAGE, 'https://tienda.ejemplo.com/faq')
        self.assertEqual(title, 'Preguntas frecuentes')
        self.assertIn('48 horas', text)
        self.assertIn('transferencia', text)
        self.assertNotIn('var x', text)
        self.assertNotIn('derechos reservados', text)
        self.assertEqual(links, ['https://tienda.ejemplo.com/envios'])

    def test_web_import_reads_linked_pages_and_publishes(self):
        pages = {'https://tienda.ejemplo.com/faq': PAGE, 'https://tienda.ejemplo.com/envios': PAGE_2}
        Wizard = type(self.env['chatroom.ai.web.import'])
        with patch('odoo.addons.chatroom_ai_agent_profile.models.web_import.check_public_url',
                   side_effect=lambda url: url), \
                patch.object(Wizard, '_fetch', autospec=True, side_effect=lambda _self, url: (url, pages[url])):
            wizard = self.env['chatroom.ai.web.import'].create({'url': 'tienda.ejemplo.com/faq'})
            wizard.action_import()
            self.assertEqual(wizard.state, 'done')
            self.assertIn('2 página(s)', wizard.result)
            records = self.env['ai.knowledge.base'].search([('source_url', 'like', 'tienda.ejemplo.com')])
            self.assertEqual(set(records.mapped('publication_state')), {'published'})
            context = self.env['ai.knowledge.base'].get_sales_context_details(False, query='envíos a Galápagos')
            self.assertIn('20 dólares', context['context'])
            # Volver a cargar actualiza, no duplica.
            self.env['chatroom.ai.web.import'].create({'url': 'https://tienda.ejemplo.com/faq'}).action_import()
        self.assertEqual(self.env['ai.knowledge.base'].search_count([('source_url', 'like', 'tienda.ejemplo.com')]), 2)

    # ------------------------------------------------------------------
    # Borrador en el chat
    # ------------------------------------------------------------------
    def test_composer_draft_and_human_reply_closes_leftovers(self):
        channel = self._channel('¿Tienen sillas para niños?')
        with self._ai(draft_json('Sí, tenemos sillas infantiles.', backing='ninguno')), self._no_send():
            channel.action_ai_auto_reply_safe()
        self._inbound(channel, '¿Y de qué colores?')
        with self._ai(draft_json('Tenemos en azul y rojo.', backing='ninguno')), self._no_send():
            channel.action_ai_auto_reply_safe()
        draft = channel.get_ai_pending_draft()
        self.assertEqual(draft['text'], 'Tenemos en azul y rojo.')
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'outbound', 'state': 'sent', 'sender_user_id': self.agent.id,
            'body': 'Tenemos en azul, rojo y verde.'})
        self.assertFalse(channel.get_ai_pending_draft(), 'Respondió una persona: no quedan borradores.')
        states = self.env['chatroom.ai.suggestion'].search([('channel_id', '=', channel.id)]).mapped('state')
        self.assertNotIn('draft', states)

    def test_composer_draft_discard(self):
        channel = self._channel('¿Hacen muebles a medida?')
        with self._ai(draft_json('Sí, hacemos muebles a medida.', backing='ninguno')), self._no_send():
            channel.action_ai_auto_reply_safe()
        self.assertTrue(channel.get_ai_pending_draft())
        channel.action_ai_discard_draft()
        self.assertFalse(channel.get_ai_pending_draft())
        self.assertFalse(channel.ai_list_state)

    # ------------------------------------------------------------------
    # Botones de WhatsApp para elegir un dato
    # ------------------------------------------------------------------
    def _options_playbook(self):
        playbook = self.env.ref('chatroom_ai_agent_profile.playbook_support')
        playbook.field_ids.filtered(lambda field: field.key == 'problema').options = \
            'Llegó dañado, No llegó, Producto equivocado'
        return playbook

    def test_asked_field_with_options_goes_as_buttons(self):
        self._options_playbook()
        channel = self._channel('Tengo un problema con el pedido 5521', intent='soporte')
        reply = with_asked('Gracias. ¿Qué pasó con tu pedido?', 'problema', intent='soporte', backing='guion',
                           playbook='soporte', data={'referencia': '5521'})
        with self._ai(reply), \
                patch.object(BaseChannel, 'action_send_text', autospec=True, return_value=True) as text, \
                patch.object(type(channel), 'action_send_interactive_buttons', autospec=True,
                             return_value=True) as buttons:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'sent')
        text.assert_not_called()
        self.assertEqual(buttons.call_args.args[1:], ('Gracias. ¿Qué pasó con tu pedido?',
                                                      ['Llegó dañado', 'No llegó', 'Producto equivocado']))

    def test_options_fall_back_to_text_and_lists(self):
        channel = self._channel('hola')
        channel.channel_type = 'whatsapp'
        with patch.object(type(channel), 'action_send_interactive_buttons', side_effect=UserError('sin api')), \
                patch.object(BaseChannel, 'action_send_text', autospec=True, return_value=True) as text:
            channel.with_context(chatroom_ai_generated=True, chatroom_ai_options=['A', 'B']).action_send_text('Elige')
        self.assertEqual(text.call_args.args[1], 'Elige\n• A\n• B')
        with patch.object(type(channel), '_send_interactive_list', autospec=True, return_value=True) as listed:
            channel.with_context(chatroom_ai_generated=True,
                                 chatroom_ai_options=['1', '2', '3', '4']).action_send_text('¿Cuántas?')
        self.assertEqual(len(listed.call_args.args[3]), 4)

    def test_approved_draft_also_goes_with_buttons(self):
        """Con IA real el reclamo quedó para aprobar: al aprobarlo, igual sale con botones."""
        playbook = self._options_playbook()
        channel = self._channel('Tengo un problema con el pedido 7788', intent='soporte')
        channel.write({'ai_playbook_id': playbook.id, 'ai_playbook_data': json.dumps({'referencia': '7788'})})
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(
            channel, '¿Qué problema tienes con tu pedido 7788?')
        with patch.object(BaseChannel, 'action_send_text', autospec=True, return_value=True) as text, \
                patch.object(type(channel), 'action_send_interactive_buttons', autospec=True,
                             return_value=self.env['chatroom.message']) as buttons:
            suggestion.action_approve_and_send()
        text.assert_not_called()
        self.assertEqual(buttons.call_args.args[2], ['Llegó dañado', 'No llegó', 'Producto equivocado'])

    def test_options_without_asked_key_use_the_named_field(self):
        playbook = self._options_playbook()
        self.assertEqual(playbook._options_for({}, '', 'Cuéntame qué pasó con el pedido'), [])
        self.assertEqual(playbook._options_for({'referencia': '1'}, '', '¿Me dices qué pasó? (problema)'),
                         ['Llegó dañado', 'No llegó', 'Producto equivocado'])
        self.assertEqual(playbook._options_for({'problema': 'No llegó'}, 'problema', ''), [],
                         'Ya lo contestó: no se vuelve a preguntar.')

    def test_simulator_shows_option_chips(self):
        self._options_playbook()
        simulator = self.env['chatroom.ai.agent.simulator'].create({'profile_id': self.profile.id,
                                                                    'message': 'Mi pedido 5521 tiene un problema'})
        reply = with_asked('¿Qué pasó con tu pedido?', 'problema', intent='soporte', backing='guion',
                           playbook='soporte', data={'referencia': '5521'})
        with self._ai(reply):
            simulator.action_send()
        self.assertIn('o_agent_sim_options', simulator.chat_html)
        self.assertIn('Producto equivocado', simulator.chat_html)

    # ------------------------------------------------------------------
    # Foto del producto recomendado
    # ------------------------------------------------------------------
    def test_product_photo_sent_once(self):
        product = self.env['product.product'].create({'name': 'Silla ergonómica Pro', 'list_price': 189.0,
                                                      'sale_ok': True, 'image_1920': PNG})
        self.env['product.product'].create({'name': 'Silla', 'list_price': 50.0, 'sale_ok': True, 'image_1920': PNG})
        channel = self._channel('¿Qué silla me recomiendas?')
        Channel = type(channel)
        with patch.object(Channel, 'action_send_product', autospec=True, return_value=True) as card:
            self.assertEqual(channel._ai_send_product_cards('Te recomiendo la Silla ergonómica Pro.'), 1)
            self.assertEqual(channel._ai_send_product_cards('La Silla ergonómica Pro es la mejor.'), 0)
        self.assertEqual(card.call_args.args[1], product.id, 'La más específica, no «Silla».')
        self.profile.send_product_images = False
        with patch.object(Channel, 'action_send_product', autospec=True) as card:
            self.assertEqual(channel._ai_send_product_cards('Otra Silla'), 0)
            card.assert_not_called()

    # ------------------------------------------------------------------
    # Cierres con acciones reales
    # ------------------------------------------------------------------
    def test_send_quote_with_link_to_accept_and_pay(self):
        if 'sale.order' not in self.env:
            self.skipTest('Ventas no instalado')
        self.env.ref('chatroom_ai_agent_profile.playbook_quote').on_complete = 'send_quote'
        self.env['product.product'].create({'name': 'Silla ergonómica Pro', 'list_price': 189.0, 'sale_ok': True})
        channel = self._channel('Quiero cotizar 3 sillas ergonómicas, soy Irene Mora', intent='venta')
        with self._ai(draft_json('Gracias Irene, te envío la cotización.', intent='venta', backing='guion',
                                 playbook='cotizacion', data={'nombre': 'Irene Mora', 'necesidad': 'sillas ergonómicas',
                                                              'detalle': '3 sillas'})), self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'handoff')
        order = self.env['sale.order'].search([('partner_id', '=', self.partner.id)], limit=1)
        self.assertTrue(order.access_token)
        link = [call.args[1] for call in sender.call_args_list if '/my/orders/' in call.args[1]]
        self.assertTrue(link, 'El cliente recibe el enlace para aceptar y pagar.')
        self.assertIn(order.name, link[0])

    def test_meeting_is_scheduled_in_the_calendar(self):
        playbook = self.env['chatroom.ai.agent.playbook'].create({
            'profile_id': self.profile.id, 'name': 'Agendar visita', 'code': 'visita', 'on_complete': 'meeting',
            'when_to_use': 'Cuando el cliente quiere visitar el local.',
            'field_ids': [(0, 0, {'label': 'Nombre', 'key': 'nombre'}),
                          (0, 0, {'label': 'Fecha y hora preferida', 'key': 'fecha_hora'})]})
        channel = self._channel('Quiero visitarlos mañana a las 10 am, soy Irene Mora')
        with self._ai(draft_json('Perfecto Irene, te esperamos.', backing='guion', playbook=playbook.code,
                                 data={'nombre': 'Irene Mora', 'fecha_hora': 'mañana a las 10 am'})), \
                self._no_send() as sender:
            channel.action_ai_auto_reply_safe()
        if 'calendar.event' in self.env:
            event = self.env['calendar.event'].search([('name', 'ilike', 'Agendar visita')])
            self.assertEqual(len(event), 1)
            self.assertIn(self.partner, event.partner_ids)
            self.assertTrue(any('te agendé' in call.args[1] for call in sender.call_args_list))
        else:
            self.assertTrue(channel.activity_ids)

    def test_option_value_is_a_classification_not_a_quote(self):
        """Con IA real: el cliente dijo «carro», la IA eligió «Vehicular» y el dato se perdía."""
        playbook = self.env['chatroom.ai.agent.playbook'].create({
            'profile_id': self.profile.id, 'name': 'Cotizar seguro', 'code': 'seguro', 'on_complete': 'handoff',
            'when_to_use': 'Cotizar un seguro.',
            'field_ids': [(0, 0, {'label': 'Tipo de seguro', 'key': 'tipo', 'options': 'Vehicular, Vida'}),
                          (0, 0, {'label': 'Detalle', 'key': 'detalle'})]})
        Playbook = self.env['chatroom.ai.agent.playbook']
        draft = {'playbook_code': 'seguro', 'evidence': 'quiero asegurar mi carro, un Sail 2021',
                 'collected': {'tipo': 'vehicular', 'detalle': 'Sail 2021'}}
        _pb, data, done, _new = Playbook._advance(playbook, Playbook, {}, False, draft)
        self.assertEqual(data, {'tipo': 'Vehicular', 'detalle': 'Sail 2021'})
        self.assertTrue(done)
        draft['collected'] = {'tipo': 'Salud'}  # no es una opción ni lo dijo el cliente
        _pb, data, _done, _new = Playbook._advance(playbook, Playbook, {}, False, draft)
        self.assertNotIn('tipo', data)

    def test_completed_playbook_acts_even_if_ai_asks_for_review(self):
        """Con IA real: pidió «revisión humana» al completar la llamada y la cita no se agendaba."""
        playbook = self.env['chatroom.ai.agent.playbook'].create({
            'profile_id': self.profile.id, 'name': 'Agendar llamada', 'code': 'llamada', 'on_complete': 'meeting',
            'when_to_use': 'Cuando quiere una llamada.',
            'field_ids': [(0, 0, {'label': 'Nombre', 'key': 'nombre'}),
                          (0, 0, {'label': 'Fecha y hora', 'key': 'fecha_hora'})]})
        channel = self._channel('Quiero una llamada mañana a las 4 de la tarde, soy Irene Mora')
        with self._ai(draft_json('Perfecto Irene, Fernando te llamará.', backing='guion', playbook=playbook.code,
                                 needs_human=True, data={'nombre': 'Irene Mora',
                                                         'fecha_hora': 'mañana a las 4 de la tarde'})), \
                self._no_send():
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'handoff')
        if 'calendar.event' in self.env:
            self.assertTrue(self.env['calendar.event'].search([('name', 'ilike', 'Agendar llamada')]))

    def test_meeting_without_clear_date_creates_a_task(self):
        playbook = self.env['chatroom.ai.agent.playbook'].create({
            'profile_id': self.profile.id, 'name': 'Agendar llamada', 'code': 'llamada', 'on_complete': 'meeting',
            'when_to_use': 'Cuando el cliente quiere una llamada.',
            'field_ids': [(0, 0, {'label': 'Fecha y hora', 'key': 'fecha_hora'})]})
        channel = self._channel('Llámenme cuando puedan')
        with self._ai(draft_json('Claro, te llamamos.', backing='guion', playbook=playbook.code,
                                 data={'fecha_hora': 'cuando puedan'})), self._no_send():
            channel.action_ai_auto_reply_safe()
        self.assertTrue(channel.activity_ids)

    def test_meeting_uses_the_business_time_zone(self):
        self.icp.set_param('chatroom_whatsapp.business_hours_tz', 'America/Guayaquil')
        channel = self._channel('hola')
        self.assertEqual(channel._ai_meeting_tz().zone, 'America/Guayaquil')
        self.icp.set_param('chatroom_whatsapp.business_hours_tz', '')
        root = self.env.ref('base.user_root')
        (self.agent | root).write({'tz': False})
        self.env.ref('base.user_admin').tz = 'America/Bogota'
        self.assertEqual(channel.with_user(root)._ai_meeting_tz().zone, 'America/Bogota',
                         'La cola corre sin zona horaria: se usa la del administrador.')

    def test_parse_when_spanish(self):
        now = datetime(2026, 9, 24, 10, 0)  # jueves
        cases = {
            'mañana a las 3': datetime(2026, 9, 25, 15, 0),
            'el martes por la mañana a las 10': datetime(2026, 9, 29, 10, 0),
            '15/10 16h': datetime(2026, 10, 15, 16, 0),
            'viernes 4 de la tarde': datetime(2026, 9, 25, 16, 0),
            '3 de octubre a las 11:00': datetime(2026, 10, 3, 11, 0),
            'para 2 personas el sábado a las 8 pm': datetime(2026, 9, 26, 20, 0),
        }
        for text, expected in cases.items():
            self.assertEqual(parse_when(text, now), expected, text)
        self.assertIsNone(parse_when('cuando puedan', now))
        self.assertIsNone(parse_when('el lunes', now), 'Sin hora no se agenda.')

    # ------------------------------------------------------------------
    # Centro de IA, resumen diario y preguntas a los datos
    # ------------------------------------------------------------------
    def test_center_data(self):
        channel = self._channel('¿Hacen envíos a Cuenca?')
        with self._ai(draft_json('Sí, hacemos envíos.', backing='ninguno')), self._no_send():
            channel.action_ai_auto_reply_safe()
        data = self.env['chatroom.ai.agent.profile'].get_ai_center_data()
        self.assertEqual(data['profile']['id'], self.profile.id)
        self.assertEqual([mode['key'] for mode in data['profile']['modes']], ['prudent', 'balanced', 'autonomous'])
        self.assertIn(channel.id, [item['channel_id'] for item in data['today']['pending']])
        item = next(item for item in data['today']['pending'] if item['channel_id'] == channel.id)
        self.assertEqual(item['question'], '¿Hacen envíos a Cuenca?')
        self.assertTrue(data['setup']['checks'])
        self.assertIn('alone_rate', data['results'])
        self.assertEqual(len(data['results']['trend']), 8)
        action = self.profile.action_open_ai_center()
        self.assertEqual(action['tag'], 'chatroom_ai_agent_profile.ai_center')

    def test_daily_summary(self):
        yesterday = fields.Date.context_today(self.profile) - timedelta(days=1)
        Event = self.env['chatroom.ai.agent.event']
        for kind in ('sent', 'sent', 'handoff'):
            Event.create({'kind': kind, 'profile_id': self.profile.id, 'date': yesterday, 'cost': 0.001})
        self.profile.summary_user_ids = self.agent
        self.assertEqual(self.env['chatroom.ai.agent.profile']._cron_daily_summary(), 1)
        message = self.profile.message_ids[:1]
        self.assertIn('Resumen del agente IA', message.subject)
        self.assertIn('Conversaciones atendidas', message.body)
        self.assertIn('67%', message.body)
        self.assertIn(self.agent.partner_id, message.partner_ids)
        self.profile.summary_enabled = False
        self.assertEqual(self.env['chatroom.ai.agent.profile']._cron_daily_summary(), 0)

    def test_ask_insights_uses_the_data(self):
        Event = self.env['chatroom.ai.agent.event']
        Event.create({'kind': 'handoff', 'profile_id': self.profile.id, 'reason': 'Reclamo por demora'})
        seen = []

        def complete(_self, messages, **kwargs):
            seen.append(messages)
            return 'El principal motivo de traspaso es «Reclamo por demora» (1).'
        with patch.object(type(self.env['chatroom.ai.service']), 'complete', complete):
            answer = self.profile.ask_insights('¿Por qué pasan a una persona?')
        self.assertIn('Reclamo por demora', answer)
        self.assertIn('Reclamo por demora', seen[0][1]['content'])
        with self.assertRaises(UserError):
            self.profile.ask_insights(' ')
