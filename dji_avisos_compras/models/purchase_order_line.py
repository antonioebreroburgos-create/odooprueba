from odoo import api, fields, models

CAMPOS_SEGUIMIENTO = ('product_id', 'product_qty', 'price_unit', 'discount', 'date_planned')


def _cifra(valor, decimales=3):
    texto = f'{valor:.{decimales}f}'
    if decimales == 3:
        texto = texto.rstrip('0').rstrip('.')
    return texto.replace('.', ',')


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _dji_nombre(self):
        nombre = self.product_id.display_name or (self.name or '').split('\n')[0]
        return nombre[:50]

    def _dji_fecha(self):
        if not self.date_planned:
            return ''
        return fields.Datetime.context_timestamp(self, self.date_planned).strftime('%d/%m/%Y')

    def _dji_foto(self):
        return {
            'producto': self._dji_nombre(),
            'cantidad': self.product_qty,
            'precio': self.price_unit,
            'dto': self.discount,
            'fecha': self._dji_fecha(),
        }

    @api.model_create_multi
    def create(self, vals_list):
        lineas = super().create(vals_list)
        for linea in lineas.filtered(lambda l: not l.display_type):
            linea.order_id._dji_seguimiento(
                f'➕ Añade {linea._dji_nombre()} ({_cifra(linea.product_qty)} {linea.product_uom_id.name or "ud"})')
        return lineas

    def write(self, vals):
        if not any(c in vals for c in CAMPOS_SEGUIMIENTO) or self.env.context.get('dji_sin_seguimiento'):
            return super().write(vals)
        antes = {l.id: l._dji_foto() for l in self}
        res = super().write(vals)
        for linea in self.filtered(lambda l: not l.display_type):
            a, d = antes[linea.id], linea._dji_foto()
            nombre = d['producto']
            cambios = []
            if a['producto'] != d['producto']:
                cambios.append(f"🔁 Cambia {a['producto']} por {d['producto']}")
            if a['cantidad'] != d['cantidad']:
                cambios.append(f"✏️ {nombre}: cantidad {_cifra(a['cantidad'])} → {_cifra(d['cantidad'])}")
            if a['precio'] != d['precio']:
                cambios.append(f"✏️ {nombre}: precio {_cifra(a['precio'], 2)} → {_cifra(d['precio'], 2)} €")
            if a['dto'] != d['dto']:
                cambios.append(f"✏️ {nombre}: dto. {_cifra(a['dto'])} % → {_cifra(d['dto'])} %")
            if a['fecha'] != d['fecha']:
                cambios.append(f"📅 Entrega prevista {a['fecha'] or '—'} → {d['fecha'] or '—'}")
            for cambio in cambios:
                linea.order_id._dji_seguimiento(cambio)
        return res

    def unlink(self):
        for linea in self.filtered(lambda l: not l.display_type):
            linea.order_id._dji_seguimiento(f'➖ Quita {linea._dji_nombre()}')
        return super().unlink()
