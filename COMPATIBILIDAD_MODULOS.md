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

## Traducciones evaluadas al importar el modulo

Odoo resuelve `_()` contra el idioma del usuario en curso. En el cuerpo
de un modulo o de una clase todavia no hay usuario: Odoo escribe en cada
arranque un aviso con traza ("no translation language detected") y el
texto queda congelado en el idioma fuente para toda la instalacion, sin
importar el idioma de quien lo lea.

El caso encontrado estaba en `chatroom_ai_usage`: un diccionario
`_SCENARIOS` con los cinco guiones del simulador de IA, definido en el
cuerpo de la clase. Se movio a `_get_scenarios()`, que los traduce en el
momento de usarlos.

Una etiqueta de campo (`string=`, `help=`, las opciones de una
`Selection`) es distinta y **no** hay que tocarla: la recoge la
maquinaria de `ir.model.fields`, que si traduce por usuario. Envolverlas
en `_()` es redundante pero inofensivo, y reescribir las casi 500 que hay
en el repositorio seria ruido puro en el diff.

Para distinguir una cosa de la otra hace falta AST, no `grep`: hay que
saber si la llamada cuelga de un `fields.X(...)` y si esta dentro de un
`def` o de un `lambda` (esos corren despues, y son correctos). El
escaner que hice se valido primero contra un fichero de prueba con dos
casos reales y cuatro falsos positivos, para confirmar que no daba cero
por estar roto. Sobre el repositorio ahora da cero de verdad.

## Bases de datos para correr las pruebas

- `qa_opt_20260907` es la buena: tiene el stack de chatroom instalado y
  carga sin problemas.
- `starir_chatroom_demo` y `starir_chatroom_demo_stairs_test` **no
  cargan el registro**. La columna `res_users.login` quedo como
  `character varying` donde el ORM de 19 espera `jsonb`, asi que
  cualquier arranque muere en `operator does not exist: character
  varying ->> unknown`. Es una migracion a medias de la propia base, no
  tiene nada que ver con el codigo: falla igual sin ningun cambio
  encima. No perder tiempo depurando pruebas ahi.
- `Prueba19` existe pero tiene todo desinstalado; da "0 tests".

Invocacion que funciona, desde Git Bash (sin las dos variables, MSYS
convierte `/chatroom_ui` en `C:/Program Files/Git/chatroom_ui` y Odoo
responde `Invalid tag`, que en el log de nivel `warn` ni se ve):

    export MSYS2_ARG_CONV_EXCL="*" MSYS_NO_PATHCONV=1
    python odoo-bin -c odoo.conf -d qa_opt_20260907 \
      -u <modulos> --test-enable --test-tags "/<modulo>,..." \
      --stop-after-init --log-level=warn --log-handler "odoo.tests:INFO"

El `--log-handler` es lo que hace visible el recuento; con `warn` a secas
la linea "N failed, M error(s) of K tests" no se imprime y no hay forma
de distinguir "todo verde" de "no corrio nada". Desde PowerShell, en
cambio, no conviene redirigir `2>&1` de un ejecutable nativo: envuelve
cada linea de stderr en un ErrorRecord y el log sale troceado.

## `_()` en un `@staticmethod` tampoco traduce

`_()` averigua el idioma mirando el `self.env` del marco de quien llama.
En un metodo estatico no hay `self`, asi que Odoo no encuentra idioma:
escribe un aviso con traza en CADA llamada y devuelve el texto sin
traducir. El caso estaba en `chatroom_whatsapp`,
`chatroom_meta_mixin._format_relative_time` ("Hace 5 min", "Nunca"...),
que ademas se llama en cada refresco de los indicadores de salud.

Pasarlo a metodo de instancia fue suficiente y no toco ningun sitio de
llamada: las dos llamadas ya eran `self._format_relative_time(...)`.

Forma de comprobarlo: contar `no translation language detected` en el log
de una vuelta completa de pruebas. Antes salia; ahora sale cero.

## Bases de datos: el entorno las crea y las borra solo

Durante una sesion de trabajo desaparecieron `qa_opt_20260907`,
`qa_ec_20260907` y las dos `starir_chatroom_demo*`, y aparecieron otras
(`chatroom_real_qa_20260906`, `demo17`, `nominaec19`). Una base creada a
proposito para probar llego a borrarse a los pocos segundos, antes de
terminar de instalarse. Hay varios procesos de Python vivos que tocan
PostgreSQL.

Consecuencia practica: no conviene apoyarse en que una base concreta
siga existiendo entre una vuelta de pruebas y la siguiente. Lo fiable es
crear una base propia al empezar:

    python odoo-bin -c odoo.conf -d qa_<lo_que_sea> \
      -i chatroom_whatsapp,chatroom_ui,chatroom_payment,\
chatroom_payment_payphone,chatroom_ai_odoo_bridge,stock,sale_management,web_tour \
      --stop-after-init

Los tres ultimos no son dependencias declaradas, pero hacen falta para
que la suite corra entera:

- Sin `stock` no existe `product.product.is_storable` y el test del
  catalogo muere con `ValueError: Invalid field`.
- Sin `sale_management` no hay pedidos de venta para los enlaces de pago.
- Sin `web_tour` no hay registro de recorridos.

Aun con los tres, el recorrido de navegador `chatroom_app_smoke_tour`
sigue sin arrancar en una base recien creada: `isTourReady` nunca se pone
a cierto, o sea que el paquete `web.assets_tests` no llega a la pagina.
No es una regresion del codigo -falla igual sin ningun cambio encima, y
el JS del recorrido esta bien-, pero queda sin resolver: hace falta una
base con el contenido que tenia la original para reproducir el entorno
donde si pasaba.

## Dependencia invertida: `hr.employee.address_home_id`

`l10n_ec_hr_payroll_19e` leia `address_home_id` en doce sitios y
`l10n_co_payroll` en uno mas. Ese campo no existe en Odoo 19 y tampoco lo
declaran esos modulos: lo anade `website_ausencias_19e`, **que a su vez
depende de `l10n_ec_hr_payroll_19e`**. O sea que el modulo de abajo usaba
un campo del de arriba.

Instalando solo la nomina, esos trece caminos morian: once con
`AttributeError` y dos con "Invalid field" (una busqueda y un create, que
usan el NOMBRE del campo y no su valor). Funcionaban unicamente por
casualidad, cuando el otro modulo estaba puesto.

Ahora todo pasa por dos ayudantes de `hr.employee`:

- `_payroll_partner()` devuelve el contacto y respeta el campo antiguo
  cuando existe, para no mover ni un asiento donde ya funcionaba.
- `_payroll_partner_field()` devuelve el NOMBRE del campo.

### El relacionado de solo lectura que se tragaba las escrituras

`address_home_id` esta declarado como `related='partner_id'` sin
`readonly=False`, y en Odoo un relacionado es de solo lectura por
defecto. Escribir en el **se descarta sin decir nada**. La importacion de
empleados desde la hoja de calculo hacia exactamente eso, asi que cada
empleado creado ahi se quedaba sin contacto, y luego la busqueda de
`create_news` no lo encontraba nunca.

Por eso `_payroll_partner_field()` no devuelve el relacionado sino el
campo real al que apunta (`partner_id`, o `work_contact_id` cuando el
modulo antiguo no esta): leerlo da el mismo valor, pero este si se puede
escribir y buscar.

La leccion general: antes de escribir o de buscar por un campo, mirar si
es `related` y si es `readonly`. Un `create` con un campo de solo lectura
no falla, simplemente pierde el dato.

## Los `_()` de las etiquetas de campo: 900 avisos por arranque

Antes se descarto tocarlos por considerarlos ruido de diff, y se hizo sin
medir. Medido: un arranque a nivel `warn` escribia **900** avisos "no
translation language detected", cada uno con su traza, y el log pasaba de
**26.000 lineas**. Con eso, cualquier aviso de verdad queda enterrado.

Envolver `string=` o `help=` en `_()` no aporta nada: quien traduce esos
dos es la maquinaria de `ir.model.fields`, que si conoce el idioma de
cada usuario. Se quitaron 368 llamadas en 36 ficheros, todas de
`l10n_ec_hr_payroll_19e`. Los avisos bajaron de 900 a 198.

Como se comprobo que no cambia nada: se volcaron la etiqueta y la ayuda
de los **17.922 campos** del registro antes y despues, y se compararon.
Cero diferencias.

Dos trampas del reescritor, por si hay que repetirlo:

