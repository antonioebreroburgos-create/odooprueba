import re

from odoo import models

from odoo.addons.dji_albaran.models.stock_picking import _cantidad, _num

from .account_move import _es_promo, _nombre_comercial, dji_impuestos


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def dji_presupuesto_datos(self):
        """Todo lo que pinta el presupuesto (o pedido), ya calculado y formateado."""
        self.ensure_one()
        es_presupuesto = self.state in ('draft', 'sent')
        lineas = []
        for linea in self.order_line.sorted(lambda l: (l.sequence, l.id)):
            if linea.display_type in ('line_section', 'line_subsection', 'line_note'):
                lineas.append({'nota': linea.name or '', 'seccion': linea.display_type != 'line_note'})
                continue
            if linea.display_type or linea.is_downpayment:
                continue
            producto = linea.product_id
            nombre = (linea.name or producto.display_name or '').strip()
            if producto.default_code:
                nombre = re.sub(r'^\[%s\]\s*' % re.escape(producto.default_code), '', nombre)
            nombre = ' · '.join(p.strip() for p in nombre.splitlines() if p.strip())
            promo = _es_promo(linea.price_unit, linea.discount)
            porcentajes = [t.amount for t in linea.tax_ids if t.amount_type == 'percent']
            unidad = ''
            if linea.product_uom_id and producto and linea.product_uom_id != producto.uom_id:
                unidad = linea.product_uom_id.name
            lineas.append({
                'nota': False,
                'codigo': producto.default_code or '',
                'nombre': nombre,
                'cantidad': _cantidad(linea.product_uom_qty),
                'unidad': unidad,
                'promo': promo,
                'precio': '' if promo else _num(linea.price_unit),
                'dto': '' if promo or not linea.discount else f'{_cantidad(linea.discount)} %',
                'iva': '' if promo else ' + '.join(f'{_cantidad(p)} %' for p in porcentajes),
                'importe': '' if promo else _num(linea.price_subtotal),
            })

        comercial = self.user_id
        contacto = ''
        if comercial:
            socio = comercial.partner_id
            contacto = socio.phone or socio.email or ''
            if 'mobile' in socio._fields and socio['mobile']:
                contacto = socio['mobile']
        return {
            'es_presupuesto': es_presupuesto,
            'titulo': 'Presupuesto' if es_presupuesto else 'Pedido',
            'numero': self.name,
            'fecha': self.date_order.strftime('%d/%m/%Y') if self.date_order else '',
            'validez': self.validity_date.strftime('%d/%m/%Y') if es_presupuesto and self.validity_date else '',
            'comercial': comercial.name or '',
            'contacto': contacto,
            'cliente': self.partner_id.commercial_partner_id,
            'nombre_comercial': _nombre_comercial(self.partner_shipping_id, self.partner_id, self.partner_id.commercial_partner_id),
            'entrega': self.partner_shipping_id or self.partner_id,
            'lineas': lineas,
            'impuestos': dji_impuestos(self),
            'base': _num(self.amount_untaxed),
            'total': _num(self.amount_total),
            'forma_pago': self.payment_term_id.name or '',
            'nota': self.note,
        }
