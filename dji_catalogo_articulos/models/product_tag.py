import re
import unicodedata

from odoo import api, fields, models
from odoo.exceptions import ValidationError


def normalizar(texto):
    """'Sin Glutén ' → 'sin gluten' (sin tildes, minúsculas, espacios simples)."""
    texto = unicodedata.normalize('NFD', texto or '')
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', texto).strip().lower()


class ProductTag(models.Model):
    _inherit = 'product.tag'

    grupo_id = fields.Many2one(
        'dji.catalogo.grupo', string='Grupo', index=True, ondelete='set null',
        help='Momento, Origen, Preparación, Conservación, Alérgenos, Características, Calidad…',
    )

    @api.model_create_multi
    def create(self, vals_list):
        # Al crear una etiqueta desde un apartado (p. ej. "Origen"), queda en ese grupo
        codigo = self.env.context.get('dji_grupo_codigo')
        if codigo and codigo != 'otras':
            grupo = self.env['dji.catalogo.grupo'].search([('codigo', '=', codigo)], limit=1)
            for vals in vals_list:
                if grupo and not vals.get('grupo_id'):
                    vals['grupo_id'] = grupo.id
        return super().create(vals_list)

    @api.constrains('name')
    def _check_nombre_duplicado(self):
        """Odoo ya impide dos etiquetas exactamente iguales; esto impide además
        'Sin gluten' / 'SIN GLUTEN' / 'Sin glutén'."""
        todas = self.search([])
        for tag in self:
            clave = normalizar(tag.name)
            otra = todas.filtered(lambda t: t.id != tag.id and normalizar(t.name) == clave)
            if otra:
                raise ValidationError(
                    f'Ya existe la etiqueta "{otra[0].name}". Usa esa en lugar de crear "{tag.name}".'
                )
