from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .meta_api import MetaGraphClient, MetaGraphError


def _meta_datetime(value):
    if not value:
        return False
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return False


class MarketingMetaPage(models.Model):
    _name = 'marketing.meta.page'
    _description = 'Página de Facebook conectada'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'active desc, name'

    name = fields.Char(string='Nombre de la página', required=True, tracking=True)
    connection_id = fields.Many2one(
        'marketing.meta.connection', string='Conexión Meta', required=True,
        ondelete='cascade', index=True, tracking=True)
    page_id = fields.Char(string='ID de página', required=True, index=True, tracking=True)
    page_access_token = fields.Char(
        string='Token de acceso de página', groups='marketing_command_center_meta.group_meta_manager')
    category = fields.Char(string='Categoría')
    page_url = fields.Char(string='URL de la página')
    website = fields.Char(string='Sitio web')
    about = fields.Text(string='Descripción de la página')
    instagram_business_account_id = fields.Char(string='ID de Instagram vinculado', readonly=True)
    instagram_username = fields.Char(string='Usuario de Instagram', readonly=True)
    instagram_followers = fields.Integer(string='Seguidores de Instagram', readonly=True)
    instagram_media_count = fields.Integer(string='Publicaciones de Instagram', readonly=True)
    instagram_social_account_id = fields.Many2one(
        'marketing.social.account', string='Cuenta Instagram en centro de mando',
        readonly=True, ondelete='set null')
    follower_count = fields.Integer(string='Seguidores', readonly=True)
    sync_days = fields.Integer(string='Días a sincronizar', default=30, required=True)
    active = fields.Boolean(default=True, tracking=True)
    state = fields.Selection([
        ('pending', 'Pendiente'), ('connected', 'Conectada'), ('error', 'Con error'),
    ], string='Estado', default='pending', tracking=True, readonly=True)
    last_sync_at = fields.Datetime(string='Última sincronización', readonly=True)
    last_error = fields.Text(string='Último detalle técnico', readonly=True)
    last_sync_summary = fields.Char(string='Resumen de la última sincronización', readonly=True)
    last_posts_count = fields.Integer(string='Publicaciones procesadas', readonly=True)
    last_comments_count = fields.Integer(string='Comentarios procesados', readonly=True)
    last_conversations_count = fields.Integer(string='Conversaciones recibidas', readonly=True)
    last_messages_count = fields.Integer(string='Mensajes recibidos', readonly=True)
    last_conversations_error = fields.Text(string='Detalle de conversaciones', readonly=True)
    last_metrics_error = fields.Text(string='Detalle de métricas', readonly=True)
    social_account_id = fields.Many2one(
        'marketing.social.account', string='Cuenta en centro de mando', readonly=True, ondelete='set null')
    company_id = fields.Many2one(
        'res.company', string='Compañía', related='connection_id.company_id', store=True, index=True)

    _page_unique = models.Constraint(
        'unique(connection_id, page_id)', 'La página ya existe en esta conexión Meta.')

    @api.onchange('connection_id')
    def _onchange_connection(self):
        if self.connection_id and not self.name:
            self.name = self.connection_id.name

    @api.constrains('sync_days')
    def _check_sync_days(self):
        for record in self:
            if record.sync_days < 1 or record.sync_days > 365:
                raise UserError(_('Los días a sincronizar deben estar entre 1 y 365.'))

    def _client(self):
        self.ensure_one()
        token = self.page_access_token or self.connection_id.user_access_token
        return MetaGraphClient(token, self.connection_id.api_version)

    @staticmethod
    def _request_page_data(client, page_id):
        """Consulta datos enriquecidos y retrocede a los campos base si hace falta."""
        try:
            return client.request(page_id, {
                'fields': 'id,name,link,fan_count,website,about,instagram_business_account',
            })
        except MetaGraphError:
            data = client.request(page_id, {'fields': 'id,name,link,fan_count'})
            data['_optional_fields_unavailable'] = True
            return data

    @api.model
    def _upsert_from_meta(self, connection, values):
        if not values.get('id'):
            return self.env['marketing.meta.page']
        page = self.search([
            ('connection_id', '=', connection.id), ('page_id', '=', values.get('id')),
        ], limit=1)
        vals = {
            'name': values.get('name') or values.get('id'),
            'page_id': values.get('id'),
            'category': values.get('category') or False,
            'page_url': values.get('link') or False,
            'follower_count': values.get('fan_count') or 0,
            'state': 'pending',
        }
        if values.get('access_token'):
            vals['page_access_token'] = values['access_token']
        if page:
            page.write(vals)
        else:
            page = self.create(dict(vals, connection_id=connection.id))
        page._ensure_social_account()
        return page

    def _ensure_social_account(self):
        self.ensure_one()
        Account = self.env['marketing.social.account']
        account = self.social_account_id or Account.search([
            ('platform', '=', 'facebook'), ('external_id', '=', self.page_id),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        vals = {
            'name': self.name, 'platform': 'facebook', 'external_id': self.page_id,
            'profile_url': self.page_url, 'follower_count': self.follower_count,
            'connection_state': 'pending', 'company_id': self.company_id.id,
        }
        if account:
            account.write(vals)
        else:
            account = Account.create(vals)
        self.social_account_id = account
        return account

    def action_test_page(self):
        for record in self:
            try:
                data = record._request_page_data(record._client(), record.page_id)
            except MetaGraphError as error:
                record.write({'state': 'error', 'last_error': str(error)})
                raise UserError(str(error)) from error
            values = {
                'name': data.get('name') or record.name,
                'page_url': data.get('link') or record.page_url,
                'follower_count': data.get('fan_count') or 0,
                'state': 'connected', 'last_error': False,
            }
            if not data.get('_optional_fields_unavailable'):
                values.update({
                    'website': data.get('website') or record.website,
                    'about': data.get('about') or record.about,
                    'instagram_business_account_id': (
                        (data.get('instagram_business_account') or {}).get('id') or False
                    ),
                })
            record.write(values)
            record._ensure_social_account()
            record._ensure_instagram_account(record._client(), data)
            record.message_post(body=_('Página verificada correctamente en Meta.'))
        return True

    def action_sync_page(self):
        for record in self:
            record._sync_one_page()
        return True

    def action_sync_inbox(self):
        """Synchronize only the inbox and return a clear result to the user."""
        for record in self:
            client = record._client()
            account = record._ensure_social_account()
            page_data = record._request_page_data(client, record.page_id)
            conversations, messages, error = record._sync_meta_conversations(
                client, account, page_data)
            record.write({
                'last_sync_at': fields.Datetime.now(),
                'last_conversations_count': conversations,
                'last_messages_count': messages,
                'last_conversations_error': error or False,
                'last_sync_summary': _(
                    '%s conversación(es) y %s mensaje(s) sincronizado(s).') % (
                        conversations, messages),
            })
            detail = _(
                'Bandeja sincronizada: %s conversación(es) y %s mensaje(s).') % (
                    conversations, messages)
            if error:
                detail += '<br/><b>%s</b><br/>%s' % (_('Avisos'), error.replace('\n', '<br/>'))
            record.message_post(body=detail)
        # Mostrar inmediatamente el resultado evita que el usuario termine en
        # el formulario de la página sin saber dónde quedaron las conversaciones.
        return self.action_open_conversations()

    def action_open_conversations(self):
        self.ensure_one()
        account_ids = (self.social_account_id | self.instagram_social_account_id).ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Conversaciones de %s') % self.name,
            'res_model': 'marketing.social.conversation',
            'view_mode': 'list,form',
            'domain': [('account_id', 'in', account_ids or [0])],
            'context': {'search_default_state_open': 1},
        }

    def action_open_messages(self):
        self.ensure_one()
        account_ids = (self.social_account_id | self.instagram_social_account_id).ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Mensajes de %s') % self.name,
            'res_model': 'marketing.social.conversation.message',
            'view_mode': 'list,form',
            'domain': [('account_id', 'in', account_ids or [0])],
        }

    def _sync_one_page(self):
        self.ensure_one()
        client = self._client()
        account = self._ensure_social_account()
        today = fields.Date.context_today(self)
        # Se envía una fecha ISO simple para mantener compatibilidad entre versiones Graph.
        since = (today - timedelta(days=max(self.sync_days, 1) - 1)).isoformat()
        until = today.isoformat()
        try:
            page_data = self._request_page_data(client, self.page_id)
            try:
                # Estos contadores están disponibles para publicaciones de página
                # con el token actual y permiten medir interacción aun cuando
                # Insights no entregue métricas avanzadas.
                posts = client.paged('%s/posts' % self.page_id, {
                    'fields': (
                        'id,message,created_time,permalink_url,attachments,'
                        'shares,comments.limit(0).summary(true),'
                        'reactions.limit(0).summary(true)'
                    ),
                    'since': since, 'until': until, 'limit': 100,
                })
            except MetaGraphError:
                # Compatibilidad con tokens/versiones que no exponen alguno de
                # los contadores agregados. La sincronización base continúa.
                posts = client.paged('%s/posts' % self.page_id, {
                    'fields': 'id,message,created_time,permalink_url,attachments',
                    'since': since, 'until': until, 'limit': 100,
                })
        except MetaGraphError as error:
            self.write({'state': 'error', 'last_error': str(error)})
            account.write({'connection_state': 'error', 'sync_message': str(error)})
            raise
        page_values = {
            'name': page_data.get('name') or self.name,
            'page_url': page_data.get('link') or self.page_url,
            'follower_count': page_data.get('fan_count') or 0,
            'state': 'connected', 'last_sync_at': fields.Datetime.now(), 'last_error': False,
        }
        if not page_data.get('_optional_fields_unavailable'):
            page_values.update({
                'website': page_data.get('website') or self.website,
                'about': page_data.get('about') or self.about,
                'instagram_business_account_id': (
                    (page_data.get('instagram_business_account') or {}).get('id') or False
                ),
            })
        self.write(page_values)
        instagram_posts, instagram_comments, instagram_metric_error = self._sync_instagram_media(
            client, page_data, since, until)
        conversation_count, message_count, conversation_error = self._sync_meta_conversations(
            client, account, page_data)
        account.write({
            'name': self.name, 'profile_url': self.page_url,
            'follower_count': self.follower_count, 'connection_state': 'connected',
            'last_sync_at': fields.Datetime.now(), 'sync_message': 'Sincronización Meta correcta',
        })
        created_posts = 0
        processed_comments = 0
        metric_errors = [instagram_metric_error] if instagram_metric_error else []
        for post in posts.get('data', []):
            publication = self._upsert_publication(account, post)
            metric_error = self._sync_post_metrics(client, publication, post.get('id'), post)
            if metric_error:
                metric_errors.append(metric_error)
            processed_comments += self._sync_post_comments(client, publication, post.get('id'))
            created_posts += 1
        summary = _('%s publicación(es) y %s comentario(s) procesado(s).') % (
            created_posts + instagram_posts, processed_comments + instagram_comments)
        self.write({
            'last_sync_summary': summary,
            'last_posts_count': created_posts + instagram_posts,
            'last_comments_count': processed_comments + instagram_comments,
            'last_conversations_count': conversation_count,
            'last_messages_count': message_count,
            'last_conversations_error': conversation_error or False,
            'last_metrics_error': '; '.join(metric_errors[:5]) or False,
        })
        self.connection_id.write({
            'state': 'connected', 'last_sync_at': fields.Datetime.now(), 'last_error': False,
        })
        self.message_post(body=_('Sincronización correcta: %s publicación(es) procesada(s).') % created_posts)
        return created_posts

    def _ensure_instagram_account(self, client, page_data):
        """Crea o actualiza la cuenta Instagram Business vinculada a la página."""
        self.ensure_one()
        if page_data.get('_optional_fields_unavailable'):
            return self.instagram_social_account_id or self.env['marketing.social.account']
        instagram_id = (page_data.get('instagram_business_account') or {}).get('id')
        if not instagram_id:
            self.write({
                'instagram_business_account_id': False,
                'instagram_username': False,
                'instagram_followers': 0,
                'instagram_media_count': 0,
                'instagram_social_account_id': False,
            })
            return self.env['marketing.social.account']
        try:
            profile = client.request(instagram_id, {
                'fields': 'id,username,name,followers_count,media_count,website',
            })
        except MetaGraphError:
            # El vínculo se conserva aunque el token no permita leer el perfil.
            profile = {'id': instagram_id}
        username = profile.get('username') or False
        Account = self.env['marketing.social.account']
        account = self.instagram_social_account_id or Account.search([
            ('platform', '=', 'instagram'), ('external_id', '=', instagram_id),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        vals = {
            'name': profile.get('name') or username or ('Instagram %s' % instagram_id),
            'platform': 'instagram', 'external_id': instagram_id,
            'profile_url': ('https://www.instagram.com/%s/' % username) if username else False,
            'follower_count': profile.get('followers_count') or 0,
            'connection_state': 'connected', 'company_id': self.company_id.id,
        }
        if account:
            account.write(vals)
        else:
            account = Account.create(vals)
        self.write({
            'instagram_business_account_id': instagram_id,
            'instagram_username': username,
            'instagram_followers': profile.get('followers_count') or 0,
            'instagram_media_count': profile.get('media_count') or 0,
            'instagram_social_account_id': account.id,
        })
        return account

    def _sync_instagram_media(self, client, page_data, since, until):
        """Sincroniza medios legibles de Instagram sin afectar Facebook."""
        self.ensure_one()
        instagram_id = (page_data.get('instagram_business_account') or {}).get('id')
        if not instagram_id:
            return 0, 0, False
        account = self._ensure_instagram_account(client, page_data)
        try:
            # El endpoint de medios puede devolver cursores inválidos en Graph
            # aunque el primer lote sea válido. Para no perder datos útiles,
            # procesamos hasta 100 medios del lote inicial; la siguiente
            # sincronización volverá a consultar los más recientes.
            media = client.request('%s/media' % instagram_id, {
                'fields': (
                    'id,caption,media_type,media_url,permalink,timestamp,'
                    'like_count,comments_count'
                ),
                'limit': 100,
            })
        except MetaGraphError:
            return 0, 0, False
        created = 0
        comments = 0
        metric_errors = []
        since_date = datetime.fromisoformat(since).date()
        until_date = datetime.fromisoformat(until).date()
        for item in media.get('data', []):
            published = _meta_datetime(item.get('timestamp'))
            if published and not since_date <= published.date() <= until_date:
                continue
            publication = self._upsert_instagram_publication(account, item)
            self._upsert_instagram_metric(publication, item)
            metric_error = self._sync_instagram_metrics(client, publication, item)
            if metric_error:
                metric_errors.append(metric_error)
            comments += self._sync_instagram_comments(client, publication, item.get('id'))
            created += 1
        return created, comments, '; '.join(metric_errors[:3])

    def _upsert_instagram_publication(self, account, media):
        Publication = self.env['marketing.social.publication']
        external_id = media.get('id')
        publication = Publication.search([
            ('external_id', '=', external_id), ('account_id', '=', account.id),
        ], limit=1)
        media_type = str(media.get('media_type') or '').upper()
        content_type = 'reel' if media_type == 'REELS' else (
            'video' if media_type == 'VIDEO' else 'post')
        caption = (media.get('caption') or '').strip()
        vals = {
            'name': caption[:120] or _('Publicación de Instagram'),
            'external_id': external_id, 'account_id': account.id,
            'published_at': _meta_datetime(media.get('timestamp')) or fields.Datetime.now(),
            'content_type': content_type, 'caption': caption or False,
            'media_url': media.get('media_url') or False,
            'url': media.get('permalink') or media.get('media_url') or False,
        }
        if publication and publication.edit_state == 'draft':
            # Conserva el borrador local hasta que el usuario lo descarte o
            # confirme una acción compatible con el proveedor.
            vals.pop('caption', None)
        if publication:
            publication.write(vals)
        else:
            publication = Publication.create(vals)
        return publication

    def _upsert_instagram_metric(self, publication, media):
        Metric = self.env['marketing.social.metric.snapshot']
        today = fields.Date.context_today(self)
        values = {
            'snapshot_date': today,
            'likes': int(media.get('like_count') or 0),
            'comments': int(media.get('comments_count') or 0),
            'source': 'meta',
            'metric_status': 'partial',
            'fetched_at': fields.Datetime.now(),
            'provider_error': False,
        }
        metric = Metric.search([
            ('publication_id', '=', publication.id), ('snapshot_date', '=', today),
        ], limit=1)
        if metric:
            metric.write(values)
        else:
            Metric.create(dict(values, publication_id=publication.id))

    def _sync_instagram_metrics(self, client, publication, media):
        """Read media insights independently; one unavailable metric must not hide the rest."""
        media_id = media.get('id')
        if not media_id:
            return False
        # Graph cambia las métricas disponibles según el tipo de media. Estas
        # son las métricas actuales para medir interacción sin forzar
        # impresiones, que no existe para varios media product types.
        metrics = ['reach', 'total_interactions', 'saved']
        if str(media.get('media_type') or '').upper() in ('VIDEO', 'REELS'):
            metrics.append('views')
        values = {}
        errors = []
        try:
            payload = client.request('%s/insights' % media_id, {'metric': ','.join(metrics)})
            rows = payload.get('data') or []
        except MetaGraphError:
            rows = []
        for row in rows:
            metric_name = row.get('name')
            value = (row.get('values') or [{}])[-1].get('value', 0)
            try:
                values[metric_name] = int(value or 0)
            except (TypeError, ValueError):
                continue
        for metric_name in metrics:
            if metric_name in values:
                continue
            try:
                payload = client.request('%s/insights' % media_id, {'metric': metric_name})
            except MetaGraphError as error:
                errors.append('%s: %s' % (metric_name, error))
                continue
            rows = payload.get('data') or []
            if not rows:
                continue
            value = (rows[-1].get('values') or [{}])[-1].get('value', 0)
            try:
                value = int(value or 0)
            except (TypeError, ValueError):
                continue
            values[metric_name] = value
        if values:
            Metric = self.env['marketing.social.metric.snapshot']
            today = fields.Date.context_today(self)
            metric = Metric.search([
                ('publication_id', '=', publication.id), ('snapshot_date', '=', today),
            ], limit=1)
            mapped = {
                'source': 'meta', 'fetched_at': fields.Datetime.now(),
                'metric_status': 'verified' if not errors else 'partial',
                'provider_error': '; '.join(errors[:3]) or False,
            }
            if 'impressions' in values:
                mapped['impressions'] = values['impressions']
            if 'reach' in values:
                mapped['reach'] = values['reach']
            if 'saved' in values:
                mapped['saves'] = values['saved']
            if 'total_interactions' in values:
                mapped['provider_engagement'] = values['total_interactions']
            if 'views' in values:
                mapped['views'] = values['views']
            if metric:
                metric.write(mapped)
            else:
                Metric.create(dict(mapped, snapshot_date=today, publication_id=publication.id))
        return '; '.join(errors[:3]) if errors else False

    @staticmethod
    def _conversation_participant(payload, owner_id):
        participants = (payload.get('participants') or {}).get('data', [])
        for participant in participants:
            if str(participant.get('id')) != str(owner_id):
                return participant
        return (participants or [{}])[0]

    def _upsert_social_conversation(self, account, payload, owner_id):
        Conversation = self.env['marketing.social.conversation']
        external_id = payload.get('id')
        if not external_id:
            return self.env['marketing.social.conversation']
        participant = self._conversation_participant(payload, owner_id)
        preview = payload.get('snippet') or ''
        values = {
            'name': participant.get('name') or ('Conversación %s' % external_id),
            'account_id': account.id,
            'external_id': external_id,
            'contact_name': participant.get('name') or False,
            'contact_external_id': participant.get('id') or False,
            'last_message_at': _meta_datetime(payload.get('updated_time')) or fields.Datetime.now(),
            'last_message_preview': preview,
            'url': payload.get('link') or False,
        }
        conversation = Conversation.search([
            ('account_id', '=', account.id), ('external_id', '=', external_id),
        ], limit=1)
        if conversation:
            conversation.write(values)
        else:
            conversation = Conversation.create(values)
        return conversation

    def _sync_social_conversation_messages(self, client, conversation):
        try:
            payload = client.paged_safe('%s/messages' % conversation.external_id, {
                'fields': 'id,message,from,to,created_time,attachments', 'limit': 100,
            }, max_pages=100)
        except MetaGraphError as error:
            return 0, str(error)
        Message = self.env['marketing.social.conversation.message']
        processed = 0
        for item in payload.get('data', []):
            external_id = item.get('id')
            if not external_id:
                continue
            sender = item.get('from') or {}
            direction = 'outbound' if str(sender.get('id')) == str(conversation.account_id.external_id) else 'inbound'
            body = item.get('message') or ''
            if not body and item.get('attachments'):
                body = _('[Adjunto recibido]')
            values = {
                'conversation_id': conversation.id,
                'external_id': external_id,
                'direction': direction,
                'author_name': sender.get('name') or False,
                'author_external_id': sender.get('id') or False,
                'body': body,
                'message_at': _meta_datetime(item.get('created_time')) or fields.Datetime.now(),
                'message_type': 'text' if item.get('message') else 'other',
            }
            message = Message.search([
                ('conversation_id', '=', conversation.id), ('external_id', '=', external_id),
            ], limit=1)
            if message:
                values.pop('read_state', None)
                message.write(values)
            else:
                Message.create(values)
            processed += 1
        return processed, payload.get('_paging_error') or False

    def _sync_meta_conversations(self, client, account, page_data):
        """Best-effort inbox sync for Facebook Pages and linked Instagram Business accounts."""
        sources = [(self.page_id, account)]
        instagram_id = (page_data.get('instagram_business_account') or {}).get('id')
        instagram_account = self.instagram_social_account_id
        if instagram_id and instagram_account:
            sources.append((instagram_id, instagram_account))
        conversations = messages = 0
        errors = []
        for owner_id, source_account in sources:
            try:
                # 50 es más estable para la API de conversaciones de Meta;
                # con 100 algunos tokens devuelven un cursor inválido.
                payload = client.paged_safe('%s/conversations' % owner_id, {
                    'fields': 'id,updated_time,participants,snippet,link', 'limit': 50,
                }, max_pages=100)
            except MetaGraphError as error:
                label = 'Instagram' if source_account.platform == 'instagram' else 'Facebook'
                errors.append('%s: %s' % (label, error))
                continue
            if payload.get('_paging_error'):
                label = 'Instagram' if source_account.platform == 'instagram' else 'Facebook'
                errors.append('%s: %s' % (label, payload['_paging_error']))
            for item in payload.get('data', []):
                conversation = self._upsert_social_conversation(source_account, item, owner_id)
                if not conversation:
                    continue
                conversations += 1
                count, error = self._sync_social_conversation_messages(client, conversation)
                messages += count
                if error:
                    errors.append('%s: %s' % (conversation.name, error))
        return conversations, messages, '\n'.join(errors)

    def _sync_instagram_comments(self, client, publication, media_id):
        if not media_id:
            return 0
        try:
            payload = client.paged('%s/comments' % media_id, {
                'fields': 'id,text,username,timestamp', 'limit': 100,
            })
        except MetaGraphError:
            return 0
        Interaction = self.env['marketing.social.interaction']
        processed = 0
        for comment in payload.get('data', []):
            external_id = comment.get('id')
            if not external_id:
                continue
            vals = {
                'publication_id': publication.id, 'interaction_type': 'comment',
                'external_id': external_id, 'text': comment.get('text') or False,
                'author_name': comment.get('username') or False,
                'interaction_date': _meta_datetime(comment.get('timestamp')) or fields.Datetime.now(),
            }
            existing = Interaction.search([('external_id', '=', external_id)], limit=1)
            if existing:
                existing.write(vals)
            else:
                Interaction.create(vals)
            processed += 1
        return processed

    def _upsert_publication(self, account, post):
        Publication = self.env['marketing.social.publication']
        external_id = post.get('id')
        publication = Publication.search([
            ('external_id', '=', external_id), ('account_id', '=', account.id),
        ], limit=1)
        title = (post.get('message') or _('Publicación de Facebook')).strip()[:120]
        vals = {
            'name': title or _('Publicación de Facebook'), 'external_id': external_id,
            'account_id': account.id, 'published_at': _meta_datetime(post.get('created_time')) or fields.Datetime.now(),
            'content_type': self._content_type_from_post(post),
            'caption': post.get('message') or False,
            'media_url': self._attachment_media_url(post),
            'url': post.get('permalink_url') or self._attachment_url(post) or False,
        }
        if publication and publication.edit_state == 'draft':
            # No destruyas una edición local que todavía espera aprobación.
            vals.pop('caption', None)
        if publication:
            publication.write(vals)
        else:
            publication = Publication.create(vals)
        return publication

    @staticmethod
    def _attachment_url(post):
        attachments = post.get('attachments') if isinstance(post, dict) else False
        rows = attachments.get('data') if isinstance(attachments, dict) else []
        return (rows or [{}])[0].get('url') or False

    @staticmethod
    def _attachment_media_url(post):
        attachments = post.get('attachments') if isinstance(post, dict) else False
        rows = attachments.get('data') if isinstance(attachments, dict) else []
        media = (rows or [{}])[0].get('media') or {}
        image = media.get('image') if isinstance(media, dict) else {}
        return (image or {}).get('src') or False

    @classmethod
    def _content_type_from_post(cls, post):
        attachments = post.get('attachments') if isinstance(post, dict) else False
        rows = attachments.get('data') if isinstance(attachments, dict) else []
        attachment_type = str((rows or [{}])[0].get('type') or '').lower()
        return 'video' if 'video' in attachment_type else 'post'

    @staticmethod
    def _summary_count(post, relation):
        value = post.get(relation) if isinstance(post, dict) else False
        if not isinstance(value, dict):
            return None
        if relation == 'shares':
            count = value.get('count')
        else:
            count = (value.get('summary') or {}).get('total_count')
        try:
            return int(count) if count is not None else None
        except (TypeError, ValueError):
            return None

    def _sync_post_metrics(self, client, publication, post_id, post=None):
        if not post_id:
            return False
        # Los contadores básicos vienen en la consulta de publicaciones. Se
        # conservan aunque el endpoint Insights no esté habilitado para el token.
        values = {'source': 'meta', 'fetched_at': fields.Datetime.now()}
        reactions = self._summary_count(post or {}, 'reactions')
        comments = self._summary_count(post or {}, 'comments')
        shares = self._summary_count(post or {}, 'shares')
        basic_counters = False
        if reactions is not None:
            values['likes'] = reactions
            basic_counters = True
        if comments is not None:
            values['comments'] = comments
            basic_counters = True
        if shares is not None:
            values['shares'] = shares
            basic_counters = True
        try:
            payload = client.request('%s/insights' % post_id, {
                'metric': 'post_impressions,post_impressions_unique,post_reactions_by_type_total',
            })
        except MetaGraphError as error:
            payload = {}
            metrics_error = str(error)
        else:
            metrics_error = False
        for row in payload.get('data', []):
            name = row.get('name')
            value = row.get('values', [{}])[-1].get('value', 0)
            if isinstance(value, dict):
                value = sum(value.values())
            if name == 'post_impressions_unique':
                values['reach'] = int(value or 0)
            elif name == 'post_impressions':
                values['impressions'] = int(value or 0)
            elif name == 'post_reactions_by_type_total':
                values['likes'] = int(value or 0)
        values['metric_status'] = 'verified' if payload.get('data') else (
            'partial' if basic_counters else 'unavailable')
        values['provider_error'] = metrics_error or False
        Metric = self.env['marketing.social.metric.snapshot']
        today = fields.Date.context_today(self)
        metric = Metric.search([('publication_id', '=', publication.id), ('snapshot_date', '=', today)], limit=1)
        values['snapshot_date'] = today
        if metric:
            metric.write(values)
        else:
            Metric.create(dict(values, publication_id=publication.id))
        return metrics_error

    def _sync_post_comments(self, client, publication, post_id):
        if not post_id:
            return 0
        try:
            payload = client.paged('%s/comments' % post_id, {
                'fields': 'id,message,from,created_time', 'limit': 100,
            })
        except MetaGraphError:
            return 0
        Interaction = self.env['marketing.social.interaction']
        processed = 0
        for comment in payload.get('data', []):
            external_id = comment.get('id')
            if not external_id:
                continue
            vals = {
                'publication_id': publication.id, 'interaction_type': 'comment',
                'external_id': external_id, 'text': comment.get('message') or False,
                'author_name': (comment.get('from') or {}).get('name') or False,
                'interaction_date': _meta_datetime(comment.get('created_time')) or fields.Datetime.now(),
            }
            existing = Interaction.search([('external_id', '=', external_id)], limit=1)
            if existing:
                existing.write(vals)
            else:
                Interaction.create(vals)
            processed += 1
        return processed
