from odoo import fields, models


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
