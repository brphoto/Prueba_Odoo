# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAislamientoPorEmpresa(TransactionCase):
    """Las tareas de IA no pueden verse entre empresas.

    Las conversaciones sí estaban aisladas, pero las tareas de IA no, y
    en su prompt y su resultado va el contenido de esas conversaciones.
    La regla de administrador era `[('id', '!=', False)]`: todas las
    filas de la base, de cualquier empresa.

    El detalle que lo hacía difícil de ver: una regla por grupo no habría
    servido. Odoo une con OR las reglas de los grupos del usuario, así
    que una regla por empresa puesta en un grupo se habría sumado a esa
    de administrador en vez de restringirla. Tiene que ser global.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.empresa_a = cls.env.company
        cls.empresa_b = cls.env['res.company'].create({'name': 'QA Empresa B'})

        def usuario(nombre, empresa, grupo):
            return cls.env['res.users'].create({
                'name': nombre,
                'login': 'qa-aislamiento-%s' % nombre.lower().replace(' ', '-'),
                'company_id': empresa.id,
                'company_ids': [(6, 0, [empresa.id])],
                'group_ids': [(4, cls.env.ref(grupo).id)],
            })

        cls.jefe_a = usuario(
            'Jefe A', cls.empresa_a,
            'chatroom_ai_agent.group_chatroom_ai_agent_manager')
        cls.jefe_b = usuario(
            'Jefe B', cls.empresa_b,
            'chatroom_ai_agent.group_chatroom_ai_agent_manager')

        def tarea(etiqueta, empresa):
            canal = cls.env['chatroom.channel'].sudo().create({
                'channel_type': 'whatsapp',
                'external_id': 'aislamiento-%s' % etiqueta,
                'company_id': empresa.id,
            })
            return cls.env['chatroom.ai.task'].sudo().create({
                'name': 'Tarea %s' % etiqueta,
                'channel_id': canal.id,
                'company_id': empresa.id,
            })

        cls.tarea_a = tarea('a', cls.empresa_a)
        cls.tarea_b = tarea('b', cls.empresa_b)

    # ------------------------------------------------------------------

    def test_a_manager_does_not_see_the_other_company_tasks(self):
        visibles = self.env['chatroom.ai.task'].with_user(self.jefe_a).search([])

        self.assertIn(self.tarea_a, visibles)
        self.assertNotIn(
            self.tarea_b, visibles,
            'Un responsable de la empresa A está viendo las tareas de IA '
            'de la empresa B, con el contenido de sus conversaciones.')

    def test_the_isolation_works_in_both_directions(self):
        visibles = self.env['chatroom.ai.task'].with_user(self.jefe_b).search([])

        self.assertIn(self.tarea_b, visibles)
        self.assertNotIn(self.tarea_a, visibles)

    def test_reading_the_other_company_task_by_id_is_refused(self):
        """Buscar no es el único camino: hay que comprobar el acceso
        directo por identificador, que es lo que hace una URL."""
        with self.assertRaises(Exception):
            self.env['chatroom.ai.task'].with_user(
                self.jefe_a).browse(self.tarea_b.id).read(['name'])

    def test_a_user_of_both_companies_sees_both(self):
        """La regla mira `company_ids`, no `company_id`: quien tiene las
        dos empresas activas tiene que ver las dos."""
        self.jefe_a.write({
            'company_ids': [(6, 0, [self.empresa_a.id, self.empresa_b.id])]})

        visibles = self.env['chatroom.ai.task'].with_user(
            self.jefe_a).with_context(
                allowed_company_ids=[self.empresa_a.id, self.empresa_b.id]
            ).search([])

        self.assertIn(self.tarea_a, visibles)
        self.assertIn(self.tarea_b, visibles)

    def test_a_task_without_company_is_visible_to_everyone(self):
        """`company_id` vacío significa «de todas»; la regla lo deja
        pasar a propósito."""
        canal = self.env['chatroom.channel'].sudo().create({
            'channel_type': 'whatsapp', 'external_id': 'aislamiento-global',
        })
        compartida = self.env['chatroom.ai.task'].sudo().create({
            'name': 'Tarea sin empresa', 'channel_id': canal.id,
        })
        compartida.sudo().write({'company_id': False})

        self.assertIn(
            compartida,
            self.env['chatroom.ai.task'].with_user(self.jefe_a).search([]))
        self.assertIn(
            compartida,
            self.env['chatroom.ai.task'].with_user(self.jefe_b).search([]))

    def test_the_cron_still_sees_everything(self):
        """Los crons corren con sudo, que salta las reglas. Si esto
        fallara, el aislamiento habría roto el trabajo de fondo."""
        todas = self.env['chatroom.ai.task'].sudo().search([])

        self.assertIn(self.tarea_a, todas)
        self.assertIn(self.tarea_b, todas)
