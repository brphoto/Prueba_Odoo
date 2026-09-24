# -*- coding: utf-8 -*-
"""Pruebas del conector de PlacetoPay.

El módulo no tenía ninguna. Lo que se cubre es la autenticación, que es
la parte que rompe de forma silenciosa: si el `tranKey` se calcula mal,
PlacetoPay rechaza todas las peticiones sin decir por qué, y si el
`nonce` se repitiera dejaría de ser de un solo uso.

La fórmula está en la documentación de PlacetoPay:
    tranKey = Base64(SHA-256(nonce + seed + secretKey))
    nonce   = Base64(nonce en claro)
Aquí se recalcula por separado y se compara, para que un cambio en el
código no pueda desviarse de la especificación sin que salte el test.
"""
import base64
import hashlib
from datetime import datetime, timezone

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPaymentPlacetopay(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref(
            'payment_placetopay.payment_provider_placetopay')
        cls.provider.write({
            'state': 'test',
            'placetopay_login': 'qa-login',
            'placetopay_secret_key': 'qa-secret',
        })

    # ------------------------------------------------------------------
    # Autenticación
    # ------------------------------------------------------------------

    def test_auth_object_has_the_four_required_keys(self):
        auth = self.provider._placetopay_build_auth()
        self.assertEqual(set(auth), {'login', 'tranKey', 'nonce', 'seed'})
        self.assertEqual(auth['login'], 'qa-login')

    def test_tran_key_matches_the_documented_formula(self):
        """Si esto se desvía, PlacetoPay rechaza todo sin explicar nada."""
        auth = self.provider._placetopay_build_auth()
        raw_nonce = base64.b64decode(auth['nonce']).decode()
        expected = base64.b64encode(hashlib.sha256(
            (raw_nonce + auth['seed'] + 'qa-secret').encode()).digest()).decode()
        self.assertEqual(auth['tranKey'], expected)

    def test_nonce_is_single_use(self):
        """El nonce tiene que ser distinto en cada petición."""
        nonces = {self.provider._placetopay_build_auth()['nonce']
                  for _ in range(10)}
        self.assertEqual(
            len(nonces), 10, 'El nonce se repitió entre peticiones.')

    def test_seed_is_a_current_iso_timestamp(self):
        """PlacetoPay rechaza una semilla de más de cinco minutos."""
        auth = self.provider._placetopay_build_auth()
        seed = datetime.fromisoformat(auth['seed'])
        delta = abs((datetime.now(timezone.utc) - seed).total_seconds())
        self.assertLess(
            delta, 300, 'La semilla debería ser del momento de la petición.')

    def test_auth_requires_credentials(self):
        """Odoo ya impide vaciar el login con el proveedor activo, asi que
        primero se desactiva; lo que se comprueba aqui es la guarda propia
        del modulo, no la del core."""
        self.provider.write({'state': 'disabled'})
        self.provider.write({'placetopay_login': False})
        with self.assertRaises(ValidationError):
            self.provider._placetopay_build_auth()

    # ------------------------------------------------------------------
    # Caducidad de la sesión de pago
    # ------------------------------------------------------------------

    def test_expiration_is_in_the_future(self):
        expiration = datetime.fromisoformat(
            self.provider._placetopay_expiration())
        self.assertGreater(expiration, datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Endpoint
    # ------------------------------------------------------------------

    def test_activating_in_production_with_the_sandbox_url_is_blocked(self):
        """El host de producción depende de la región y hay que ponerlo a
        mano. Sin esta guarda, activar el proveedor sin cambiarlo dejaba
        los cobros yendo al sandbox: la pasarela responde que todo fue
        bien y el dinero no se mueve."""
        self.provider.write({'state': 'test'})
        with self.assertRaises(ValidationError):
            self.provider.write({'state': 'enabled'})

    def test_activating_in_production_with_a_real_host_is_allowed(self):
        self.provider.write({
            'placetopay_base_url': 'https://checkout.placetopay.ec',
            'state': 'enabled',
        })
        self.assertEqual(
            self.provider._placetopay_get_base_url(),
            'https://checkout.placetopay.ec')
