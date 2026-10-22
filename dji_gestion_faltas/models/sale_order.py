from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_abrir_gestion_faltas(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Gestionar faltas",
            "res_model": "dji.faltas.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }
