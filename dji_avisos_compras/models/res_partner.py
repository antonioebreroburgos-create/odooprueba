from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dji_whatsapp_pedidos = fields.Char(
        string='WhatsApp pedidos',
        help='Móvil del responsable de pedidos del proveedor. Al confirmar una compra se le '
             'manda por WhatsApp el pedido en PDF para que confirme que lo ha recibido.',
    )

    @api.onchange('dji_whatsapp_pedidos')
    def _onchange_dji_whatsapp_pedidos(self):
        if self.dji_whatsapp_pedidos:
            self.dji_whatsapp_pedidos = self.dji_whatsapp_pedidos.replace(' ', '').replace('-', '')
