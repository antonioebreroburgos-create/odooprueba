from odoo import fields, models


def _num(valor, decimales=2):
    """1234.5 → '1.234,50' (formato español)."""
    texto = f'{valor:,.{decimales}f}'
    return texto.replace(',', '#').replace('.', ',').replace('#', '.')


def _nombre_comercial(*contactos):
    """Nombre del establecimiento (campo "Nombre comercial" del contacto),
    p. ej. "PEÑA BETICA BOLLULLOS" para la razón social del titular. Se mira
    primero la dirección de entrega y luego el cliente; si el nombre
    comercial es igual que la razón social no se repite."""
    for contacto in contactos:
        if not contacto or 'comercial' not in contacto._fields:
            continue
        nombre = (contacto.comercial or '').strip()
        if nombre and nombre.lower() != (contacto.commercial_partner_id.name or '').strip().lower():
            return nombre
    return ''


def _cantidad(valor):
    """1.0 → '1' · 2.5 → '2,5' · 0.125 → '0,125' (sin ceros de relleno)."""
    texto = f'{valor:.3f}'.rstrip('0').rstrip('.')
    return texto.replace('.', ',')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    dji_firma_fecha = fields.Datetime(
        string='Firmado el', copy=False, readonly=True,
        help='Momento en que el cliente firmó la entrega en Odoo (botón Firmar).',
    )

    def write(self, vals):
        # Guarda cuándo firma el cliente, para imprimirlo en el albarán
        if vals.get('signature') and 'dji_firma_fecha' not in vals:
            vals = dict(vals, dji_firma_fecha=fields.Datetime.now())
        elif 'signature' in vals and not vals['signature']:
            vals = dict(vals, dji_firma_fecha=False)
        return super().write(vals)

    # ------------------------------------------------------------
    # Devoluciones: traslado de retorno (viene de un albarán o trae
    # mercancía desde la ubicación del cliente).
    # ------------------------------------------------------------
    def dji_albaran_es_devolucion(self):
        self.ensure_one()
        return bool(
            self.return_id
            or self.move_ids.origin_returned_move_id
            or self.location_id.usage == 'customer'
        )

    def dji_albaran_original(self):
        """En una devolución, el albarán (ALB/OUT) del que procede."""
        self.ensure_one()
        origen = self.return_id or self.move_ids.origin_returned_move_id.picking_id[:1]
        if not origen:
            return self.env['stock.picking']
        return origen.dji_albaran_salida()

    # ------------------------------------------------------------
    # Número de albarán: el del traslado de SALIDA (ALB/OUT/...).
    # En la entrega en dos pasos (PICK → ALB/OUT) se puede imprimir
    # desde el PICK; el cliente debe ver siempre el número del ALB/OUT,
    # que es el que luego va referenciado en la factura.
    # Una devolución lleva su propio número.
    # ------------------------------------------------------------
    def dji_albaran_salida(self):
        self.ensure_one()
        if self.picking_type_code == 'outgoing' or self.dji_albaran_es_devolucion():
            return self
        destinos = self.move_ids.move_dest_ids.picking_id
        for _nivel in range(3):
            salida = destinos.filtered(lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel')
            if salida:
                return salida.sorted('id')[:1]
            destinos = destinos.move_ids.move_dest_ids.picking_id
            if not destinos:
                break
        if self.sale_id:
            salida = self.sale_id.picking_ids.filtered(
                lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel')
            if salida:
                return salida.sorted('id')[:1]
        return self

    def dji_albaran_numero(self):
        return self.dji_albaran_salida().name

    def _dji_albaran_pedido(self):
        self.ensure_one()
        return (self.sale_id or self.dji_albaran_salida().sale_id
                or self.move_ids.origin_returned_move_id.picking_id.sale_id[:1]
                or self.return_id.sale_id)

    def dji_albaran_valorado(self):
        self.ensure_one()
        return bool(self._dji_albaran_pedido()) and not self.partner_id.commercial_partner_id.dji_albaran_sin_precios

    # ------------------------------------------------------------
    # Reparto de cantidades entre líneas de venta.
    # Normalmente cada movimiento viene de una sola línea de venta. Si
    # el mismo artículo está dos veces en el pedido (una pagada y otra
    # en promoción) y los movimientos se han juntado, o el movimiento
    # no trae línea de venta, se reparte entre las líneas de ese
    # artículo para que cada trozo lleve su precio y su descuento.
    # ------------------------------------------------------------
    @staticmethod
    def _dji_es_promo(sale_line):
        if not sale_line:
            return False
        return (sale_line.discount or 0.0) >= 100.0 or not sale_line.price_unit

    def _dji_repartir(self, move, qty_prod, restante, lineas_producto):
        """Devuelve [(línea de venta, cantidad en unidad del producto)]."""
        propia = move.sale_line_id
        orden = (propia.ids and [propia] or []) + [
            sl for sl in lineas_producto.get(move.product_id.id, []) if sl != propia]
        trozos = []
        pendiente = qty_prod
        for sl in orden:
            if pendiente <= 1e-9:
                break
            disponible = restante.get(sl.id, 0.0)
            if disponible <= 1e-9:
                continue
            toma = min(disponible, pendiente)
            restante[sl.id] = disponible - toma
            trozos.append((sl, toma))
            pendiente -= toma
        if pendiente > 1e-9:
            sl = propia or (orden[0] if orden else self.env['sale.order.line'])
            for i, (linea, cant) in enumerate(trozos):
                if linea == sl:
                    trozos[i] = (linea, cant + pendiente)
                    break
            else:
                trozos.append((sl, pendiente))
        return trozos

    def dji_albaran_datos(self):
        """Todo lo que pinta el albarán, ya calculado y formateado."""
        self.ensure_one()
        devolucion = self.dji_albaran_es_devolucion()
        salida = self.dji_albaran_salida()
        pedido = self._dji_albaran_pedido()
        cliente = (pedido.partner_invoice_id or self.partner_id).commercial_partner_id
        entrega = salida.partner_id or self.partner_id
        fecha = salida.date_done or salida.scheduled_date or self.date_done or self.scheduled_date
        valorado = self.dji_albaran_valorado()
        tiene_caducidad = 'expiration_date' in self.env['stock.lot']._fields
        original = self.dji_albaran_original() if devolucion else self.env['stock.picking']

        # Líneas de venta por artículo y cantidad pendiente de asignar (unidad del producto)
        lineas_producto = {}
        restante = {}
        for sl in pedido.order_line.filtered(lambda l: l.product_id and not l.display_type).sorted(lambda l: (l.sequence, l.id)):
            lineas_producto.setdefault(sl.product_id.id, []).append(sl)
            restante[sl.id] = sl.product_uom_id._compute_quantity(
                sl.product_uom_qty, sl.product_id.uom_id, round=False)

        lineas = []
        base = 0.0
        impuestos = {}  # etiqueta -> importe
        unidades = 0.0
        promos = 0
        for move in self.move_ids.filtered(lambda m: m.state != 'cancel').sorted(lambda m: (m.sequence, m.id)):
            producto = move.product_id
            partes = [(ml.lot_id, ml.lot_name, ml.quantity, ml.product_uom_id)
                      for ml in move.move_line_ids if ml.quantity]
            if not partes:
                qty = move.quantity or move.product_uom_qty
                if not qty:
                    continue
                partes = [(self.env['stock.lot'], False, qty, move.product_uom)]
            for lote, nombre_lote, qty, uom in partes:
                uom = uom or producto.uom_id
                qty_prod = uom._compute_quantity(qty, producto.uom_id, round=False)
                for sale_line, qty_trozo_prod in self._dji_repartir(move, qty_prod, restante, lineas_producto):
                    qty_trozo = producto.uom_id._compute_quantity(qty_trozo_prod, uom, round=False)
                    promo = self._dji_es_promo(sale_line)
                    fila = {
                        'codigo': producto.default_code or '',
                        'nombre': producto.with_context(display_default_code=False).display_name,
                        'lote': lote.name or nombre_lote or '',
                        'caducidad': '',
                        'cantidad': _cantidad(qty_trozo),
                        'unidad': '' if uom == producto.uom_id else uom.name,
                        'promo': promo,
                        'precio': '', 'iva': '', 'importe': '',
                    }
                    unidades += qty_trozo
                    promos += 1 if promo else 0
                    if tiene_caducidad and lote and lote.expiration_date:
                        fila['caducidad'] = lote.expiration_date.strftime('%d/%m/%Y')
                    if valorado and sale_line and not promo:
                        qty_venta = producto.uom_id._compute_quantity(
                            qty_trozo_prod, sale_line.product_uom_id, round=False) \
                            if sale_line.product_uom_id and sale_line.product_uom_id != producto.uom_id else qty_trozo_prod
                        neto = sale_line.price_unit * (1 - (sale_line.discount or 0.0) / 100.0)
                        importe = qty_venta * neto
                        base += importe
                        porcentajes = []
                        for tax in sale_line.tax_ids:
                            hijos = tax.children_tax_ids if tax.amount_type == 'group' else tax
                            for t in hijos:
                                if t.amount_type != 'percent':
                                    continue
                                etiqueta = t.invoice_label or t.name
                                impuestos[etiqueta] = impuestos.get(etiqueta, 0.0) + importe * t.amount / 100.0
                                porcentajes.append(_cantidad(t.amount))
                        signo = '−' if devolucion else ''
                        fila.update({
                            'precio': _num(neto),
                            'iva': ' + '.join(f'{p} %' for p in porcentajes),
                            'importe': signo + _num(importe),
                        })
                    lineas.append(fila)

        bancos = [
            {'banco': b.bank_id.name or '', 'cuenta': b.acc_number}
            for b in self.company_id.partner_id.bank_ids
        ]
        total_impuestos = sum(impuestos.values())

        # Firma del cliente hecha en Odoo (botón Firmar del albarán de salida)
        con_firma = salida if salida.signature else (self if self.signature else self.env['stock.picking'])
        firma_fecha = ''
        if con_firma and con_firma.dji_firma_fecha:
            local = fields.Datetime.context_timestamp(con_firma, con_firma.dji_firma_fecha)
            firma_fecha = local.strftime('%d/%m/%Y a las %H:%M')
        signo = '−' if devolucion else ''
        resumen = (f"{len(lineas)} {'línea' if len(lineas) == 1 else 'líneas'} · "
                   f"{_cantidad(unidades)} unidades{' devueltas' if devolucion else ''}")
        if promos:
            resumen += f" · {promos} en promoción"
        return {
            'devolucion': devolucion,
            'titulo': 'ALBARÁN DE DEVOLUCIÓN' if devolucion else 'ALBARÁN DE ENTREGA',
            'numero': salida.name,
            'original': original.name if original and original != self else '',
            'fecha': fecha.strftime('%d/%m/%Y') if fecha else '',
            'pedido': pedido.name or self.origin or '',
            'comercial': pedido.user_id.name or '',
            'cliente': cliente,
            'nombre_comercial': _nombre_comercial(entrega, cliente),
            'entrega': entrega,
            'nota': salida.note or self.note,
            'valorado': valorado,
            'lineas': lineas,
            'resumen': resumen,
            'base': signo + _num(base),
            'impuestos': [{'etiqueta': k, 'importe': signo + _num(v)} for k, v in impuestos.items()],
            'total': signo + _num(base + total_impuestos),
            'bancos': bancos,
            'firma': con_firma.signature if con_firma else False,
            'firma_fecha': firma_fecha,
        }
