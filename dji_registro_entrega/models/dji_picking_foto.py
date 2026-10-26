from odoo import models, fields


class DjiPickingFoto(models.Model):
    _name = "dji.picking.foto"
    _description = "Foto vinculada a un albarán"
    _order = "fecha_subida desc"

    picking_id = fields.Many2one(
        "stock.picking",
        string="Albarán",
        required=True,
        ondelete="cascade",
    )
    tipo = fields.Selection(
        [("carga", "Carga (almacén)"), ("entrega", "Entrega (cliente)")],
        string="Tipo",
        required=True,
    )
    url = fields.Char(string="URL de la foto", required=True)
    fecha_subida = fields.Datetime(string="Fecha subida", default=fields.Datetime.now)
    subida_por = fields.Char(string="Subida por")

    # Análisis IA — solo en fotos de carga
    ia_analisis = fields.Text(string="Análisis IA")
    ia_estado = fields.Selection(
        [("ok", "Sin incidencias"), ("incidencia", "Incidencias detectadas"), ("pendiente", "Pendiente de análisis")],
        string="Estado IA",
        default="pendiente",
    )
