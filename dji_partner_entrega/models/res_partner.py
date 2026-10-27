# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ── Zona de reparto (Many2one a dji.zona) ─────────────────────────────
    dji_zona_id = fields.Many2one(
        comodel_name='dji.zona',
        string='Zona de reparto',
        ondelete='set null',
        help='Zona geográfica a la que pertenece este cliente / dirección de entrega.',
    )

    # ── Días de servicio (checkboxes) ──────────────────────────────────────
    dji_dia_lunes     = fields.Boolean(string='Lunes')
    dji_dia_martes    = fields.Boolean(string='Martes')
    dji_dia_miercoles = fields.Boolean(string='Miércoles')
    dji_dia_jueves    = fields.Boolean(string='Jueves')
    dji_dia_viernes   = fields.Boolean(string='Viernes')
    dji_dia_sabado    = fields.Boolean(string='Sábado')
    dji_dia_domingo   = fields.Boolean(string='Domingo')

    @property
    def dji_dias_activos(self):
        """Devuelve lista de claves ['lunes', 'martes', ...] con los días marcados."""
        dias = []
        if self.dji_dia_lunes:     dias.append('lunes')
        if self.dji_dia_martes:    dias.append('martes')
        if self.dji_dia_miercoles: dias.append('miercoles')
        if self.dji_dia_jueves:    dias.append('jueves')
        if self.dji_dia_viernes:   dias.append('viernes')
        if self.dji_dia_sabado:    dias.append('sabado')
        if self.dji_dia_domingo:   dias.append('domingo')
        return dias
