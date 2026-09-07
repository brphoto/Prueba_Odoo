# Compatibilidad entre modulos

Notas de convivencia detectadas al probar los modulos instalados juntos en
una misma base. No son errores de un modulo en particular: son choques que
solo aparecen cuando dos modulos tocan la misma vista o el mismo campo.

## l10n_co_payroll y l10n_ec_hr_payroll_19e no pueden convivir

**Sintoma.** Instalar `l10n_ec_hr_payroll_19e` en una base que ya tiene
`l10n_co_payroll` falla con:

```
Element '<xpath expr="//field[@name='line_ids']">' cannot be located in parent view
  en l10n_ec_hr_payroll_19e/views/hr_payroll_view.xml
```

**Causa.** `l10n_co_payroll/views/co_payroll_payslip_views.xml` **renombra**
el campo del recibo de nomina en la vista heredada:

```xml
<xpath expr="//page[@name='salary_computation']/field[@name='line_ids']"
       position="attributes">
    <attribute name="name">visible_line_ids</attribute>
</xpath>
```

A partir de ahi el formulario de `hr.payslip` ya no tiene un campo
`line_ids` en esa pagina, y el xpath del modulo ecuatoriano (que hace
`position="replace"` sobre `//field[@name='line_ids']`) no encuentra su
ancla. El orden de instalacion no importa: si el colombiano queda
aplicado antes, el ecuatoriano no instala.

**Alcance.** Cada modulo, por separado, instala y pasa sus tests sin
problemas. El choque es exclusivamente al tenerlos juntos.

**Que hacer.** No instalar las dos localizaciones de nomina en la misma
base de datos. Son de paises distintos y no hay ningun escenario real que
las necesite a la vez; separar por base de datos (o por empresa en
instalaciones distintas) es lo correcto.

Si en algun momento hiciera falta que convivan, la solucion es cambiar el
xpath del modulo ecuatoriano para que ancle en la pagina en vez de en el
nombre del campo, y que no dependa de como lo haya dejado otro modulo:

```xml
<xpath expr="//page[@name='salary_computation']" position="inside">
```

No se hizo ese cambio porque alteraria la vista de nomina ecuatoriana para
resolver un escenario que no se da.

## Modulos opcionales referenciados sin comprobacion

El patron correcto en este repositorio para depender de un modulo opcional
es comprobar el modelo en el registro:

```python
if 'marketing.vehicle.listing' not in self.env:
    return None
```

Cuidado con la trampa que tenia `marketing_social_agent._vehicle_rows`: la
comprobacion estaba, pero la rama de salida devolvia
`self.env['marketing.vehicle.listing']`, es decir accedia al modelo que
acababa de descartar y lanzaba `KeyError`. Si el modelo no existe hay que
devolver `None` o una lista vacia, nunca un recordset de ese modelo, y el
llamador tiene que tolerarlo antes de usar metodos de recordset
(`.filtered`, `.mapped`).

## Bases de datos de prueba sucias

Instalar y desinstalar modulos repetidamente sobre la misma base deja
columnas `NOT NULL` huerfanas (se vio con `res_partner.group_rfq`, de
`purchase`). El sintoma es un `null value in column ... violates not-null
constraint` en un `INSERT` que ni siquiera menciona esa columna, porque el
ORM ya no conoce el campo pero la columna sigue en la tabla.

No es un error del codigo: antes de dar por bueno un fallo asi, hay que
reproducirlo en una base creada de cero.

## Codificacion de los ficheros: UTF-8 sin BOM y acentos literales

Convencion del repositorio, con el porque de cada parte.

**Todo fichero de texto va en UTF-8 sin marca BOM.** El BOM no rompe hoy
(lxml y Python lo toleran), pero ensucia los diffs, se ve como basura en
editores que no lo esperan y revienta en cuanto algo concatena o
preprocesa el fichero: los tres bytes acaban en mitad del documento.
Aparecio en once XML de `l10n_ec_hr_payroll_19e`, todos del mismo modulo,
que es la firma de un editor configurado en "UTF-8 con BOM".

**Los acentos se escriben tal cual, nunca como escape de seis
caracteres.** Dentro de un literal de Python el escape produce el
caracter correcto y no cambia nada en ejecucion, pero esconde el texto a
quien lee el codigo y a las herramientas de traduccion. Dentro de un
comentario o de un XML es peor: ahi no es un escape, es texto literal
ilegible, del tipo `# La restricci` seguido del codigo en crudo.

Hay una guarda automatica en
`l10n_ec_hr_payroll_19e/tests/test_encoding.py` que falla si vuelve
cualquiera de las dos cosas en ese modulo, con el fichero y la linea. Se
comprobo que detecta ambas regresiones y no pasa en vacio.

Para revisar el repositorio entero, dos comprobaciones:

- BOM: el fichero empieza por los bytes `EF BB BF`.
- Escapes: expresion regular de dos barras invertidas, `u`, y cuatro
  digitos hexadecimales; solo importan los que representan un caracter
  imprimible (codigo mayor o igual a `A0`), porque los de control
  (saltos de linea, tabuladores) si son legitimos.

Vale la pena mirar tambien el mojibake (una "A" con tilde seguida de
un simbolo raro donde deberia haber un acento) , que es UTF-8
leido como latin-1 y vuelto a guardar, y el caracter de reemplazo
`U+FFFD`, que significa que el acento ya se perdio de forma
irrecuperable. Ahora mismo no hay ninguno de los dos.
