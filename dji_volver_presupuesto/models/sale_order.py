from markupsafe import Markup, escape

from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _dji_comprobar_volver(self):
        """Comprueba que la venta se puede devolver a presupuesto."""
        self.ensure_one()
        if self.state != 'sale':
            raise UserError(_('%s no está confirmado; solo se pueden devolver a presupuesto pedidos confirmados.', self.name))
        facturas = self.invoice_ids.filtered(lambda f: f.state == 'posted')
        if facturas:
            raise UserError(_(
                '%(pedido)s ya tiene factura publicada (%(facturas)s). '
                'Haz antes la rectificativa; no se puede volver a presupuesto.',
                pedido=self.name, facturas=', '.join(facturas.mapped('name'))))
        entregados = self.picking_ids.filtered(
            lambda p: p.state == 'done' and p.location_dest_id.usage == 'customer')
        if entregados:
            raise UserError(_(
                'La mercancía de %(pedido)s ya se ha entregado al cliente (%(alb)s). '
                'En ese caso hay que hacer una devolución, no volver a presupuesto.',
                pedido=self.name, alb=', '.join(entregados.mapped('name'))))

    def action_dji_volver_presupuesto(self):
        """Deshace el picking, cancela la venta y la deja en presupuesto.

        1. Cancela los traslados que no están hechos (ALB/OUT y PICK pendientes),
           liberando lo reservado.
        2. En los traslados internos ya hechos (PICK Stock -> Furgón) pone las
           cantidades a cero, con lo que el stock vuelve a su ubicación de origen
           con el mismo lote.
        3. Cancela la venta (y sus facturas en borrador) y la pasa a presupuesto.
        """
        for order in self:
            order._dji_comprobar_volver()

        for order in self:
            pendientes = order.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
            hechos = order.picking_ids.filtered(
                lambda p: p.state == 'done' and p.location_dest_id.usage != 'customer')

            # 1. Traslados pendientes: liberar reservas y cancelar
            if pendientes:
                pendientes.do_unreserve()
                pendientes.with_context(skip_cancel_activity=True).action_cancel()

            # 2. Traslados hechos (PICK): cantidades a cero
            devuelto = []
            for picking in hechos:
                bloqueado = picking.is_locked
                if bloqueado:
                    picking.is_locked = False
                lineas = picking.move_line_ids.filtered(lambda ml: ml.quantity)
                for ml in lineas:
                    devuelto.append('%s: %s %s%s' % (
                        ml.product_id.display_name,
                        ('%g' % ml.quantity).replace('.', ','),
                        ml.product_uom_id.name,
                        ' (lote %s)' % ml.lot_id.name if ml.lot_id else ''))
                lineas.write({'quantity': 0})
                if bloqueado:
                    picking.is_locked = True
                picking.message_post(body=_(
                    'Cantidades puestas a cero al devolver %s a presupuesto. '
                    'El stock vuelve a su ubicación de origen.', order.name))

            # 3. Cancelar la venta y dejarla en presupuesto
            if order.locked:
                order.action_unlock()
            order._action_cancel()
            order.action_draft()

            cuerpo = Markup('<p><b>%s</b></p>') % _('Devuelto a presupuesto.')
            if pendientes:
                cuerpo += Markup('<p>%s %s</p>') % (_('Cancelados:'), ', '.join(pendientes.mapped('name')))
            if hechos:
                cuerpo += Markup('<p>%s %s</p>') % (_('Puestos a cero:'), ', '.join(hechos.mapped('name')))
            if devuelto:
                cuerpo += Markup('<ul>%s</ul>') % Markup('').join(
                    Markup('<li>%s</li>') % escape(t) for t in devuelto)
            order.message_post(body=cuerpo)

        if len(self) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return True
