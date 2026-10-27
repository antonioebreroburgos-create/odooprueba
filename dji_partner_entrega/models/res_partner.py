# -*- coding: utf-8 -*-
from odoo import models, fields, api

# Zonas de reparto — editar aquí para añadir/quitar zonas
ZONAS = [
    ('zona_norte', 'Norte'),
    ('zona_sur', 'Sur'),
    ('zona_este', 'Este'),
    ('zona_oeste', 'Oeste'),
    ('zona_centro', 'Centro'),
    ('zona_almeria', 'Almería'),
    ('zona_huelva', 'Huelva'),
    ('zona_sevilla', 'Sevilla'),
    ('zona_cadiz', 'Cádiz'),
    ('zona_malaga', 'Málaga'),
    ('zona_cordoba', 'Córdoba'),
    ('zona_granada', 'Granada'),
    ('zona_jaen', 'Jaén'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ── Zona de reparto (selección única) ──────────────────────────────────
    dji_zona = fields.Selection(
        selection=ZONAS,
        string='Zona de reparto',
        help='Zona geográfica a la que pertenece este cliente / dirección de entrega.',
    )

    # ── Días de servicio (checkboxes) ──────────────────────────────────────
    dji_dia_lunes    = fields.Boolean(string='Lunes')
    dji_dia_martes   = fields.Boolean(string='Martes')
    dji_dia_miercoles = fields.Boolean(string='Miércoles')
    dji_dia_jueves   = fields.Boolean(string='Jueves')
    dji_dia_viernes  = fields.Boolean(string='Viernes')
    dji_dia_sabado   = fields.Boolean(string='Sábado')
    dji_dia_domingo  = fields.Boolean(string='Domingo')

    # Campo calculado: lista de claves de días activos (para uso en Python)
    @property
    def dji_dias_activos(self):
        """Devuelve lista de claves ['lunes', 'martes', ...] con los días marcados."""
        dias = []
        if self.dji_dia_lunes:    dias.append('lunes')
        if self.dji_dia_martes:   dias.append('martes')
        if self.dji_dia_miercoles: dias.append('miercoles')
        if self.dji_dia_jueves:   dias.append('jueves')
        if self.dji_dia_viernes:  dias.append('viernes')
        if self.dji_dia_sabado:   dias.append('sabado')
        if self.dji_dia_domingo:  dias.append('domingo')
        return dias

    def get_dji_dias_activos(self):
        """Versión como método (para llamar desde RPC)."""
        return self.dji_dias_activos
