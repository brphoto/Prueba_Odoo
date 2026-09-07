# -*- coding: utf-8 -*-
"""Prueba de humo de la app de Chatroom en un navegador real.

Los tests de Python cubren el modelo, pero la mayor parte de la logica de
la bandeja vive en Owl: paginacion del historial, borradores por
conversacion y busqueda de mensajes contra el servidor. Un error de
sintaxis o una referencia rota en el bundle no la ve ningun test de ORM.

Este caso levanta la app en Chrome headless y recorre esas tres piezas.
"""
from datetime import timedelta

from odoo.fields import Datetime
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAppTour(HttpCase):

    def _create_channel(self, name, external_id, message_count):
        partner = self.env['res.partner'].create({'name': name})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': external_id,
            'partner_id': partner.id,
            'assigned_user_id': self.env.ref('base.user_admin').id,
            'last_message_date': Datetime.now(),
        })
        base = Datetime.now() - timedelta(days=2)
        self.env['chatroom.message'].create([{
            'channel_id': channel.id,
            'direction': 'inbound' if index % 2 == 0 else 'outbound',
            'body': 'mensaje-tour-%02d' % index,
            'state': 'read',
            'date': base + timedelta(minutes=index),
        } for index in range(message_count)])
        return channel

    def test_chatroom_app_smoke_tour(self):
        # 80 mensajes: por encima de la tanda de 60 del hilo, para que el
        # boton "Ver mensajes anteriores" tenga que aparecer y para que
        # 'mensaje-tour-03' quede fuera de la carga inicial (asi la
        # busqueda tiene que resolverse en el servidor para encontrarlo).
        self._create_channel('TOUR LARGA', '573001112220', 80)
        self._create_channel('TOUR CORTA', '573001112221', 3)
        self.env.flush_all()
        self.start_tour(
            '/odoo/action-chatroom_whatsapp.action_chatroom_app',
            'chatroom_app_smoke_tour',
            login='admin',
        )
