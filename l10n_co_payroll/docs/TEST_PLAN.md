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

## Matriz exhaustiva implementada

- Las 2 estructuras salariales (`CO_ORDINARIA` y `CO_INTEGRAL`) deben tener las 37 reglas colombianas enlazadas al motor nativo; mensual, quincenal, semanal y extraordinaria se prueban como tipos de periodo.
- Las 22 entradas de novedades se evalúan con valores positivos y se verifica su impacto en devengados, deducciones, IBC y aportes.
- Se prueban los 4 tipos de periodo: mensual, quincenal, semanal y extraordinario.
- Se prueban límites de IBC ordinario e integral, fondo de solidaridad y las clases de riesgo I y V.
- Cada frecuencia se prepara en sandbox y genera/prevalida un documento DIAN y un archivo PILA sin transmisión real.
- El catálogo debe pasar con 0 reglas inválidas, 0 errores de prueba y 0 hallazgos bloqueantes en los casos válidos.
- Se prueban fórmulas de liquidación definitiva sobre 360 días, intereses proporcionales, incapacidades por tramos, tabla de retención UVT y vencimiento DIAN.
- La suite automatizada actual reporta 28 pruebas post-instalación, 0 fallos y 0 errores en la base demo y en la base de humo con los módulos propios instalados.