- `ast` da `col_offset` en **bytes UTF-8**, no en caracteres. Este
  repositorio esta lleno de acentos, asi que contando caracteres los
  cortes caen desplazados y dejan parentesis sin cerrar. Hay que
  trabajar sobre los bytes del fichero.
- Solo es seguro quitar `_("literal")` cuando es argumento DIRECTO de un
  `fields.Algo(...)`. Los que llevan formato (`_("%s") % x`), los que
  reciben una variable, los de dentro de un `lambda` y los que estan
  dentro de la lista de una `Selection` no se tocan: unos siguen siendo
  necesarios y otros se evaluan mas tarde.

Los 198 que quedan son de esas categorias.

## Auditoria del registro: lo que salio limpio

Merece la pena dejar constancia de lo que NO hay, para no volver a
buscarlo. Inspeccionando el registro cargado (mucho mas fiable que
analizar el texto) sobre los 97 modelos propios:

- 0 campos calculados y almacenados sin `depends`.
- 0 `depends` que apunten a un campo inexistente.
- 0 modelos sin ninguna regla de acceso.
- Los 2 `_order` sobre campos no almacenados son de modelos del nucleo
  (`payment.provider`, `res.users`), no de este repositorio.

Un aviso sobre como medir esto: los `depends` que se declaran con el
decorador `@api.depends` **no** estan en `campo._depends`, que solo se
rellena cuando se pasa `depends=` al construir el campo. Hay que usar
`campo.get_depends(modelo)`. Mirar el atributo a secas daba 15 falsos
positivos, entre ellos campos que si tenian su decorador.

## El puerto 8019 compartido: por que los tests de navegador "fallan solos"

Sintoma: los recorridos de navegador (`chatroom_app_smoke_tour`,
`marketing_command_center_tour`) fallan con

    The ready "odoo.isTourReady('...')" code was always falsy

unas veces si y otras no, y el test `TestPortalSecurity` del portal de
ausencias devuelve 404 en una ruta que existe.

Causa: hay OTRO Odoo escuchando en el puerto 8019, el que se arranca
desde VS Code con el depurador, desde una instalacion distinta
(`C:\Users\Bryan\Desktop\odoo19e\server`) y con otra configuracion. En
Windows dos procesos pueden quedarse con el mismo puerto sin que ninguno
de en el error "address already in use": las conexiones se reparten entre
ambos de forma impredecible.

Cuando la peticion de `url_open` cae en el servidor del depurador, este
responde desde otra base y otro `addons_path`: la ruta del portal no
existe alli (404) y la pagina que devuelve no registra ningun recorrido
(`isTourReady` nunca se pone a cierto).

No es un fallo del codigo. Se descarto midiendo: assets en frio, con y
sin `-u`, en aislamiento y dentro de la suite completa. Lo que lo
resuelve es usar un puerto propio:

    python odoo-bin -c odoo.conf -d qa_<base> --http-port=8791 \
      --max-cron-threads=0 --test-enable --test-tags "/<modulo>" \
      --stop-after-init --log-level=warn --log-handler "odoo.tests:INFO"

Con el puerto propio la suite entera (311 tests de chatroom, marketing,
CRM, nomina y POS) pasa en verde y los recorridos dejan de ser
intermitentes.

`--max-cron-threads=0` tambien hace falta: sin el, el planificador de
tareas del otro proceso compite por las filas de `ir_cron` y el arranque
puede morir con "could not serialize access due to concurrent update".

## Renombrado de `marketing_command_center_patiotuerca`

El modulo no tenia nada especifico de Patiotuerca: importa un feed JSON
generico por endpoint o por fichero, hace upsert por id externo y lleva
estados publicado/despublicado/sin actualizar. Se renombro a
`marketing_command_center_catalog`, y el modelo de conexion pasa de
`marketing.patiotuerca.connection` a `marketing.catalog.connection`.

Lo que NO se toco: el valor `('patiotuerca', 'Patiotuerca')` del campo
"Origen". Nombra un portal real y hay filas guardadas con el; quitarlo
las dejaria con un valor de seleccion que ya no existe. Se anadio
`('external', 'Catalogo externo')`, que es el que reciben los feeds
nuevos, para que el modulo no quede atado a ningun portal.

### Como se renombra un modulo de Odoo sin perder datos

Odoo no sabe que un modulo cambio de nombre. Sin ayuda, el viejo queda
como "no instalable" (su carpeta ya no existe), el nuevo se instala
desde cero y los datos ya cargados quedan huerfanos. La solucion es un
`pre_init_hook` en el modulo nuevo (`hooks.py`) que renombra en sitio
antes de que Odoo instale nada.

Tres cosas que costaron un intento fallido cada una:

1. **No borrar la fila del modulo nuevo.** El primer intento borraba
   `ir_module_module` del nombre nuevo para que el viejo ocupara su
   sitio. Pero esa fila es la que Odoo esta usando en ese momento: el
   arranque muere con `MissingError` al calcular `description_html`. Hay
   que mover los datos del viejo al nuevo y borrar el viejo al final.

2. **`ir_model_data` guarda ADEMAS el nombre del modelo en texto.** No
   basta con `ir_model.model`. Si no se actualiza, al cargar el XML Odoo
   encuentra el identificador pero ve que apunta a otro modelo y aborta:
   "found record of different model marketing.patiotuerca.connection".

3. **Los identificadores XML que cambiaron hay que renombrarlos uno a
   uno** en `ir_model_data`. Si no, Odoo crea registros nuevos y deja los
   viejos sueltos: grupos duplicados, reglas duplicadas y menus repetidos.

Ademas del modelo y su tabla hay que mirar la secuencia
`<tabla>_id_seq`, y las columnas donde el nombre del modelo vive como
texto suelto: `ir_act_window.res_model`, `ir_ui_view.model`,
`ir_act_server.model_name`, `ir_filters.model_id`, `mail_message.model`,
`mail_activity.res_model`, `mail_followers.res_model`,
`ir_attachment.res_model`.

La migracion se comprobo clonando una base real que tenia el modulo
viejo (`create database ... template ...`) y verificando despues 16
condiciones: modulo nuevo instalado, ninguno viejo, tabla renombrada,
conexion y vehiculos intactos y ligados entre si, modelo renombrado,
cero registros XML del modulo viejo y ni un identificador duplicado.

## Escrituras que el `raise` siguiente deshace

Patron encontrado 45 veces en el repositorio:

    except Exception as error:
        record.write({'state': 'error', 'last_error': str(error)})
        raise UserError(...)

Parece razonable y no lo es. Una excepcion que sale del metodo deshace
la transaccion entera, asi que ese `write` **se pierde siempre**. El
usuario lee el mensaje del dialogo, lo cierra, y el formulario sigue
mostrando el estado anterior: ni rastro del fallo, ni fecha, ni detalle
tecnico. Justo lo contrario de lo que pretendia quien lo escribio.

El escaner (`scan_write_raise.py`) informa ademas de QUE campos escribe
cada caso, porque no todos son iguales:

- **Diagnostico** (`last_error`, `sync_message`, `permissions_summary`,
  `error_category`, `validation_message`): existen para sobrevivir al
  fallo. Son el caso a arreglar.
- **Estado de negocio** (los nueve `write({'state': ...})` de
  `chatroom_whatsapp`): si el mensaje se creo en esa misma transaccion,
  lo correcto es que desaparezca entero, no quedarse marcado como
  fallido. Esos se dejaron como estaban, a proposito.

Dos cosas que el escaner NO debe marcar y por eso las descarta: una
escritura dentro de `with ... registry.cursor()` (que es justamente la
solucion) y un `write` colocado despues de un `raise` (codigo muerto).
Aun asi dio un falso positivo que hubo que mirar a mano:
`catalog_connection.py` ya resolvia su caso con `rollback()` y
`commit()` explicitos.

### La solucion: un mixin, no trece copias

Los cuatro conectores de marketing dependen todos de
`marketing_command_center`, asi que el ayudante vive ahi una sola vez:
`marketing.diagnostic.mixin`, con `_persist_diagnostic(valores)`. Abre
una transaccion propia (`self.env.registry.cursor()`) y confirma, de
modo que lo escrito sobrevive al rollback del `raise`.

Durante las pruebas escribe en la transaccion en curso en vez de abrir
otra: confirmar de verdad dejaria datos en la base y el caso siguiente
los heredaria. Hay un test que lo comprueba parcheando
`registry.cursor` y exigiendo que no se llame.

