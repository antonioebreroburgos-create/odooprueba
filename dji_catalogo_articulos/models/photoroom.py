import base64
import logging

import requests

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

URL_DEFECTO = 'https://image-api.photoroom.com/v2/edit'


class DjiCatalogoPhotoroom(models.AbstractModel):
    """Foto de producto uniforme con Photoroom: fondo blanco, producto
    recortado y centrado con el mismo margen, cuadrada y en JPG.

    Configuración (Ajustes → Técnico → Parámetros del sistema):
      dji_catalogo.photoroom_api_key   (obligatorio) clave de la API
      dji_catalogo.photoroom_tamano    por defecto 1200x1200
      dji_catalogo.photoroom_margen    por defecto 0.1  (10 % alrededor del producto)
      dji_catalogo.photoroom_sombra    por defecto vacío (sin sombra); ej. ai.soft
    """
    _name = 'dji.catalogo.photoroom'
    _description = 'Normalizar fotos de producto con Photoroom'

    @api.model
    def fondo_blanco(self, imagen_b64):
        if not imagen_b64:
            raise UserError('Primero sube una foto.')
        param = self.env['ir.config_parameter'].sudo()
        clave = (param.get_param('dji_catalogo.photoroom_api_key') or '').strip()
        if not clave:
            raise UserError(
                'Falta la clave de Photoroom. Ponla en Ajustes → Técnico → Parámetros del sistema, '
                'con la clave "dji_catalogo.photoroom_api_key".'
            )
        datos = {
            'removeBackground': 'true',
            'background.color': 'FFFFFF',
            'outputSize': param.get_param('dji_catalogo.photoroom_tamano') or '1200x1200',
            'padding': param.get_param('dji_catalogo.photoroom_margen') or '0.1',
            'export.format': 'jpeg',
        }
        sombra = (param.get_param('dji_catalogo.photoroom_sombra') or '').strip()
        if sombra:
            datos['shadow.mode'] = sombra

        url = param.get_param('dji_catalogo.photoroom_url') or URL_DEFECTO
        try:
            res = requests.post(
                url,
                headers={'x-api-key': clave},
                files={'imageFile': ('foto.jpg', base64.b64decode(imagen_b64))},
                data=datos,
                timeout=90,
            )
        except requests.RequestException as e:
            _logger.warning('Photoroom no responde: %s', e)
            raise UserError('No se ha podido conectar con Photoroom. Inténtalo de nuevo en un momento.') from e

        if res.status_code != 200:
            detalle = res.text[:300]
            _logger.warning('Photoroom HTTP %s: %s', res.status_code, detalle)
            if res.status_code in (401, 403):
                raise UserError('Photoroom ha rechazado la clave de la API. Revisa "dji_catalogo.photoroom_api_key".')
            if res.status_code == 402:
                raise UserError('La cuenta de Photoroom no tiene créditos suficientes.')
            raise UserError(f'Photoroom no ha podido tratar la foto (error {res.status_code}): {detalle}')
        return base64.b64encode(res.content)
