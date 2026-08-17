# Nómina Colombia

Módulo operativo para Odoo 19 que consolida la nómina calculada por `hr_payroll` en un producto independiente. No depende de módulos DIAN, nómina electrónica, XML, SOAP, certificados ni servicios externos.

El nombre técnico del producto es `l10n_co_payroll`. Se conserva el nombre de los modelos internos `l10n.co.payroll.*` para facilitar la continuidad de datos y desarrollos.

## Qué incluye

- Panel kanban y listado de periodos con estados, indicadores y hallazgos.
- Asistente guiado para crear periodos mensuales, quincenales, semanales o extraordinarios.
- Filtros por empleado, departamento, cargo, estructura salarial y lote de nómina.
- Consolidado por empleado con devengados, deducciones, neto, aportes, días y horas.
- Validaciones antes del cierre: recibos sin validar, ausencia de contrato, salario básico cero, neto negativo y deducciones superiores al devengado.
- Comparación contra el último periodo cerrado y variación del neto.
- Auditoría de preparación, validación y cierre.
- Exportación CSV y resumen PDF corporativo.
- Parámetros anuales configurables para salario mínimo, auxilio, UVT y tasas de referencia.
- Flujo de aprobación configurable: sin aprobación adicional, una aprobación o doble aprobación con usuarios distintos.
- Novedades laborales con aprobación: ingresos, retiros, incapacidades, licencias, vacaciones, suspensiones y variaciones.
- Base IBC de referencia, estado PILA y provisiones configurables de cesantías, intereses, vacaciones y prima.
- Exportación de auditoría PILA en CSV para revisión o adaptación al operador elegido.
- Parámetros de jornada y recargos para extender el cálculo operativo sin acoplarlo a servicios externos.
- Perfiles separados para usuario, supervisor y auditor, con reglas por compañía.

## Flujo recomendado

1. Abrir **Nómina Colombia > Crear periodo** o **Panel**.
2. Definir frecuencia, rango, fecha de pago y filtros opcionales.
3. Pulsar **Preparar / actualizar**.
4. Revisar el resumen, la comparación y la pestaña **Validaciones**.
5. Corregir los recibos en la nómina estándar de Odoo.
6. Volver a preparar, validar y cerrar desde el perfil supervisor.
7. Descargar CSV o imprimir el PDF.

La exportación PILA marca las líneas como **Exportado** para dejar trazabilidad. Antes de exportar se puede usar **Marcar PILA revisada**; el archivo es una base de auditoría y debe adaptarse al operador PILA y a la parametrización vigente.

## Instalación y actualización

1. Copia `l10n_co_payroll` dentro de la carpeta de addons de Odoo.
2. Activa el modo desarrollador y actualiza la lista de aplicaciones.
3. Instala o actualiza **Nómina Colombia**.
4. Asigna los perfiles Usuario, Supervisor y Auditor según la responsabilidad de cada persona.

Las pruebas automatizadas se ejecutan con `--test-enable --stop-after-init --workers=0`. El módulo no crea datos laborales ficticios en producción; los escenarios de prueba crean sus propios empleados, recibos, novedades y parámetros.

Los importes se toman de las líneas calculadas por `hr_payroll`: básico, devengado, deducciones (`DED`), neto y aportes de empresa (`COMP`). Los parámetros anuales son de referencia y deben ser mantenidos por el responsable laboral/contable; no reemplazan una revisión legal.

## Capacidades empresariales incluidas

- Versiones legales por vigencia, empresa y periodo, con activación, archivo, soporte normativo y mapeo de reglas salariales.
- Perfiles PILA por empleado y vigencia: tipo y subtipo de cotizante, EPS, AFP, ARL, caja y clase de riesgo.
- Archivo PILA configurable por operador, delimitador, codificación, encabezado y formato CSV o ancho fijo. La parametrización debe mantenerse con la ficha técnica vigente del operador elegido.
- Ajustes aprobables para retroactivos, anticipos, préstamos, embargos y otros conceptos, con aplicación controlada al periodo.
- Liquidaciones definitivas con cálculo de salarios pendientes, cesantías, intereses, vacaciones, primas y deducciones.
- Asientos contables de nómina y provisiones, con cuentas configurables por compañía y trazabilidad al periodo.
- Lotes bancarios exportables, selección de cuentas de empleado y control de beneficiarios sin cuenta configurada.
- Bitácora de auditoría para preparación, aprobaciones, cierre, exportaciones, contabilidad, pagos, PILA y liquidaciones.

El producto está diseñado para operar sin servicios DIAN, XML, certificados, SOAP ni conexiones electrónicas externas. Las tarifas, topes, códigos y estructuras de PILA deben ser revisados y actualizados por el responsable laboral antes de usarlos en producción.

## Complementos opcionales

- `l10n_co_payroll_documents`: documentos laborales, certificados y archivos visibles de forma controlada.
- `l10n_co_payroll_portal`: autoservicio de empleados, desprendibles y solicitudes de vacaciones, permisos o cambios de datos. Este módulo es opcional y no se instala con el núcleo.

El núcleo también incorpora calendario, tareas operativas, reglas de validación por empresa, simulador salarial, sandbox, historial salarial, préstamos, embargos, conciliación bancaria y analítica de costos.
