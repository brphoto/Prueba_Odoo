from odoo import api, models, modules


class ChatroomDiagnosticMixin(models.AbstractModel):
    """Deja constancia de un fallo aunque después se lance una excepción.

    En Odoo, una excepción que sale del método deshace la transacción
    entera. Por eso el patrón `record.write({'error_message': ...})`
    seguido de `raise` **pierde siempre** lo que acaba de escribir: el
    usuario lee el diálogo, lo cierra, y la ficha sigue como si no se
    hubiera intentado nada.

    Hay dos situaciones distintas y cada una necesita lo suyo:

    - El registro YA EXISTE y venía de una transacción anterior: basta
      con volver a escribirlo desde una transacción propia.
      -> `_persist_diagnostic`

    - El registro se creó en ESTA misma transacción, así que el rollback
      no solo pierde el mensaje: se lleva el registro entero y no queda
      ni rastro del intento. Escribirlo desde otro cursor tampoco vale,
      porque esa fila todavía no existe fuera de la transacción que va a
      deshacerse. Hay que crearlo de nuevo, ya en la transacción aparte.
      -> `_persist_diagnostic_record`

    Nada de esto es para un estado de negocio que convenga deshacer con
    el resto de la operación. Es solo para el rastro del diagnóstico.
    """
    _name = 'chatroom.diagnostic.mixin'
    _description = 'Diagnóstico de chatroom que sobrevive al fallo'

    def init(self):
        """Registra el mixin en ir_model si la base aún no lo tiene.

        El mixin llegó en una versión posterior de chatroom_whatsapp. En una
        base donde chatroom_whatsapp no se actualizó desde entonces, instalar
        o actualizar un módulo que lo hereda (chatroom_ai_usage,
        chatroom_ai_agent, chatroom_payment) falla al guardar la herencia:
        "Missing required value for the field 'Padre' (parent_id)" en
        ir.model.inherit. Odoo llama a init() de cada modelo antes de
        reflejar sus herencias, así que aquí da tiempo a registrar el padre.
        """
        super().init()
        name = ChatroomDiagnosticMixin._name
        self.env.cr.execute('SELECT 1 FROM ir_model WHERE model = %s', [name])
        if self.env.cr.fetchone():
            return
        env = self.env(context=dict(self.env.context, module='chatroom_whatsapp'))
        env['ir.model']._reflect_models([name])
        env['ir.model.fields']._reflect_fields([name])

    def _persist_diagnostic(self, values):
        """Reescribe `values` sobre este registro, en transacción propia.

        Solo sirve para registros que ya estaban guardados antes de la
        operación que ha fallado.
        """
        if not self:
            return
        if modules.module.current_test:
            # En pruebas no se abre otra transacción: dejaría datos
            # escritos de verdad y el caso siguiente los heredaría.
            self.write(values)
            return
        with self.env.registry.cursor() as cr:
            self.with_env(self.env(cr=cr)).write(values)

    @api.model
    def _persist_diagnostic_record(self, modelo, values):
        """Crea un registro de rastro en una transacción propia.

        Para cuando lo que se pierde no es un campo sino el registro
        entero, porque se creó dentro de la operación que falla.
        Devuelve el id creado, o False si no se pudo.
        """
        if modules.module.current_test:
            return self.env[modelo].sudo().create(values).id
        with self.env.registry.cursor() as cr:
            entorno = self.env(cr=cr)
            return entorno[modelo].sudo().create(values).id
