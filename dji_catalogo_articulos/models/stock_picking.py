from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    catalogo_pendientes = fields.Integer(
        string='Artículos por completar', compute='_compute_catalogo_pendientes',
    )

    def _catalogo_plantillas(self):
        self.ensure_one()
        return self.move_ids.product_id.product_tmpl_id

    @api.depends('move_ids.product_id', 'move_ids.product_id.product_tmpl_id.catalogo_revisado')
    def _compute_catalogo_pendientes(self):
        for picking in self:
            if picking.picking_type_code != 'incoming':
                picking.catalogo_pendientes = 0
                continue
            plantillas = picking._catalogo_plantillas()
            picking.catalogo_pendientes = len(plantillas.filtered(lambda p: not p.catalogo_revisado))

    def action_completar_articulos(self):
        self.ensure_one()
        asistente = self.env['dji.catalogo.completar'].crear_desde_recepcion(self)
        return {
            'type': 'ir.actions.act_window',
            'name': f'Completar artículos · {self.name}',
            'res_model': 'dji.catalogo.completar',
            'res_id': asistente.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'dialog_size': 'extra-large'},
        }
