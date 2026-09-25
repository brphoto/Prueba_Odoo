# -*- coding: utf-8 -*-
import json
from contextlib import contextmanager
from unittest.mock import patch

KNOWLEDGE = (
    'Horario de atención: lunes a viernes de 8:00 a 18:00.\n\n'
    'Envíos a todo el país en 48 horas.\n\n'
    'El plan básico cuesta 25 dólares mensuales.')


def draft_json(reply, confidence=0.95, intent='consulta', needs_human=False, backing='conocimiento',
               gap='', playbook='', data=None, sentiment='neutral', urgency='normal'):
    return json.dumps({'reply': reply, 'confidence': confidence, 'intent': intent,
                       'needs_human': needs_human, 'reason': 'ok', 'sentiment': sentiment,
                       'urgency': urgency, 'respaldo': backing, 'vacio': gap, 'guion': playbook,
                       'datos': data or {}})


def is_verifier(conversation):
    return 'verificador estricto' in (conversation[0].get('content') or '')


def verifier_json(verified=True, detail=''):
    return json.dumps({'respaldada': verified, 'sin_respaldo': detail})


def fake_provider(reply_json, verified=True):
    """Para parchar `_ai_chat_completion` (autospec) con side_effect en los tours."""
    def provider(_channel, conversation, *args, **kwargs):
        return verifier_json(verified) if is_verifier(conversation) else reply_json
    return provider


def setup_agent(env):
    """Proveedor simulado, aprobación general activa y conocimiento publicado."""
    icp = env['ir.config_parameter'].sudo()
    for key, value in {
        'chatroom_whatsapp.ai_enabled': 'True',
        'chatroom_whatsapp.ai_provider_url': 'https://ia.invalid/v1',
        'chatroom_whatsapp.ai_api_key': 'clave-de-prueba',
        'chatroom_whatsapp.business_hours_enabled': 'False',
        'chatroom_ai_agent.safe_auto_reply': 'True',
        'chatroom_ai_agent.require_approval': 'True',
        'chatroom_whatsapp.ai_require_approval': 'True',
        'chatroom_ai_learning.autonomy_frozen': 'False',
        'chatroom_ai_learning.shadow_enabled': 'False',
    }.items():
        icp.set_param(key, value)
    if 'chatroom.ai.autonomy.policy' in env:
        env['chatroom.ai.autonomy.policy'].search([]).write({'active': False})
    profile = env.ref('chatroom_ai_agent_profile.profile_main')
    profile.write({
        'semantic_search': False,  # sin proveedor real: las pruebas que la usan la activan y simulan
        'agent_name': 'Valeria',
        'business_description': 'Somos una tienda de muebles de oficina; vendemos sillas, escritorios y '
                                'archivadores con entrega a domicilio.',
    })
    knowledge = env['ai.knowledge.base'].create({
        'name': 'Información general', 'source_type': 'text', 'source_text': KNOWLEDGE,
        'keyword_tags': 'horario, envíos, plan, precio'})
    knowledge.action_index()
    knowledge.action_publish()
    return profile, knowledge


class AgentMixin:

    _seq = 0

    def _channel(self, text, partner=None, intent=False):
        AgentMixin._seq += 1
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '59309911%04d' % AgentMixin._seq,
            'partner_id': (partner or self.partner).id, 'assigned_user_id': self.agent.id,
            'ai_intent': intent,
        })
        self._inbound(channel, text)
        return channel

    def _inbound(self, channel, text):
        return self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound', 'body': text, 'state': 'read'})

    @contextmanager
    def _ai(self, answer, verified=True):
        """IA simulada. El verificador responde `verified` salvo que `answer`
        sea una función (entonces decide ella)."""
        seen = []

        def fake(_self, conversation, *args, **kwargs):
            seen.append(conversation)
            if callable(answer):
                return answer(conversation)
            if is_verifier(conversation):
                return verifier_json(verified)
            return answer
        with patch.object(type(self.env['chatroom.channel']), '_ai_chat_completion', fake):
            yield seen

    @contextmanager
    def _no_send(self):
        with patch.object(type(self.env['chatroom.channel']), 'action_send_text', autospec=True,
                          return_value=True) as sender:
            yield sender