Cuidado al anadir el mixin a un modelo que ya tiene `_inherit`: hay que
FUNDIR las dos listas. Dejar dos asignaciones de `_inherit` en la misma
clase no da error, simplemente la segunda anula a la primera y el mixin
no se aplica. Paso dos veces; se detecta con un recorrido AST que cuente
asignaciones de `_inherit` por clase.

## Iconos: 30 de 44 modulos salian con la cara por defecto de Odoo

Odoo antepone el nombre del modulo a la ruta que declare `icon`:

    fpath = manifest.raw_value('icon').lstrip('/')
    tools.file_path(fpath)

Una ruta como `static/description/icon.svg`, sin el modulo delante, no
resuelve, y Odoo devuelve `/base/static/description/icon.png` sin avisar
de nada. Once modulos tenian su dibujo hecho y aparecian igualmente con
el icono generico solo por eso. Otros diecinueve no tenian dibujo.

Sin clave `icon`, Odoo busca `static/description/icon.png`. Un modulo
que solo tiene `icon.svg` necesita declararla si o si.

La forma de comprobarlo es preguntarselo a Odoo, no deducirlo:
`odoo.modules.module.get_module_icon(nombre)` sobre cada modulo, y
contar cuantos devuelven la ruta generica. Ahora son cero de 44.

Los diecinueve iconos nuevos comparten marco (256x256, fondo oscuro,
panel interior) con los que ya existian, y cambian degradado y simbolo.
Dos detalles que costaron una pasada:

- Los identificadores de `<defs>` (`marca`, `marco`, `sombra`) llevan el
  nombre del modulo. Dentro de Odoo cada icono se sirve como imagen
  propia y no se pisan, pero al renderizar los diecinueve juntos para
  revisarlos, `url(#marca)` se resolvia contra el primero y salieron
  todos naranjas.
- Conviene mirarlos renderizados, no solo leer el SVG. Un simbolo de
  moneda dibujado con dos trazos cruzados se leia como una cruz. Se
  renderizan con Chrome headless (`--screenshot`) sobre una hoja de
  contacto HTML.

## Savepoint por canal en las campanas NPS

`_process_batch` recorre destinatarios y atrapa la excepcion de cada uno
con un comentario que dice "un fallo individual no detiene la campana".
No era cierto: sin savepoint, un fallo de CONSULTA deja la transaccion
abortada en PostgreSQL, y a partir de ahi revientan tanto el `write` que
registra el error como todos los destinatarios siguientes. El `except`
prometia justo lo que no podia cumplir.

El savepoint tiene que ser **por canal**, no por destinatario. Si se
envolvieran el correo y el WhatsApp en el mismo savepoint, un fallo de
WhatsApp desharia el correo que ya habia salido, y como el `except`
marcaba fallido "lo que siguiera en pendiente", el destinatario acabaria
marcado como fallido tambien en correo. Hay un test que lo fija.

## Configuracion: el escaner que casi da un falso positivo masivo

Primer intento de auditar `ir.config_parameter`: comparar las claves de
`get_param(...)` con las de `set_param(...)`. Resultado: 35 claves
"imposibles de configurar" y 23 "ajustes que nadie lee". Casi todo falso.

Dos motivos:

- En Odoo un ajuste no se guarda con `set_param`, sino declarando el
  campo con `config_parameter='clave'`. El escaner no miraba eso.
- Aqui hay ayudantes que reciben la clave como argumento
  (`_hour('chatroom_whatsapp.business_hours_start')`,
  `_fulfillment_param_enabled('chatroom_ai_sales.require_stock')`), asi
  que buscar `get_param('clave')` no ve la lectura.

Lo que si funciona es medir DONDE APARECE la clave: en
`res_config_settings` significa que se ofrece, en cualquier otro fichero
de logica significa que se usa, y los tests no cuentan como uso. Con ese
criterio: **94 claves bien conectadas, 0 ajustes huerfanos**.

La unica clave sin interfaz es `chatroom_whatsapp.webhook_max_bytes`, y
se deja a proposito: es un limite de proteccion con valor por defecto
seguro (2 MB) y acotado entre 64 KB y 10 MB. Es una perilla tecnica, no
una decision de usuario.

## Ayuda en los campos de Ajustes

Un campo de Ajustes es una decision que alguien tiene que tomar. Sin
`help` solo se ve la etiqueta, y quien no sepa de antemano que hace
"Perfil de seguridad" o cuantos minutos poner en un SLA, lo deja como
venia. La pantalla existe pero no se usa.

Estaban al **71%** (75 de 106). Ahora al 100%, comprobado en el registro
cargado y no solo en el fichero: 88 campos propios, todos con ayuda.

Los textos dicen que pasa si se activa, que valor es razonable o de
donde se saca el dato. Un `help` generico habria sido peor que ninguno,
porque ocupa el sitio del bueno.

Cuidado al partir un texto largo en varios literales: Python los
concatena sin anadir nada, asi que hay que dejar el espacio al final de
cada trozo. La primera pasada produjo "la conversacionse marca" en los
31 campos. Se detecta buscando palabras anormalmente largas en el valor
del `help` una vez leido con `ast`.

## Accesibilidad: los avisos que Odoo ya emite y nadie lee

Odoo revisa cada vista al cargarla y avisa de defectos de
accesibilidad, pero el aviso se pierde entre miles de lineas de
arranque. Recogidos y agrupados salieron **20**, todos reales para quien
usa lector de pantalla:

- 16 avisos por un `alert-*` sin `role` (6 defectos distintos; el resto
  eran la misma vista revalidada al actualizar su heredada).
- 4 iconos `<i class="fa ...">` sin titulo ni texto: para quien no los ve
  sencillamente no existen.

Ahora son **0**.

El rol NO es el mismo para todos, y ponerlo a ojo seria peor que no
ponerlo:

- `role="alert"` interrumpe lo que el lector este diciendo. Se reserva
  para un error que responde a una accion: el formulario que no paso la
  validacion, la consulta a la IA que fallo.
- `role="status"` se anuncia sin cortar. Es lo que corresponde a un aviso
  que ya estaba ahi: "la IA esta pausada", "no tienes permiso", una nota
  informativa de la pasarela de pago.

Un lector que interrumpe cada vez que se pinta una nota informativa
acaba siendo ruido, y el usuario aprende a ignorarlo.

Odoo **no** acepta `aria-hidden="true"` como descripcion, aunque para un
icono decorativo junto a su texto sea justamente lo correcto. Donde lo
habia se anadio `title` sin quitarlo: el lector lo sigue ignorando y de
paso el usuario con raton obtiene un rotulo.

Odoo solo revisa las vistas de escritorio. Las plantillas de sitio web,
las de pasarelas de pago y los componentes Owl tienen el mismo problema
y **nadie avisa**: ahi hubo otros 12, y son pantallas que ve el cliente
final. Solo se dejo sin rol el informe PDF de nomina, porque en un
documento impreso no significan nada.

## Incoherencia de permisos en la lista de contratos

Odoo detecto que `l10n_ec_hr_view_contract_tree` se muestra a
`hr.group_hr_user` pero su `decoration-danger` dependia de
`contract_type_id`, que solo leen los de nomina: para el resto de
usuarios la decoracion no podia evaluarse.

Se quito la decoracion en vez de restringir la vista entera. La misma
senal la da el `placeholder` con el simbolo de aviso de esa columna,
para quien puede verla; restringir la vista habria cambiado a quien le
aparece el menu, que es un cambio mayor y nadie lo pidio.

## Campos que comparten etiqueta

En un formulario salen dos casillas llamadas igual, y en el selector de
columnas dos entradas identicas: el usuario no sabe cual es cual. El
patron mas repetido es `X_ids` (la relacion) y `X_count` (cuantos hay)
compartiendo nombre; el contador pasa a "Numero de ...".

Se arreglaron 10 pares. Quedan 7 que NO son un problema de etiqueta sino
de modelo, y por eso se dejan anotados en vez de renombrados:

- `hr.employee`: `freelance` / `is_freelance`, y `type_id` /
  `contract_type`. Son dos campos para el mismo concepto. Unificarlos
  exige decidir cual se queda y migrar los datos existentes.
- `hr.employee`: `address_home_id` / `partner_id`. Es correcto que
  compartan etiqueta: el primero es un relacionado del segundo.
