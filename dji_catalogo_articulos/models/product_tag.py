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

    complementaria_ids = fields.Many2many(
        'product.tag', 'dji_tag_complementaria_rel', 'tag_id', 'complementaria_id',
        string='Complementarias',
        help='Familias que se ofrecen junto a esta en el catálogo de Copiloto, '
             'p. ej. Hamburguesas → Pan de hamburguesa, Salsas. El vínculo es de ida y vuelta.',
    )

    def _sincronizar_complementarias(self, antes):
        """Mantiene el vínculo de ida y vuelta: si Hamburguesas lleva Salsas,
        Salsas lleva Hamburguesas; y si se quita de un lado, se quita del otro."""
        if self.env.context.get('dji_sin_espejo'):
            return
        espejo = self.with_context(dji_sin_espejo=True)
        for tag in espejo:
            ahora = tag.complementaria_ids
            previas = antes.get(tag.id, self.browse())
            for nueva in ahora - previas:
                if tag not in nueva.complementaria_ids:
                    nueva.complementaria_ids = [(4, tag.id)]
            for quitada in previas - ahora:
                if tag in quitada.complementaria_ids:
                    quitada.complementaria_ids = [(3, tag.id)]

    def write(self, vals):
        if 'complementaria_ids' not in vals or self.env.context.get('dji_sin_espejo'):
            return super().write(vals)
        antes = {t.id: t.complementaria_ids for t in self}
        res = super().write(vals)
        self._sincronizar_complementarias(antes)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        # Al crear una etiqueta desde un apartado (p. ej. "Origen"), queda en ese grupo
        codigo = self.env.context.get('dji_grupo_codigo')
        if codigo and codigo != 'otras':
            grupo = self.env['dji.catalogo.grupo'].search([('codigo', '=', codigo)], limit=1)
            for vals in vals_list:
                if grupo and not vals.get('grupo_id'):
                    vals['grupo_id'] = grupo.id
        tags = super().create(vals_list)
        tags.filtered('complementaria_ids')._sincronizar_complementarias({})
        return tags

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
