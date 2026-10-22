import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

NOMBRE_ETIQUETA_FALTAS = "FALTAS"
WEBHOOK_TIMEOUT = 5  # segundos; si no responde a tiempo, no bloquea al usuario


class DjiFaltasWizard(models.TransientModel):
    _name = "dji.faltas.wizard"
    _description = "Gestión de faltas de un pedido de venta"

    order_id = fields.Many2one("sale.order", required=True, readonly=True)
    line_ids = fields.One2many(
        "dji.faltas.wizard.line", "wizard_id", string="Líneas del pedido"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = res.get("order_id") or self.env.context.get("default_order_id")
        if not order_id:
            return res

        order = self.env["sale.order"].browse(order_id)
        if order.state not in ("draft", "sent"):
            raise UserError(
                _("Solo se pueden gestionar faltas en presupuestos sin confirmar.")
            )

        etiqueta = self.env["sale.order.tag"].sudo().search(
            [("name", "=", NOMBRE_ETIQUETA_FALTAS)], limit=1
        )
        if etiqueta and etiqueta in order.so_tag_ids:
            raise UserError(
                _("Este presupuesto ya es de FALTAS. Deja en él las líneas pendientes.")
            )

        if "line_ids" in fields_list:
            lineas_vals = []
            for linea in order.order_line.filtered(
                lambda l: not l.display_type and l.product_uom_qty > 0
            ):
                disponible = linea.product_id.with_context(
                    warehouse=order.warehouse_id.id if order.warehouse_id else False
                ).qty_available
                sugerencia = max(0.0, linea.product_uom_qty - disponible)
                lineas_vals.append((0, 0, {
                    "order_line_id": linea.id,
                    "product_id": linea.product_id.id,
                    "descripcion": linea.name,
                    "qty_pedida": linea.product_uom_qty,
                    "qty_disponible": disponible,
                    "qty_falta": sugerencia,
                }))
            res["line_ids"] = lineas_vals

        return res

    def action_confirmar(self):
        self.ensure_one()

        pedido = self.order_id
        lineas_falta = self.line_ids.filtered(lambda l: l.qty_falta > 0)
        if not lineas_falta:
            raise UserError(_("Marca la cantidad en falta en al menos un producto."))

        errores = []
        for l in lineas_falta:
            if l.qty_falta > l.qty_pedida:
                errores.append("- %s: falta %g pero se pidieron %g" % (
                    l.product_id.display_name, l.qty_falta, l.qty_pedida))
        if errores:
            raise UserError(
                _("La falta no puede ser mayor que lo pedido:\n") + "\n".join(errores)
            )

        etiqueta = self.env["sale.order.tag"].sudo().search(
            [("name", "=", NOMBRE_ETIQUETA_FALTAS)], limit=1
        )
        if not etiqueta:
            etiqueta = self.env["sale.order.tag"].sudo().create(
                {"name": NOMBRE_ETIQUETA_FALTAS}
            )

        # ---------- Presupuesto FALTAS: reutilizar o crear ----------
        faltas = self.env["sale.order"].search([
            ("id", "!=", pedido.id),
            ("partner_id", "=", pedido.partner_id.id),
            ("partner_shipping_id", "=", pedido.partner_shipping_id.id),
            ("company_id", "=", pedido.company_id.id),
            ("state", "in", ("draft", "sent")),
            ("so_tag_ids", "in", etiqueta.ids),
        ], order="id desc", limit=1)

        es_nuevo = False
        if not faltas:
            vals = {
                "partner_id": pedido.partner_id.id,
                "partner_invoice_id": pedido.partner_invoice_id.id,
                "partner_shipping_id": pedido.partner_shipping_id.id,
                "user_id": pedido.user_id.id,
                "team_id": pedido.team_id.id,
                "company_id": pedido.company_id.id,
                "pricelist_id": pedido.pricelist_id.id,
                "payment_term_id": pedido.payment_term_id.id,
                "fiscal_position_id": pedido.fiscal_position_id.id,
                "so_tag_ids": [(6, 0, [etiqueta.id])],
                "origin": pedido.name,
            }
            if "warehouse_id" in pedido._fields and pedido.warehouse_id:
                vals["warehouse_id"] = pedido.warehouse_id.id
            if "route_id" in pedido._fields and pedido.route_id:
                vals["route_id"] = pedido.route_id.id
            faltas = self.env["sale.order"].create(vals)
            es_nuevo = True
        else:
            origenes = faltas.origin or ""
            if pedido.name not in origenes:
                faltas.write({
                    "origin": (origenes + ", " + pedido.name) if origenes else pedido.name
                })

        # Nombres de campo que cambian entre versiones de Odoo
        campo_uom = (
            "product_uom_id" if "product_uom_id" in pedido.order_line._fields
            else "product_uom"
        )
        campo_imp = (
            "tax_ids" if "tax_ids" in pedido.order_line._fields else "tax_id"
        )

        resumen = []
        for wl in lineas_falta:
            linea = wl.order_line_id
            falta = wl.qty_falta
            precio = linea.price_unit
            dto = linea.discount
            producto = linea.product_id

            existente = faltas.order_line.filtered(
                lambda x: not x.display_type and x.product_id == producto
                and x.price_unit == precio and x.discount == dto
            )
            if existente:
                ex = existente[0]
                ex.write({
                    "product_uom_qty": ex.product_uom_qty + falta,
                    "price_unit": precio,
                    "discount": dto,
                })
            else:
                self.env["sale.order.line"].create({
                    "order_id": faltas.id,
                    "product_id": producto.id,
                    "name": linea.name,
                    "product_uom_qty": falta,
                    campo_uom: linea[campo_uom].id,
                    "price_unit": precio,
                    "discount": dto,
                    campo_imp: [(6, 0, linea[campo_imp].ids)],
                })

            resumen.append("%g x %s" % (falta, producto.display_name))

            restante = linea.product_uom_qty - falta
            if restante <= 0:
                linea.unlink()
            else:
                linea.write({
                    "product_uom_qty": restante,
                    "price_unit": precio,
                    "discount": dto,
                })

        texto = "; ".join(resumen)

        pedido.message_post(body=_("Faltas pasadas a %s: %s") % (faltas.name, texto))
        faltas.message_post(body=_("Faltas recibidas de %s: %s") % (pedido.name, texto))

        # NOTA: de momento avisamos con una nota de chatter (mención) en vez
        # de una actividad (mail.activity). Hay un bug en el módulo
        # sales_team_security de este Odoo 19 ("'res.users' object has no
        # attribute 'activity_team_ids'") que revienta el chatter de
        # CUALQUIER pedido que tenga una actividad asignada, para
        # cualquier usuario que lo abra. Hasta que se corrija esa regla,
        # no creamos actividades desde aquí.
        if pedido.user_id and pedido.user_id.partner_id:
            faltas.message_post(
                body=_("Productos que han quedado en falta del pedido %s: %s") % (
                    pedido.name, texto),
                subject=_("Faltas de %s") % pedido.name,
                partner_ids=[pedido.user_id.partner_id.id],
            )

        self._avisar_whatsapp_comercial(pedido, faltas, resumen)

        mensaje = _("%s %s con %d producto(s).") % (
            _("Creado") if es_nuevo else _("Añadido a"), faltas.name, len(resumen))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Faltas gestionadas"),
                "message": mensaje,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }


    def _avisar_whatsapp_comercial(self, pedido, faltas, resumen):
        """Avisa por WhatsApp al comercial vía webhook a Netlify.
        No lanza excepción si falla: el presupuesto FALTAS ya está creado
        y no queremos que un problema de red deje el wizard en un estado
        confuso para el almacén.
        """
        if not pedido.user_id:
            return

        params = self.env["ir.config_parameter"].sudo()
        base_url = params.get_param("web.base.url") or ""
        enlace_faltas = "%s/odoo/sales/%s" % (base_url.rstrip("/"), faltas.id)

        url = params.get_param("dji_gestion_faltas.webhook_url")
        if not url:
            _logger.info(
                "dji_gestion_faltas: sin dji_gestion_faltas.webhook_url "
                "configurado, no se avisa por WhatsApp del pedido %s",
                pedido.name,
            )
            return
        secret = params.get_param("dji_gestion_faltas.webhook_secret")

        payload = {
            "empresa": "DJI",
            "comercial_odoo_user_id": pedido.user_id.id,
            "cliente": pedido.partner_id.display_name,
            "pedido_origen": pedido.name,
            "pedido_faltas": faltas.name,
            "pedido_faltas_id": faltas.id,
            "productos": resumen,
            "enlace_faltas": enlace_faltas,
        }
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["X-Webhook-Secret"] = secret

        try:
            requests.post(url, json=payload, headers=headers, timeout=WEBHOOK_TIMEOUT)
        except Exception:
            _logger.warning(
                "dji_gestion_faltas: fallo avisando por WhatsApp del pedido %s",
                pedido.name,
                exc_info=True,
            )


class DjiFaltasWizardLine(models.TransientModel):
    _name = "dji.faltas.wizard.line"
    _description = "Línea de gestión de faltas"

    wizard_id = fields.Many2one("dji.faltas.wizard", required=True, ondelete="cascade")
    order_line_id = fields.Many2one("sale.order.line", required=True, readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    descripcion = fields.Char(string="Producto", readonly=True)
    qty_pedida = fields.Float(string="Pedido", readonly=True)
    qty_disponible = fields.Float(string="Disponible (ref.)", readonly=True)
    qty_falta = fields.Float(string="Falta")
