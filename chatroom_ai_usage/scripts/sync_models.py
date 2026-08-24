result = env['chatroom.ai.provider.model'].action_sync_from_provider()
print('SYNC_TAG=%s' % result.get('tag'))
print('SYNC_MESSAGE=%s' % result.get('params', {}).get('message'))
print('CHAT_MODELS=%s' % env['chatroom.ai.provider.model'].search_count([
    ('supports_chat', '=', True), ('active', '=', True),
]))
