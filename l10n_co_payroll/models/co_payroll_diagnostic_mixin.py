from odoo import models, modules


class CoPayrollDiagnosticMixin(models.AbstractModel):
    """Guarda el motivo de un fallo aunque después se lance una excepción.

    El patrón que había repartido por la nómina es este:

        except Exception as error:
            record.write({'state': 'error', 'error_message': str(error)})
            raise UserError(...)

    En Odoo, una excepción que sale del método deshace la transacción
    entera, así que ese `write` **se pierde siempre**. El usuario lee el
    diálogo de error, lo cierra, y la ficha sigue como si nunca se
    hubiera intentado nada.

    Donde más duele es en la transmisión a la DIAN: el `write` que se
    perdía guardaba `retry_count` y `next_retry_at`, o sea el contador de
    reintentos y cuándo toca el siguiente. Al deshacerse, el contador
    nunca avanzaba y el cron de reintentos no tenía nada que recoger:
    cada vuelta empezaba de cero contra la DIAN.

    Ojo con lo que NO debe pasar por aquí: un estado de negocio que
    convenga deshacer con el resto de la operación. Esto es solo para el
    rastro del diagnóstico.
    """
    _name = 'l10n.co.payroll.diagnostic.mixin'
    _description = 'Diagnóstico de nómina que sobrevive al fallo'

    def _persist_diagnostic(self, values, despues=None):
        """Escribe `values` en una transacción propia y la confirma.

        `despues` es opcional: una función que recibe el registro ya
        dentro de esa transacción, para lo que haya que guardar además
        del `write`. En la DIAN sirve para la bitácora de intentos, que
        se perdía por el mismo motivo que el resto.

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
            if despues:
                despues(self)
            return
        with self.env.registry.cursor() as cr:
            registro = self.with_env(self.env(cr=cr))
            registro.write(values)
            if despues:
                despues(registro)