- `hr.leave`: `attachment` / `file`; `hr.payslip.input`: `overtime_id` /
  `new_id`; `hr.payslip.run`: `transfer_ids` contra `bank_transfer_ids`
  y `check_ids`. Aqui la etiqueta que se repite viene del nucleo de
  Odoo, asi que renombrar del lado propio solo tapa la mitad.

## Modo oscuro: por que salian blancos los botones, buscadores y campos

Odoo compila el MISMO SCSS dos veces: una para `web.assets_backend` y
otra para `web.assets_web_dark`, cambiando antes un punado de variables
SCSS. `$o-view-background-color` vale `white` en la primera y `#262A36`
en la segunda.

De ahi salen las dos causas, y la segunda es la que mas dano hacia:

### 1. Colores escritos a mano

`background: #fff` no se entera de nada: se queda blanco sobre el fondo
negro. Habia 209 declaraciones asi en chatroom y marketing.

Se cambiaron por variables (`$o-view-background-color`, `$o-gray-100`,
`$o-gray-200`, `$o-gray-300`) en vez de escribir una hoja `.dark.scss`
por modulo: no hay dos sitios que mantener sincronizados, y los ocho
modulos que no tenian hoja oscura quedaron arreglados sin anadir
ninguna.

**Lo que NO se toco, y por que:**

- `color: #fff` sobre un boton de color o un degradado. Es correcto en
  los dos temas; cambiarlo lo romperia. Se reviso uno a uno: los 31 que
  hay estan sobre un fondo propio de color, y los dos dudosos heredan un
  fondo oscuro del padre.
- Los tintes CON TONO: `#fff3cd` es un aviso, `#d1f7dd` un exito,
  `#f8d7da` un error, `#dcf8c6` la burbuja saliente de WhatsApp.
  Amarillo de aviso es amarillo de aviso en los dos temas. Se
  distinguen midiendo la diferencia entre canales del color (mas de 24
  = tiene tono), no a ojo.

### 2. Variables CSS que nadie define

