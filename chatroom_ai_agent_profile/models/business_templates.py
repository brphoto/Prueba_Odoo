# -*- coding: utf-8 -*-
"""Plantillas por tipo de negocio: la puesta en marcha pasa de «escribir todo»
a «revisar y ajustar». Todo queda editable en el perfil."""

# Cada guion: (código, nombre, cuándo aplica, al completar, [(dato, clave, obligatorio, opciones)])
TEMPLATES = {
    'store': {
        'label': 'Tienda o comercio',
        'role': 'asesor de ventas y atención al cliente',
        'objective': 'Resolver dudas de productos, precios, envíos y pagos con la información oficial, y '
                     'reunir los datos de quien quiere comprar para que el equipo cierre la venta.',
        'synonyms': 'precio: costo, valor, cuánto cuesta, tarifa\nenvío: despacho, entrega, delivery, domicilio\n'
                    'pago: pagar, transferencia, tarjeta, efectivo\ndevolución: cambio, reembolso, garantía',
        'playbooks': [
            ('cotizacion', 'Compra o cotización', 'Cuando el cliente quiere comprar o pedir una cotización.', 'quote', [
                ('Nombre del cliente', 'nombre', True, ''),
                ('Producto que necesita', 'necesidad', True, ''),
                ('Cantidad', 'detalle', True, ''),
                ('Ciudad de entrega', 'ciudad', False, ''),
            ]),
            ('soporte', 'Problema con un pedido', 'Cuando el cliente tiene un problema con un pedido o producto.',
             'handoff', [
                 ('Número de pedido o factura', 'referencia', True, ''),
                 ('Qué pasó', 'problema', True, 'Llegó dañado, No llegó, Producto equivocado'),
             ]),
        ],
        'checklist': ['Horario de atención', 'Envíos: ciudades, costo y tiempo', 'Formas de pago',
                      'Devoluciones y garantía', 'Promociones vigentes'],
    },
    'services': {
        'label': 'Servicios profesionales',
        'role': 'asesor comercial',
        'objective': 'Explicar los servicios con la información oficial, entender qué necesita el cliente y '
                     'agendar una reunión o dejar lista la solicitud para el equipo.',
        'synonyms': 'precio: costo, valor, tarifa, honorarios, presupuesto\nreunión: cita, llamada, videollamada',
        'playbooks': [
            ('cotizacion', 'Solicitud de servicio', 'Cuando el cliente quiere contratar o pedir una propuesta.',
             'handoff', [
                 ('Nombre y empresa', 'nombre', True, ''),
                 ('Servicio que necesita', 'necesidad', True, ''),
                 ('Alcance o detalle', 'detalle', True, ''),
                 ('Fecha en que lo necesita', 'plazo', False, ''),
             ]),
            ('reunion', 'Agendar reunión', 'Cuando el cliente quiere una reunión o llamada.', 'meeting', [
                ('Nombre', 'nombre', True, ''),
                ('Fecha y hora preferida', 'fecha_hora', True, ''),
                ('Medio', 'medio', True, 'Videollamada, Llamada, Presencial'),
            ]),
        ],
        'checklist': ['Servicios que ofrecen', 'Cómo trabajan (etapas, plazos)', 'Precios o rangos de precio',
                      'Horario de atención', 'Casos o clientes de referencia'],
    },
    'clinic': {
        'label': 'Clínica o consultorio',
        'role': 'asistente de agendamiento y atención a pacientes',
        'objective': 'Informar servicios, horarios y precios con la información oficial y agendar citas; nunca dar '
                     'diagnósticos ni indicaciones médicas.',
        'synonyms': 'cita: turno, consulta, agendar, reservar\nprecio: costo, valor, cuánto cuesta',
        'playbooks': [
            ('cita', 'Agendar cita', 'Cuando el paciente quiere una cita o turno.', 'meeting', [
                ('Nombre del paciente', 'nombre', True, ''),
                ('Especialidad o servicio', 'necesidad', True, ''),
                ('Fecha y hora preferida', 'fecha_hora', True, ''),
                ('Primera vez', 'primera_vez', False, 'Sí, No'),
            ]),
        ],
        'extra_restrictions': '- No des diagnósticos, dosis ni indicaciones médicas: ofrece una cita con el profesional.',
        'checklist': ['Especialidades y servicios', 'Horarios por especialidad', 'Precios de consulta',
                      'Seguros o convenios aceptados', 'Dirección y cómo llegar'],
    },
    'real_estate': {
        'label': 'Inmobiliaria',
        'role': 'asesor inmobiliario',
        'objective': 'Entender qué propiedad busca el cliente, informar con la información oficial y agendar visitas.',
        'synonyms': 'arriendo: alquiler, renta\ndepartamento: depa, apartamento, suite\nprecio: valor, costo, cuánto',
        'playbooks': [
            ('busqueda', 'Busca una propiedad', 'Cuando el cliente busca comprar o arrendar una propiedad.', 'handoff', [
                ('Nombre', 'nombre', True, ''),
                ('Operación', 'operacion', True, 'Compra, Arriendo'),
                ('Tipo de propiedad', 'tipo', True, 'Casa, Departamento, Terreno'),
                ('Zona o sector', 'zona', True, ''),
                ('Presupuesto', 'presupuesto', False, ''),
            ]),
            ('visita', 'Agendar visita', 'Cuando el cliente quiere visitar una propiedad.', 'meeting', [
                ('Nombre', 'nombre', True, ''),
                ('Propiedad', 'propiedad', True, ''),
                ('Fecha y hora preferida', 'fecha_hora', True, ''),
            ]),
        ],
        'checklist': ['Zonas donde trabajan', 'Requisitos para arrendar o comprar', 'Comisiones',
                      'Horario de visitas', 'Financiamiento'],
    },
    'restaurant': {
        'label': 'Restaurante',
        'role': 'anfitrión del restaurante',
        'objective': 'Informar menú, horarios y ubicación con la información oficial, tomar reservas y pedidos.',
        'synonyms': 'reserva: mesa, reservar, apartar\ndomicilio: delivery, envío, llevar\nmenú: carta, platos',
        'playbooks': [
            ('reserva', 'Reserva de mesa', 'Cuando el cliente quiere reservar una mesa.', 'meeting', [
                ('Nombre', 'nombre', True, ''),
                ('Número de personas', 'personas', True, ''),
                ('Fecha y hora', 'fecha_hora', True, ''),
            ]),
            ('pedido', 'Pedido a domicilio', 'Cuando el cliente quiere pedir comida a domicilio.', 'handoff', [
                ('Nombre', 'nombre', True, ''),
                ('Pedido', 'necesidad', True, ''),
                ('Dirección de entrega', 'direccion', True, ''),
                ('Forma de pago', 'pago', True, 'Efectivo, Tarjeta, Transferencia'),
            ]),
        ],
        'checklist': ['Menú y precios', 'Horario', 'Zonas y costo de domicilio', 'Dirección', 'Formas de pago'],
    },
    'insurance': {
        'label': 'Seguros',
        'role': 'asesor de seguros',
        'objective': 'Explicar coberturas con la información oficial y reunir los datos para cotizar; los siniestros y '
                     'reclamos pasan a una persona.',
        'synonyms': 'póliza: seguro, cobertura\nsiniestro: choque, accidente, robo\nprecio: prima, costo, valor',
        'playbooks': [
            ('cotizacion', 'Cotizar un seguro', 'Cuando el cliente quiere cotizar un seguro.', 'handoff', [
                ('Nombre', 'nombre', True, ''),
                ('Tipo de seguro', 'tipo', True, 'Vehículo, Vida, Salud'),
                ('Detalle (vehículo, edad, personas)', 'detalle', True, ''),
                ('Ciudad', 'ciudad', False, ''),
            ]),
        ],
        'checklist': ['Tipos de seguro que ofrecen', 'Aseguradoras con las que trabajan', 'Qué se necesita para cotizar',
                      'Cómo reportar un siniestro', 'Formas de pago'],
    },
}


def template_selection():
    return [(key, value['label']) for key, value in TEMPLATES.items()]
