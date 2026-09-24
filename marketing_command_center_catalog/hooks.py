"""Migración del módulo cuando venía llamándose `..._patiotuerca`.

El módulo se llamaba `marketing_command_center_patiotuerca` y su modelo
de conexión `marketing.patiotuerca.connection`. El nombre no describía lo
que hace: importa un feed JSON genérico por endpoint o por fichero, hace
upsert por id externo y lleva estados publicado/despublicado. De
Patiotuerca no había nada salvo el nombre.

Odoo no sabe que un módulo pasó a llamarse de otra forma. Sin este
enganche, en las bases donde el módulo viejo estaba instalado pasaría lo
siguiente: el viejo quedaría marcado como «no instalable» (su carpeta ya
no existe), el nuevo se instalaría desde cero creando su propia tabla, y
las conexiones y los vehículos ya cargados quedarían huérfanos en una
tabla que nadie vuelve a mirar.

Lo que se hace aquí, antes de que Odoo instale nada, es renombrar en
sitio: el módulo, sus registros XML, el modelo, su tabla y las columnas
que apuntan a ella. Así la instalación «nueva» se encuentra los datos ya
en su sitio y solo actualiza lo que haga falta.

Es idempotente: si no hay rastro del nombre viejo, no hace nada.
"""
import logging

_logger = logging.getLogger(__name__)

MODULO_VIEJO = "marketing_command_center_patiotuerca"
MODULO_NUEVO = "marketing_command_center_catalog"
MODELO_VIEJO = "marketing.patiotuerca.connection"
MODELO_NUEVO = "marketing.catalog.connection"
TABLA_VIEJA = "marketing_patiotuerca_connection"
TABLA_NUEVA = "marketing_catalog_connection"

# Identificadores XML que cambiaron de nombre dentro del módulo. Sin esto
# Odoo crearía registros nuevos y dejaría los viejos sueltos: grupos
# duplicados, reglas duplicadas y un menú repetido.
XMLIDS = [
    ("group_patiotuerca_user", "group_catalog_user"),
    ("group_patiotuerca_manager", "group_catalog_manager"),
    ("module_category_marketing_patiotuerca", "module_category_marketing_catalog"),
    ("privilege_marketing_patiotuerca", "privilege_marketing_catalog"),
    ("patiotuerca_connection_company_rule", "catalog_connection_company_rule"),
    ("patiotuerca_listing_company_rule", "catalog_listing_company_rule"),
    ("access_marketing_patiotuerca_connection_user",
     "access_marketing_catalog_connection_user"),
    ("access_marketing_patiotuerca_connection_manager",
     "access_marketing_catalog_connection_manager"),
    ("action_marketing_patiotuerca_connections",
     "action_marketing_catalog_connections"),
    ("menu_marketing_patiotuerca_root", "menu_marketing_catalog_root"),
    ("menu_marketing_patiotuerca_connections",
     "menu_marketing_catalog_connections"),
    ("menu_marketing_patiotuerca_listings",
     "menu_marketing_catalog_listings"),
    ("view_marketing_patiotuerca_connection_list",
     "view_marketing_catalog_connection_list"),
    ("view_marketing_patiotuerca_connection_form",
     "view_marketing_catalog_connection_form"),
    ("patiotuerca_demo_connection", "catalog_demo_connection"),
    ("patiotuerca_demo_vehicle_1", "catalog_demo_vehicle_1"),
    ("patiotuerca_demo_vehicle_2", "catalog_demo_vehicle_2"),
    ("patiotuerca_demo_vehicle_3", "catalog_demo_vehicle_3"),
    ("patiotuerca_demo_vehicle_4", "catalog_demo_vehicle_4"),
]


def _existe_tabla(cr, nombre):
    cr.execute("select to_regclass(%s)", (nombre,))
    return bool(cr.fetchone()[0])


def _existe_columna(cr, tabla, columna):
    cr.execute(
        "select 1 from information_schema.columns "
        "where table_name = %s and column_name = %s", (tabla, columna))
    return bool(cr.fetchone())


