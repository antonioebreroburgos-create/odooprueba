# -*- coding: utf-8 -*-
from odoo import models, fields, api

DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
DIAS_LABEL = {
    'lunes': 'Lunes', 'martes': 'Martes', 'miercoles': 'Miércoles',
    'jueves': 'Jueves', 'viernes': 'Viernes', 'sabado': 'Sábado', 'domingo': 'Domingo',
}

# Etiquetas que excluyen el pedido del planificador (normalizado sin tildes, mayúsculas)
TAGS_EXCLUIR = [
    'faltas',
    'devolucion',
    'no tratar. ppto en estudio',
    'no tratar',
]

def _norm(s):
    return s.lower().strip() \
        .replace('é','e').replace('è','e').replace('ê','e') \
        .replace('á','a').replace('à','a').replace('â','a') \
        .replace('ó','o').replace('ò','o').replace('ô','o') \
        .replace('í','i').replace('ì','i').replace('î','i') \
        .replace('ú','u').replace('ù','u').replace('û','u') \
        .replace('ñ','n')


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
    def get_pedidos(self, ruta_id=None, dia=None):
        """Devuelve presupuestos (draft/sent) filtrados por ruta y/o día, excluyendo etiquetas especiales"""
        domain = [('state', 'in', ['draft', 'sent'])]
        if ruta_id:
            domain.append(('route_ids', 'in', [int(ruta_id)]))

        orders = self.env['sale.order'].search(domain, order='partner_id asc, name asc')

        result = []
        for o in orders:
            tag_norms = [_norm(t.name) for t in o.so_tag_ids]

            # Excluir pedidos con etiquetas prohibidas
            if any(tn in TAGS_EXCLUIR for tn in tag_norms):
                continue

            dia_tags = [tn for tn in tag_norms if tn in DIAS]

            if dia == 'sin_dia' and dia_tags:
                continue
            if dia and dia != 'sin_dia' and dia not in dia_tags:
                continue

            rutas = o.route_ids
            # Ciudad: dirección de entrega → cliente facturación → partner principal
            city = (
                (o.partner_shipping_id.city if o.partner_shipping_id else '') or
                (o.partner_invoice_id.city if o.partner_invoice_id else '') or
                o.partner_id.city or
                o.partner_id.commercial_partner_id.city or
                ''
            ).strip()

            result.append({
                'id': o.id,
                'name': o.name,
                'partner': o.partner_id.name or '',
                'city': city,
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
        """Devuelve todas las rutas que tienen presupuestos activos (excluyendo etiquetas especiales)"""
        rutas = self.env['stock.route'].search([])
        result = []
        for r in rutas:
            # Contar pedidos válidos (sin etiquetas excluidas)
            candidates = self.env['sale.order'].search([
                ('state', 'in', ['draft', 'sent']),
                ('route_ids', 'in', [r.id]),
            ])
            count = sum(
                1 for o in candidates
                if not any(_norm(t.name) in TAGS_EXCLUIR for t in o.so_tag_ids)
            )
            if count > 0:
                result.append({'id': r.id, 'name': r.name, 'count': count})
        return result

    @api.model
    def set_dia_pedido(self, order_id, dia_nuevo):
        """Cambia el día de reparto de un pedido (etiqueta)"""
        order = self.env['sale.order'].browse(int(order_id))
        if not order:
            return {'error': 'Pedido no encontrado'}

        Tag = self.env['sale.order.tag']

        # Quitar todas las etiquetas de día existentes
        tags_a_quitar = order.so_tag_ids.filtered(
            lambda t: _norm(t.name) in DIAS
        )
        order.so_tag_ids = [(3, t.id) for t in tags_a_quitar]

        if dia_nuevo and dia_nuevo != 'sin_dia':
            label = DIAS_LABEL.get(dia_nuevo, dia_nuevo.capitalize())
            tag = Tag.search([('name', '=ilike', label)], limit=1)
            if not tag:
                tag = Tag.create({'name': label})
            order.so_tag_ids = [(4, tag.id)]

        return {'ok': True}

    @api.model
    def set_ruta_pedido(self, order_id, ruta_id):
        """Cambia la ruta/repartidor de un pedido"""
        order = self.env['sale.order'].browse(int(order_id))
        if not order:
            return {'error': 'Pedido no encontrado'}

        todas_rutas_reparto = self.env['stock.route'].search([]).ids
        otras_rutas = order.route_ids.filtered(lambda r: r.id not in todas_rutas_reparto)

        if ruta_id:
            order.route_ids = [(5, 0, 0)]
            for r in otras_rutas:
                order.route_ids = [(4, r.id)]
            order.route_ids = [(4, int(ruta_id))]
        else:
            order.route_ids = [(5, 0, 0)]
            for r in otras_rutas:
                order.route_ids = [(4, r.id)]

        return {'ok': True}
