from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # Fotos
    dji_foto_ids = fields.One2many(
        "dji.picking.foto",
        "picking_id",
        string="Fotos",
    )
    dji_fotos_carga = fields.One2many(
        "dji.picking.foto",
        "picking_id",
        string="Fotos de carga",
        domain=[("tipo", "=", "carga")],
    )
    dji_fotos_entrega = fields.One2many(
        "dji.picking.foto",
        "picking_id",
        string="Fotos de entrega",
        domain=[("tipo", "=", "entrega")],
    )

    # Contadores calculados
    dji_num_fotos_carga = fields.Integer(
        string="Nº fotos carga",
        compute="_compute_dji_stats",
        store=True,
    )
    dji_num_fotos_entrega = fields.Integer(
        string="Nº fotos entrega",
        compute="_compute_dji_stats",
        store=True,
    )

    # Estado IA global del picking (peor caso entre todas las fotos de carga)
    dji_ia_estado = fields.Selection(
        [("sin_fotos", "Sin fotos"), ("pendiente", "Pendiente análisis"), ("ok", "Sin incidencias"), ("incidencia", "Incidencias detectadas")],
        string="Estado IA",
        compute="_compute_dji_stats",
        store=True,
    )

    # Texto resumen del análisis IA (concatenación de todos los análisis)
    dji_ia_resumen = fields.Text(
        string="Resumen análisis IA",
        compute="_compute_dji_stats",
        store=True,
    )

    @api.depends("dji_foto_ids", "dji_foto_ids.tipo", "dji_foto_ids.ia_estado", "dji_foto_ids.ia_analisis")
    def _compute_dji_stats(self):
        for picking in self:
            fotos_carga = picking.dji_foto_ids.filtered(lambda f: f.tipo == "carga")
            fotos_entrega = picking.dji_foto_ids.filtered(lambda f: f.tipo == "entrega")

            picking.dji_num_fotos_carga = len(fotos_carga)
            picking.dji_num_fotos_entrega = len(fotos_entrega)

            if not fotos_carga:
                picking.dji_ia_estado = "sin_fotos"
                picking.dji_ia_resumen = False
            elif any(f.ia_estado == "incidencia" for f in fotos_carga):
                picking.dji_ia_estado = "incidencia"
                picking.dji_ia_resumen = "\n\n".join(
                    f.ia_analisis for f in fotos_carga if f.ia_analisis
                )
            elif all(f.ia_estado == "ok" for f in fotos_carga):
                picking.dji_ia_estado = "ok"
                picking.dji_ia_resumen = "\n\n".join(
                    f.ia_analisis for f in fotos_carga if f.ia_analisis
                )
            else:
                picking.dji_ia_estado = "pendiente"
                picking.dji_ia_resumen = False
