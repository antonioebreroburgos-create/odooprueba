# -*- coding: utf-8 -*-
from odoo import models, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_dji_sort_lines(self):
        """Abre el wizard de ordenación de líneas."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ordenar líneas del pedido',
            'res_model': 'dji.sort.lines.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
            },
        }
