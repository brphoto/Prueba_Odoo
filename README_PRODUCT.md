# Nómina Colombia - producto reutilizable

Este directorio contiene únicamente el producto propio para nuevos clientes. No incluye migradores ni modificaciones de `nav_dian`, `nav_nomina` o `fix_extructuras_de_pago`.

## Flujo recomendado

1. Ejecutar **Parametrización inicial**.
2. Cargar catálogos desde **Carga masiva** o usar el asistente **Vincular empleado a PILA**.
3. Crear el periodo con **Preparar y validar automáticamente**.
4. Revisar el diagnóstico integral.
5. Generar PILA, asiento contable y lote de pagos.
6. Exportar al operador/banco, conciliar y cerrar con checklist.

## Carga masiva

Se admite CSV separado por `;`, tabulador o `,`, y Excel `.xlsx` cuando está disponible `openpyxl`.

Tipos y columnas mínimas:

- Empleados: `identificacion;nombre`
- Administradoras: `tipo;codigo;nombre`
- Centros de costo: `codigo;nombre`
- Perfiles PILA: `identificacion;vigente_desde;cobertura;eps;pension;arl;caja;referencia`
- Cuentas bancarias: `identificacion;cuenta;banco`

Primero usar **Solo validar**. Las cargas se procesan por compañía y actualizan por clave natural; no crean duplicados de empleados, administradoras o centros de costo.

## Formatos externos

Los formatos PILA y bancarios son configurables por operador: delimitador, codificación, encabezados, terminador de línea, prefijo y referencia técnica. Cada cliente debe cargar la versión técnica vigente que le entregue su operador antes de transmitir o cargar archivos en producción.
