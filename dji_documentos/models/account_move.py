import base64
import re

from odoo import models

from odoo.addons.dji_albaran.models.stock_picking import _cantidad, _nombre_comercial, _num


def _qr_png(env, texto):
    """PNG del QR: con la librería qrcode (dependencia de Odoo) y, si no
    estuviera, con el generador de códigos de barras de los informes."""
    try:
        import io
        import qrcode
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=1)
        qr.add_data(texto)
        qr.make(fit=True)
        salida = io.BytesIO()
        qr.make_image().save(salida, format='PNG')
        return salida.getvalue()
    except Exception:
        pass
    try:
        return env['ir.actions.report'].barcode('QR', texto, width=180, height=180)
    except Exception:
        return False


def _es_promo(precio, descuento):
    return (descuento or 0.0) >= 100.0 or not precio


def dji_impuestos(registro, signo=1):
    """Desglose de IVA por tipo (base y cuota de cada impuesto).

    Facturas: la cuota sale de los apuntes de impuesto de la propia factura
    (lo contabilizado). Pedidos: se calcula por tipo y se cuadra el último
    céntimo con el total de impuestos del pedido."""
    es_factura = registro._name == 'account.move'
    lineas = registro.invoice_line_ids.filtered(lambda l: l.display_type == 'product') if es_factura \
        else registro.order_line.filtered(lambda l: not l.display_type)
    moneda = registro.currency_id
    datos = {}  # impuesto -> [base, cuota]
    for linea in lineas:
        for imp in linea.tax_ids:
            for t in (imp.children_tax_ids if imp.amount_type == 'group' else imp):
                datos.setdefault(t, [0.0, 0.0])[0] += linea.price_subtotal
    if es_factura:
        for apunte in registro.line_ids.filtered('tax_line_id'):
            datos.setdefault(apunte.tax_line_id, [0.0, 0.0])[1] += abs(apunte.amount_currency)
    else:
        for t, valores in datos.items():
            valores[1] = moneda.round(valores[0] * t.amount / 100.0) if t.amount_type == 'percent' else 0.0
        if datos:
            diferencia = moneda.round(registro.amount_tax - sum(v[1] for v in datos.values()))
            if diferencia:
                mayor = max(datos, key=lambda t: datos[t][1])
                datos[mayor][1] += diferencia
    filas = []
    for t in sorted(datos, key=lambda t: (t.amount, t.id)):
        base, cuota = datos[t]
        if not base and not cuota:
            continue
        filas.append({
            'etiqueta': t.invoice_label or t.name,
            'porcentaje': f'{_cantidad(t.amount)} %' if t.amount_type == 'percent' else '',
            'base': _num(signo * base),
            'cuota': _num(signo * cuota),
        })
    return filas


