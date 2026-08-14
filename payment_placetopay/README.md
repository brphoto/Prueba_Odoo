# PlacetoPay para Odoo 19

Proveedor de pago para el checkout de Odoo 19 usando el **Web Checkout** de
[PlacetoPay](https://docs.placetopay.dev/checkout) (Evertec). El cliente es
redirigido a la página alojada por PlacetoPay, paga con tarjeta, PSE, Baloto,
Efecty u otros medios habilitados en su cuenta, y vuelve a Odoo con el estado
final de la transacción.

## Configuración

1. Copiar `payment_placetopay` dentro de un directorio incluido en
   `addons_path`.
2. Actualizar la lista de aplicaciones e instalar
   **Payment Provider: PlacetoPay**.
3. Ir a **Contabilidad/Ventas > Configuración > Proveedores de pago >
   PlacetoPay**.
4. Completar:
   - **PlacetoPay Login** y **PlacetoPay Secret Key**: credenciales
     entregadas por PlacetoPay (una pareja para pruebas y otra para
     producción).
   - **PlacetoPay Base URL**: `https://checkout-test.placetopay.com` para el
     entorno sandbox. En producción use el host asignado a su cuenta
     (por ejemplo `https://checkout-co.placetopay.com` para Colombia o
     `https://checkout.placetopay.ec` para Ecuador; confírmelo con
     PlacetoPay).
   - **Checkout Language**: idioma/país mostrado en la pasarela.
   - **Default Document Type**: tipo de documento por defecto para el pagador
     cuando el cliente no tiene uno más específico configurado.
5. Publicar el proveedor y probar con las tarjetas de prueba entregadas por
   PlacetoPay.

## Funcionamiento

- Al iniciar el pago, el módulo crea una sesión vía `POST /api/session`
  firmada con el algoritmo de autenticación de PlacetoPay
  (`tranKey = Base64(SHA-256(nonce + seed + secretKey))`) y redirige al
  cliente al `processUrl` devuelto.
- Al volver del checkout, Odoo consulta `GET /api/session/{requestId}` para
  obtener el estado definitivo de la transacción (aprobada, rechazada o
  pendiente) y actualiza la transacción de Odoo.
- Como PlacetoPay Checkout no ofrece un webhook servidor-a-servidor, un cron
  (`PlacetoPay: Consultar pagos pendientes`, cada 2 minutos) vuelve a
  consultar cualquier transacción que haya quedado pendiente por si el
  navegador nunca regresó a Odoo.

## Notas

- El módulo no implementa reembolsos ni tokenización de tarjetas: la API de
  sesión documentada para Checkout no expone esos endpoints; si su cuenta los
  soporta mediante otro producto de PlacetoPay, deberán añadirse aparte.
- Los códigos de estado (`APPROVED`, `REJECTED`, `PENDING`,
  `PENDING_VALIDATION`, `FAILED`, `REJECTED_BY_PAYER`, `ABANDONED`) siguen la
  documentación pública de PlacetoPay; verifique con su ejecutivo de cuenta si
  su integración usa códigos adicionales y ajuste `const.py` si es necesario.