def migrar_nombre_anterior(env):
    """Convierte lo que quede del módulo viejo al nombre nuevo."""
    cr = env.cr

    cr.execute("select id, state from ir_module_module where name = %s",
               (MODULO_VIEJO,))
    fila = cr.fetchone()
    if not fila:
        return  # Instalación limpia: no hay nada que migrar.

    _, estado = fila
    if estado != "installed":
        # Estaba solo listado, nunca instalado: basta con quitarlo para
        # que no aparezca un módulo fantasma sin carpeta.
        cr.execute("delete from ir_module_module where name = %s", (MODULO_VIEJO,))
        _logger.info("Se retira el módulo %s, que nunca llegó a instalarse.",
                     MODULO_VIEJO)
        return

    _logger.info("Se migra %s -> %s conservando sus datos.",
                 MODULO_VIEJO, MODULO_NUEVO)

    # Se conserva la fila del modulo NUEVO, que es la que Odoo acaba de
    # crear y esta usando en este mismo momento: borrarla deja al ORM con
    # un registro en cache que ya no existe y el arranque muere con
    # MissingError al leer `description_html`. Lo que se mueve son los
    # datos del viejo, y el viejo se retira al final.
    cr.execute("update ir_model_data set module = %s where module = %s",
               (MODULO_NUEVO, MODULO_VIEJO))
    cr.execute(
        "update ir_module_module_dependency set name = %s where name = %s",
        (MODULO_NUEVO, MODULO_VIEJO))

    for viejo, nuevo in XMLIDS:
        cr.execute(
            "update ir_model_data set name = %s "
            "where module = %s and name = %s",
            (nuevo, MODULO_NUEVO, viejo))

    # El modelo y su tabla.
    cr.execute("update ir_model set model = %s where model = %s",
               (MODELO_NUEVO, MODELO_VIEJO))
    cr.execute("update ir_model_fields set relation = %s where relation = %s",
               (MODELO_NUEVO, MODELO_VIEJO))
    cr.execute("update ir_model_fields set model = %s where model = %s",
               (MODELO_NUEVO, MODELO_VIEJO))
    cr.execute(
        "update ir_model_data set name = %s "
        "where model = 'ir.model' and name = %s",
        ("model_" + MODELO_NUEVO.replace(".", "_"),
         "model_" + MODELO_VIEJO.replace(".", "_")))
    # `ir_model_data` guarda ADEMAS el nombre del modelo en texto. Sin
    # actualizarlo, al cargar el XML Odoo encuentra el identificador pero
    # ve que apunta a otro modelo y aborta con "found record of different
    # model marketing.patiotuerca.connection".
    cr.execute("update ir_model_data set model = %s where model = %s",
               (MODELO_NUEVO, MODELO_VIEJO))
    cr.execute(
        "update ir_act_window set res_model = %s where res_model = %s",
        (MODELO_NUEVO, MODELO_VIEJO))
    cr.execute("update ir_ui_view set model = %s where model = %s",
               (MODELO_NUEVO, MODELO_VIEJO))
    # El resto de sitios donde el nombre del modelo vive como texto suelto.
    for tabla, columna in (("ir_act_server", "model_name"),
                           ("ir_filters", "model_id"),
                           ("mail_followers", "res_model"),
                           ("mail_message_subtype", "res_model")):
        if _existe_tabla(cr, tabla) and _existe_columna(cr, tabla, columna):
            cr.execute(
                'update "%s" set "%s" = %%s where "%s" = %%s'
                % (tabla, columna, columna), (MODELO_NUEVO, MODELO_VIEJO))
    # El modelo hereda de mail.thread, asi que arrastra su historial de
    # mensajes y sus actividades: si no se renombran tambien, el chatter
    # de cada conexion aparece vacio.
    cr.execute(
        "update mail_message set model = %s where model = %s",
        (MODELO_NUEVO, MODELO_VIEJO))
    if _existe_tabla(cr, "mail_activity"):
        cr.execute(
            "update mail_activity set res_model = %s where res_model = %s",
            (MODELO_NUEVO, MODELO_VIEJO))
    if _existe_columna(cr, "ir_attachment", "res_model"):
        cr.execute(
            "update ir_attachment set res_model = %s where res_model = %s",
            (MODELO_NUEVO, MODELO_VIEJO))

    if _existe_tabla(cr, TABLA_VIEJA) and not _existe_tabla(cr, TABLA_NUEVA):
        cr.execute('alter table "%s" rename to "%s"' % (TABLA_VIEJA, TABLA_NUEVA))
        _logger.info("Tabla %s renombrada a %s.", TABLA_VIEJA, TABLA_NUEVA)

    # La secuencia de la clave primaria arrastra el nombre viejo.
    cr.execute("select to_regclass(%s)", (TABLA_VIEJA + "_id_seq",))
    if cr.fetchone()[0]:
        cr.execute('alter sequence "%s_id_seq" rename to "%s_id_seq"'
                   % (TABLA_VIEJA, TABLA_NUEVA))

    # Por ultimo se retira el modulo viejo, junto con el registro XML que
    # lo representaba. Si se dejara, Odoo lo mostraria como un modulo sin
    # carpeta y cualquier intento de abrirlo fallaria.
    cr.execute("select id from ir_module_module where name = %s", (MODULO_VIEJO,))
    fila_vieja = cr.fetchone()
    if fila_vieja:
        cr.execute(
            "delete from ir_model_data "
            "where model = 'ir.module.module' and res_id = %s", (fila_vieja[0],))
        cr.execute("delete from ir_module_module where id = %s", (fila_vieja[0],))

    _logger.info("Migración de %s completada.", MODULO_VIEJO)


def pre_init_hook(env):
    """Odoo llama a esto justo antes de instalar el módulo."""
    migrar_nombre_anterior(env)
