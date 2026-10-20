from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dji_registro_mercantil = fields.Char(
        string='Registro Mercantil (pie de factura)',
        help='Texto que sale al pie de las facturas, p. ej. '
             '"Inscrita en el Registro Mercantil de Huelva, tomo 000, folio 00, hoja H-0000".',
    )
