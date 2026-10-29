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
    if not partner:
        return []
    dias = []
    if getattr(partner, 'dji_dia_lunes', False):     dias.append('lunes')
    if getattr(partner, 'dji_dia_martes', False):    dias.append('martes')
    if getattr(partner, 'dji_dia_miercoles', False): dias.append('miercoles')
    if getattr(partner, 'dji_dia_jueves', False):    dias.append('jueves')
    if getattr(partner, 'dji_dia_viernes', False):   dias.append('viernes')
    if getattr(partner, 'dji_dia_sabado', False):    dias.append('sabado')
    if getattr(partner, 'dji_dia_domingo', False):   dias.append('domingo')
    return dias

def _partner_zona_id(partner):
    if not partner:
        return None
    zona = getattr(partner, 'dji_zona_id', False)
    return zona.id if zona else None

def _partner_zona_name(partner):
    if not partner:
        return ''
    zona = getattr(partner, 'dji_zona_id', False)
    return zona.name if zona else ''


class DjiPlanificadorRutas(models.TransientModel):
    _name = 'dji.planificador.rutas'
    _description = 'Planificador de Rutas DJI'

    @api.model
    def get_pedidos(self, ruta_id=None, dia=None, zona_id=None, modo_dia='tags', modo_estado='todos'):
        """
        Devuelve presupuestos (draft/sent) filtrados.

        Parámetros:
          ruta_id  – ID de ruta/repartidor (opcional)
          dia      – clave de día o 'sin_dia' (opcional)
          zona_id  – ID de dji.zona (opcional)
          modo_dia – 'tags'    → filtra por etiquetas de día del pedido
                     'partner' → filtra por días de servicio del partner (dji_dia_*)
        """
        domain = [('state', 'in', ['draft', 'sent', 'sale'])]
        if ruta_id:
            domain.append(('route_ids', 'in', [int(ruta_id)]))

        orders = self.env['sale.order'].search(domain, order='partner_id asc, name asc')

        result = []
        for o in orders:
            tag_norms = [_norm(t.name) for t in o.so_tag_ids]
            if any(tn in TAGS_EXCLUIR for tn in tag_norms):
                continue

            shipping = o.partner_shipping_id or o.partner_id

            # Filtro de zona
            if zona_id:
                p_zona_id = _partner_zona_id(shipping) or _partner_zona_id(o.partner_id)
                if p_zona_id != int(zona_id):
                    continue

            # Filtro de día
            if modo_dia == 'partner':
                partner_dias = _partner_dias(shipping) or _partner_dias(o.partner_id)
                if dia == 'sin_dia' and partner_dias:
                    continue
                if dia and dia != 'sin_dia' and dia not in partner_dias:
                    continue
                dia_tags = partner_dias
            else:
                dia_tags = [tn for tn in tag_norms if tn in DIAS]
                if dia == 'sin_dia' and dia_tags:
                    continue
                if dia and dia != 'sin_dia' and dia not in dia_tags:
                    continue

            city = (
                (o.partner_shipping_id.city if o.partner_shipping_id else '') or
                (o.partner_invoice_id.city if o.partner_invoice_id else '') or
                o.partner_id.city or
                o.partner_id.commercial_partner_id.city or ''
            ).strip()

            rutas = o.route_ids
            zona_name = _partner_zona_name(shipping) or _partner_zona_name(o.partner_id)
            zona_id_val = _partner_zona_id(shipping) or _partner_zona_id(o.partner_id)

            # Nombre comercial: si hay dirección de entrega diferente al cliente, mostramos su nombre
            # Si no, usamos el nombre comercial del partner principal
            shipping_partner = o.partner_shipping_id
            if shipping_partner and shipping_partner != o.partner_id:
                commercial_name = (shipping_partner.name or '').strip()
            else:
                commercial_name = (o.partner_id.commercial_company_name or '').strip()

            result.append({
                'id': o.id,
                'name': o.name,
                'partner': o.partner_id.name or '',
                'commercial_name': commercial_name,
                'city': city,
                'amount': o.amount_total,
                'currency': o.currency_id.symbol or '€',
                'tags': [t.name for t in o.so_tag_ids],
                'dia_tags': dia_tags,
                'ruta_ids': rutas.ids,
                'ruta_names': [r.name for r in rutas],
                'state': o.state,
                'estado_label': 'Pedido' if o.state == 'sale' else 'Presupuesto',
                'zona_id': zona_id_val or 0,
                'zona_name': zona_name,
                'partner_dias': _partner_dias(shipping) or _partner_dias(o.partner_id),
            })

        return result

    @api.model
    def get_rutas(self):
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
        """Devuelve las zonas (dji.zona) que tienen presupuestos activos."""
        try:
            zonas = self.env['dji.zona'].search([])
        except Exception:
            return []

        orders = self.env['sale.order'].search([('state', 'in', ['draft', 'sent'])])
        zona_count = {}
        for o in orders:
            tag_norms = [_norm(t.name) for t in o.so_tag_ids]
            if any(tn in TAGS_EXCLUIR for tn in tag_norms):
                continue
            shipping = o.partner_shipping_id or o.partner_id
            zid = _partner_zona_id(shipping) or _partner_zona_id(o.partner_id)
            if zid:
                zona_count[zid] = zona_count.get(zid, 0) + 1

        result = []
        for z in zonas:
            count = zona_count.get(z.id, 0)
            if count > 0:
                result.append({'id': z.id, 'name': z.name, 'count': count})
        return result

    @api.model
    def set_dia_pedido(self, order_id, dia_nuevo):
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
