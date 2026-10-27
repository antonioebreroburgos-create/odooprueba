# -*- coding: utf-8 -*-
from odoo import models, fields, api

DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
DIAS_LABEL = {
    'lunes': 'Lunes', 'martes': 'Martes', 'miercoles': 'Miércoles',
    'jueves': 'Jueves', 'viernes': 'Viernes', 'sabado': 'Sábado', 'domingo': 'Domingo',
}
TAGS_EXCLUIR = ['faltas', 'devolucion', 'no tratar. ppto en estudio', 'no tratar']

def _norm(s):
    return s.lower().strip() \
        .replace('é','e').replace('è','e').replace('ê','e') \
        .replace('á','a').replace('à','a').replace('â','a') \
        .replace('ó','o').replace('ò','o').replace('ô','o') \
        .replace('í','i').replace('ì','i').replace('î','i') \
        .replace('ú','u').replace('ù','u').replace('û','u') \
        .replace('ñ','n')

def _partner_dias(partner):
    """Devuelve lista de días activos en el partner (campo dji_*)."""
    if not partner:
        return []
    dias = []
    if getattr(partner, 'dji_dia_lunes', False):    dias.append('lunes')
    if getattr(partner, 'dji_dia_martes', False):   dias.append('martes')
    if getattr(partner, 'dji_dia_miercoles', False): dias.append('miercoles')
    if getattr(partner, 'dji_dia_jueves', False):   dias.append('jueves')
    if getattr(partner, 'dji_dia_viernes', False):  dias.append('viernes')
    if getattr(partner, 'dji_dia_sabado', False):   dias.append('sabado')
    if getattr(partner, 'dji_dia_domingo', False):  dias.append('domingo')
    return dias

def _partner_zona(partner):
    """Devuelve la zona del partner (campo dji_zona)."""
    if not partner:
        return None
    return getattr(partner, 'dji_zona', None) or None


class DjiPlanificadorRutas(models.TransientModel):
    _name = 'dji.planificador.rutas'
    _description = 'Planificador de Rutas DJI'

    @api.model
    def get_pedidos(self, ruta_id=None, dia=None, zona=None, modo_dia='tags'):
        """
        Devuelve presupuestos (draft/sent) filtrados.

        Parámetros:
          ruta_id  – ID de ruta/repartidor (opcional)
          dia      – clave de día o 'sin_dia' (opcional)
          zona     – clave de zona dji_zona del partner (opcional)
          modo_dia – 'tags'    → filtra por etiquetas de día en el pedido (comportamiento clásico)
                     'partner' → filtra por días de servicio del partner (dji_dia_*)
        """
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

            # Determinar partner de entrega
            shipping = o.partner_shipping_id or o.partner_id

            # Filtro de zona (por campo dji_zona del partner de entrega o principal)
            if zona:
                partner_zona = _partner_zona(shipping) or _partner_zona(o.partner_id)
                if partner_zona != zona:
                    continue

            # Días: según el modo elegido
            if modo_dia == 'partner':
                # Usar campos dji_dia_* del partner
                partner_dias = _partner_dias(shipping) or _partner_dias(o.partner_id)
                if dia == 'sin_dia' and partner_dias:
                    continue
                if dia and dia != 'sin_dia' and dia not in partner_dias:
                    continue
                dia_tags = partner_dias  # lo que se devuelve al frontend como "día"
            else:
                # Comportamiento clásico: etiquetas de día en el pedido
                dia_tags = [tn for tn in tag_norms if tn in DIAS]
                if dia == 'sin_dia' and dia_tags:
                    continue
                if dia and dia != 'sin_dia' and dia not in dia_tags:
                    continue

            # Ciudad
            city = (
                (o.partner_shipping_id.city if o.partner_shipping_id else '') or
                (o.partner_invoice_id.city if o.partner_invoice_id else '') or
                o.partner_id.city or
                o.partner_id.commercial_partner_id.city or
                ''
            ).strip()

            rutas = o.route_ids
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
                # Información extra del partner para el planificador
                'zona': _partner_zona(shipping) or _partner_zona(o.partner_id) or '',
                'partner_dias': _partner_dias(shipping) or _partner_dias(o.partner_id),
            })

        return result

    @api.model
    def get_rutas(self):
        """Devuelve todas las rutas que tienen presupuestos activos (excluyendo etiquetas especiales)."""
        rutas = self.env['stock.route'].search([])
        result = []
        for r in rutas:
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
    def get_zonas(self):
        """Devuelve las zonas que tienen presupuestos activos."""
        # Importar las zonas desde el modelo de partner si existe el módulo
        try:
            from odoo.addons.dji_partner_entrega.models.res_partner import ZONAS
        except ImportError:
            return []

        orders = self.env['sale.order'].search([('state', 'in', ['draft', 'sent'])])
        zona_count = {}
        for o in orders:
            tag_norms = [_norm(t.name) for t in o.so_tag_ids]
            if any(tn in TAGS_EXCLUIR for tn in tag_norms):
                continue
            shipping = o.partner_shipping_id or o.partner_id
            zona = _partner_zona(shipping) or _partner_zona(o.partner_id)
            if zona:
                zona_count[zona] = zona_count.get(zona, 0) + 1

        result = []
        for key, label in ZONAS:
            count = zona_count.get(key, 0)
            if count > 0:
                result.append({'key': key, 'label': label, 'count': count})
        return result

    @api.model
    def set_dia_pedido(self, order_id, dia_nuevo):
        """Cambia el día de reparto de un pedido (etiqueta)."""
        order = self.env['sale.order'].browse(int(order_id))
        if not order:
            return {'error': 'Pedido no encontrado'}

        Tag = self.env['sale.order.tag']
        tags_a_quitar = order.so_tag_ids.filtered(lambda t: _norm(t.name) in DIAS)
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
        """Cambia la ruta/repartidor de un pedido."""
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
