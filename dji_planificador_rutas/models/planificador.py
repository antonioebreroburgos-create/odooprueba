# -*- coding: utf-8 -*-
from odoo import models, fields, api
import json

DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
DIAS_LABEL = {
    'lunes': 'Lunes', 'martes': 'Martes', 'miercoles': 'Miércoles',
    'jueves': 'Jueves', 'viernes': 'Viernes', 'sabado': 'Sábado', 'domingo': 'Domingo',
}


class DjiPlanificadorRutas(models.TransientModel):
    _name = 'dji.planificador.rutas'
    _description = 'Planificador de Rutas DJI'

    ruta_id = fields.Many2one('stock.route', string='Repartidor / Ruta')
    dia = fields.Selection([
        ('lunes', 'Lunes'),
        ('martes', 'Martes'),
        ('miercoles', 'Miércoles'),
        ('jueves', 'Jueves'),
        ('viernes', 'Viernes'),
        ('sabado', 'Sábado'),
        ('domingo', 'Domingo'),
        ('sin_dia', 'Sin día'),
    ], string='Día')

    @api.model
    def get_pedidos(self, ruta_id=None, dia=None):  # args posicionales desde JS
        """Devuelve presupuestos (draft/sent) filtrados por ruta y/o día"""
        domain = [('state', 'in', ['draft', 'sent'])]
        if ruta_id:
            domain.append(('route_ids', 'in', [int(ruta_id)]))

        orders = self.env['sale.order'].search(domain, order='partner_id asc')

        # Filtrar por día via etiquetas
        DIAS_NORM = {d.lower().replace('é', 'e').replace('á', 'a').replace('ó', 'o')
                     .replace('í', 'i').replace('ú', 'u'): d for d in DIAS}

        result = []
        for o in orders:
            tag_names = [t.name.lower().strip()
                         .replace('é', 'e').replace('á', 'a').replace('ó', 'o')
                         .replace('í', 'i').replace('ú', 'u')
                         for t in o.so_tag_ids]
            dia_tags = [t for t in tag_names if t in DIAS_NORM]

            if dia == 'sin_dia' and dia_tags:
                continue
            if dia and dia != 'sin_dia' and dia not in dia_tags:
                continue

            rutas = o.route_ids
            result.append({
                'id': o.id,
                'name': o.name,
                'partner': o.partner_id.name or '',
                'amount': o.amount_total,
                'currency': o.currency_id.symbol or '€',
                'tags': [t.name for t in o.so_tag_ids],
                'dia_tags': dia_tags,
                'ruta_ids': rutas.ids,
                'ruta_names': [r.name for r in rutas],
                'state': o.state,
            })

        return result

    @api.model
    def get_rutas(self):
        """Devuelve todas las rutas que tienen presupuestos activos"""
        rutas = self.env['stock.route'].search([])
        # Solo rutas que tienen al menos un presupuesto
        result = []
        for r in rutas:
            count = self.env['sale.order'].search_count([
                ('state', 'in', ['draft', 'sent']),
                ('route_ids', 'in', [r.id]),
            ])
            if count > 0:
                result.append({'id': r.id, 'name': r.name, 'count': count})
        return result

    @api.model
    def set_dia_pedido(self, order_id=None, dia_nuevo=None):
        """Cambia el día de reparto de un pedido (etiqueta)"""
        order = self.env['sale.order'].browse(int(order_id))
        if not order:
            return {'error': 'Pedido no encontrado'}

        Tag = self.env['sale.order.tag']

        # Quitar todas las etiquetas de día existentes
        tags_a_quitar = order.so_tag_ids.filtered(
            lambda t: t.name.lower().strip()
            .replace('é', 'e').replace('á', 'a').replace('ó', 'o')
            .replace('í', 'i').replace('ú', 'u') in DIAS
        )
        order.so_tag_ids = [(3, t.id) for t in tags_a_quitar]

        if dia_nuevo and dia_nuevo != 'sin_dia':
            # Buscar o crear etiqueta del nuevo día
            label = DIAS_LABEL.get(dia_nuevo, dia_nuevo.capitalize())
            tag = Tag.search([('name', '=ilike', label)], limit=1)
            if not tag:
                tag = Tag.create({'name': label})
            order.so_tag_ids = [(4, tag.id)]

        return {'ok': True}

    @api.model
    def set_ruta_pedido(self, order_id=None, ruta_id=None):
        """Cambia la ruta/repartidor de un pedido"""
        order = self.env['sale.order'].browse(int(order_id))
        if not order:
            return {'error': 'Pedido no encontrado'}

        # Obtener todas las rutas actuales que NO son de reparto
        # (conservamos otras rutas que no sean las de repartidores)
        todas_rutas_reparto = self.env['stock.route'].search([]).ids
        otras_rutas = order.route_ids.filtered(lambda r: r.id not in todas_rutas_reparto)

        if ruta_id:
            order.route_ids = [(5, 0, 0)]  # limpiar todas
            for r in otras_rutas:
                order.route_ids = [(4, r.id)]
            order.route_ids = [(4, int(ruta_id))]
        else:
            # Sin ruta — quitar todas las rutas de reparto
            order.route_ids = [(5, 0, 0)]
            for r in otras_rutas:
                order.route_ids = [(4, r.id)]

        return {'ok': True}
