from odoo import api, models, modules


class MarketingDiagnosticMixin(models.AbstractModel):
    """Guarda el motivo de un fallo aunque después se lance una excepción.

    El patrón que hay repartido por todos los conectores es este:

        except Exception as error:
            record.write({'state': 'error', 'last_error': str(error)})
            raise UserError(...)

    Parece razonable y no lo es. En Odoo, una excepción que sale del
    método deshace la transacción entera, así que ese `write` **se pierde
    siempre**. El usuario lee el mensaje del diálogo, lo cierra, y el
    formulario sigue mostrando el estado anterior: ni rastro de lo que
    pasó, ni fecha, ni detalle técnico. Justo lo contrario de lo que
    pretendía quien escribió el `write`.

    Los campos de diagnóstico (`last_error`, `sync_message`,
    `permissions_summary`, ...) existen precisamente para sobrevivir al
    fallo. Para eso hay que escribirlos en una transacción aparte, que es
    lo que hace este ayudante.

    Ojo con lo que NO debe pasar por aquí: un estado de negocio que
    convenga deshacer junto con el resto de la operación. Si el envío de
    un mensaje falla y el mensaje se creó en esa misma transacción, lo
    correcto es que desaparezca entero, no dejarlo marcado como fallido.
    Esto es solo para el rastro del diagnóstico.
    """
    _name = 'marketing.diagnostic.mixin'
    _description = 'Diagnóstico que sobrevive al fallo'

    def _persist_diagnostic(self, values):
        """Escribe `values` en una transacción propia y la confirma.

        Pensado para llamarse dentro de un `except`, justo antes de
        relanzar. No relanza por su cuenta: quien llama decide qué
        excepción sale y con qué mensaje.
        """
        if not self:
            return
        if modules.module.current_test:
            # En pruebas no se abre otra transacción: dejaría datos
            # escritos de verdad en la base y el caso siguiente los
            # heredaría. Escribir en la actual basta para comprobar los
            # valores, y el propio test se deshace al terminar.
            self.write(values)
            return
        with self.env.registry.cursor() as cr:
            self.with_env(self.env(cr=cr)).write(values)

    @api.model
    def _persist_diagnostic_record(self, modelo, values):
        """Crea un registro de rastro en una transacción propia.

        Para cuando lo que se pierde no es un campo sino el registro
        entero, porque se creó dentro de la operación que falla.
        Escribirlo con `_persist_diagnostic` no serviría: desde otro
        cursor esa fila todavía no existe.

        Devuelve el id creado.
        """
        if modules.module.current_test:
            return self.env[modelo].sudo().create(values).id
        with self.env.registry.cursor() as cr:
            return self.env(cr=cr)[modelo].sudo().create(values).id
