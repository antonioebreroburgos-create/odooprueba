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

    grupo = fields.Char(
        string='Grupo',
        help='Opcional. Agrupa las etiquetas en el catálogo: Tipo, Dieta, Conservación, Uso…',
    )

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
