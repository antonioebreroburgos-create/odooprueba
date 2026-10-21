import re

from odoo import models

from odoo.addons.dji_albaran.models.stock_picking import _cantidad, _num

from .account_move import _linea_direccion, dji_impuestos


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _dji_ref_proveedor(self, linea):
        """Código del artículo en el catálogo del proveedor (tarifa de proveedor)."""
        vendedor = linea.selected_seller_id
        if not vendedor or vendedor.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id:
            vendedor = linea.product_id.seller_ids.filtered(
                lambda s: s.partner_id.commercial_partner_id == self.partner_id.commercial_partner_id
                and (not s.product_id or s.product_id == linea.product_id))[:1]
        return (vendedor.product_code or '').strip()

    def _dji_entregar_en(self):
        """Dónde nos lo tienen que traer: dirección de envío directo, la del
        almacén que recibe o, si no hay, la de la empresa."""
        if self.dest_address_id:
            return self.dest_address_id
        tipo = self.picking_type_id if 'picking_type_id' in self._fields else False
        almacen = tipo and tipo.warehouse_id
        return (almacen and almacen.partner_id) or self.company_id.partner_id

    def dji_compra_datos(self, sin_precios=False):
        """Todo lo que pinta el pedido de compra (o la solicitud de presupuesto)."""
        self.ensure_one()
        solicitud = self.state in ('draft', 'sent', 'to approve')
        lineas = []
        for linea in self.order_line.sorted(lambda l: (l.sequence, l.id)):
            if linea.display_type in ('line_section', 'line_subsection', 'line_note'):
                lineas.append({'nota': linea.name or '', 'seccion': linea.display_type != 'line_note'})
                continue
            if linea.display_type or linea.is_downpayment:
                continue
            producto = linea.product_id
            nombre = (linea.name or producto.display_name or '').strip()
            ref_proveedor = self._dji_ref_proveedor(linea) if producto else ''
            # Odoo antepone al nombre nuestro código o el del proveedor: ya van en columna
            for codigo in (producto.default_code, ref_proveedor):
                if codigo:
                    nombre = re.sub(r'^\[%s\]\s*' % re.escape(codigo), '', nombre)
            nombre = ' · '.join(p.strip() for p in nombre.splitlines() if p.strip())
            porcentajes = [t.amount for t in linea.tax_ids if t.amount_type == 'percent']
            lineas.append({
                'nota': False,
                'codigo': producto.default_code or '',
                'ref_proveedor': ref_proveedor,
                'nombre': nombre,
                'cantidad': _cantidad(linea.product_qty),
                'unidad': linea.product_uom_id.name or '',
                'precio': _num(linea.price_unit),
                'dto': f'{_cantidad(linea.discount)} %' if linea.discount else '',
                'iva': ' + '.join(f'{_cantidad(p)} %' for p in porcentajes),
                'importe': _num(linea.price_subtotal),
                'entrega': linea.date_planned.strftime('%d/%m/%Y') if linea.date_planned else '',
            })

        fechas = {l['entrega'] for l in lineas if not l['nota'] and l['entrega']}
        entrega_unica = len(fechas) <= 1
        if entrega_unica:
            for l in lineas:
                l['entrega'] = ''

        comprador = self.user_id
        contacto = ''
        if comprador:
            socio = comprador.partner_id
            contacto = socio.phone or socio.email or ''
            if 'mobile' in socio._fields and socio['mobile']:
                contacto = socio['mobile']
        proveedor = self.partner_id.commercial_partner_id
        entregar = self._dji_entregar_en()
        fecha_entrega = self.date_planned or (self.order_line[:1].date_planned if self.order_line else False)
        return {
            'solicitud': solicitud,
            'anulado': self.state == 'cancel',
            'sin_precios': sin_precios,
            'titulo': 'Solicitud de presupuesto' if solicitud else 'Pedido de compra',
            'numero': self.name,
            'fecha': (self.date_approve if not solicitud and self.date_approve else self.date_order).strftime('%d/%m/%Y')
                     if (self.date_approve or self.date_order) else '',
            'entrega': fecha_entrega.strftime('%d/%m/%Y') if fecha_entrega else '',
            'varias_fechas': not entrega_unica,
            'su_referencia': self.partner_ref or '',
            'comprador': comprador.name or '',
            'contacto': contacto,
            'proveedor': proveedor,
            'proveedor_contacto': self.partner_id if self.partner_id != proveedor else False,
            'proveedor_tel': self.partner_id.phone or proveedor.phone or '',
            'proveedor_email': self.partner_id.email or proveedor.email or '',
            'entregar_nombre': entregar.name if entregar != self.company_id.partner_id else self.company_id.name,
            'entregar_direccion': _linea_direccion(entregar),
            'entregar_tel': entregar.phone or '',
            'con_ref_proveedor': any(l.get('ref_proveedor') for l in lineas),
            'lineas': lineas,
            'impuestos': dji_impuestos(self),
            'base': _num(self.amount_untaxed),
            'total': _num(self.amount_total),
            'forma_pago': self.payment_term_id.name or '',
            'incoterm': self.incoterm_id.display_name if self.incoterm_id else '',
            'nota': self.note,
            'registro': self.company_id.dji_registro_mercantil or '',
        }