def dji_bancos(company):
    return [
        {'banco': b.bank_id.name or '', 'cuenta': b.acc_number}
        for b in company.partner_id.bank_ids
    ]


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ------------------------------------------------------------
    # Albaranes de cada línea de factura
    # ------------------------------------------------------------
    def _dji_albaranes_linea(self, linea):
        """Albaranes (ALB/OUT, o de devolución en una rectificativa) de los
        que sale una línea de factura. Se acotan a los hechos entre la factura
        anterior de esa misma línea de venta y esta, para no mezclar los de
        otras facturas cuando un pedido se factura en varias veces."""
        rect = self.move_type == 'out_refund'
        movs = linea.sale_line_ids.move_ids.filtered(lambda m: m.state == 'done' and m.picking_id)
        if rect:
            movs = movs.filtered(lambda m: m.location_id.usage == 'customer')
        else:
            movs = movs.filtered(lambda m: m.location_dest_id.usage == 'customer')
        albaranes = movs.picking_id
        if not albaranes:
            return albaranes
        fecha = self.invoice_date or self.date
        if not fecha:
            return albaranes
        previas = linea.sale_line_ids.invoice_lines.move_id.filtered(
            lambda m: m != self and m.state == 'posted' and m.move_type == self.move_type
            and m.invoice_date and (m.invoice_date, m.id) < (fecha, self.id or 0))
        desde = max(previas.mapped('invoice_date')) if previas else None
        acotados = albaranes.filtered(
            lambda p: p.date_done and p.date_done.date() <= fecha
            and (not desde or p.date_done.date() > desde))
        return acotados or albaranes

    # ------------------------------------------------------------
    # QR de VERI*FACTU: se usa el que ya calcula el módulo de VERI*FACTU
    # instalado (el de Odoo o el de la OCA), sea cual sea el nombre del campo.
    # ------------------------------------------------------------
    def dji_factura_qr(self):
        self.ensure_one()
        candidatos = [n for n in self._fields if 'qr' in n and ('verifactu' in n or 'aeat' in n)]
        # primero las imágenes ya generadas, luego las URL
        candidatos.sort(key=lambda n: 0 if self._fields[n].type == 'binary' else 1)
        for nombre in candidatos:
            campo = self._fields[nombre]
            try:
                valor = self[nombre]
            except Exception:
                continue
            if not valor:
                continue
            if campo.type == 'binary':
                datos = valor if isinstance(valor, bytes) else valor.encode()
                return 'data:image/png;base64,' + datos.decode()
            if campo.type in ('char', 'text') and str(valor).startswith('http'):
                png = _qr_png(self.env, str(valor))
                if png:
                    return 'data:image/png;base64,' + base64.b64encode(png).decode()
        return False

    def _dji_motivo_rectificacion(self):
        self.ensure_one()
        for nombre, campo in self._fields.items():
            if 'refund_reason' in nombre and campo.type == 'selection' and self[nombre]:
                etiquetas = dict(campo._description_selection(self.env))
                return etiquetas.get(self[nombre], self[nombre])
        ref = (self.ref or '').strip()
        m = re.match(r'^[^:]{3,40}:\s*[^,]+,\s*(.+)$', ref)
        return m.group(1) if m else ref

    # ------------------------------------------------------------
    # Todo lo que pinta la factura, ya calculado y formateado
    # ------------------------------------------------------------
    def dji_factura_datos(self):
        self.ensure_one()
        rect = self.move_type == 'out_refund'
        signo = -1 if rect else 1
        menos = '−' if rect else ''
        cliente = self.partner_id.commercial_partner_id
        direccion = self.partner_id

        # Líneas agrupadas por albarán
        grupos = {}
        orden = []
        for linea in self.invoice_line_ids.sorted(lambda l: (l.sequence, l.id)):
            if linea.display_type in ('line_section', 'line_note'):
                clave = orden[-1] if orden else ('',)
                if clave not in grupos:
                    grupos[clave] = {'albaranes': self.env['stock.picking'], 'lineas': [], 'subtotal': 0.0}
                    orden.append(clave)
                grupos[clave]['lineas'].append({'nota': linea.name or '', 'seccion': linea.display_type == 'line_section'})
                continue
            if linea.display_type != 'product':
                continue
            albaranes = self._dji_albaranes_linea(linea)
            clave = tuple(sorted(albaranes.ids)) or ('',)
            if clave not in grupos:
                grupos[clave] = {'albaranes': albaranes, 'lineas': [], 'subtotal': 0.0}
                orden.append(clave)
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
            grupos[clave]['lineas'].append({
                'nota': False,
                'codigo': producto.default_code or '',
                'nombre': nombre,
                'cantidad': _cantidad(linea.quantity),
                'unidad': unidad,
                'promo': promo,
                'precio': '' if promo else _num(linea.price_unit),
                'dto': '' if promo or not linea.discount else f'{_cantidad(linea.discount)} %',
                'iva': '' if promo else ' + '.join(f'{_cantidad(p)} %' for p in porcentajes),
                'importe': '' if promo else menos + _num(linea.price_subtotal),
            })
            grupos[clave]['subtotal'] += linea.price_subtotal

        lista_grupos = []
        hay_albaranes = any(grupos[c]['albaranes'] for c in orden)
        def _orden_grupo(c):
            fechas = [d for d in grupos[c]['albaranes'].mapped('date_done') if d]
            return (not grupos[c]['albaranes'], min(fechas).timestamp() if fechas else 0, orden.index(c))

        for clave in sorted(orden, key=_orden_grupo):
            g = grupos[clave]
            alb = g['albaranes'].sorted(lambda p: (p.date_done or p.scheduled_date, p.id))
            if alb:
                fechas = sorted({p.date_done.strftime('%d/%m/%Y') for p in alb if p.date_done})
                pedidos = sorted({p.sale_id.name for p in alb if p.sale_id})
                titulo = ('Albarán de devolución ' if rect else 'Albarán ') if len(alb) == 1 else (
                    'Albaranes de devolución ' if rect else 'Albaranes ')
                cabecera = {
                    'titulo': titulo + ', '.join(alb.mapped('name')),
                    'detalle': ' · '.join(filter(None, [', '.join(fechas),
                                                        ('Pedido ' + ', '.join(pedidos)) if pedidos else ''])),
                }
            elif hay_albaranes:
                cabecera = {'titulo': 'Otros conceptos', 'detalle': ''}
            else:
                cabecera = False
            lista_grupos.append({
                'cabecera': cabecera,
                'subtotal': menos + _num(g['subtotal']) + ' €' if cabecera else '',
                'lineas': g['lineas'],
            })

        # Forma de pago: giro (recibo domiciliado) o transferencia
        modo = self['payment_mode_id'] if 'payment_mode_id' in self._fields else False
        nombre_modo = (modo.name if modo else '') or ''
        metodo = modo.payment_method_id if modo and 'payment_method_id' in modo._fields else False
        codigo_metodo = (metodo.code if metodo else '') or ''
        es_giro = bool(re.search(r'giro|recibo|domicil|remesa|sepa|direct.debit', f'{nombre_modo} {codigo_metodo}', re.I))
        vencimientos = []
        cuenta_cliente = ''
        if es_giro and not rect:
            for l in self.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable').sorted('date_maturity'):
                if l.date_maturity:
                    vencimientos.append({'fecha': l.date_maturity.strftime('%d/%m/%Y'), 'importe': _num(abs(l.amount_currency))})
            if 'mandate_id' in self._fields and self['mandate_id'] and self['mandate_id'].partner_bank_id:
                iban = (self['mandate_id'].partner_bank_id.acc_number or '').replace(' ', '')
                cuenta_cliente = '•••• ' + iban[-4:] if iban else ''
        forma_pago = nombre_modo or self.invoice_payment_term_id.name or ''

        origen = self.reversed_entry_id
        pedidos = self.invoice_line_ids.sale_line_ids.order_id
        return {
            'rectificativa': rect,
            'titulo': 'FACTURA RECTIFICATIVA' if rect else 'FACTURA',
            'numero': self.name if self.name and self.name != '/' else 'BORRADOR',
            'borrador': self.state == 'draft',
            'fecha': (self.invoice_date or self.date).strftime('%d/%m/%Y') if (self.invoice_date or self.date) else '',
            'cliente': cliente,
            'nombre_comercial': _nombre_comercial(self.partner_shipping_id if 'partner_shipping_id' in self._fields else False, direccion, cliente),
            'direccion': direccion,
            'cod_cliente': cliente.ref or '',
            'comercial': self.invoice_user_id.name or '',
            'forma_pago': forma_pago,
            'pedidos': ', '.join(pedidos.mapped('name')),
            'origen': origen.name or '',
            'origen_fecha': origen.invoice_date.strftime('%d/%m/%Y') if origen and origen.invoice_date else '',
            'motivo': self._dji_motivo_rectificacion() if rect else '',
            'grupos': lista_grupos,
            'impuestos': dji_impuestos(self, signo),
            'base': menos + _num(self.amount_untaxed),
            'total_iva': menos + _num(self.amount_tax),
            'total': menos + _num(self.amount_total),
            'giro': es_giro and not rect,
            'vencimientos': vencimientos,
            'cuenta_cliente': cuenta_cliente,
            'bancos': dji_bancos(self.company_id),
            'nota': self.narration,
            'qr': self.dji_factura_qr(),
            'registro': self.company_id.dji_registro_mercantil or '',
        }
