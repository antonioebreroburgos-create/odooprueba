from odoo import api, fields, models


class DjiDevolucionPropuesta(models.Model):
    _name = 'dji.devolucion.propuesta'
    _description = 'Línea de propuesta de devolución masiva'
    _order = 'sale_order_id, picking_id, product_id'

    devolucion_id = fields.Many2one('sale.order', string='Devolución', required=True, ondelete='cascade', index=True)
    move_id = fields.Many2one('stock.move', string='Movimiento original', required=True, readonly=True, ondelete='cascade')
    picking_id = fields.Many2one(related='move_id.picking_id', string='Albarán', store=True)
    sale_line_id = fields.Many2one('sale.order.line', string='Línea de venta', required=True, readonly=True, ondelete='cascade')
    sale_order_id = fields.Many2one(related='sale_line_id.order_id', string='Venta', store=True)
    fecha_venta = fields.Datetime(related='sale_order_id.date_order', string='Fecha venta')
    product_id = fields.Many2one('product.product', string='Producto', required=True, readonly=True)
    lot_id = fields.Many2one('stock.lot', string='Lote', readonly=True)
    cantidad = fields.Float('Cantidad a devolver', digits='Product Unit', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unidad', readonly=True)
    price_unit = fields.Float(related='sale_line_id.price_unit', string='Precio venta')
    discount = fields.Float(related='sale_line_id.discount', string='Desc. %')
    currency_id = fields.Many2one(related='devolucion_id.currency_id')
    subtotal = fields.Monetary('Importe (sin imp.)', compute='_compute_subtotal', currency_field='currency_id')

    @api.depends('cantidad', 'uom_id', 'sale_line_id.price_unit', 'sale_line_id.discount', 'sale_line_id.product_uom_id')
    def _compute_subtotal(self):
        for line in self:
            sl = line.sale_line_id
            if not sl or not line.uom_id:
                line.subtotal = 0.0
                continue
            qty = line.uom_id._compute_quantity(line.cantidad, sl.product_uom_id)
            line.subtotal = qty * sl.price_unit * (1 - (sl.discount or 0.0) / 100.0)


class DjiDevolucionFaltante(models.Model):
    _name = 'dji.devolucion.faltante'
    _description = 'Cantidad de devolución no asignable a ninguna venta'
    _order = 'product_id'

    devolucion_id = fields.Many2one('sale.order', string='Devolución', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Producto', required=True, readonly=True)
    cantidad = fields.Float('Cantidad sin asignar', digits='Product Unit', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='Unidad', readonly=True)
    motivo = fields.Char('Motivo', readonly=True)
