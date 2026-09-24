from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestMarketingCommandCenterTour(HttpCase):
    """Prueba de humo del centro de mando en un navegador real.

    Los tests de ORM comprueban que el modelo recalcula; este comprueba
    que en pantalla ocurre de verdad: que la vista compila, que el
    formulario monta y que la secuencia elegir filtro → guardar deja los
    indicadores actualizados sin pasar por «Actualizar indicadores».

    Fue este tour el que destapó que el administrador no pertenecía a
    ningún grupo de marketing y recibía un AccessError al abrir el menú.
    """

    def test_marketing_command_center_tour(self):
        dashboard = self.env.ref(
            'marketing_command_center.marketing_social_dashboard_main')
        # Los datos se siembran aquí y no desde el botón del formulario:
        # así el tour no depende del refresco de la vista tras la acción y
        # se concentra en lo que se quiere comprobar.
        dashboard.action_seed_demo_data()
        dashboard.write({'platform_filter': 'all', 'period_days': 30})
        dashboard.action_refresh()
        self.assertTrue(
            dashboard.publication_count,
            'El fixture del tour debería dejar publicaciones contadas.')
        self.env.flush_all()

        self.start_tour(
            '/odoo/action-marketing_command_center.action_marketing_social_dashboard',
            'marketing_command_center_tour',
            login='admin',
        )
