from collections import defaultdict
from datetime import date, timedelta

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
        help='Solo se devolverá contra ventas confirmadas en esta fecha o después. '
             'No puede ser anterior a la fecha límite (inicio del trimestre aún no liquidado en incentivos). '
             'Vacío = fecha límite.')
    dev_fecha_limite = fields.Date(
        'Fecha límite', compute='_compute_dev_fecha_limite',
        help='Inicio del trimestre más antiguo que aún no está liquidado en incentivos: '
             'trimestre de (hoy - días de liquidación). Días configurables en el parámetro de sistema '
             'dji_devoluciones_masivas.dias_liquidacion (por defecto 45).')
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

    @api.model
    def _dev_get_fecha_limite(self):
        dias = int(self.env['ir.config_parameter'].sudo().get_param(
            'dji_devoluciones_masivas.dias_liquidacion', 45))
        ref = fields.Date.context_today(self) - timedelta(days=dias)
        return date(ref.year, 3 * ((ref.month - 1) // 3) + 1, 1)

    def _compute_dev_fecha_limite(self):
        limite = self._dev_get_fecha_limite()
        for order in self:
            order.dev_fecha_limite = limite

    def _dev_aplicar_fecha_limite(self):
        """Garantiza que la búsqueda no vaya más atrás de la fecha límite."""
        limite = self._dev_get_fecha_limite()
        if not self.dev_fecha_desde:
            self.with_context(dev_no_invalidar=True).dev_fecha_desde = limite
        elif self.dev_fecha_desde < limite:
            raise UserError(_(
                "La fecha 'Buscar ventas desde' (%(desde)s) es anterior a la fecha límite (%(limite)s).\n"
                "No se puede devolver contra ventas de trimestres ya liquidados en incentivos.",
                desde=self.dev_fecha_desde.strftime('%d/%m/%Y'), limite=limite.strftime('%d/%m/%Y')))
        return limite

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
        if campos_entrada & set(vals) and not self.env.context.get('dev_no_invalidar'):
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
        self._dev_aplicar_fecha_limite()

        solicitado, faltantes = self._dev_cantidades_solicitadas()
        if not solicitado and not faltantes:
            raise UserError(_("Añade en las líneas del presupuesto los productos y cantidades que devuelve el cliente."))

        disponible = self._dev_disponible_por_venta(list(solicitado))
        asignaciones, pendiente = self._dev_repartir(solicitado, disponible)

        # Propuesta: una línea por movimiento de albarán original y lote (cantidad en la unidad del movimiento)
        por_move_lote = defaultdict(float)
        for move, lot, qty_base in asignaciones:
            por_move_lote[(move, lot)] += qty_base
        propuesta_vals = []
        for (move, lot), qty_base in por_move_lote.items():
            propuesta_vals.append({
                'devolucion_id': self.id,
                'move_id': move.id,
                'lot_id': lot.id or False,
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
                    'motivo': self._dev_motivo_faltante(product, solicitado[product], qty_base),
                })
        for v in faltantes:
            v.setdefault('price_unit', self._dev_precio_sugerido(self.env['product.product'].browse(v['product_id'])))
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
        desde = max(self.dev_fecha_desde or date.min, self._dev_get_fecha_limite())
        domain.append(('order_id.date_order', '>=', fields.Datetime.to_datetime(desde)))
        lineas = self.env['sale.order.line'].search(domain)

        # Cantidades ya comprometidas en otras devoluciones masivas calculadas pero no ejecutadas
        reservado = defaultdict(float)
        otras = self.env['dji.devolucion.propuesta'].search([
            ('devolucion_id', '!=', self.id),
            ('devolucion_id.dev_estado', '=', 'propuesta'),
            ('sale_line_id', 'in', lineas.ids),
        ])
        for o in otras:
            reservado[(o.move_id.id, o.lot_id.id)] += o.uom_id._compute_quantity(o.cantidad, o.move_id.product_uom)

        for line in lineas:
            if line.order_id.dev_es_devolucion:
                continue
            product = line.product_id
            tope = min(line.qty_delivered, line.qty_invoiced)
            tope_base = line.product_uom_id._compute_quantity(tope, product.uom_id)
            if product.uom_id.compare(tope_base, 0) <= 0:
                continue
            for move, lot, libre_base in self._dev_libre_por_move_lote(line, reservado):
                tomar = min(libre_base, tope_base)
                if product.uom_id.compare(tomar, 0) <= 0:
                    break
                resultado[line.order_id][product].append((move, lot, tomar))
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

    @api.model
    def _dev_lotes_de_move(self, move):
        """{lote: cantidad (unidad del move)} entregada por el movimiento de salida, según sus líneas."""
        res = defaultdict(float)
        for ml in move.move_line_ids:
            if ml.lot_id:
                res[ml.lot_id] += ml.product_uom_id._compute_quantity(ml.quantity, move.product_uom)
        return res

    @api.model
    def _dev_devuelto_por_lote(self, move):
        """{lote: cantidad (unidad del move)} ya devuelta (o pendiente) de un movimiento de salida."""
        res = defaultdict(float)
        for r in move.returned_move_ids.filtered(lambda r: r.state != 'cancel'):
            for ml in r.move_line_ids:
                if ml.lot_id:
                    res[ml.lot_id] += ml.product_uom_id._compute_quantity(ml.quantity, move.product_uom)
        return res

    def _dev_libre_por_move_lote(self, sale_line, reservado):
        """Lista de (move_salida, lote, qty_base libre). Sin lote, lote = registro vacío."""
        res = []
        product = sale_line.product_id
        Lot = self.env['stock.lot']
        for move in self._dev_moves_salida(sale_line):
            libre_move = move.quantity - self._dev_devuelto_de_move(move)
            if move.product_uom.compare(libre_move, 0) <= 0:
                continue
            if product.tracking == 'none':
                libre = libre_move - reservado.get((move.id, False), 0.0)
                libre_base = move.product_uom._compute_quantity(libre, product.uom_id)
                if product.uom_id.compare(libre_base, 0) > 0:
                    res.append((move, Lot, libre_base))
                continue
            # Producto con lote: solo se puede devolver lo que salió con lote conocido
            devuelto_lote = self._dev_devuelto_por_lote(move)
            for lot, qty in self._dev_lotes_de_move(move).items():
                libre = min(qty - devuelto_lote.get(lot, 0.0), libre_move) - reservado.get((move.id, lot.id), 0.0)
                if move.product_uom.compare(libre, 0) <= 0:
                    continue
                libre_move -= libre
                res.append((move, lot, move.product_uom._compute_quantity(libre, product.uom_id)))
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
                total = sum(q for _m, _l, q in moves)
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
                for move, lot, qty in moves:
                    tomar = min(qty, pendiente[product])
                    asignaciones.append((move, lot, tomar))
                    pendiente[product] -= tomar
                    if product.uom_id.compare(pendiente[product], 0) <= 0:
                        del pendiente[product]
                        break
        return asignaciones, pendiente

    # ------------------------------------------------------------------
    # Diagnóstico de lo no asignado
    # ------------------------------------------------------------------
    @staticmethod
    def _dev_fmt(qty):
        return ('%.3f' % qty).rstrip('0').rstrip('.')

    def _dev_motivo_faltante(self, product, solicitado_base, pendiente_base):
        """Explica por qué no se ha podido asignar una cantidad."""
        uom = product.uom_id
        desde = max(self.dev_fecha_desde or date.min, self._dev_get_fecha_limite())
        lineas = self.env['sale.order.line'].search([
            ('order_id.partner_id', 'child_of', self.partner_id.commercial_partner_id.id),
            ('order_id.state', '=', 'sale'),
            ('order_id', '!=', self.id),
            ('product_id', '=', product.id),
        ]).filtered(lambda l: not l.order_id.dev_es_devolucion)
        motivos = []
        asignado = solicitado_base - pendiente_base
        if uom.compare(asignado, 0) > 0:
            motivos.append(_('Asignadas %(a)s de %(s)s.', a=self._dev_fmt(asignado), s=self._dev_fmt(solicitado_base)))
        if not lineas:
            motivos.append(_('No consta ninguna venta de este producto a este cliente.'))
            return ' '.join(motivos)

        antes = lineas.filtered(lambda l: l.order_id.date_order.date() < desde)
        periodo = lineas - antes

        def neto(l):
            return l.product_uom_id._compute_quantity(min(l.qty_delivered, l.qty_invoiced), uom)

        antes_netas = antes.filtered(lambda l: uom.compare(neto(l), 0) > 0).sorted(
            lambda l: l.order_id.date_order, reverse=True)
        if antes_netas:
            refs = ', '.join('%s (%s)' % (l.order_id.name, l.order_id.date_order.strftime('%d/%m/%Y'))
                             for l in antes_netas[:3])
            if len(antes_netas) > 3:
                refs += _(' y %s más', len(antes_netas) - 3)
            motivos.append(_('%(q)s vendidas antes de la fecha límite %(f)s (trimestre liquidado): %(refs)s.',
                             q=self._dev_fmt(sum(neto(l) for l in antes_netas)),
                             f=desde.strftime('%d/%m/%Y'), refs=refs))
        sin_facturar = periodo.filtered(lambda l: l.product_uom_id.compare(l.qty_delivered, l.qty_invoiced) > 0)
        if sin_facturar:
            motivos.append(_('Entregado pero sin facturar en: %s.', ', '.join(sin_facturar.order_id.mapped('name'))))
        sin_entregar = periodo.filtered(lambda l: l.product_uom_id.compare(l.qty_delivered, 0) <= 0)
        if sin_entregar:
            motivos.append(_('Sin entregar en: %s.', ', '.join(sin_entregar.order_id.mapped('name'))))
        devueltas = periodo.filtered(lambda l: any(m.returned_move_ids.filtered(lambda r: r.state != 'cancel')
                                                  for m in l.move_ids))
        if devueltas:
            motivos.append(_('Ya tienen devoluciones: %s.', ', '.join(devueltas.order_id.mapped('name'))))
        if product.tracking != 'none':
            sin_lote = periodo.filtered(lambda l: any(
                m.state == 'done' and not m.move_line_ids.lot_id for m in self._dev_moves_salida(l)))
            if sin_lote:
                motivos.append(_('Albaranes sin lote registrado en: %s.', ', '.join(sin_lote.order_id.mapped('name'))))
        if len(motivos) <= 1:
            motivos.append(_('No quedan más ventas entregadas y facturadas en el periodo.'))
        return ' '.join(motivos)

    def _dev_precio_sugerido(self, product):
        """Último precio neto (unidad base) vendido a este cliente; si no hay, precio de tarifa."""
        sl = self.env['sale.order.line'].search([
            ('order_id.partner_id', 'child_of', self.partner_id.commercial_partner_id.id),
            ('order_id.state', '=', 'sale'),
            ('order_id', '!=', self.id),
            ('product_id', '=', product.id),
        ], order='id desc', limit=1)
        if sl:
            neto = sl.price_unit * (1 - (sl.discount or 0.0) / 100.0)
            qty_base = sl.product_uom_id._compute_quantity(1.0, product.uom_id)
            return neto / qty_base if qty_base else neto
        return product.lst_price

    # ------------------------------------------------------------------
    # 2) EJECUTAR
    # ------------------------------------------------------------------
    def action_dev_ejecutar(self):
        self._dev_check(('propuesta',))
        lineas = self.dev_propuesta_ids.filtered(lambda l: l.uom_id.compare(l.cantidad, 0) > 0)
        extras = self.dev_faltante_ids.filtered(lambda f: f.incluir and f.uom_id.compare(f.cantidad, 0) > 0)
        if not lineas and not extras:
            raise UserError(_("No hay nada que devolver: la propuesta está vacía y no se ha marcado "
                              "'Abonar igualmente' en ninguna línea no asignada."))
        if lineas:
            limite = self._dev_get_fecha_limite()
            antiguas = lineas.sale_order_id.filtered(lambda so: so.date_order.date() < limite)
            if antiguas:
                raise UserError(_(
                    "Las ventas %(ventas)s son anteriores a la fecha límite (%(limite)s): ese trimestre ya está "
                    "liquidado en incentivos. Vuelve a calcular la propuesta.",
                    ventas=', '.join(antiguas.mapped('name')), limite=limite.strftime('%d/%m/%Y')))
            self._dev_revalidar(lineas)
        self._dev_validar_extras(extras)

        # a) Devoluciones de albarán (una por albarán original)
        por_picking = defaultdict(lambda: self.env['dji.devolucion.propuesta'])
        for l in lineas:
            por_picking[l.picking_id] |= l
        devoluciones = self.env['stock.picking']
        for picking, pls in por_picking.items():
            devoluciones |= self._dev_devolver_albaran(picking, pls)
        # b) Entrada de stock de lo no asignado que se abona igualmente
        devoluciones |= self._dev_recepcion_sin_venta(extras)

        # c) Rectificativa(s) en borrador
        rectificativas = self._dev_crear_rectificativas(lineas, extras)

        self.write({
            'dev_estado': 'ejecutada',
            'dev_picking_ids': [Command.set(devoluciones.ids)],
            'dev_factura_ids': [Command.set(rectificativas.ids)],
        })
        partes = [_('Devolución ejecutada contra %s ventas.', len(lineas.sale_order_id))]
        if extras:
            partes.append(_('%s líneas abonadas sin venta de origen (no restan en incentivos).', len(extras)))
        partes.append(_('%(albaranes)s albaranes de devolución/entrada validados y %(facturas)s rectificativas en borrador.',
                        albaranes=len(devoluciones), facturas=len(rectificativas)))
        cuerpo = Markup('').join(Markup('<p>%s</p>') % p for p in partes)
        if lineas:
            cuerpo += Markup('<ul>%s</ul>') % Markup('').join(
                Markup('<li>%s</li>') % escape(n) for n in lineas.sale_order_id.mapped('name'))
        self.message_post(body=cuerpo)
        return True

    def _dev_validar_extras(self, extras):
        errores = []
        for f in extras:
            if f.product_id.is_storable and f.product_id.tracking != 'none' and not f.lot_id:
                errores.append(_('%s: indica el lote que devuelve el cliente.', f.product_id.display_name))
            if f.lot_id and f.lot_id.product_id != f.product_id:
                errores.append(_('%s: el lote %s no es de este producto.', f.product_id.display_name, f.lot_id.name))
            if f.price_unit < 0:
                errores.append(_('%s: el precio de abono no puede ser negativo.', f.product_id.display_name))
        if errores:
            raise UserError(_("Revisa las líneas no asignadas marcadas para abonar:\n- %s", '\n- '.join(errores)))

    def _dev_recepcion_sin_venta(self, extras):
        """Entrada de stock desde el cliente para lo abonado sin venta de origen."""
        almacenables = extras.filtered(lambda f: f.product_id.is_storable)
        if not almacenables:
            return self.env['stock.picking']
        wh = self.warehouse_id or self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)], limit=1)
        ptype = wh.out_type_id.return_picking_type_id or wh.in_type_id
        loc_src = self.partner_id.property_stock_customer or self.env.ref('stock.stock_location_customers')
        loc_dest = ptype.default_location_dest_id or wh.lot_stock_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': ptype.id,
            'partner_id': (self.partner_shipping_id or self.partner_id).id,
            'location_id': loc_src.id,
            'location_dest_id': loc_dest.id,
            'origin': _('%s (sin venta de origen)', self.name),
            'company_id': self.company_id.id,
        })
        pares = []
        for f in almacenables:
            move = self.env['stock.move'].create({
                'picking_id': picking.id,
                'product_id': f.product_id.id,
                'product_uom_qty': f.cantidad,
                'product_uom': f.uom_id.id,
                'location_id': loc_src.id,
                'location_dest_id': loc_dest.id,
                'picking_type_id': ptype.id,
                'company_id': self.company_id.id,
            })
            pares.append((move, f))
        picking.action_confirm()
        for move, f in pares:
            if f.lot_id:
                move._do_unreserve()
                move.move_line_ids.unlink()
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'lot_id': f.lot_id.id,
                    'quantity': move.product_uom_qty,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': move.company_id.id,
                })
            else:
                move.quantity = move.product_uom_qty
            move.picked = True
        self._dev_validar_albaran(picking, _('la entrada sin venta de origen'))
        return picking

    def _dev_validar_albaran(self, picking, descripcion):
        picking.with_context(
            skip_backorder=True, picking_ids_not_to_backorder=picking.ids, skip_sms=True,
        ).button_validate()
        if picking.state != 'done':
            raise UserError(_("No se ha podido validar automáticamente %(desc)s (%(alb)s).",
                              desc=descripcion, alb=picking.name))
        picking.message_post(body=_('Generado desde la devolución masiva %s.', self.name))

    def _dev_revalidar(self, lineas):
        """Vuelve a comprobar las cantidades justo antes de ejecutar (pueden haber cambiado o editado a mano)."""
        errores = []
        por_move = defaultdict(float)
        por_move_lote = defaultdict(float)
        por_sale_line = defaultdict(float)
        for l in lineas:
            q = l.uom_id._compute_quantity(l.cantidad, l.move_id.product_uom)
            por_move[l.move_id] += q
            if l.lot_id:
                por_move_lote[(l.move_id, l.lot_id)] += q
            elif l.product_id.tracking != 'none':
                errores.append(_('%(prod)s en %(alb)s: falta indicar el lote',
                                 prod=l.product_id.display_name, alb=l.picking_id.name))
            por_sale_line[l.sale_line_id] += l.uom_id._compute_quantity(l.cantidad, l.sale_line_id.product_uom_id)
        for move, qty in por_move.items():
            libre = move.quantity - self._dev_devuelto_de_move(move)
            if move.product_uom.compare(qty, libre) > 0:
                errores.append(_('%(prod)s en %(alb)s: se piden %(q)s y solo quedan %(l)s por devolver',
                                 prod=move.product_id.display_name, alb=move.picking_id.name,
                                 q=round(qty, 3), l=round(libre, 3)))
        for (move, lot), qty in por_move_lote.items():
            libre = self._dev_lotes_de_move(move).get(lot, 0.0) - self._dev_devuelto_por_lote(move).get(lot, 0.0)
            if move.product_uom.compare(qty, libre) > 0:
                errores.append(_('%(prod)s lote %(lote)s en %(alb)s: se piden %(q)s y solo quedan %(l)s por devolver',
                                 prod=move.product_id.display_name, lote=lot.name, alb=move.picking_id.name,
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
        MoveLine = self.env['stock.move.line']
        for move in devolucion.move_ids:
            origen = move.origin_returned_move_id
            if move.product_id.tracking == 'none':
                move.quantity = move.product_uom_qty
            else:
                # Mismo lote (y cantidad por lote) que salió en el albarán original
                move._do_unreserve()
                move.move_line_ids.unlink()
                for l in lineas.filtered(lambda x: x.move_id == origen):
                    MoveLine.create({
                        'move_id': move.id,
                        'picking_id': devolucion.id,
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'lot_id': l.lot_id.id,
                        'quantity': l.uom_id._compute_quantity(l.cantidad, move.product_uom),
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'company_id': move.company_id.id,
                    })
            move.picked = True
        self._dev_validar_albaran(devolucion, _('la devolución del albarán %s', picking.name))
        return devolucion

    def _dev_crear_rectificativas(self, lineas, extras=None):
        """Una sola rectificativa por devolución (salvo que las ventas tengan distinta dirección de
        facturación, posición fiscal, moneda o compañía, que obligan a separarlas). Las líneas con venta
        van enlazadas a su línea de venta (Odoo descuenta lo facturado y el dashboard lo resta); las
        abonadas sin venta de origen van sin enlace."""
        extras = extras or self.env['dji.devolucion.faltante']
        grupos = defaultdict(lambda: defaultdict(float))
        facturas = defaultdict(lambda: self.env['account.move'])
        for l in lineas:
            sl = l.sale_line_id
            so = sl.order_id
            qty = l.uom_id._compute_quantity(l.cantidad, sl.product_uom_id)
            clave = (so.partner_invoice_id.id, so.fiscal_position_id.id, so.currency_id.id, so.company_id.id)
            grupos[clave][sl] += qty
            facturas[clave] |= sl.invoice_lines.move_id.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
        clave_propia = (self.partner_invoice_id.id, self.fiscal_position_id.id, self.currency_id.id, self.company_id.id)
        if extras:
            grupos[clave_propia]  # asegura el grupo aunque no haya líneas con venta

        Move = self.env['account.move'].with_context(default_move_type='out_refund')
        creadas = self.env['account.move']
        for clave, por_linea in grupos.items():
            originales = facturas[clave].sorted(lambda m: (m.invoice_date or fields.Date.today(), m.id))
            sale_lines = self.env['sale.order.line'].browse([sl.id for sl in por_linea]).sorted(
                lambda sl: (sl.order_id.date_order, sl.order_id.id, sl.sequence, sl.id))
            ventas = sale_lines.order_id
            vals = (ventas[:1] or self)._prepare_invoice()
            vals.pop('transaction_ids', None)
            lineas_factura = []
            for sl in sale_lines:
                lv = sl._prepare_invoice_line(quantity=por_linea[sl])
                lv['name'] = '[%s] %s' % (sl.order_id.name, lv.get('name') or sl.name)
                lineas_factura.append(Command.create(lv))
            extras_grupo = extras if clave == clave_propia else extras.browse()
            for f in extras_grupo:
                lineas_factura.append(Command.create({
                    'product_id': f.product_id.id,
                    'name': '[%s] %s' % (_('Sin venta'), f.product_id.display_name),
                    'quantity': f.cantidad,
                    'product_uom_id': f.uom_id.id,
                    'price_unit': f.price_unit,
                }))
            notas = [_('Rectifica las facturas: %s', ', '.join(originales.mapped('name')) or '-'),
                     _('Ventas de origen: %s', ', '.join(ventas.mapped('name')) or '-')]
            if extras_grupo:
                notas.append(_('Incluye %s líneas sin venta de origen.', len(extras_grupo)))
            vals.update({
                'move_type': 'out_refund',
                # Con una sola factura original se enlaza; con varias se relacionan en la nota
                'reversed_entry_id': originales.id if len(originales) == 1 else False,
                'invoice_origin': ', '.join(ventas.mapped('name')) or self.name,
                'ref': _('Devolución %(dev)s', dev=self.name),
                'narration': Markup('').join(Markup('<p>%s</p>') % n for n in notas),
                'invoice_line_ids': lineas_factura,
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
