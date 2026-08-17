# Parametrización colombiana predeterminada

El módulo carga una base operativa para Colombia al instalarse en una base nueva. La parametrización se organiza por vigencia legal; no se deben mezclar valores de años diferentes en un mismo periodo.

## Estructuras salariales incluidas

- Nómina colombiana ordinaria (`CO_ORDINARIA`): reglas para salarios ordinarios.
- Nómina colombiana de salario integral (`CO_INTEGRAL`): reglas para salarios integrales.

## Tipos o frecuencias de nómina

El periodo de nómina define el tipo o frecuencia de liquidación, independiente de la estructura salarial:

- Mensual.
- Quincenal.
- Semanal.
- Extraordinaria.

La frecuencia de pago no cambia el envío de nómina electrónica: los pagos quincenales o semanales se consolidan en el documento soporte de pago de nómina electrónica del periodo mensual correspondiente.

## Conceptos y reglas cargados

Se crean reglas para salario básico, auxilio de transporte, horas extra diurnas y nocturnas, trabajo dominical o festivo, recargo nocturno, comisiones, bonificaciones salariales y no salariales, IBC, salud, pensión, fondo de solidaridad pensional, retención, embargos, anticipos, préstamos, otras deducciones, aportes patronales, ARL, caja, SENA, ICBF, vacaciones, incapacidades, licencias, prima, cesantías, intereses de cesantías y reintegros.

También se crean entradas de nómina con códigos reutilizables para novedades (`HED`, `HEN`, `HDF`, `RN`, `COMISION`, `BONO_SAL`, `BONO_NOSAL`, `RETENCION`, `EMBARGO`, `ANTICIPO`, `PRESTAMO`, `OTRAS_DED`, `VAC_PAGADA`, `INCAPACIDAD`, `LIC_MAT`, `LIC_PAT`, `LIC_REM`, `AUSENCIA`, `PRIMA_PAGO`, `CESANTIA_PAGO`, `INTERES_CESANT` y `REINTEGRO`).

## Valores legales versionados

La versión 2026 incluida contiene salario mínimo, auxilio de transporte, UVT, jornada semanal, IBC mínimo y máximo, salario integral, porcentajes de salud y pensión, solidaridad, ARL por clase de riesgo, caja, SENA, ICBF, recargos y provisiones. Los campos de exoneración de salud, SENA e ICBF y la retención en la fuente son parametrizables por empresa y no se activan sin soporte.

Las reglas predeterminadas se identifican internamente como reglas del producto. Si una empresa modifica una regla, esa modificación se conserva; las nuevas versiones legales pueden revisarse y aprobarse sin alterar periodos ya cerrados.

## Configuración necesaria antes de producción

La carga predeterminada deja el módulo listo para parametrizar, pero cada empresa debe completar y revisar:

- NIT, tipo de documento, responsabilidades fiscales y datos de la compañía.
- Códigos reales de EPS, AFP, ARL y caja de compensación para cada colaborador.
- Clase y tarifa de riesgo laboral, salario integral, tipo y subtipo de cotizante.
- Calendario, centros de costo, cuentas contables y método de pago.
- Credenciales, certificado, ambiente y rangos autorizados de nómina electrónica ante la DIAN.
- Operador PILA, novedades y reglas particulares de retención o embargos.

El envío DIAN y la PILA se prueban localmente con prevalidación, pero la habilitación real requiere credenciales, certificado y pruebas autorizadas por la empresa. El módulo no debe presentar valores demo como producción.

## Controles legales incorporados

- Liquidación definitiva con cesantías y prima sobre 360 días, intereses de cesantías al 12% anual proporcional y vacaciones a 15 días por año, todo versionado.
- Incapacidades con tramos configurables y trazabilidad del responsable: empleador, EPS, ARL o AFP; se conserva certificado y soporte.
- Horas extra y recargos con acumulación de HED, HEN, HDF y RN, límites preventivos diario/semanal y alerta cuando se requiere autorización.
- Tabla base de retención en UVT por rangos del artículo 383 del Estatuto Tributario. La empresa puede editar la versión legal y sustituir el cálculo con una entrada soportada.
- PILA con catálogo de tipo/subtipo de cotizante, códigos de novedad y redondeo a peso para los importes exportados.
- Vencimiento DIAN visible en cada periodo: primeros diez días del mes siguiente, con estado en plazo, próximo a vencer o vencido.
- Marco pensional seleccionable para conservar la operación vigente parametrizada mientras se revisan cambios normativos.

## Fuentes para revisión anual

La parametrización debe ser revisada por el responsable laboral y tributario de la empresa frente a la norma vigente. Referencias iniciales: [Resolución DIAN 0013 de 2021](https://normograma.dian.gov.co/dian/compilacion/docs/resolucion_dian_0013_2021.htm), [Resolución DIAN 227 de 2025](https://normograma.dian.gov.co/dian/compilacion/docs/resolucion_dian_0227_2025.htm), [Resolución UGPP 467 de 2025](https://www.ugpp.gov.co/wp-content/uploads/2025/05/Resolucion_467_de_2025.pdf), [Ley 2466 de 2025](https://www.suin-juriscol.gov.co/viewDocument.asp?ruta=Leyes%2F30055086), [Ley 52 de 1975](https://www.suin-juriscol.gov.co/viewDocument.asp?ruta=Leyes%2F1606193) y [Código Sustantivo del Trabajo](https://www.suin-juriscol.gov.co/viewdocument.asp?ruta=codigo%2F30019323).
