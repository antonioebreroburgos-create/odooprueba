from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = "res.partner"

    dji_latitud = fields.Float(
        string="Latitud GPS",
        digits=(10, 7),
        help="Latitud de la dirección de entrega (coordenada GPS capturada desde la app de repartidor)",
    )
    dji_longitud = fields.Float(
        string="Longitud GPS",
        digits=(10, 7),
        help="Longitud de la dirección de entrega (coordenada GPS capturada desde la app de repartidor)",
    )
    dji_tiene_gps = fields.Boolean(
        string="Tiene GPS",
        compute="_compute_dji_tiene_gps",
        store=True,
    )
    dji_maps_url = fields.Char(
        string="Ver en Google Maps",
        compute="_compute_dji_maps_url",
    )

    @api.depends("dji_latitud", "dji_longitud")
    def _compute_dji_tiene_gps(self):
        for p in self:
            p.dji_tiene_gps = bool(p.dji_latitud and p.dji_longitud)

    @api.depends("dji_latitud", "dji_longitud")
    def _compute_dji_maps_url(self):
        for p in self:
            if p.dji_latitud and p.dji_longitud:
                p.dji_maps_url = (
                    f"https://www.google.com/maps?q={p.dji_latitud},{p.dji_longitud}"
                )
            else:
                p.dji_maps_url = False
