from odoo import api, fields, models

from ..models.catalogo_campos import APARTADOS, dominio_grupo, es_del_grupo

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
                **{f'tags_{c}': [(6, 0, p.product_tag_ids.filtered(lambda t, c=c: es_del_grupo(t, c)).ids)]
                   for c in APARTADOS},
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


# Tablas de las etiquetas de cada línea del asistente
TABLAS_ETIQUETAS = [f'dji_catalogo_linea_{c}_rel' for c in (
    'producto', 'momento', 'origen', 'preparacion', 'conservacion', 'alergenos', 'caracteristicas', 'calidad', 'otras')]


class CatalogoCompletarLinea(models.TransientModel):
    _name = 'dji.catalogo.completar.linea'
    _description = 'Artículo a completar para el catálogo'

    def init(self):
        """Las tablas de etiquetas de las líneas tienen que borrarse en cascada con la línea.
        Si alguna se creó sin "ON DELETE CASCADE" (pasó con la de Producto al añadirla en la
        19.0.1.3.0), al guardar el asistente Odoo no podía borrar las líneas y salía
        "Another model is using the record… dji_catalogo_linea_producto_rel_linea_id_fkey".
        Aquí se rehacen las claves con borrado en cascada (y se limpian filas huérfanas)."""
        cr = self.env.cr
        for tabla in TABLAS_ETIQUETAS:
            cr.execute("SELECT to_regclass(%s)", (tabla,))
            if not cr.fetchone()[0]:
                continue
            cr.execute(f'DELETE FROM "{tabla}" WHERE linea_id NOT IN (SELECT id FROM "{self._table}") '
                       f'OR tag_id NOT IN (SELECT id FROM product_tag)')
            for columna, destino in (('linea_id', self._table), ('tag_id', 'product_tag')):
                cr.execute("""
                    SELECT c.conname, c.confdeltype
                      FROM pg_constraint c
                      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
                     WHERE c.conrelid = %s::regclass AND c.contype = 'f' AND a.attname = %s
                """, (tabla, columna))
                claves = cr.fetchall()
                if claves and all(tipo == 'c' for _, tipo in claves):
                    continue  # ya borra en cascada
                for nombre, _tipo in claves:
                    cr.execute(f'ALTER TABLE "{tabla}" DROP CONSTRAINT "{nombre}"')
                cr.execute(f'ALTER TABLE "{tabla}" ADD CONSTRAINT "{tabla}_{columna}_fkey" '
                           f'FOREIGN KEY ("{columna}") REFERENCES "{destino}" (id) ON DELETE CASCADE')

    asistente_id = fields.Many2one('dji.catalogo.completar', required=True, ondelete='cascade')
    product_tmpl_id = fields.Many2one('product.template', string='Artículo', required=True, readonly=True)
    referencia = fields.Char(related='product_tmpl_id.default_code', string='Ref.')
    nombre = fields.Char(string='Descripción')
    imagen = fields.Image(string='Foto', max_width=1920, max_height=1920)
    imagen_original = fields.Image(string='Foto original', max_width=1920, max_height=1920)
    tags_producto = fields.Many2many(
        'product.tag', 'dji_catalogo_linea_producto_rel', 'linea_id', 'tag_id',
        string='Producto', domain=dominio_grupo('producto'),
    )
    tags_momento = fields.Many2many(
        'product.tag', 'dji_catalogo_linea_momento_rel', 'linea_id', 'tag_id',
        string='Momento', domain=dominio_grupo('momento'),
    )
    tags_origen = fields.Many2many(
        'product.tag', 'dji_catalogo_linea_origen_rel', 'linea_id', 'tag_id',
        string='Origen', domain=dominio_grupo('origen'),
    )
    tags_preparacion = fields.Many2many(
        'product.tag', 'dji_catalogo_linea_preparacion_rel', 'linea_id', 'tag_id',
        string='Preparación', domain=dominio_grupo('preparacion'),
    )
    tags_conservacion = fields.Many2many(
        'product.tag', 'dji_catalogo_linea_conservacion_rel', 'linea_id', 'tag_id',
        string='Conservación', domain=dominio_grupo('conservacion'),
    )
    tags_alergenos = fields.Many2many(
        'product.tag', 'dji_catalogo_linea_alergenos_rel', 'linea_id', 'tag_id',
        string='Alérgenos', domain=dominio_grupo('alergenos'),
    )
    tags_caracteristicas = fields.Many2many(
        'product.tag', 'dji_catalogo_linea_caracteristicas_rel', 'linea_id', 'tag_id',
        string='Características', domain=dominio_grupo('caracteristicas'),
    )
    tags_calidad = fields.Many2many(
        'product.tag', 'dji_catalogo_linea_calidad_rel', 'linea_id', 'tag_id',
        string='Calidad', domain=dominio_grupo('calidad'),
    )
    tags_otras = fields.Many2many(
        'product.tag', 'dji_catalogo_linea_otras_rel', 'linea_id', 'tag_id',
        string='Otras etiquetas', domain=dominio_grupo('otras'),
    )
    tag_ids = fields.Many2many(
        'product.tag', string='Etiquetas', compute='_compute_tag_ids',
        help='Todas las etiquetas del artículo, de todos los grupos.',
    )

    @api.depends(*[f'tags_{c}' for c in APARTADOS])
    def _compute_tag_ids(self):
        for linea in self:
            todas = self.env['product.tag']
            for c in APARTADOS:
                todas |= linea[f'tags_{c}']
            linea.tag_ids = todas
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
