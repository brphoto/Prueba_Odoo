# Plan de calidad y pruebas

## Flujo principal

- Crear un periodo mensual, quincenal, semanal y extraordinario.
- Verificar filtros por empleado, departamento, cargo, estructura y lote.
- Preparar el periodo y confirmar consolidado por empleado, totales y comparación.
- Validar un recibo pendiente, sin contrato, sin identificación, con neto negativo y con deducciones superiores al devengado.
- Corregir el origen, preparar nuevamente y cerrar desde Supervisor.

## Aprobaciones parametrizables

- `Sin aprobación adicional`: permite cerrar cuando no existan bloqueantes.
- `Una aprobación`: requiere una aprobación de Supervisor.
- `Doble aprobación`: requiere dos Supervisores distintos.
- `Bloquear advertencias`: convierte las advertencias en un control obligatorio de cierre.
- `Exigir aprobación de novedades`: controla novedades pendientes antes de aprobar o cerrar.

## Seguridad

- Usuario: opera periodos y novedades, pero no modifica el resumen calculado ni los hallazgos.
- Supervisor: configura parámetros, aprueba, rechaza, cierra y cancela.
- Auditor: consulta información sin permisos de modificación.
- Las reglas de registros restringen la información a las compañías permitidas.

## Salidas

- CSV consolidado por empleado.
- CSV de auditoría PILA con IBC de referencia, tipo/subtipo y estado.
- PDF del resumen del periodo.
- La exportación PILA cambia el estado de las líneas a `Exportado`.
