# Históricos Comerciales para RFM

Módulo independiente para cargar compras históricas sin crear pedidos,
productos ni facturas en Odoo.

## Flujo

1. Ir a `Inteligencia comercial > Configuración > Históricos comerciales > Cargas históricas`.
2. Crear un lote y adjuntar un `.csv` o `.xlsx`.
3. Usar la plantilla incluida o cargar las columnas equivalentes.
4. Importar, revisar errores y duplicados.
5. Aprobar el lote para alimentar RFM/ABC.

Columnas soportadas: cliente, RUC/identificación, código externo, correo,
teléfono, número de factura, fecha, monto, moneda y tipo de movimiento.
Los nombres de columnas aceptan variantes en español e inglés.

Los históricos aprobados se suman a la facturación actual para Recencia,
Frecuencia y Monto. No se enlazan con `sale.order`, `account.move.line` ni
productos. Cada registro conserva lote, fila de origen y huella para detectar
recargas duplicadas.

En el contacto se puede fijar una categoría RFM manual, guardar el motivo y
dejar que esa categoría prevalezca sobre el cálculo automático.
