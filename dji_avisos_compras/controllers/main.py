import hmac
import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DjiAvisosCompras(http.Controller):
    """Copiloto avisa aquí de lo que responde el proveedor por WhatsApp
    (botones Recibido / No lo he recibido, textos y fotos)."""

    @http.route('/dji_avisos_compras/respuesta', type='http', auth='public',
                methods=['POST'], csrf=False, save_session=False)
    def respuesta(self, **_kw):
        secreto = (request.env['ir.config_parameter'].sudo()
                   .get_param('dji_avisos_compras.webhook_secret') or '').strip()
        recibido = request.httprequest.headers.get('x-webhook-secret', '')
        if not secreto or not hmac.compare_digest(secreto, recibido):
            return request.make_json_response({'error': 'Unauthorized'}, status=401)
        try:
            datos = json.loads(request.httprequest.get_data(as_text=True) or '{}')
            pedido = request.env['purchase.order'].with_user(SUPERUSER_ID).browse(int(datos.get('pedido_id') or 0)).exists()
            if not pedido:
                return request.make_json_response({'error': 'Pedido no encontrado'}, status=404)
            pedido.dji_aviso_registrar_respuesta(
                datos.get('tipo') or 'mensaje', datos.get('texto') or None, datos.get('media_urls') or [])
            return request.make_json_response({'ok': True})
        except Exception as e:
            _logger.exception('Respuesta de proveedor por WhatsApp')
            return request.make_json_response({'error': str(e)}, status=500)
