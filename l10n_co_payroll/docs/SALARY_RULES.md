# Motor de reglas salariales

Cada version legal (`l10n.co.payroll.parameter`) puede tener reglas propias, ordenadas por secuencia y con codigo unico.

Una regla define:

- Condicion de aplicacion, por ejemplo `worked_days > 0 and basic_wage <= minimum_wage * 2`.
- Formula segura, por ejemplo `min(transport_allowance, basic_wage * 0.10)`.
- Impacto: `earning`, `deduction`, `employer`, `ibc` o `provision`.
- Operacion: `add` para sumar al valor base o `replace` para reemplazarlo.

Variables disponibles: `basic_wage`, `gross_wage`, `deduction_total`, `net_wage`, `worked_days`, `worked_hours`, `ibc_base`, `minimum_wage`, `transport_allowance` y `uvt_value`.

Funciones disponibles:

- `rule('CODIGO')`: resultado de una regla anterior de la misma secuencia.
- `source('CODIGO')`: total del concepto con ese codigo en las lineas del recibo.
- `legal('campo')`: valor de otro parametro legal, por ejemplo `legal('health_employee_rate')`.
- `min`, `max`, `abs`, `round`, `int`, `float`, `ceil`, `floor`.

El motor bloquea imports, atributos, acceso a objetos y funciones no autorizadas. Al preparar el periodo guarda cada resultado, condicion y formula por empleado para auditoria.
