from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dji_albaran_sin_precios = fields.Boolean(
        string='Albarán sin precios',
        help='Si se marca, los albaranes de entrega de este cliente se imprimen sin precios, IVA ni totales.',
    )
