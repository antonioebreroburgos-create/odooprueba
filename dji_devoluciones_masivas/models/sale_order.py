from collections import defaultdict

from markupsafe import Markup, escape

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

# Nombres de etiqueta (sale.order.tag) que marcan un presupuesto como devolución masiva
TAG_DEVOLUCION = {'DEVOLUCION', 'DEVOLUCIÓN'}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dev_es_devolucion = fields.Boolean(
        'Es devolución masiva', compute='_compute_dev_es_devolucion',
        help='Se activa cuando el presupuesto lleva la etiqueta DEVOLUCION.')
    dev_fecha_desde = fields.Date(
        'Buscar ventas desde', copy=False,
        help='Solo se devolverá contra ventas con fecha igual o posterior. Vacío = todas.')
    dev_estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('propuesta', 'Propuesta calculada'),
        ('ejecutada', 'Ejecutada'),
    ], string='Estado devolución', default='borrador', copy=False)
    dev_propuesta_ids = fields.One2many('dji.devolucion.propuesta', 'devolucion_id', string='Propuesta', copy=False)
    dev_faltante_ids = fields.One2many('dji.devolucion.faltante', 'devolucion_id', string='No asignado', copy=False)
    dev_picking_ids = fields.Many2many(
        'stock.picking', 'dji_devolucion_picking_rel', 'order_id', 'picking_id',
        string='Albaranes de devolución', copy=False)
    dev_factura_ids = fields.Many2many(
        'account.move', 'dji_devolucion_move_rel', 'order_id', 'move_id',
        string='Rectificativas', copy=False)
    dev_picking_count = fields.Integer(compute='_compute_dev_counts')
    dev_factura_count = fields.Integer(compute='_compute_dev_counts')
    dev_ventas_count = fields.Integer('Ventas afectadas', compute='_compute_dev_counts')
    dev_total_propuesta = fields.Monetary('Importe propuesta (sin imp.)', compute='_compute_dev_counts')

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('so_tag_ids', 'so_tag_ids.name')
    def _compute_dev_es_devolucion(self):
        for order in self:
            order.dev_es_devolucion = any(
                (tag.name or '').strip().upper() in TAG_DEVOLUCION for tag in order.so_tag_ids)

    @api.depends('dev_picking_ids', 'dev_factura_ids', 'dev_propuesta_ids.subtotal', 'dev_propuesta_ids.sale_order_id')
    def _compute_dev_counts(self):
        for order in self:
            order.dev_picking_count = len(order.dev_picking_ids)
            order.dev_factura_count = len(order.dev_factura_ids)
            order.dev_ventas_count = len(order.dev_propuesta_ids.sale_order_id)
            order.dev_total_propuesta = sum(order.dev_propuesta_ids.mapped('subtotal'))

    # ------------------------------------------------------------------
    # Protecciones
    # ------------------------------------------------------------------
    def action_confirm(self):
        devoluciones = self.filtered('dev_es_devolucion')
        if devoluciones:
            raise UserError(_(
                "El presupuesto %s es una DEVOLUCIÓN y no se puede confirmar como venta.\n"
                "Usa los botones 'Calcular devolución' y 'Ejecutar devolución'.",
                ', '.join(devoluciones.mapped('name'))))
        return super().action_confirm()

    def write(self, vals):
        # Si cambian los datos de entrada con una propuesta ya calculada, la propuesta deja de ser válida
        campos_entrada = {'order_line', 'partner_id', 'dev_fecha_desde'}
        invalidar = self.env['sale.order']
        if campos_entrada & set(vals):
            invalidar = self.filtered(lambda o: o.dev_estado == 'propuesta')
        if self.filtered(lambda o: o.dev_estado == 'ejecutada') and campos_entrada & set(vals):
            raise UserError(_("Esta devolución ya está ejecutada y no se puede modificar."))
        res = super().write(vals)
        if invalidar:
            invalidar.dev_propuesta_ids.unlink()
            invalidar.dev_faltante_ids.unlink()
            super(SaleOrder, invalidar).write({'dev_estado': 'borrador'})
        return res

    def _dev_check(self, estados):
        self.ensure_one()
        if not self.dev_es_devolucion:
            raise UserError(_("Este presupuesto no tiene la etiqueta DEVOLUCION."))
        if self.state not in ('draft', 'sent'):
            raise UserError(_("La devolución debe hacerse desde un presupuesto sin confirmar."))
        if self.dev_estado not in estados:
            raise UserError(_("Acción no disponible en el estado actual de la devolución."))

    # ------------------------------------------------------------------
    # 1) CALCULAR PROPUESTA
    # ------------------------------------------------------------------
    def action_dev_calcular(self):
        self._dev_check(('borrador', 'propuesta'))
        self.dev_propuesta_ids.unlink()
        self.dev_faltante_ids.unlink()

        solicitado, faltantes = self._dev_cantidades_solicitadas()
        if not solicitado and not faltantes:
            raise UserError(_("Añade en las líneas del presupuesto los productos y cantidades que devuelve el cliente."))

        disponible = self._dev_disponible_por_venta(list(solicitado))
        asignaciones, pendiente = self._dev_repartir(solicitado, disponible)

        # Propuesta: una línea por movimiento de albarán original (cantidad en la unidad del movimiento)
        por_move = defaultdict(float)
        for move, qty_base in asignaciones:
            por_move[move] += qty_base
        propuesta_vals = []
        for move, qty_base in por_move.items():
            propuesta_vals.append({
                'devolucion_id': self.id,
                'move_id': move.id,
                'sale_line_id': move.sale_line_id.id,
                'product_id': move.product_id.id,
                'cantidad': move.product_id.uom_id._compute_quantity(qty_base, move.product_uom),
                'uom_id': move.product_uom.id,
            })
        self.env['dji.devolucion.propuesta'].create(propuesta_vals)

        for product, qty_base in pendiente.items():
            if not product.uom_id.is_zero(qty_base):
                faltantes.append({
                    'product_id': product.id,
                    'cantidad': qty_base,
                    'uom_id': product.uom_id.id,
                    'motivo': _('No hay ventas entregadas y facturadas suficientes para este cliente en el periodo'),
                })
        self.env['dji.devolucion.faltante'].create([dict(v, devolucion_id=self.id) for v in faltantes])

        self.dev_estado = 'propuesta'
        return True

    def _dev_cantidades_solicitadas(self):
        """Suma por producto (en su unidad base) lo que el cliente devuelve, según las líneas del presupuesto."""
        solicitado = defaultdict(float)
        faltantes = []
        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id):
            product = line.product_id
            if line.product_uom_qty <= 0:
                continue
            qty_base = line.product_uom_id._compute_quantity(line.product_uom_qty, product.uom_id)
            if not product.is_storable:
                faltantes.append({'product_id': product.id, 'cantidad': qty_base, 'uom_id': product.uom_id.id,
                                  'motivo': _('Producto no almacenable: no tiene albarán que devolver')})
            elif product.tracking != 'none':
                faltantes.append({'product_id': product.id, 'cantidad': qty_base, 'uom_id': product.uom_id.id,
                                  'motivo': _('Producto con lote/número de serie: devolver manualmente indicando el lote')})
            else:
                solicitado[product] += qty_base
        return solicitado, faltantes

    def _dev_disponible_por_venta(self, products):
        """Devuelve {venta: {producto: [(move_salida, qty_base_devolvible), ...]}}

        Devolvible por línea de venta = min(entregado, facturado) (Odoo ya descuenta devoluciones
        y rectificativas anteriores), repartido entre sus movimientos de salida al cliente, descontando
        devoluciones pendientes y lo ya reservado por otras devoluciones masivas sin ejecutar.
        """
        resultado = defaultdict(lambda: defaultdict(list))
        if not products:
            return resultado
        commercial = self.partner_id.commercial_partner_id
        domain = [
            ('order_id.partner_id', 'child_of', commercial.id),
            ('order_id.state', '=', 'sale'),
            ('order_id', '!=', self.id),
            ('product_id', 'in', [p.id for p in products]),
            ('qty_delivered', '>', 0),
            ('qty_invoiced', '>', 0),
        ]
        if self.dev_fecha_desde:
            domain.append(('order_id.date_order', '>=', fields.Datetime.to_datetime(self.dev_fecha_desde)))
        lineas = self.env['sale.order.line'].search(domain)

        # Cantidades ya comprometidas en otras devoluciones masivas calculadas pero no ejecutadas
        reservado = defaultdict(float)
        otras = self.env['dji.devolucion.propuesta'].search([
            ('devolucion_id', '!=', self.id),
            ('devolucion_id.dev_estado', '=', 'propuesta'),
            ('sale_line_id', 'in', lineas.ids),
        ])
        for o in otras:
            reservado[o.move_id.id] += o.uom_id._compute_quantity(o.cantidad, o.move_id.product_uom)

        for line in lineas:
            if line.order_id.dev_es_devolucion:
                continue
            product = line.product_id
            tope = min(line.qty_delivered, line.qty_invoiced)
            tope_base = line.product_uom_id._compute_quantity(tope, product.uom_id)
            if product.uom_id.compare(tope_base, 0) <= 0:
                continue
            for move, libre_base in self._dev_libre_por_move(line, reservado):
                tomar = min(libre_base, tope_base)
                if product.uom_id.compare(tomar, 0) <= 0:
                    break
                resultado[line.order_id][product].append((move, tomar))
                tope_base -= tomar
        return resultado

    @api.model
    def _dev_moves_salida(self, sale_line):
        return sale_line.move_ids.filtered(
            lambda m: m.state == 'done'
            and m.picking_id
            and not m.origin_returned_move_id
            and m.location_dest_usage == 'customer'
        ).sorted(lambda m: (m.date, m.id), reverse=True)

    @api.model
    def _dev_devuelto_de_move(self, move):
        """Cantidad (unidad del move) ya devuelta o en devolución pendiente de un movimiento de salida."""
        total = 0.0
        for r in move.returned_move_ids.filtered(lambda r: r.state != 'cancel'):
            qty = r.quantity if r.state == 'done' else r.product_uom_qty
            total += r.product_uom._compute_quantity(qty, move.product_uom)
        return total

    def _dev_libre_por_move(self, sale_line, reservado):
        res = []
        product = sale_line.product_id
        for move in self._dev_moves_salida(sale_line):
            libre = move.quantity - self._dev_devuelto_de_move(move) - reservado.get(move.id, 0.0)
            libre_base = move.product_uom._compute_quantity(libre, product.uom_id)
            if product.uom_id.compare(libre_base, 0) > 0:
                res.append((move, libre_base))
        return res

    @api.model
    def _dev_repartir(self, solicitado, disponible):
        """Algoritmo voraz de cobertura: en cada paso elige la venta que más cubre de lo pendiente
        (en proporción por producto, así no se mezclan unidades distintas). Desempate: más productos
        completados y, después, la venta más reciente."""
        pendiente = dict(solicitado)
        candidatas = {so: dict(prods) for so, prods in disponible.items()}
        asignaciones = []

        def puntuacion(order):
            cubierto = 0.0
            completos = 0
            for product, moves in candidatas[order].items():
                if product not in pendiente:
                    continue
                total = sum(q for _m, q in moves)
                cubierto += min(total, pendiente[product]) / pendiente[product]
                if product.uom_id.compare(total, pendiente[product]) >= 0:
                    completos += 1
            return (round(cubierto, 6), completos, order.date_order, order.id)

        while pendiente and candidatas:
            mejor = max(candidatas, key=puntuacion)
            if puntuacion(mejor)[0] <= 0:
                break
            for product, moves in candidatas.pop(mejor).items():
                if product not in pendiente:
                    continue
                for move, qty in moves:
                    tomar = min(qty, pendiente[product])
                    asignaciones.append((move, tomar))
                    pendiente[product] -= tomar
                    if product.uom_id.compare(pendiente[product], 0) <= 0:
                        del pendiente[product]
                        break
        return asignaciones, pendiente

    # ------------------------------------------------------------------
    # 2) EJECUTAR
    # ------------------------------------------------------------------
    def action_dev_ejecutar(self):
        self._dev_check(('propuesta',))
        lineas = self.dev_propuesta_ids.filtered(lambda l: l.uom_id.compare(l.cantidad, 0) > 0)
        if not lineas:
            raise UserError(_("La propuesta no tiene ninguna cantidad a devolver."))
        self._dev_revalidar(lineas)

        # a) Devoluciones de albarán (una por albarán original)
        por_picking = defaultdict(lambda: self.env['dji.devolucion.propuesta'])
        for l in lineas:
            por_picking[l.picking_id] |= l
        devoluciones = self.env['stock.picking']
        for picking, pls in por_picking.items():
            devoluciones |= self._dev_devolver_albaran(picking, pls)

        # b) Rectificativas (borrador) enlazadas a las líneas de venta
        rectificativas = self._dev_crear_rectificativas(lineas)

        self.write({
            'dev_estado': 'ejecutada',
            'dev_picking_ids': [Command.set(devoluciones.ids)],
            'dev_factura_ids': [Command.set(rectificativas.ids)],
        })
        cuerpo = Markup('<p>%s</p><ul>%s</ul><p>%s</p>') % (
            _('Devolución ejecutada contra %s ventas.', len(lineas.sale_order_id)),
            Markup('').join(Markup('<li>%s</li>') % escape(n) for n in lineas.sale_order_id.mapped('name')),
            _('%(albaranes)s albaranes de devolución validados y %(facturas)s rectificativas en borrador.',
              albaranes=len(devoluciones), facturas=len(rectificativas)),
        )
        self.message_post(body=cuerpo)
        return True

    def _dev_revalidar(self, lineas):
        """Vuelve a comprobar las cantidades justo antes de ejecutar (pueden haber cambiado o editado a mano)."""
        errores = []
        por_move = defaultdict(float)
        por_sale_line = defaultdict(float)
        for l in lineas:
            por_move[l.move_id] += l.uom_id._compute_quantity(l.cantidad, l.move_id.product_uom)
            por_sale_line[l.sale_line_id] += l.uom_id._compute_quantity(l.cantidad, l.sale_line_id.product_uom_id)
        for move, qty in por_move.items():
            libre = move.quantity - self._dev_devuelto_de_move(move)
            if move.product_uom.compare(qty, libre) > 0:
                errores.append(_('%(prod)s en %(alb)s: se piden %(q)s y solo quedan %(l)s por devolver',
                                 prod=move.product_id.display_name, alb=move.picking_id.name,
                                 q=round(qty, 3), l=round(libre, 3)))
        for sl, qty in por_sale_line.items():
            tope = min(sl.qty_delivered, sl.qty_invoiced)
            if sl.product_uom_id.compare(qty, tope) > 0:
                errores.append(_('%(prod)s en %(venta)s: se piden %(q)s y lo entregado/facturado neto es %(t)s',
                                 prod=sl.product_id.display_name, venta=sl.order_id.name,
                                 q=round(qty, 3), t=round(tope, 3)))
        if errores:
            raise UserError(_("No se puede ejecutar la devolución:\n- %s\n\nVuelve a calcular la propuesta.",
                              '\n- '.join(errores)))

    def _dev_devolver_albaran(self, picking, lineas):
        cantidades = defaultdict(float)
        for l in lineas:
            cantidades[l.move_id.id] += l.uom_id._compute_quantity(l.cantidad, l.move_id.product_uom)

        wizard = self.env['stock.return.picking'].with_context(
            active_id=picking.id, active_ids=picking.ids, active_model='stock.picking',
        ).create({'picking_id': picking.id})
        encontrados = set()
        for rl in wizard.product_return_moves:
            qty = cantidades.get(rl.move_id.id, 0.0)
            rl.write({'quantity': qty, 'to_refund': True})
            if qty:
                encontrados.add(rl.move_id.id)
        if set(cantidades) - encontrados:
            raise UserError(_("No se han encontrado todas las líneas a devolver en el albarán %s.", picking.name))

        devolucion = wizard._create_return()
        for move in devolucion.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        devolucion.with_context(
            skip_backorder=True, picking_ids_not_to_backorder=devolucion.ids, skip_sms=True,
        ).button_validate()
        if devolucion.state != 'done':
            raise UserError(_(
                "No se ha podido validar automáticamente la devolución %(dev)s del albarán %(alb)s.",
                dev=devolucion.name, alb=picking.name))
        devolucion.message_post(body=_('Devolución generada desde la devolución masiva %s.', self.name))
        return devolucion

    def _dev_crear_rectificativas(self, lineas):
        """Una rectificativa por factura original (y dirección de facturación), con las líneas
        enlazadas a su línea de venta para que Odoo descuente lo facturado."""
        grupos = defaultdict(lambda: defaultdict(float))
        facturas_orig = {}
        for l in lineas:
            sl = l.sale_line_id
            qty = l.uom_id._compute_quantity(l.cantidad, sl.product_uom_id)
            factura = sl.invoice_lines.move_id.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
            ).sorted(lambda m: (m.invoice_date or fields.Date.today(), m.id), reverse=True)[:1]
            clave = (factura.id or 0, sl.order_id.partner_invoice_id.id)
            facturas_orig[clave] = factura
            grupos[clave][sl] += qty

        Move = self.env['account.move'].with_context(default_move_type='out_refund')
        creadas = self.env['account.move']
        for clave, por_linea in grupos.items():
            factura = facturas_orig[clave]
            sale_lines = self.env['sale.order.line'].browse([sl.id for sl in por_linea])
            ventas = sale_lines.order_id
            vals = ventas[0]._prepare_invoice()
            vals.pop('transaction_ids', None)
            ref = _('Devolución %(dev)s', dev=self.name)
            if factura:
                ref = _('%(ref)s - rectifica %(fac)s', ref=ref, fac=factura.name)
            vals.update({
                'move_type': 'out_refund',
                'reversed_entry_id': factura.id or False,
                'invoice_origin': ', '.join(ventas.mapped('name')),
                'ref': ref,
                'invoice_line_ids': [
                    Command.create(sl._prepare_invoice_line(quantity=qty))
                    for sl, qty in por_linea.items()
                ],
            })
            creadas |= Move.create(vals)
        return creadas

    # ------------------------------------------------------------------
    # Botones inteligentes
    # ------------------------------------------------------------------
    def action_dev_ver_albaranes(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', self.dev_picking_ids.ids)]
        action['context'] = {}
        return action

    def action_dev_ver_rectificativas(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_out_refund_type')
        action['domain'] = [('id', 'in', self.dev_factura_ids.ids)]
        action['context'] = {'default_move_type': 'out_refund'}
        return action
