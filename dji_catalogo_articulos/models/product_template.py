from odoo import api, fields, models

from .catalogo_campos import APARTADOS, dominio_grupo, es_del_grupo


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    catalogo_revisado = fields.Boolean(
        string='Revisado para catálogo', copy=False, index=True,
        help='Artículo comprobado con la mercancía delante (etiquetas, foto, formato). '
             'Solo los artículos revisados salen en los catálogos de Copiloto.',
    )
    catalogo_revisado_fecha = fields.Datetime(string='Revisado el', copy=False, readonly=True)
    catalogo_revisado_uid = fields.Many2one('res.users', string='Revisado por', copy=False, readonly=True)
    ficha_tecnica = fields.Binary(string='Ficha técnica', attachment=True, copy=False)
    ficha_tecnica_nombre = fields.Char(string='Nombre de la ficha técnica', copy=False)
    imagen_original = fields.Image(
        string='Foto original', copy=False, attachment=True,
        help='La foto tal cual se subió, antes de pasar por "Fondo blanco". Sirve para volver a ella.',
    )

    tags_producto = fields.Many2many(
        'product.tag', string='Producto', domain=dominio_grupo('producto'),
        compute='_compute_tags_grupos', inverse='_inverse_tags_producto',
    )
    tags_momento = fields.Many2many(
        'product.tag', string='Momento', domain=dominio_grupo('momento'),
        compute='_compute_tags_grupos', inverse='_inverse_tags_momento',
    )
    tags_origen = fields.Many2many(
        'product.tag', string='Origen', domain=dominio_grupo('origen'),
        compute='_compute_tags_grupos', inverse='_inverse_tags_origen',
    )
    tags_preparacion = fields.Many2many(
        'product.tag', string='Preparación', domain=dominio_grupo('preparacion'),
        compute='_compute_tags_grupos', inverse='_inverse_tags_preparacion',
    )
    tags_conservacion = fields.Many2many(
        'product.tag', string='Conservación', domain=dominio_grupo('conservacion'),
        compute='_compute_tags_grupos', inverse='_inverse_tags_conservacion',
    )
    tags_alergenos = fields.Many2many(
        'product.tag', string='Alérgenos', domain=dominio_grupo('alergenos'),
        compute='_compute_tags_grupos', inverse='_inverse_tags_alergenos',
    )
    tags_caracteristicas = fields.Many2many(
        'product.tag', string='Características', domain=dominio_grupo('caracteristicas'),
        compute='_compute_tags_grupos', inverse='_inverse_tags_caracteristicas',
    )
    tags_calidad = fields.Many2many(
        'product.tag', string='Calidad', domain=dominio_grupo('calidad'),
        compute='_compute_tags_grupos', inverse='_inverse_tags_calidad',
    )
    tags_otras = fields.Many2many(
        'product.tag', string='Otras etiquetas', domain=dominio_grupo('otras'),
        compute='_compute_tags_grupos', inverse='_inverse_tags_otras',
    )

    @api.depends('product_tag_ids', 'product_tag_ids.grupo_id')
    def _compute_tags_grupos(self):
        for p in self:
            for codigo in APARTADOS:
                p[f'tags_{codigo}'] = p.product_tag_ids.filtered(lambda t, c=codigo: es_del_grupo(t, c))

    def _inverse_tags_grupo(self, codigo):
        for p in self:
            resto = p.product_tag_ids.filtered(lambda t: not es_del_grupo(t, codigo))
            p.product_tag_ids = resto | p[f'tags_{codigo}']

    def _inverse_tags_producto(self):
        self._inverse_tags_grupo('producto')

    def _inverse_tags_momento(self):
        self._inverse_tags_grupo('momento')

    def _inverse_tags_origen(self):
        self._inverse_tags_grupo('origen')

    def _inverse_tags_preparacion(self):
        self._inverse_tags_grupo('preparacion')

    def _inverse_tags_conservacion(self):
        self._inverse_tags_grupo('conservacion')

    def _inverse_tags_alergenos(self):
        self._inverse_tags_grupo('alergenos')

    def _inverse_tags_caracteristicas(self):
        self._inverse_tags_grupo('caracteristicas')

    def _inverse_tags_calidad(self):
        self._inverse_tags_grupo('calidad')

    def _inverse_tags_otras(self):
        self._inverse_tags_grupo('otras')

    def action_foto_fondo_blanco(self):
        for p in self:
            nueva = self.env['dji.catalogo.photoroom'].fondo_blanco(p.image_1920)
            vals = {'image_1920': nueva}
            if not p.imagen_original:
                vals['imagen_original'] = p.image_1920
            p.write(vals)

    def action_foto_restaurar(self):
        for p in self.filtered('imagen_original'):
            p.write({'image_1920': p.imagen_original, 'imagen_original': False})

    def action_catalogo_reabrir(self):
        self.write({'catalogo_revisado': False, 'catalogo_revisado_fecha': False, 'catalogo_revisado_uid': False})
