from odoo import _, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_dji_volver_presupuesto(self):
        """Desde el PICK o el ALB/OUT: devuelve a presupuesto la venta de origen."""
        ventas = self.sale_id
        if not ventas:
            raise UserError(_('Este traslado no viene de un pedido de venta.'))
        return ventas.action_dji_volver_presupuesto()
