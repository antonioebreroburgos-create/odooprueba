# -*- coding: utf-8 -*-
from odoo import models, fields


class DjiZona(models.Model):
    _name = 'dji.zona'
    _description = 'Zona de reparto DJI'
    _order = 'name asc'

    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(string='Activa', default=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Ya existe una zona con ese nombre.'),
    ]