Repartido por los modulos habia este patron, que parece defensivo y no
lo es:

    background-color: var(--o-view-background-color, #fff);

Odoo **nunca define** `--o-view-background-color` como propiedad CSS. Se
comprobo compilando los dos paquetes y contando definiciones: **cero** en
ambos. Con la variable sin definir gana siempre el respaldo, `#fff`, asi
que esos elementos se quedaban blancos. Eran 31 usos, y justo los de los
buscadores, los campos y los paneles.

Lo que si existe es la variable SCSS del mismo nombre, sin los dos
guiones: `$o-view-background-color`. Esa es la que se usa ahora.

Contraste util: `--border-color` SI esta definida (11 veces en claro, 16
en oscuro) y por eso los bordes ya se adaptaban bien. No se toco.

### 3. La hoja oscura de chatroom_ui inventaba nombres paralelos

Definia `--chatroom-ui-surface-dark` en vez de redefinir
`--chatroom-ui-surface`, asi que todo lo que usara la variable original
seguia blanco. Ahora la hoja oscura redefine las variables base en
`:root` (ese fichero solo entra en el paquete oscuro, asi que no afecta
al tema claro) y conserva los alias `-dark` para no romper sus propias
reglas.

### Como se comprueba

Mirar el SCSS no vale: hay que compilar los dos paquetes y comparar el
CSS resultante.

    bundle = env["ir.qweb"]._get_asset_bundle("web.assets_web_dark", css=True)
    css = "".join(a.raw.decode() for a in bundle.css())

Ojo: `bundle.stylesheets` son los ficheros de ORIGEN, con el `$o-...` sin
resolver. Lo que hay que pedir es `bundle.css()`.

Resultado: los mismos selectores dan `white` en el paquete claro y
`#262A36` en el oscuro. Recorriendo el CSS oscuro entero en busca de
fondos claros en selectores propios se paso de **20 a 0** (los dos que
siguen apareciendo son el texto de respaldo de un `var(...)` que ya
resuelve a oscuro; el auditor no evalua variables).

## Diagnosticos perdidos: los que faltaban, y una variante nueva

Se cerro el patron `write` + `raise` en nomina y en lo que quedaba de
chatroom. El caso mas grave estaba en la transmision a la DIAN:

    document.write({..., "retry_count": retry_count,
                    "next_retry_at": next_retry})
    document._log_attempt("send", "error", str(exc))
    raise UserError(...)

Ese `write` guardaba el CONTADOR DE REINTENTOS y cuando toca el
siguiente. Al deshacerse, el contador nunca avanzaba y el cron de
reintentos no tenia nada que recoger: cada vuelta empezaba de cero
contra la DIAN. Y con el se perdia tambien la bitacora de intentos, asi
que un fallo de transmision no dejaba NINGUN rastro.

### Dos situaciones, no una

Al llegar a chatroom aparecio una variante que el mixin de marketing no
cubria:

- El registro YA EXISTIA de una transaccion anterior: basta con volver a
  escribirlo desde una transaccion propia. -> `_persist_diagnostic`
- El registro se creo en ESTA misma transaccion. Aqui el rollback no
  solo pierde el mensaje: se lleva el registro entero. Y escribirlo
  desde otro cursor TAMPOCO vale, porque esa fila todavia no existe
  fuera de la transaccion que va a deshacerse. Hay que crearlo de nuevo,
  ya en la transaccion aparte. -> `_persist_diagnostic_record`

Pasaba en dos sitios: el historial de un enlace de pago y el snapshot de
consumo de IA. En los dos, un fallo no dejaba ni constancia del intento.

Al recrear el registro NO sirve `copy_data()`: descarta los campos
marcados `copy=False`, y el enlace de pago es uno de ellos. Hay que
guardar el diccionario de valores original y reutilizarlo.

### La trampa de `_inherit` en lista

Para dar el mixin a `hr.payslip`, que aqui se extiende con
`_inherit = "hr.payslip"`, no basta con pasar a lista: con `_inherit`
en lista y sin `_name`, Odoo NO extiende el modelo, crea uno nuevo
sacado del nombre de la clase y se queda sin tabla. El arranque muere
con "null value in column parent_id of relation ir_model_inherit". El
patron correcto, el mismo que usa el nucleo en `pos_sale`:

    _name = "hr.payslip"
    _inherit = ["hr.payslip", "l10n.co.payroll.diagnostic.mixin"]

Y hay que actualizar con `-u` el modulo que DEFINE el mixin: con `-i`
sobre un modulo ya instalado no pasa nada, el modelo abstracto no se
registra y el error es el mismo.

## Campos con la misma etiqueta: los ultimos

Quedaban siete pares. Seis eran nuestros y se han desambiguado:

- `hr.payslip.input`: `new_id` y `overtime_id` se llamaban los dos
  "New". Ahora "Novedad" y "Hora extra".
- `hr.payslip.run`: `check_ids` y `bank_transfer_ids` compartian
  "Payment associated to this Payslip". Ahora "Pagos con cheque" y
  "Pagos por transferencia".
- `hr.leave`: `file` (el que se sube) y `attachment` (el ya guardado)
  eran los dos "Adjunto".
- `hr.employee`: `freelance` (del contrato, manual) contra
  `is_freelance` (del empleado, calculado). No son duplicados: viven en
  modelos distintos y afloran juntos porque Odoo 19 relaciona la version
  vigente sobre el empleado. Pueden diferir legitimamente, asi que se
  etiquetan por su origen en vez de fusionarlos.
- `hr.employee`: `contract_type` NO es el tipo de contrato -ese es
  `type_id`, que apunta al catalogo-: sus valores son Nomina, Prestacion
  de servicios y C-Level, o sea la modalidad. Ahora se llama asi.

El unico que queda, `address_home_id` / `partner_id`, es correcto: el
primero es un relacionado del segundo y comparten etiqueta a proposito.

## Instagram marcaba como "sin datos" lo que era "no disponible"

Las dos rutas de metricas de Meta no hacian lo mismo:

- Facebook (`_sync_post_metrics`) escribe SIEMPRE el snapshot, con
  `metric_status` en `verified`, `partial` o `unavailable`.
- Instagram (`_sync_instagram_metrics`) solo lo escribia `if values`, o
  sea cuando Meta habia devuelto alguna metrica. Si no devolvia nada, no
  quedaba registro.

La diferencia importa porque el producto entero se apoya en distinguir
las dos cosas: el panel tiene un contador de "Metricas no disponibles",
y la instruccion que se le manda a la IA dice literalmente que una
metrica no disponible NO equivale a cero. Sin registro, una publicacion
de Instagram cuyas metricas Meta no da se leia como medida en cero, y el
contador del panel no se enteraba nunca.

Ademas, el fallo de la llamada en lote se descartaba en silencio
(`except MetaGraphError: rows = []`), asi que si luego fallaban tambien
las llamadas de una en una, no quedaba ni el motivo.

## Un `_persist_diagnostic` que no persistia nada

En `social_network_profile._sync_one_profile` el mixin se habia aplicado
al registro de ejecucion:

    log = Log.create({...})          # en ESTA transaccion
    ...
    except ...:
        log._persist_diagnostic({...})   # no llega a ninguna parte
        raise

`_persist_diagnostic` reescribe desde otra transaccion, y esa fila
todavia no existe fuera de la que va a deshacerse: la escritura afecta a
cero filas y el registro desaparece igual. Para eso esta
`_persist_diagnostic_record`, que vuelve a crearlo.

Lo mismo con la cuenta social: `_ensure_social_account()` la crea si no
existia, y en ese caso su estado de error tampoco se puede conservar
—no hay a que volver—, asi que solo se persiste la que ya existia.

Para no repetirlo hay un escaner (`auditar_persist.py`) que busca, dentro
de cada metodo, si la variable sobre la que se llama a
`_persist_diagnostic` viene de un `.create()` del mismo metodo. Sobre el
repositorio da cuatro resultados y los cuatro son tests, donde el
ayudante escribe a proposito en la transaccion en curso.

## Concurrencia: dos mensajes del mismo contacto nuevo

Meta entrega los webhooks en paralelo y cada uno corre en su propia
transaccion. Si el primer mensaje de un contacto llega dos veces a la
vez, los dos buscan el canal, ninguno lo encuentra, y los dos lo crean.

El canal esta protegido por `unique(external_id, channel_type,
company_id)`, asi que el segundo se estrellaba con un `IntegrityError`
SIN CAPTURAR: la peticion entera fallaba y Meta la reintentaba. El
contacto, en cambio, NO tiene restriccion unica, asi que ademas quedaban
dos `res.partner` para el mismo numero.

El arreglo es el mismo patron que ya usaba la creacion de mensajes
entrantes: savepoint y, si salta la restriccion, quedarse con el que
gano la carrera. La diferencia esta en que aqui el savepoint envuelve
LAS DOS creaciones -contacto y canal-, para que el perdedor deshaga
tambien el contacto que acababa de crear. Envolviendo solo el canal, el
contacto duplicado se quedaba.

Solo se absorbe `UniqueViolation` y solo si al re-buscar aparece el
canal. Cualquier otro fallo de integridad sigue saliendo: taparlo
esconderia un bug de verdad.

## Rendimiento: indices y contadores

### Tres indices, no diez

El escaner encontro diez campos filtrados y sin indice, pero indexar
todo es contraproducente: cada indice cuesta en cada escritura y en
disco. Solo se anadieron tres, y el criterio es la SELECTIVIDAD:

- `chatroom.channel.assigned_user_id` (`btree_not_null`): la bandeja
  filtra por agente en cada carga y hay tantos valores como agentes.
  `not_null` deja fuera las conversaciones sin asignar, que son muchas y
  no se buscan por este campo.
- `marketing.social.publication.account_id`: practicamente toda consulta
  de marketing pasa por la cuenta.
- `chatroom.ai.task.completed_at` (`btree_not_null`): el panel cuenta
  "completadas hoy" con un rango de fechas y las tareas se acumulan.

Los otros siete se descartaron por baja selectividad: `direction` tiene
dos valores, `state` y `risk_level` tres o cinco, `channel_type` ya esta
cubierto por el indice de la restriccion unica. Un indice sobre una
columna de dos valores casi nunca se usa; PostgreSQL prefiere recorrer.

Aviso honesto: las tablas de la base de pruebas estan vacias, asi que la
eleccion es por patron de consulta y selectividad, no medida.

### El panel ejecutivo hacia 16 COUNT sobre la misma tabla

Cuatro contadores de tareas que solo se diferenciaban por el estado, y
tres de valoraciones de sugerencias, cada uno con su `search_count`.
Agrupando con `_read_group` se recorre una sola vez: siete consultas
menos por refresco.

El test que lo protege no fija un numero de consultas -eso se romperia
con cualquier cambio legitimo- sino que compara el coste con 5 tareas y
con 50. Con margen de UNA consulta, porque la primera pasada carga cosas
en cache que la segunda ya tiene y eso mueve el numero sin depender de
los datos. Lo que detecta es una consulta POR TAREA, que serian 45 mas.

## Disponibilidad: llamadas de red sin timeout

Una llamada sin `timeout` espera indefinidamente si el otro extremo
acepta la conexion y no responde, y deja un worker de Odoo colgado. No
da error ni aparece en los logs.

Revisado `requests.*` y `urlopen` en todo el repositorio: **cero casos**.
El unico que marco el escaner era un falso positivo, un `timeout` que se
pasa dentro de un diccionario con `**kwargs` en vez de como literal.

## El cron de automatizaciones perdia el trabajo de la pasada entera

`chatroom_ai_agent/models/chatroom_ai_automation.py`, en
`_cron_run_scheduled`. Cuando una automatizacion fallaba se hacia:

    except Exception as exc:
        self.env.cr.rollback()
        automation.write({...'last_error': str(exc)[:4000]})

`cr.rollback()` no deshace la automatizacion que ha fallado: deshace la
**transaccion entera**. El cron recorre todas las automatizaciones
activas dentro de una sola transaccion y no confirma entre una y otra,
asi que si reventaba la tercera se perdian tambien las tareas que ya
habian creado la primera y la segunda, y sus registros de ejecucion.

Ademas `total` ya habia sumado esas tareas, de modo que el cron
terminaba informando de un trabajo que acababa de tirar.

Ahora es un savepoint por automatizacion, y el recuento se suma en el
`else` del `try`, solo cuando el savepoint se ha soltado bien.

### Por que el rastro del fallo va por una transaccion aparte

El savepoint se lleva por delante el registro de `chatroom.ai.automation.run`
que abre `_run_for_channels` al empezar, porque se creo dentro. Si el
error solo se escribiera en la transaccion normal, la automatizacion
fallida no apareceria en ningun sitio: el usuario abre el historial y
parece que el cron no la ejecuto.

Se usa el mixin `chatroom.diagnostic.mixin`, que ya estaba en el
repositorio para esto mismo: `_persist_diagnostic` para el campo
`last_error` de la automatizacion (que ya existia antes) y
`_persist_diagnostic_record` para crear de nuevo la ejecucion fallida
(que no existe fuera de la transaccion que se acaba de deshacer).

### Medido, no deducido

**Esto no se puede comprobar en una prueba de Odoo.** El arnes prohibe
`cr.rollback()` dentro de un test y lanza un AssertionError antes de que
la linea llegue a hacer nada. Las pruebas nuevas suspenden con el codigo
anterior, pero por ese AssertionError, no por la perdida de datos.

La perdida real se midio fuera del arnes, con un cursor normal sobre
`qa_claude_b` (`scratchpad/demostrar_rollback.py`): dos automatizaciones,
la primera correcta y la segunda que falla.

| | informa creadas | sobreviven | rastro del fallo | en historial |
|---|---|---|---|---|
| Antes | 3 | **0** | si | **0** |
| Ahora | 3 | **3** | si | 1 |

## El descarte de canales costaba una consulta por canal

En el mismo fichero, `_run_for_channels` preguntaba con `search_count`,
canal por canal, si ya habia una tarea viva. El cron diario recorre
cientos de conversaciones y la mayoria estan ya atendidas, asi que el
grueso del trabajo era precisamente descartarlas.

Dos cambios:

- Una sola consulta agrupada para todo el lote, con el conjunto de ids
  ocupados en memoria. Se alimenta con lo que se crea en el bucle, para
  que un canal repetido en el mismo lote siga omitiendose igual.
- El descarte sale **fuera** del savepoint. Solo consulta, no escribe
  nada que haya que poder deshacer, y dentro costaba un `SAVEPOINT` y un
  `RELEASE` por cada canal omitido.

Medido con 40 canales todos ocupados, que es el caso normal del cron:

| | 3 canales | 40 canales |
|---|---|---|
| Antes | 15 consultas | **122** |
| Ahora | 7 consultas | **3** |

Que con 40 salgan menos que con 3 no es un error de medida: la segunda
pasada aprovecha lo que la primera dejo en cache. Es justo el motivo por
el que el test compara con margen en vez de fijar una cifra.

El test (`test_skipping_does_not_cost_a_query_per_channel`) compara los
dos costes con margen de dos consultas. No fija una cifra: lo que tiene
que detectar es una consulta POR CANAL.

## Un semaforo de seguridad que daba verde con la IA sin supervision

`chatroom_ai_operations`, comprobacion `human_approval`. Decia asi:

    ready = _param_enabled('chatroom_ai_agent.require_approval', True) or \
            get_param('chatroom_ai_agent.safety_profile', 'supervised') == 'supervised'

Quien decide de verdad si algo necesita revision humana son otros dos
parametros, y cada uno manda en un sitio distinto:

- `require_approval`, en `chatroom.channel._ai_requires_approval`, rige
  las respuestas automaticas.
- `mode`, en `chatroom.ai.task.create_from_channel`, rige las tareas: con
  'supervised' o 'simulation' fuerza la aprobacion aunque el otro este
  desactivado.

`safety_profile` no lo consulta nadie al decidir. Es un selector de
preajustes cuyo onchange escribe esos dos. La comprobacion miraba
precisamente el que no impone nada e ignoraba el que si.

### El camino que rompia

El usuario destilda la casilla de aprobacion en Ajustes y nunca toca el
selector de perfil. Entonces el parametro del perfil **no existe**,
`get_param` devuelve el 'supervised' por defecto, y el `or` da verde.

Contrastado en base real (`scratchpad/comprobar_aprobacion.py`), creando
una tarea de verdad en cada combinacion:

| situacion | comprobacion | tarea real | coinciden |
|---|---|---|---|
| instalacion por defecto | protegido | pide aprobacion | si |
| destilda la casilla, nunca toca el perfil | **protegido** | **NO la pide** | **NO** |
| elige el preajuste automatico | error | NO la pide | si |
| destilda la casilla, modo supervisado | protegido | pide aprobacion | si |

La cuarta fila coincidia por casualidad: daba verde por el perfil, no por
el modo. Con el perfil en 'automatic' y el modo en 'supervised' habria
dado rojo mientras las tareas si pedian aprobacion.

Ahora son tres estados, porque la realidad tiene tres:

- `require_approval` activo -> **ok**.
- Desactivado pero el modo protege -> **warning**: las tareas siguen
  pidiendo aprobacion, las respuestas automaticas no. Un verde o un rojo
  a secas ocultaban esa mitad.
- Desactivado y modo automatico -> **error**.

El mismo indicador estaba duplicado en `chatroom_ai_setup.py` con la
misma logica. Corregido igual, y hay un test que exige que los dos sitios
digan lo mismo.

## Otros arreglos en chatroom_ai_operations

**El aviso de WhatsApp mentia cuando no habia lineas.** `any([])` es
falso igual que "hay lineas pero les falta credencial", asi que quien no
habia dado de alta ninguna leia "Hay lineas activas, pero falta completar
sus credenciales" y se ponia a buscar unas credenciales inexistentes.

**`action_run_all` hacia doce busquedas** antes de empezar, una por cada
comprobacion definida, y se dispara desde el panel y desde el cron. Ahora
es una busqueda para los doce codigos y una creacion en lote de los que
falten.

**El panel se traia el pipeline entero a memoria** para contarlo y
sumarlo con `mapped()` y `filtered()`. `expected_revenue` y
`estimated_capital_trapped` estan almacenados, asi que el agregado sale
de Postgres sin materializar ningun registro.

**Los tres contadores de consumo de IA salian de dos consultas sobre el
mismo conjunto** -un `search_count` y un `search`- mas dos recorridos en
memoria. Agrupando por `success` salen los tres de una sola consulta.

### Lo que NO se toco, y por que

- **Los contadores por estado de `chatroom.ai.task` y
  `chatroom.payment.link`.** Son tres y dos `search_count` sobre la misma
  tabla, el patron que si se agrupo en el panel ejecutivo de IA. Aqui no:
  `state` esta indexado en ambos modelos, y los dominios son selectivos
  ('failed', 'awaiting_approval'). Tres lecturas por indice sobre pocas
  filas pueden ganarle a un `GROUP BY` que recorre una tabla llena de
  tareas 'done'. Sin datos reales que lo midan, cambiarlo es apostar.

- **`_sla_channel_ids`.** Parece el candidato obvio -trae las
  conversaciones abiertas y las filtra en Python- pero no es un N+1: el
  calculo del semaforo esta agregado en lote. Y el dominio equivalente
  usaria `_search_first_response_sla_state`, que agrega la tabla de
  mensajes **entera, sin filtrar por conversacion abierta**. Cambiarlo
  seria probablemente peor.

### Sobre las pruebas nuevas

Doce, en `test_operations_veracidad.py`. Los siete tests que ya habia
eran casi todos `assertIsInstance(valor, int)`: comprobaban que el panel
devolviera numeros, no que fueran los correctos. Por eso el fallo de
seguridad llevaba ahi sin que nadie lo viera.

Cinco de las nuevas suspenden con el codigo anterior, por la asercion y
no por un artefacto del arnes. Las cuatro del panel **no** distinguen:
agregar en SQL da el mismo resultado que sumar en memoria. Son guardas
para el futuro, no cazadoras de este fallo, y conviene no confundirlas.

## marketing_command_center_catalog: la sincronizacion del feed

### Un id repetido en el feed tumbaba la sincronizacion entera

`action_sync` armaba un indice de lo ya guardado y consultaba ahi, pero
**no metia en el indice lo que iba creando**. Si el proveedor mandaba dos
veces el mismo `id` en el mismo feed, la segunda fila tampoco aparecia en
el indice y se intentaba crear otra vez:

    psycopg2.errors.UniqueViolation: duplicate key value violates
    unique constraint "marketing_vehicle_listing_external_unique"

Y como eso sube hasta el `except`, se perdia la sincronizacion completa
por un duplicado ajeno. Ahora los nuevos se acumulan en un diccionario
por id: gana la ultima fila, que es lo que habria pasado si el anuncio ya
hubiera existido.

### El manejo del error solo corria en produccion

    except Exception as exc:
        if not modules.module.current_test:
            connection.env.cr.rollback()
            connection.write({'state': 'error', ...})
            connection.env.cr.commit()
        raise

Tres cosas mal:

1. `cr.rollback()` deshace la transaccion ENTERA. Con varias conexiones
   seleccionadas se llevaba lo que ya habian sincronizado las anteriores.
   Con una sola, borraba el `demo_mode = True` que `action_load_demo`
   acababa de escribir: el usuario pulsaba "Cargar demo", fallaba, y el
   modo demo no se quedaba puesto.
2. `cr.commit()` a mitad de peticion confirmaba ese estado parcial.
3. El `if not current_test` dejaba **todo el bloque sin probar**. Lo unico
   que corria en produccion era exactamente lo que ningun test tocaba.

Ahora: un savepoint por conexion, que descarta la sincronizacion a medias
de esa conexion y nada mas, y el rastro por `_persist_diagnostic`, que ya
estaba en el repositorio para esto. Sin `commit`, sin `rollback`, y sin
camino distinto en pruebas.

### Crear de uno en uno

Cada vehiculo nuevo era su propio INSERT. Medido sobre `qa_claude_b` con
un feed de vehiculos nuevos (`scratchpad/medir_catalogo.py`):

| vehiculos nuevos | antes | ahora |
|---|---|---|
| 10 | 40 consultas | 28 |
| 100 | **208** | **14** |

Que con 100 salgan menos que con 10 es la cache de la misma transaccion,
igual que en el cron de automatizaciones. Lo que importa es que antes
crecia unas dos consultas por fila y ahora no crece.

### El filtro de desactualizados cargaba la tabla entera

`_search_is_stale` hacia `self.search([]).filtered('is_stale')`: traia a
memoria TODOS los anuncios de TODAS las conexiones y calculaba la
vigencia de cada uno, para quedarse con unos pocos. Era un filtro de la
vista de lista.

"Desactualizado" si se puede expresar como dominio: sin fecha de visto, o
con esa fecha por detras del corte. El corte depende de
`stale_after_hours`, que es de la **conexion**, asi que se arma un trozo
por conexion y se unen con OR. Las conexiones son pocas; los anuncios,
muchos. Esta extraido en `_stale_domain`.

`_compute_counts` hacia lo mismo por otra via: leia `listing_ids` entero
y lo recorria cuatro veces. Ahora son dos consultas agrupadas -una por
estado y otra por vigencia- para todo el lote de conexiones, no una por
conexion: en la vista de lista eso habria sido un N+1 nuevo.

### Sobre las pruebas

Trece nuevas. Tres suspenden con el codigo anterior:

- el id repetido (UniqueViolation),
- el rastro del fallo, que en pruebas no se escribia nunca,
- y el feed sin lista, que reventaba al leer un `last_error` vacio.

Las otras diez son guardas: ausentes, ventanas de vigencia por conexion,
contadores que no se mezclan entre conexiones. No cazan este fallo, lo
sujetan hacia adelante.

Un aviso de honestidad sobre `test_a_failed_sync_does_not_undo_what_came
_before_it`: **no distingue** las dos versiones, porque en pruebas el
`cr.rollback()` antiguo estaba detras del `if not current_test` y no
llegaba a ejecutarse. La perdida real solo se ve fuera del arnes.

## Barrido sistematico de `cr.rollback()` / `cr.commit()` en rutas de error

El patron ya habia aparecido tres veces, asi que en vez de seguir
encontrandolo de uno en uno se escribio un escaner
(`scratchpad/scan_rollback.py`), validado antes contra un fichero con
cuatro positivos y cuatro negativos conocidos.

Distingue tres cosas, porque no todas son un fallo:

- `ROLLBACK-EXCEPT`: rollback dentro de un `except`. El patron malo.
- `COMMIT-EXCEPT`: commit dentro de un `except`. Confirma estado parcial.
- `COMMIT-BUCLE`: commit dentro de un bucle. A veces es deliberado.

**Resultado: 9 hallazgos, 1 fallo real y 8 usos correctos.** Merece la
pena dejar escrito por que los ocho son correctos, para no volver a
"arreglarlos":

- `chatroom_channel.action_mark_read` — rollback en un reintento de
  `SerializationFailure`. Ahi el rollback COMPLETO es obligatorio: en
  REPEATABLE READ un savepoint conserva la misma instantanea y el
  reintento vuelve a chocar con el mismo conflicto. Hace falta una
  transaccion nueva.
- `whatsapp_webhook` (x2) — la base puede haber quedado abortada por una
  carrera, asi que se revierte y se crea un evento pendiente nuevo para
  que el cron lo recupere sin devolver 500 a Meta. Es el patron de
  "volver a crear en transaccion limpia", correcto.
- `_cron_send_scheduled_messages`, `_cron_retry_failed_messages`,
  `_cron_ai_sales_fulfillment`, `_process_ai_in_background` — savepoint
  por elemento y commit por elemento, porque el envio a la Cloud API ya
  salio y no se puede deshacer. Sin ese commit, un fallo posterior
  revierte el estado 'enviado' y el cron siguiente le escribe al cliente
  otra vez.

Nota: `marketing_lead_intelligence` y `crm_engagement_automation`, que
eran los dos sospechosos apuntados en la ronda anterior, estan **limpios**
de este patron.

## El unico real: el cron de consumo de IA reventaba entero

`chatroom_ai_usage`. Tres cosas encadenadas, y la primera es un fallo
introducido en una ronda anterior de este mismo trabajo.

### El mixin estaba en la clase equivocada

`chatroom.ai.usage.snapshot` llama a `_persist_diagnostic_record`, pero
el `_inherit` con `chatroom.diagnostic.mixin` se habia puesto en
`chatroom.ai.funding`, otra clase del mismo fichero. No se ve leyendo la
clase; se ve preguntandoselo al registro:

    chatroom.ai.funding           _persist? si   _persist_record? si
    chatroom.ai.usage.snapshot    _persist? NO   _persist_record? NO

Consecuencia medida sobre `qa_claude_b` con la API caida
(`scratchpad/ver_fallo_uso.py`):

| | antes | ahora |
|---|---|---|
| `action_refresh` | **AttributeError** | UserError con el motivo |
| `_cron_refresh_usage` | **revienta** | devuelve 0 |

El cron solo atrapa `UserError`. Un `AttributeError` no lo es, asi que
subia hasta el planificador y el trabajo quedaba marcado como fallido, en
vez de anotar la incidencia y seguir.

### El indicador de Ajustes solo registraba los exitos

`_set_sync_status` escribe tres `ir.config_parameter`. Los cinco sitios
que lo llaman se reparten asi: los dos de exito no lanzan nada, y los
tres de fallo terminan todos en `raise`. Ese `raise` deshace la
transaccion **con la anotacion dentro**.

Es decir: el campo rojo de "ultimo error" de la pantalla de Ajustes no
llegaba a escribirse nunca, y la fecha de ultima sincronizacion se
quedaba en la ultima correcta. Un refresco automatico que llevara semanas
fallando se veia igual que uno sano.

Ahora `_set_sync_status(..., durable=True)` en los tres caminos de fallo
escribe en transaccion propia. En el camino correcto NO se usa: ahi
interesa que el estado y el resumen que lo respalda se guarden o se
pierdan juntos.

Comprobado leyendo los parametros desde OTRA transaccion, que es lo que
vera el usuario al abrir Ajustes (`scratchpad/ver_estado_uso.py`):

    estado guardado: error
    error guardado:  se cayo la red

### Y el rollback del cron

    except UserError:
        self.env.cr.rollback()
        return 0

Sustituido por un savepoint alrededor de la llamada. Ademas de no
deshacer la transaccion entera, quita el ultimo motivo por el que este
camino no se podia probar: `cr.rollback()` esta prohibido dentro de los
tests de Odoo, asi que cualquier prueba del cron fallaba por el arnes
antes de llegar a comprobar nada.

### Pruebas

Ocho nuevas, y **cinco suspenden con el codigo anterior**, todas por la
asercion y no por un artefacto del arnes. Una de ellas,
`test_the_model_really_has_the_diagnostic_helpers`, comprueba
directamente en el registro que el modelo tiene los ayudantes: es la
unica forma de que un mixin puesto en la clase de al lado se note.

## Barrido: metodos llamados sobre modelos que no los tienen

Escrito a raiz del mixin mal puesto de `chatroom_ai_usage`. La clave es
que **no se puede hacer leyendo el codigo**: la llamada es correcta, el
mixin existe y el fichero lo importa. Hay que preguntarle al REGISTRO,
que es quien sabe lo que hereda cada modelo sumando todos los modulos
instalados.

`scratchpad/scan_metodos.py` revisa `self.<metodo>()` dentro de clases con
`_name`, y `self.env['x.y'].<metodo>()` en cualquier sitio.

**2.230 llamadas revisadas, 0 hallazgos.** El de `chatroom_ai_usage` era
el unico, y ya estaba arreglado.

Tres modelos salen como "no instalados, sin comprobar": `mailing.list`,
`mailing.mailing` y `project.task`. Los tres sitios que los usan estan
protegidos con `'x' in self.env` y un mensaje claro; comprobado uno a uno.

### Limitacion importante del metodo

El escaner solo sirve para modulos **instalados**: en uno que no lo este,
sus propios metodos no estan en el registro y saldrian todos como falsos
positivos. Por eso hay que comprobar primero el estado de instalacion.

Haciendolo aparecio otra cosa.

## Dos modulos del ambito no estaban instalados (y uno no podia estarlo)

`chatroom_ai_autonomy` y `chatroom_control_center` estaban en disco pero
sin instalar. Como **`-u` sobre un modulo no instalado es un no-op**
-el mismo error que `-i` sobre uno instalado-, sus pruebas nunca habian
entrado en ninguna regresion de este trabajo.

Al instalarlos, `chatroom_ai_autonomy` fallo:

    ValueError: External ID not found in the system:
    chatroom_ai_autonomy.menu_chatroom_ai_autonomy_root

`autonomy_exception_views.xml` (cuarto en el manifiesto) define un
`menuitem` cuyo padre se declara en `chatroom_ai_autonomy_menus.xml`
(septimo). En una base nueva el modulo **no se puede instalar**. En una
donde ya lo estaba no se nota, porque el xmlid ya existe: por eso nunca
habia dado la cara.

Arreglado moviendo ese `menuitem` al fichero de menus, con los demas.

## Barrido: `except` mas estrechos de lo que el bloque puede lanzar

`scratchpad/scan_except.py`, validado contra 2 positivos y 5 negativos.
Mira dos situaciones concretas, no "todo except estrecho":

- **RED**: el bloque sale a la red y no se cubre `OSError` ni `Exception`.
- **CRON**: un `_cron_*` con un `except` estrecho.

5 candidatos, 3 reales.

### La red: `URLError` no cubre lo que pasa al LEER

`meta_api.py` (x2) y `social_network_api.py` envuelven `urlopen` y
convierten todo en `MetaGraphError` / `SocialNetworkApiError`, que es lo
que esperan **23 sitios** del codigo. Capturaban
`HTTPError, URLError, TimeoutError, ValueError`.

`URLError` solo cubre lo que falla al ABRIR la conexion. Un corte
mientras se lee el cuerpo sale como `HTTPException` (IncompleteRead,
RemoteDisconnected) o como `OSError` (ConnectionReset, SSLError), y esos
se escapaban sin convertirse. Los 23 manejadores se los perdian y el
fallo subia hasta tumbar la sincronizacion entera: exactamente el mismo
patron que el AttributeError del cron de consumo.

Anadidos `HTTPException` y `OSError` a los tres.

### El cron de consumo, otra vez

`_cron_refresh_usage` seguia capturando solo `UserError`. Ahora tiene
ademas un manejador amplio que registra el fallo entero en el log -un
error asi hay que arreglarlo, no esconderlo- y deja el cron vivo para el
proximo intento, en vez de que el planificador lo marque como fallido.

### Un falso positivo y un vecino

`_cron_notify_waiting_response` capturaba `TypeError, ValueError`, pero
solo alrededor del `int()` de un parametro de configuracion, con valor
por defecto. Correcto tal cual.

Mirandolo se vio otra cosa al lado: el bucle que avisa canal por canal no
tenia proteccion. Un fallo en uno tumbaba la corrida y revertia la marca
`waiting_response_notified` de los ya avisados, asi que el cron siguiente
les mandaba el aviso otra vez. Ahora lleva savepoint por conversacion,
igual que `_cron_retry_failed_messages` en el mismo fichero.

## Lo que NO se toco: autonomia contra la puerta de aprobacion

Al instalar `chatroom_ai_autonomy` fallan dos de sus pruebas. **No es una
regresion de este trabajo** -el unico cambio propio en
`chatroom_ai_agent/models/chatroom_ai_task.py` es un indice en
`completed_at`- sino un conflicto de diseño entre dos modulos.

`chatroom_ai_autonomy` autoriza una accion concreta escribiendo
`requires_approval = False` en la linea del plan, y lo dice en un
comentario: *"The policy is the per-task approval gate. It does not
modify the global tool definition; it only authorizes this concrete
task."*

`chatroom_ai_agent` lo impide por dos sitios distintos:

1. El `write` de `chatroom.ai.task.action` **revierte** cualquier
   escritura de ese campo al valor de la herramienta. Comprobado
   (`scratchpad/ver_autonomia.py`):

       linea creada con requires_approval=True
       tras write(False)        -> True

2. Y la puerta de ejecucion no lee el campo de la linea, sino
   `tool.requires_approval`.

Es decir, la autorizacion por tarea de la autonomia no funciona, y no por
descuido: hay una defensa deliberada que la anula. Hoy la unica forma de
ejecutar una accion marcada como sensible es que `approved_by` sea un
usuario del grupo manager, o sea, una aprobacion humana real.

**Resolverlo a favor de la autonomia significa debilitar a proposito una
puerta de aprobacion, y esa decision no es mia.** Queda documentado y sin
tocar.

## Instalacion en base limpia: los 31 modulos

Lo de `chatroom_ai_autonomy` enseño que **`-u` en verde no significa que
el modulo se pueda instalar**. Un fallo de orden en el manifiesto solo se
ve en una base donde el xmlid todavia no existe.

Comprobado creando `qa_fresh` desde cero e instalando los 31 modulos del
ambito con `--without-demo=all`, que es como se instala en produccion:

    0 errores · Modules loaded · los 31 en estado 'installed'

Conviene repetirlo cada vez que se toque un manifiesto o un fichero de
datos. Es barato y cierra una clase entera de fallo que las regresiones
de `-u` no ven.

Detalle del metodo, por si se repite: construir la lista de modulos con
`ls | xargs basename` **parte por espacios**, y la ruta lleva "Program
Files". Salian 97 modulos en vez de 31. Mejor un bucle sobre el glob.

## Aislamiento por empresa: 16 reglas nuevas

De los modelos del ambito con `company_id`, 27 tenian regla por empresa y
32 no. La asimetria delataba olvido, no criterio.

El caso que lo resume:

    chatroom.channel   3 reglas, todas con ('company_id', 'in', company_ids)
    chatroom.ai.task   2 reglas, NINGUNA menciona empresa
                       y la de administrador es [('id', '!=', False)]

O sea: las conversaciones estaban aisladas, pero las tareas de IA -que
llevan el contenido de esas conversaciones en su prompt y su resultado-
no. Un responsable de la empresa A veia las de la B.

### Por que las reglas son GLOBALES

Odoo une con OR las reglas de los grupos a los que pertenece el usuario,
y aplica las globales con AND sobre ese resultado. Una regla por empresa
puesta en un grupo se habria **sumado** a la de administrador
(`[('id', '!=', False)]`) en vez de restringirla, y no habria aislado
nada. Por eso van sin `groups`.

Dominio: `['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`.
La rama de `False` deja pasar los registros "de todas las empresas"; con
los campos `required=True` no llega a usarse, pero evita que el dia que
alguien haga el campo opcional las filas desaparezcan sin explicacion.

16 modelos, en 8 modulos. `chatroom_ai_usage` y `crm_customer_experience`
no tenian fichero de seguridad: se creo y se anadio al manifiesto.

### Lo que se dejo fuera a proposito, y por que

Los modelos de **configuracion** no llevan regla. Sus registros vienen
del XML del modulo y el `default=lambda self: self.env.company` los fija
a la empresa 1:

    chatroom.ai.tool       13 filas, 13 del XML, todas de la empresa 1
    chatroom.ai.playbook    9 filas,  9 del XML, todas de la empresa 1

Ponerles esta regla dejaria al agente **sin herramientas** en cualquier
segunda empresa, y con ello sin funcionar. Arreglarlo de verdad exige
decidir antes si las herramientas y los playbooks son globales o de cada
empresa, y eso es una decision de producto, no de codigo.

`crm.team.member` tambien queda fuera: es un modelo del core de Odoo, no
de estos modulos.

### Comprobacion

`chatroom_ai_agent/tests/test_aislamiento_empresa.py`, seis pruebas con
dos empresas y dos responsables de verdad. **Tres suspenden al quitar la
regla**: la que mira de A a B, la que mira de B a A y la que intenta
leer por identificador (que es lo que hace una URL). Las otras tres
-usuario con las dos empresas, registro sin empresa, y que el cron con
`sudo` siga viendolo todo- pasan en ambos casos por diseño: estan para
que el aislamiento no rompa nada.

## crm_customer_intelligence: el corte RFM ya se prueba

Era el peor ratio del ambito: 2.626 lineas y 12 pruebas. Y lo que no se
probaba era justo el corte A/B/C, de donde salen las listas de envio, las
alertas y los paneles.

15 pruebas nuevas sobre logica pura:

- **El reparto percentil.** Diez clientes dan exactamente 2/3/5. Se fijan
  tambien los bordes que el codigo trata a mano: con un solo cliente el
  20% redondea a cero y sin la guarda del minimo se quedaba sin
  categoria; con dos, uno a A y otro a B.
- **Los codigos salen del catalogo.** La documentacion promete que si el
  usuario recodifica sus categorias el corte usa las que existen de
  verdad. Se comprueba renombrandolas a oro/plata/bronce.
- **Los umbrales**, incluidos los de respaldo (70/40) cuando alguien
  desactiva todas las categorias, y que ambos son inclusivos.
- **La fusion de fuentes**: que los totales se sumen, que gane la fecha
  mas reciente -quedarse con la de la fuente externa envejeceria al
  cliente sin motivo- y que una fila sin importe o sin contacto no cree
  un cliente en la clasificacion.

Aviso honesto: **ninguna de estas 15 cazo un fallo.** La logica estaba
bien. Son pruebas de caracterizacion: fijan un comportamiento correcto
pero no probado, en un sitio donde un error cambia de categoria a
clientes reales sin que nadie lo note.
