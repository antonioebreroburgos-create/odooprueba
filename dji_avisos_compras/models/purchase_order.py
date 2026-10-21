import base64
import logging
from datetime import timedelta

import requests
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

TIMEOUT = 15  # segundos: la confirmación del pedido no debe quedarse colgada
HORAS_RECORDATORIO = 24
CLAVE_SEGUIMIENTO = 'dji_avisos_compras.seguimiento'


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    dji_aviso_estado = fields.Selection([
        ('enviado', 'Enviado, sin respuesta'),
        ('recibido', 'Recibido por el proveedor'),
        ('no_recibido', 'El proveedor NO lo ha recibido'),
        ('sin_telefono', 'Proveedor sin WhatsApp'),
        ('error', 'Error al enviar el WhatsApp'),
    ], string='Aviso WhatsApp', copy=False, tracking=True)
    dji_aviso_fecha = fields.Datetime(string='Aviso enviado el', copy=False, readonly=True)
    dji_aviso_respuesta_fecha = fields.Datetime(string='Respuesta del proveedor', copy=False, readonly=True)
    dji_aviso_recordado = fields.Boolean(string='Recordatorio enviado', copy=False, readonly=True)

    # ------------------------------------------------------------
    # Llamada al webhook de Copiloto (Netlify)
    # ------------------------------------------------------------
    def _dji_parametros(self):
        param = self.env['ir.config_parameter'].sudo()
        return {
            'url': (param.get_param('dji_avisos_compras.webhook_url') or '').strip(),
            'secreto': (param.get_param('dji_avisos_compras.webhook_secret') or '').strip(),
            'empresa': (param.get_param('dji_avisos_compras.empresa') or 'DJI').strip(),
        }

    def _dji_webhook(self, payload):
        """POST al webhook. Devuelve el JSON de respuesta o lanza UserError."""
        cfg = self._dji_parametros()
        if not cfg['url'] or not cfg['secreto']:
            raise UserError(_('Faltan los parámetros dji_avisos_compras.webhook_url / webhook_secret.'))
        payload = dict(payload, empresa=cfg['empresa'])
        try:
            res = requests.post(cfg['url'], json=payload, timeout=TIMEOUT,
                                headers={'x-webhook-secret': cfg['secreto']})
        except requests.RequestException as e:
            raise UserError(_('Sin respuesta de Copiloto: %s', e)) from e
        if res.status_code >= 300:
            raise UserError(_('Copiloto respondió %(c)s: %(t)s', c=res.status_code, t=res.text[:300]))
        try:
            return res.json()
        except ValueError:
            return {}

    def _dji_datos_base(self):
        self.ensure_one()
        comprador = self.user_id
        entrega = self.date_planned
        return {
            'pedido_id': self.id,
            'pedido': self.name,
            'proveedor': self.partner_id.commercial_partner_id.name or self.partner_id.name,
            'proveedor_id': self.partner_id.commercial_partner_id.id,
            'comprador_odoo_user_id': comprador.id or False,
            'comprador_nombre': comprador.name or '',
            'empresa_nombre': self.company_id.name,
            'fecha_entrega': fields.Date.to_date(entrega).strftime('%d/%m/%Y') if entrega else 'a convenir',
            'lineas': len(self.order_line.filtered(lambda l: not l.display_type)),
            'callback_url': self._dji_callback_url(),
            'total': round(self.amount_total, 2),
        }

    def _dji_callback_url(self):
        """Dirección de ESTE Odoo (pruebas o producción) a la que Copiloto
        devuelve las respuestas del proveedor."""
        param = self.env['ir.config_parameter'].sudo()
        base = (param.get_param('dji_avisos_compras.callback_base_url')
                or param.get_param('web.base.url') or '').rstrip('/')
        return f'{base}/dji_avisos_compras/respuesta'

    def _dji_telefono_proveedor(self):
        self.ensure_one()
        return (self.partner_id.dji_whatsapp_pedidos
                or self.partner_id.commercial_partner_id.dji_whatsapp_pedidos or '').strip()

    def _dji_pdf_base64(self):
        self.ensure_one()
        pdf, _tipo = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'purchase.action_report_purchase_order', self.ids)
        return base64.b64encode(pdf).decode()

    def _dji_nota(self, texto):
        self.with_context(dji_desde_whatsapp=True).message_post(
            body=texto, message_type='comment', subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------
    # Envío del aviso al proveedor
    # ------------------------------------------------------------
    def _dji_enviar_aviso(self, recordatorio=False):
        for order in self:
            telefono = order._dji_telefono_proveedor()
            datos = order._dji_datos_base()
            if not telefono:
                order.dji_aviso_estado = 'sin_telefono'
                order._dji_nota(_('⚠️ No se ha avisado al proveedor por WhatsApp: no tiene "WhatsApp pedidos" en su ficha.'))
                try:
                    order._dji_webhook(dict(datos, evento='sin_telefono'))
                except UserError as e:
                    _logger.warning('Aviso compra %s (sin teléfono): %s', order.name, e)
                continue
            try:
                payload = dict(datos, evento='recordatorio' if recordatorio else 'pedido_confirmado',
                               telefono=telefono, pdf_base64=order._dji_pdf_base64(),
                               pdf_nombre=f'{order.name}.pdf')
                order._dji_webhook(payload)
            except Exception as e:  # nunca bloquear la confirmación del pedido
                _logger.exception('Aviso compra %s', order.name)
                order.dji_aviso_estado = 'error'
                order._dji_nota(_('❌ No se ha podido enviar el WhatsApp al proveedor (%s): %s', telefono, e))
                continue
            vals = {'dji_aviso_estado': 'enviado'}
            if recordatorio:
                vals['dji_aviso_recordado'] = True
            else:
                vals.update({'dji_aviso_fecha': fields.Datetime.now(), 'dji_aviso_recordado': False,
                             'dji_aviso_respuesta_fecha': False})
            order.write(vals)
            order._dji_nota(
                _('⏰ Recordatorio por WhatsApp enviado al proveedor (%s): sigue sin confirmar.', telefono)
                if recordatorio else
                _('📲 Pedido enviado por WhatsApp al proveedor (%s) con el PDF. Pendiente de que confirme la recepción.', telefono))

    def button_approve(self, force=False):
        antes = {o.id: o.state for o in self}
        res = super().button_approve(force=force)
        nuevos = self.filtered(lambda o: o.state == 'purchase' and antes.get(o.id) != 'purchase')
        if nuevos and not self.env.context.get('dji_sin_aviso_whatsapp'):
            nuevos._dji_enviar_aviso()
        return res

    def action_dji_reenviar_aviso(self):
        self.filtered(lambda o: o.state in ('purchase', 'done'))._dji_enviar_aviso()
        return True

    @api.model
    def _dji_cron_recordatorios(self):
        ahora = fields.Datetime.now()
        if ahora.weekday() >= 5:  # sábado y domingo no se molesta a nadie
            return
        limite = ahora - timedelta(hours=HORAS_RECORDATORIO)
        pendientes = self.search([
            ('state', 'in', ('purchase', 'done')),
            ('dji_aviso_estado', '=', 'enviado'),
            ('dji_aviso_recordado', '=', False),
            ('dji_aviso_fecha', '<=', limite),
        ], limit=50)
        for order in pendientes:
            order._dji_enviar_aviso(recordatorio=True)
            self.env.cr.commit()  # cada pedido por separado: si uno falla, los demás siguen

    # ------------------------------------------------------------
    # Respuestas del proveedor por WhatsApp (las registra Copiloto vía XML-RPC)
    # ------------------------------------------------------------
    def dji_aviso_registrar_respuesta(self, tipo, texto=None, media_urls=None):
        """tipo: 'recibido' | 'no_recibido' | 'mensaje'. Lo llama Copiloto."""
        textos = {
            'recibido': _('✅ El proveedor ha confirmado por WhatsApp que ha recibido el pedido.'),
            'no_recibido': _('❌ El proveedor dice por WhatsApp que NO ha recibido el pedido. Se le ha reenviado el PDF.'),
            'mensaje': _('💬 Mensaje del proveedor por WhatsApp:'),
        }
        for order in self:
            vals = {'dji_aviso_respuesta_fecha': fields.Datetime.now()}
            if tipo in ('recibido', 'no_recibido'):
                vals['dji_aviso_estado'] = tipo
            elif order.dji_aviso_estado == 'enviado':
                vals['dji_aviso_estado'] = 'recibido'  # si escribe sobre el pedido, es que lo tiene
            order.write(vals)
            cuerpo = Markup('%s') % textos.get(tipo, textos['mensaje'])
            if texto:
                cuerpo += Markup('<br/><i>«%s»</i>') % texto
            for url in media_urls or []:
                cuerpo += Markup('<br/><a href="%s" target="_blank">📎 Adjunto</a>') % url
            order.with_context(dji_desde_whatsapp=True).message_post(
                body=cuerpo, message_type='comment', subtype_xmlid='mail.mt_note',
                author_id=order.partner_id.commercial_partner_id.id)
        return True

    # ------------------------------------------------------------
    # Mensajes en el historial: del proveedor (correo) y de compañeros
    # ------------------------------------------------------------
    def _message_post_after_hook(self, message, msg_values):
        res = super()._message_post_after_hook(message, msg_values)
        if self.env.context.get('dji_desde_whatsapp') or len(self) != 1:
            return res
        try:
            self._dji_avisar_mensaje(message)
        except Exception:  # un aviso no puede impedir que se guarde el mensaje
            _logger.exception('Aviso de mensaje en %s', self.name)
        return res

    @staticmethod
    def _dji_texto_mensaje(message):
        texto = ' '.join(html2plaintext(message.body or '').split())
        if len(texto) > 280:
            texto = texto[:277] + '…'
        return texto, len(message.attachment_ids)

    def _dji_avisar_mensaje(self, message):
        if message.message_type not in ('email', 'comment'):
            return  # cambios de estado, seguimiento automático, etc.
        autor = message.author_id
        if autor and autor == self.env.ref('base.partner_root', raise_if_not_found=False):
            return  # OdooBot / procesos automáticos
        texto, adjuntos = self._dji_texto_mensaje(message)
        if not texto and not adjuntos:
            return
        usuario = autor and autor.with_context(active_test=False).user_ids.filtered(lambda u: not u.share)[:1]
        if usuario:
            # Un compañero escribe en el pedido (mensaje o nota): se avisa al
            # comprador, salvo que lo haya escrito él mismo.
            extra = f' (+{adjuntos} adjunto{"s" if adjuntos > 1 else ""})' if adjuntos else ''
            self._dji_seguimiento(f'💬 «{texto or "sin texto"}»{extra}', usuario=usuario)
            return
        # Escribe alguien de fuera (el proveedor, normalmente por correo).
        # Las notas internas no cuentan; los correos que entran, siempre.
        if message.message_type == 'comment' and (message.subtype_id.internal or message.is_internal):
            return
        if self.state not in ('sent', 'to approve', 'purchase', 'done'):
            return
        self._dji_webhook(dict(
            self._dji_datos_base(), evento='mensaje_proveedor',
            texto=texto, adjuntos=adjuntos,
            autor=autor.name or message.email_from or self.partner_id.name,
        ))

    # ------------------------------------------------------------
    # Seguimiento: modificaciones del pedido hechas por otros usuarios
    # ------------------------------------------------------------
    def write(self, vals):
        cancelados = self.browse()
        if vals.get('state') == 'cancel':
            cancelados = self.filtered(lambda o: o.state in ('purchase', 'done'))
        res = super().write(vals)
        for order in cancelados:
            order._dji_seguimiento('🚫 Ha CANCELADO el pedido', comprobar_estado=False)
        return res

    def _dji_seguimiento_activo(self, usuario, comprobar_estado=True):
        self.ensure_one()
        if self.env.context.get('dji_sin_seguimiento'):
            return False
        if comprobar_estado and self.state not in ('purchase', 'done'):
            return False
        return bool(
            self.dji_aviso_estado  # solo pedidos que ya se avisaron al proveedor
            and self.user_id
            and usuario and usuario != self.user_id  # lo que hace el comprador no se le avisa
            and not usuario._is_superuser() and not usuario.share
        )

    def _dji_seguimiento(self, texto, usuario=None, comprobar_estado=True):
        """Apunta un cambio o mensaje. Al guardar (fin de la transacción) se
        manda UN solo WhatsApp al comprador por pedido con todo lo apuntado."""
        usuario = usuario or self.env.user
        datos = self.env.cr.precommit.data.get(CLAVE_SEGUIMIENTO)
        for order in self:
            if not order._dji_seguimiento_activo(usuario, comprobar_estado):
                continue
            if datos is None:
                datos = self.env.cr.precommit.data[CLAVE_SEGUIMIENTO] = {}
                self.env.cr.precommit.add(self._dji_seguimiento_preparar)
            apunte = datos.setdefault(order.id, {'autor': usuario.name, 'textos': []})
            if texto not in apunte['textos']:
                apunte['textos'].append(texto)

    def _dji_seguimiento_preparar(self):
        """Justo antes del commit: monta los avisos. Se envían después del
        commit, para no avisar de cambios que al final no se guardan."""
        datos = self.env.cr.precommit.data.get(CLAVE_SEGUIMIENTO) or {}
        cfg = self._dji_parametros()
        if not datos or not cfg['url'] or not cfg['secreto']:
            return
        envios = []
        for order in self.env['purchase.order'].sudo().browse(list(datos)).exists():
            apunte = datos[order.id]
            texto = f"{apunte['autor']}: " + ' · '.join(apunte['textos'])
            if len(texto) > 600:
                texto = texto[:597] + '…'
            envios.append(dict(order._dji_datos_base(), evento='aviso_comprador',
                               texto=texto, empresa=cfg['empresa']))

        def enviar():
            for payload in envios:
                try:
                    res = requests.post(cfg['url'], json=payload, timeout=TIMEOUT,
                                        headers={'x-webhook-secret': cfg['secreto']})
                    if res.status_code >= 300:
                        _logger.warning('Seguimiento compra %s: %s %s', payload['pedido'], res.status_code, res.text[:200])
                except Exception:
                    _logger.exception('Seguimiento compra %s', payload['pedido'])

        if envios:
            self.env.cr.postcommit.add(enviar)
