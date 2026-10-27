# -*- coding: utf-8 -*-
from datetime import date, timedelta
from odoo import models, fields, api

DIAS_ORD = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
DIAS_LABEL = {
    'lunes': 'Lunes', 'martes': 'Martes', 'miercoles': 'Miércoles',
    'jueves': 'Jueves', 'viernes': 'Viernes', 'sabado': 'Sábado', 'domingo': 'Domingo',
}
# weekday() de Python: 0=lun, 1=mar, ..., 6=dom
WEEKDAY_MAP = {0: 'lunes', 1: 'martes', 2: 'miercoles',
               3: 'jueves', 4: 'viernes', 5: 'sabado', 6: 'domingo'}
PEDIDO_MINIMO = 90.0


def _proxima_fecha(dias_activos):
    """Calcula la próxima fecha de entrega a partir de hoy (inclusive mañana)."""
    if not dias_activos:
        return None
    hoy = date.today()
    for offset in range(1, 15):  # buscar en los próximos 14 días
        candidate = hoy + timedelta(days=offset)
        if WEEKDAY_MAP.get(candidate.weekday()) in dias_activos:
            return candidate
    return None


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Campo calculado: aviso de próxima entrega (texto, no guardado)
    dji_aviso_entrega = fields.Char(
        string='Próxima entrega',
        compute='_compute_dji_avisos',
        store=False,
    )
    # Aviso de pedido mínimo
    dji_aviso_minimo = fields.Char(
        string='Aviso pedido mínimo',
        compute='_compute_dji_avisos',
        store=False,
    )

    @api.depends('partner_shipping_id', 'partner_shipping_id.dji_dia_lunes',
                 'partner_shipping_id.dji_dia_martes', 'partner_shipping_id.dji_dia_miercoles',
                 'partner_shipping_id.dji_dia_jueves', 'partner_shipping_id.dji_dia_viernes',
                 'partner_shipping_id.dji_dia_sabado', 'partner_shipping_id.dji_dia_domingo',
                 'partner_id', 'partner_id.dji_dia_lunes',
                 'partner_id.dji_dia_martes', 'partner_id.dji_dia_miercoles',
                 'partner_id.dji_dia_jueves', 'partner_id.dji_dia_viernes',
                 'partner_id.dji_dia_sabado', 'partner_id.dji_dia_domingo',
                 'amount_untaxed')
    def _compute_dji_avisos(self):
        for order in self:
            # Determinar el partner de entrega (shipping o principal)
            entrega = order.partner_shipping_id or order.partner_id
            if entrega:
                dias = entrega.dji_dias_activos
            else:
                dias = []

            # Aviso próxima entrega
            if dias:
                proxima = _proxima_fecha(dias)
                if proxima:
                    dia_semana = DIAS_LABEL.get(WEEKDAY_MAP.get(proxima.weekday(), ''), '')
                    fecha_str = proxima.strftime('%d/%m/%Y')
                    dias_nombres = [DIAS_LABEL[d] for d in dias if d in DIAS_LABEL]
                    order.dji_aviso_entrega = (
                        f"Próxima entrega: {dia_semana} {fecha_str} "
                        f"(días habituales: {', '.join(dias_nombres)})"
                    )
                else:
                    order.dji_aviso_entrega = False
            else:
                order.dji_aviso_entrega = False

            # Aviso pedido mínimo
            if order.amount_untaxed and order.amount_untaxed < PEDIDO_MINIMO:
                order.dji_aviso_minimo = (
                    f"⚠️ Base del pedido ({order.amount_untaxed:.2f} €) "
                    f"inferior al mínimo de {PEDIDO_MINIMO:.2f} €"
                )
            else:
                order.dji_aviso_minimo = False

    @api.model
    def get_avisos_pedido(self, order_id):
        """Devuelve los avisos de un pedido para mostrar en el frontend."""
        order = self.browse(int(order_id))
        if not order:
            return {}
        return {
            'aviso_entrega': order.dji_aviso_entrega or False,
            'aviso_minimo': order.dji_aviso_minimo or False,
        }
