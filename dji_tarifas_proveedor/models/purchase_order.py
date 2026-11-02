import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.tools import format_date, formatLang

_logger = logging.getLogger(__name__)

ESTADOS = [
    ('ok', 'Correcto'),
    ('distinto', 'Distinto'),
    ('sin_articulo', 'Sin tarifa'),
    ('sin_precio', 'Sin precio'),
]


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    x_tarifa_nombre = fields.Char('Tarifa del proveedor', copy=False, readonly=True)
    x_tarifa_resumen = fields.Char('Comprobación de tarifa', compute='_compute_x_tarifa_resumen')
    x_tarifa_hay_distintos = fields.Boolean(compute='_compute_x_tarifa_resumen')

    @api.depends('order_line.x_tarifa_estado', 'x_tarifa_nombre')
    def _compute_x_tarifa_resumen(self):
        for order in self:
            lineas = order.order_line.filtered(lambda l: not l.display_type and l.product_id)
            distintos = len(lineas.filtered(lambda l: l.x_tarifa_estado == 'distinto'))
            order.x_tarifa_hay_distintos = bool(distintos)
            fuera = len(lineas.filtered(lambda l: l.x_tarifa_estado == 'sin_articulo'))
            correctos = len(lineas.filtered(lambda l: l.x_tarifa_estado == 'ok'))
            if not (distintos or fuera or correctos):
                order.x_tarifa_resumen = order.x_tarifa_nombre or False
                continue
            partes = []
            if distintos:
                partes.append(_('%s con precio distinto a la tarifa', distintos))
            if fuera:
                partes.append(_('%s que no están en la tarifa', fuera))
            if correctos:
                partes.append(_('%s correctos', correctos))
            texto = ', '.join(partes)
            order.x_tarifa_resumen = f"{order.x_tarifa_nombre}: {texto}" if order.x_tarifa_nombre else texto

    # ------------------------------------------------------------------
    def _comprobar_tarifa(self, forzar=False, silencioso=False):
        servicio = self.env['tarifas.proveedor.servicio']
        for order in self:
            datos = servicio.obtener_tarifa(order.partner_id, forzar=forzar, silencioso=silencioso)
            if datos:
                desde = format_date(self.env, datos.get('vigente_desde')) if datos.get('vigente_desde') else ''
                order.x_tarifa_nombre = f"{datos.get('proveedor')} · {datos.get('tarifa')}" + (f" ({desde})" if desde else '')
            else:
                order.x_tarifa_nombre = _('Este proveedor no tiene tarifa cargada en la app de Tarifas')
            order.order_line._evaluar_tarifa(datos)

    def action_comprobar_tarifa(self):
        """Botón: vuelve a leer la tarifa (sin caché) y comprueba todas las líneas."""
        self._comprobar_tarifa(forzar=True)
        return True

    def action_aplicar_precios_tarifa(self):
        """Botón: pone el precio de tarifa en las líneas con precio distinto (respeta el descuento)."""
        for order in self:
            for line in order.order_line.filtered(lambda l: l.x_tarifa_estado == 'distinto' and l.x_tarifa_precio and not l.qty_invoiced):
                descuento = line.discount or 0.0
                precio = line.x_tarifa_precio / (1 - descuento / 100) if descuento < 100 else line.x_tarifa_precio
                antes = line.price_unit
                line.price_unit = precio
                order.message_post(body=_('Precio de %(producto)s cambiado a la tarifa: %(antes)s → %(ahora)s', producto=line.product_id.display_name,
                                          antes=formatLang(self.env, antes, currency_obj=order.currency_id),
                                          ahora=formatLang(self.env, precio, currency_obj=order.currency_id)))
            order._comprobar_tarifa()
        return True

    def button_confirm(self):
        # Al confirmar se comprueba la tarifa y, si hay diferencias, se deja nota en el historial. Nunca bloquea.
        for order in self.filtered(lambda o: o.state in ('draft', 'sent')):
            try:
                order._comprobar_tarifa(forzar=True, silencioso=True)
                distintas = order.order_line.filtered(lambda l: l.x_tarifa_estado == 'distinto')
                if distintas:
                    filas = Markup('').join(
                        Markup('<li>%s: pedido %s, tarifa %s (%s %%)</li>') % (
                            l.product_id.display_name,
                            formatLang(self.env, l._precio_efectivo(), currency_obj=order.currency_id),
                            formatLang(self.env, l.x_tarifa_precio, currency_obj=order.currency_id),
                            f"{l.x_tarifa_dif:+.1f}")
                        for l in distintas)
                    order.message_post(body=Markup('<p>%s</p><ul>%s</ul>') % (
                        _('Pedido confirmado con precios distintos a la tarifa del proveedor:'), filas))
            except Exception:
                _logger.exception('Tarifas de proveedor: fallo al comprobar el pedido %s', order.name)
        return super().button_confirm()


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    x_tarifa_estado = fields.Selection(ESTADOS, string='Tarifa', copy=False)
    x_tarifa_precio = fields.Float('Precio tarifa', digits='Product Price', copy=False)
    x_tarifa_dif = fields.Float('Dif. tarifa %', digits=(16, 1), copy=False)
    x_tarifa_info = fields.Char('Detalle tarifa', copy=False)

    def _uom(self):
        # Odoo 19: product_uom_id; versiones anteriores: product_uom
        return self.product_uom_id if 'product_uom_id' in self._fields else self.product_uom

    def _precio_efectivo(self):
        return (self.price_unit or 0.0) * (1 - (self.discount or 0.0) / 100)

    def _evaluar_tarifa(self, datos):
        servicio = self.env['tarifas.proveedor.servicio']
        tolerancia = servicio._config()['tolerancia']
        for line in self:
            vals = {'x_tarifa_estado': False, 'x_tarifa_precio': 0.0, 'x_tarifa_dif': 0.0, 'x_tarifa_info': False}
            if line.display_type or not line.product_id or not datos:
                line.update(vals)
                continue
            t = servicio.linea_de_tarifa(datos, line.product_id, line.order_id.partner_id)
            if not t or t.get('descartado'):
                vals['x_tarifa_estado'] = 'sin_articulo'
                line.update(vals)
                continue
            efectivo = line._precio_efectivo()
            esperado, base = servicio.precio_esperado(t, line._uom(), efectivo)
            info = f"{t.get('ref') or ''} {t.get('descripcion') or ''}".strip()
            if t.get('formato'):
                info += f" · {t['formato']}"
            if not esperado:
                vals.update(x_tarifa_estado='sin_precio', x_tarifa_info=info + (f" · {t['notas']}" if t.get('notas') else ''))
                line.update(vals)
                continue
            dif = (efectivo - esperado) / esperado * 100 if esperado else 0.0
            vals.update(
                x_tarifa_precio=esperado,
                x_tarifa_dif=dif,
                x_tarifa_estado='ok' if abs(dif) <= tolerancia or abs(efectivo - esperado) < 0.01 else 'distinto',
                x_tarifa_info=f"{info} · tarifa por {base}",
            )
            line.update(vals)

    @api.onchange('product_id', 'price_unit', 'product_qty', 'discount', 'product_uom_id')
    def _onchange_comprobar_tarifa(self):
        """Comprobación en tiempo real al meter o cambiar una línea (usa la tarifa en caché)."""
        for line in self:
            if not line.product_id or not line.order_id.partner_id:
                continue
            try:
                datos = self.env['tarifas.proveedor.servicio'].obtener_tarifa(line.order_id.partner_id, silencioso=True)
                line._evaluar_tarifa(datos)
            except Exception:
                _logger.exception('Tarifas de proveedor: fallo en la comprobación en tiempo real')
