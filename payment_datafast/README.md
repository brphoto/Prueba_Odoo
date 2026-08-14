# Datafast para Odoo 19

Proveedor de pago para el checkout de Odoo 19 usando el widget alojado de
Datafast Dataweb/OPPWA.

## Configuración

1. Copiar `payment_datafast` dentro de un directorio incluido en `addons_path`.
2. Actualizar la lista de aplicaciones e instalar **Payment Provider: Datafast**.
3. Ir a **Contabilidad > Configuración > Proveedores de pago > Datafast**.
4. En modo de prueba completar las credenciales `entityId`, `Authorization`, MID,
   TID y el nombre del comercio proporcionados por Datafast.
5. Configurar la URL de pruebas indicada por Datafast, normalmente
   `https://test.oppwa.com` o `https://eu-test.oppwa.com`.
6. Activar **Permitir tokenización** si se van a guardar tarjetas para pagos
   posteriores o recurrentes.
7. Publicar el proveedor y probar únicamente con las tarjetas y montos de prueba.

El cliente debe tener nombre, identificación, correo, teléfono y dirección de
facturación porque Datafast los solicita en la fase final de certificación.

## Funciones incluidas

- Checkout alojado Dataweb con VISA, Mastercard, Diners, Discover y AMEX.
- Envío de los campos obligatorios de identificación, dirección, carrito y
  desglose tributario ecuatoriano.
- Tokenización OneClickCheckout: creación, pago con token y eliminación remota.
- Reembolsos/anulaciones parciales mediante `paymentType=RF`.
- Botón de verificación manual por referencia cuando el navegador no vuelve a
  Odoo.

## Producción

Datafast debe certificar el desarrollo antes de habilitarlo en producción. En
ese momento se deben sustituir la URL, `entityId`, autorización, MID y TID por
los valores de producción entregados por Datafast, eliminar el modo de prueba
y coordinar la transacción de salida a producción con Datafast.

La integración cubre Dataweb/OPPWA. Nativa y MSDK son productos distintos de
Datafast con hardware, SDK y credenciales propias.
