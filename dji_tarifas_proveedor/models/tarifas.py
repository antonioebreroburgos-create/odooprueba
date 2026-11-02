import logging
import re
import time
import unicodedata

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Caché en memoria de las tarifas: {(bd, empresa, partner_id): (momento, datos)}
_CACHE = {}
_CACHE_SEGUNDOS = 600


def normalizar(texto):
    """Minúsculas, sin tildes y sin signos (igual que la app de Tarifas)."""
    texto = unicodedata.normalize('NFD', str(texto or '').lower())
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', texto).strip()


class TarifasProveedorServicio(models.AbstractModel):
    _name = 'tarifas.proveedor.servicio'
    _description = 'Consulta de tarifas de proveedor (app de Tarifas)'

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    @api.model
    def _config(self):
        icp = self.env['ir.config_parameter'].sudo()
        try:
            tolerancia = float(icp.get_param('tarifas_proveedor.tolerancia') or 1.0)
        except ValueError:
            tolerancia = 1.0
        return {
            'url': (icp.get_param('tarifas_proveedor.supabase_url') or '').rstrip('/'),
            'key': icp.get_param('tarifas_proveedor.supabase_key') or '',
            'empresa': icp.get_param('tarifas_proveedor.empresa') or 'DJI',
            'tolerancia': tolerancia,
        }

    # ------------------------------------------------------------------
    # Lectura de la tarifa vigente del proveedor
    # ------------------------------------------------------------------
    @api.model
    def obtener_tarifa(self, partner, forzar=False, silencioso=False):
        """Devuelve {proveedor, tarifa, vigente_desde, lineas: [...]} o None si el proveedor no tiene tarifa.
        silencioso=True: ante un error de conexión devuelve None en lugar de avisar."""
        partner = partner.commercial_partner_id if partner else partner
        if not partner:
            return None
        cfg = self._config()
        if not cfg['url'] or not cfg['key']:
            if silencioso:
                return None
            raise UserError(_('Falta configurar la conexión con la app de Tarifas en Compras > Configuración > Ajustes.'))
        clave = (self.env.cr.dbname, cfg['empresa'], partner.id)
        ahora = time.time()
        if not forzar and clave in _CACHE and ahora - _CACHE[clave][0] < _CACHE_SEGUNDOS:
            return _CACHE[clave][1]
        try:
            r = requests.post(
                f"{cfg['url']}/rest/v1/rpc/tarifa_para_odoo",
                json={'p_empresa': cfg['empresa'], 'p_partner_id': partner.id},
                headers={'apikey': cfg['key'], 'Authorization': f"Bearer {cfg['key']}", 'Content-Type': 'application/json'},
                timeout=10,
            )
            r.raise_for_status()
            datos = r.json() or None
        except Exception as e:
            _logger.warning('Tarifas de proveedor: no se pudo consultar la tarifa de %s: %s', partner.display_name, e)
            if silencioso:
                return None
            raise UserError(_('No se pudo consultar la app de Tarifas: %s', e)) from e
        if datos:
            datos = self._preparar(datos)
        _CACHE[clave] = (ahora, datos)
        return datos

    @api.model
    def _preparar(self, datos):
        """Índices para buscar rápido la línea de tarifa de cada artículo."""
        por_producto, por_ref, por_ean = {}, {}, {}
        for linea in datos.get('lineas') or []:
            if linea.get('odoo_product_id'):
                por_producto.setdefault(linea['odoo_product_id'], linea)
            if linea.get('ref'):
                por_ref.setdefault(normalizar(linea['ref']), linea)
            if linea.get('ean'):
                por_ean.setdefault(str(linea['ean']).strip(), linea)
        datos['_por_producto'], datos['_por_ref'], datos['_por_ean'] = por_producto, por_ref, por_ean
        return datos

    @api.model
    def linea_de_tarifa(self, datos, product, partner):
        """Busca la línea de tarifa de un artículo:
        1) vínculo hecho en la app, 2) código del proveedor de la pestaña Compra, 3) código de barras."""
        if not datos or not product:
            return None
        linea = datos['_por_producto'].get(product.id)
        if linea:
            return linea
        partner = partner.commercial_partner_id
        for si in product.seller_ids:
            # Odoo 16+ usa partner_id; Odoo 13/15 usa name
            si_partner = si.partner_id if 'partner_id' in si._fields else si.name
            if si_partner.commercial_partner_id == partner and si.product_code:
                linea = datos['_por_ref'].get(normalizar(si.product_code))
                if linea:
                    return linea
        if product.barcode:
            return datos['_por_ean'].get(product.barcode.strip())
        return None

    # ------------------------------------------------------------------
    # Comparación de precio
    # ------------------------------------------------------------------
    @api.model
    def precio_esperado(self, linea, uom, precio_pedido):
        """Precio de tarifa en la misma unidad que la línea del pedido.
        Devuelve (precio, base) donde base es 'caja', 'kg', 'litro' o 'unidad'."""
        neto = linea.get('precio_neto')
        caja = linea.get('precio_caja')
        kg = linea.get('precio_kg')
        kg_ud = linea.get('kg_unidad')
        unidad = linea.get('unidad_precio') or 'U'

        candidatos = []          # (base, precio)
        if caja:
            candidatos.append(('caja', caja))
        if unidad in ('KG', 'L') and neto:
            candidatos.append(('kg' if unidad == 'KG' else 'litro', neto))
        elif kg:
            candidatos.append(('kg', kg))
        if unidad == 'U' and neto:
            candidatos.append(('unidad', neto))
        if unidad == 'CAJA' and neto:
            candidatos.append(('caja', neto))
        if unidad in ('KG', 'L') and neto and kg_ud:
            candidatos.append(('unidad', round(neto * kg_ud, 4)))
        if not candidatos:
            return None, None

        # Si la unidad de la línea lo deja claro (Caja, kg, litro), se usa ese precio.
        # "Unidades" NO se fuerza: en Odoo muchos artículos se compran en "Unidades"
        # aunque cada unidad sea una caja (p. ej. "30Und/Caja"); en ese caso se usa
        # el precio de tarifa más cercano (unidad, caja o kg).
        nombre = normalizar(uom.name if uom else '')
        if re.search(r'\b(caja|cajas|cj|bulto|bultos|pack|paquete)\b', nombre):
            preferida = 'caja'
        elif re.search(r'\b(kg|kgs|kilo|kilos|kilogramo|kilogramos)\b', nombre):
            preferida = 'kg'
        elif re.search(r'\b(l|lt|litro|litros)\b', nombre):
            preferida = 'litro'
        else:
            preferida = None
        elegidos = [c for c in candidatos if c[0] == preferida]
        if len(elegidos) == 1 or (elegidos and not precio_pedido):
            return elegidos[0][1], elegidos[0][0]
        # Si no está claro, el precio de tarifa más cercano al del pedido
        lista = elegidos or candidatos
        if not precio_pedido:
            return lista[0][1], lista[0][0]
        base, precio = min(lista, key=lambda c: abs(c[1] - precio_pedido))
        return precio, base
