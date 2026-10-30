# -*- coding: utf-8 -*-
from odoo import models, fields, api


SORT_FIELDS = [
    ('name', 'Producto (A→Z)'),
    ('name_desc', 'Producto (Z→A)'),
    ('price_unit', 'Precio unitario (↑ menor primero)'),
    ('price_unit_desc', 'Precio unitario (↓ mayor primero)'),
    ('margin_percent', 'Margen % (↑ menor primero)'),
    ('margin_percent_desc', 'Margen % (↓ mayor primero)'),
    ('price_subtotal', 'Importe línea (↑ menor primero)'),
    ('price_subtotal_desc', 'Importe línea (↓ mayor primero)'),
    ('product_uom_qty', 'Cantidad (↑ menor primero)'),
    ('product_uom_qty_desc', 'Cantidad (↓ mayor primero)'),
]


class DjiSortLinesWizard(models.TransientModel):
    _name = 'dji.sort.lines.wizard'
    _description = 'Ordenar líneas del pedido'

    order_id = fields.Many2one('sale.order', string='Pedido', required=True)
    sort_by = fields.Selection(SORT_FIELDS, string='Ordenar por',
                               default='margin_percent_desc', required=True)

    def action_sort(self):
        order = self.order_id
        sort_key_str = self.sort_by or 'margin_percent_desc'

        if sort_key_str.endswith('_desc'):
            field = sort_key_str[:-5]
            reverse = True
        else:
            field = sort_key_str
            reverse = False

        def get_val(line):
            val = getattr(line, field, None)
            if val is None:
                return (1, 0, '')
            if isinstance(val, str):
                return (0, 0, val.lower())
            return (0, -val if reverse else val, '')

        # Para strings el reverse funciona diferente
        def get_val_str(line):
            val = getattr(line, field, '') or ''
            return val.lower()

        def get_val_num(line):
            val = getattr(line, field, 0) or 0
            return val

        if field == 'name':
            sorted_lines = sorted(order.order_line, key=get_val_str, reverse=reverse)
        else:
            sorted_lines = sorted(order.order_line, key=get_val_num, reverse=reverse)

        for i, line in enumerate(sorted_lines):
            line.sequence = (i + 1) * 10

        return {'type': 'ir.actions.act_window_close'}
