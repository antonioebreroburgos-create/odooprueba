from odoo import api, fields, models

CAMPO_UDS = 'uom_qty'  # "Unidades por defecto" (campo propio de DJI en product.template)


class CatalogoCompletar(models.TransientModel):
    _name = 'dji.catalogo.completar'
    _description = 'Completar artículos de una recepción para el catálogo'

    picking_id = fields.Many2one('stock.picking', string='Recepción', readonly=True)
    linea_ids = fields.One2many('dji.catalogo.completar.linea', 'asistente_id', string='Artículos')
    tiene_uds = fields.Boolean(compute='_compute_tiene_uds')

    def _compute_tiene_uds(self):
        existe = CAMPO_UDS in self.env['product.template']._fields
        for rec in self:
            rec.tiene_uds = existe

    @api.model
    def crear_desde_recepcion(self, picking):
        tiene_uds = CAMPO_UDS in self.env['product.template']._fields
        lineas = []
        # Pendientes primero; los ya revisados al final (en gris)
        plantillas = picking._catalogo_plantillas().sorted(lambda p: (p.catalogo_revisado, p.name or ''))
        for p in plantillas:
            lineas.append((0, 0, {
                'product_tmpl_id': p.id,
                'nombre': p.name,
                'imagen': p.image_1920,
                'imagen_original': p.imagen_original,
                'tag_ids': [(6, 0, p.product_tag_ids.ids)],
                'uds_defecto': p[CAMPO_UDS] if tiene_uds else 0.0,
                'ficha': p.ficha_tecnica,
                'ficha_nombre': p.ficha_tecnica_nombre,
                'ya_revisado': p.catalogo_revisado,
                'revisado': p.catalogo_revisado,
            }))
        return self.create({'picking_id': picking.id, 'linea_ids': lineas})

    def action_marcar_todos(self):
        self.linea_ids.write({'revisado': True})
        return self._reabrir()

    def _reabrir(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'name': f'Completar artículos · {self.picking_id.name}',
            'context': {'dialog_size': 'extra-large'},
        }

    def action_guardar(self):
        tiene_uds = CAMPO_UDS in self.env['product.template']._fields
        ahora = fields.Datetime.now()
        for linea in self.linea_ids:
            p = linea.product_tmpl_id
            vals = {}
            if linea.nombre and linea.nombre != p.name:
                vals['name'] = linea.nombre
            if linea.imagen != p.image_1920:
                vals['image_1920'] = linea.imagen
            if linea.imagen_original != p.imagen_original:
                vals['imagen_original'] = linea.imagen_original
            if set(linea.tag_ids.ids) != set(p.product_tag_ids.ids):
                vals['product_tag_ids'] = [(6, 0, linea.tag_ids.ids)]
            if tiene_uds and linea.uds_defecto != p[CAMPO_UDS]:
                vals[CAMPO_UDS] = linea.uds_defecto
            if linea.ficha != p.ficha_tecnica or linea.ficha_nombre != p.ficha_tecnica_nombre:
                vals['ficha_tecnica'] = linea.ficha
                vals['ficha_tecnica_nombre'] = linea.ficha_nombre
            if linea.revisado and not p.catalogo_revisado:
                vals.update({'catalogo_revisado': True, 'catalogo_revisado_fecha': ahora,
                             'catalogo_revisado_uid': self.env.uid})
            elif not linea.revisado and p.catalogo_revisado:
                vals.update({'catalogo_revisado': False, 'catalogo_revisado_fecha': False,
                             'catalogo_revisado_uid': False})
            elif linea.revisado and vals:
                # Ya estaba revisado y se ha corregido algo: queda constancia de quién y cuándo
                vals.update({'catalogo_revisado_fecha': ahora, 'catalogo_revisado_uid': self.env.uid})
            if vals:
                p.write(vals)
        return {'type': 'ir.actions.act_window_close'}


class CatalogoCompletarLinea(models.TransientModel):
    _name = 'dji.catalogo.completar.linea'
    _description = 'Artículo a completar para el catálogo'

    asistente_id = fields.Many2one('dji.catalogo.completar', required=True, ondelete='cascade')
    product_tmpl_id = fields.Many2one('product.template', string='Artículo', required=True, readonly=True)
    referencia = fields.Char(related='product_tmpl_id.default_code', string='Ref.')
    nombre = fields.Char(string='Descripción')
    imagen = fields.Image(string='Foto', max_width=1920, max_height=1920)
    imagen_original = fields.Image(string='Foto original', max_width=1920, max_height=1920)
    tag_ids = fields.Many2many(
        'product.tag', 'dji_catalogo_completar_linea_tag_rel', 'linea_id', 'tag_id', string='Etiquetas',
    )
    uds_defecto = fields.Float(string='Uds. por defecto', digits='Product Unit')
    ficha = fields.Binary(string='Ficha técnica (PDF)')
    ficha_nombre = fields.Char(string='Nombre del archivo')
    ya_revisado = fields.Boolean(string='Ya estaba revisado', readonly=True)
    revisado = fields.Boolean(string='Revisado')
    tiene_uds = fields.Boolean(related='asistente_id.tiene_uds')

    def action_fondo_blanco(self):
        for linea in self:
            nueva = self.env['dji.catalogo.photoroom'].fondo_blanco(linea.imagen)
            vals = {'imagen': nueva}
            if not linea.imagen_original:
                vals['imagen_original'] = linea.imagen
            linea.write(vals)
        return self.asistente_id._reabrir()

    def action_restaurar_foto(self):
        for linea in self.filtered('imagen_original'):
            linea.write({'imagen': linea.imagen_original, 'imagen_original': False})
        return self.asistente_id._reabrir()
