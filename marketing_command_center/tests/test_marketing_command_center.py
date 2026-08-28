import base64
from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMarketingCommandCenter(TransactionCase):

    def _create_dataset(self):
        company = self.env['res.company'].create({'name': 'QA Marketing Social'})
        account = self.env['marketing.social.account'].create({
            'name': 'QA Instagram', 'platform': 'instagram',
            'external_id': 'qa-instagram-001', 'company_id': company.id,
        })
        campaign = self.env['marketing.social.campaign'].create({
            'name': 'QA Campaña de contenido', 'objective': 'leads',
            'company_id': company.id,
        })
        publication = self.env['marketing.social.publication'].create({
            'name': 'QA Publicación CRM', 'account_id': account.id,
            'campaign_id': campaign.id,
            'published_at': datetime.combine(fields.Date.context_today(self), datetime.min.time()),
            'content_type': 'reel',
        })
        metric = self.env['marketing.social.metric.snapshot'].create({
            'publication_id': publication.id,
            'snapshot_date': fields.Date.context_today(self),
            'reach': 1000, 'impressions': 1500, 'views': 2500,
            'likes': 100, 'comments': 20, 'shares': 30, 'saves': 10,
            'leads': 5, 'sales_amount': 100,
        })
        self.env['marketing.social.interaction'].create({
            'publication_id': publication.id, 'interaction_type': 'comment',
            'author_name': 'Cliente QA', 'text': 'Quiero una cotización',
            'interaction_date': datetime.combine(fields.Date.context_today(self), datetime.min.time()),
            'intent': 'price', 'response_state': 'pending',
        })
        return account, campaign, publication, metric

    def test_metrics_compute_engagement_and_counts(self):
        account, campaign, publication, metric = self._create_dataset()
        self.assertEqual(metric.total_interactions, 160)
        self.assertAlmostEqual(metric.engagement_rate, 16.0, places=2)
        self.assertEqual(publication.latest_reach, 1000)
        self.assertEqual(publication.pending_interaction_count, 1)
        self.assertEqual(account.publication_count, 1)
        self.assertEqual(campaign.publication_count, 1)

    def test_dashboard_refresh_and_natural_language_agent(self):
        self._create_dataset()
        dashboard = self.env['marketing.social.dashboard'].create({
            'name': 'QA Centro de mando', 'company_id': self.env['res.company'].search(
                [('name', '=', 'QA Marketing Social')], limit=1).id,
        })
        dashboard.action_refresh()
        self.assertEqual(dashboard.publication_count, 1)
        self.assertEqual(dashboard.reach_total, 1000)
        self.assertAlmostEqual(dashboard.engagement_rate, 16.0, places=2)
        self.assertEqual(dashboard.pending_comments, 1)
        agent = self.env['marketing.social.agent.chat'].create({
            'name': 'QA Agente', 'company_id': dashboard.company_id.id,
        })
        agent.write({'draft_message': '¿Cuál fue la mejor publicación?'})
        agent.action_send_message()
        self.assertEqual(agent.state, 'answered')
        self.assertEqual(agent.intent, 'top')
        self.assertIn('QA Publicación CRM', agent.answer)
        self.assertEqual(agent.message_count, 2)

    def test_dashboard_demo_creates_reusable_dataset(self):
        dashboard = self.env['marketing.social.dashboard'].create({'name': 'QA Demo'})
        dashboard.action_seed_demo_data()
        self.assertEqual(self.env['marketing.social.publication'].search_count([('demo_record', '=', True)]), 12)
        self.assertEqual(self.env['marketing.social.metric.snapshot'].search_count([]), 12)
        self.assertEqual(dashboard.data_state, 'demo')
        dashboard.action_seed_demo_data()
        self.assertEqual(self.env['marketing.social.publication'].search_count([('demo_record', '=', True)]), 12)

    def test_agent_understands_trend_comments_and_audience_queries(self):
        self._create_dataset()
        agent = self.env['marketing.social.agent.chat'].create({
            'name': 'QA Consultas naturales', 'company_id': self.env['res.company'].search(
                [('name', '=', 'QA Marketing Social')], limit=1).id,
        })
        queries = [
            ('¿Qué tendencia ves?', 'trend', 'engagement consolidado'),
            ('¿Cuántos comentarios están pendientes?', 'comments', 'pendiente(s)'),
            ('¿Cuál es el alcance y las reproducciones?', 'audience', 'alcance acumulado'),
        ]
        for question, expected_intent, expected_text in queries:
            agent.write({'draft_message': question})
            agent.action_send_message()
            self.assertEqual(agent.state, 'answered')
            self.assertEqual(agent.intent, expected_intent)
            self.assertIn(expected_text, agent.answer)
        self.assertEqual(agent.message_count, 6)

    def test_dashboard_actions_open_native_views(self):
        dashboard = self.env['marketing.social.dashboard'].create({'name': 'QA Navegación'})
        agent_action = dashboard.action_open_agent()
        publication_action = dashboard.action_open_publications()
        self.assertEqual(agent_action['res_model'], 'marketing.social.agent.chat')
        self.assertEqual(publication_action['res_model'], 'marketing.social.publication')
        self.assertIn('kanban', publication_action['view_mode'])

    def test_account_external_id_is_unique_per_platform(self):
        self.env['marketing.social.account'].create({
            'name': 'QA Facebook 1', 'platform': 'facebook', 'external_id': 'qa-same',
        })
        with self.assertRaises(ValidationError):
            self.env['marketing.social.account'].create({
                'name': 'QA Facebook 2', 'platform': 'facebook', 'external_id': 'qa-same',
            })

    def test_dashboard_comparison_and_alerts_are_actionable(self):
        self._create_dataset()
        dashboard = self.env['marketing.social.dashboard'].create({
            'name': 'QA Alertas', 'period_days': 30,
            'engagement_alert_threshold': 20, 'pending_comments_alert_threshold': 1,
            'company_id': self.env['res.company'].search([('name', '=', 'QA Marketing Social')], limit=1).id,
        })
        dashboard.action_refresh()
        self.assertEqual(dashboard.open_alert_count, 2)
        self.assertIn('No hay datos del período anterior', dashboard.comparison_summary)
        self.assertTrue(dashboard.action_open_alerts()['domain'])
        dashboard.alert_ids.action_resolve()
        self.assertEqual(dashboard.open_alert_count, 0)

    def test_guided_utf8_csv_import_updates_existing_records(self):
        account, _campaign, publication, _metric = self._create_dataset()
        wizard = self.env['marketing.social.import.wizard'].create({
            'file_name': 'metricas.csv', 'import_type': 'metrics',
            'company_id': account.company_id.id,
            'file_data': base64.b64encode((
                'external_id,snapshot_date,reach,impressions,views,likes,comments,shares,saves,clicks,leads,sales_amount\n'
                ',2026-08-27,1200,1800,2800,110,22,31,12,55,6,125.50\n'
            ).encode('utf-8')),
        })
        # The import contract uses the publication external ID; assign one before importing.
        publication.write({'external_id': 'qa-publication-001'})
        wizard.file_data = base64.b64encode((
            'external_id,snapshot_date,reach,impressions,views,likes,comments,shares,saves,clicks,leads,sales_amount\n'
            'qa-publication-001,2026-08-27,1200,1800,2800,110,22,31,12,55,6,125.50\n'
        ).encode('utf-8'))
        template_action = wizard.action_download_template()
        self.assertIn('/web/content/', template_action['url'])
        wizard.action_import()
        metric = self.env['marketing.social.metric.snapshot'].search([
            ('publication_id', '=', publication.id), ('snapshot_date', '=', '2026-08-27')], limit=1)
        self.assertEqual(metric.reach, 1200)
        self.assertEqual(metric.sales_amount, 125.50)
