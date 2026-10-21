from odoo import api, fields, models

from .product_tag import normalizar

# Grupos de partida con sus etiquetas. Se cargan una sola vez; después se
# gestionan desde Inventario → Catálogo → Grupos / Etiquetas.
GRUPOS = [
    ('producto', 'Producto', ['Hamburguesas', 'Pan de hamburguesa', 'Salsas', 'Patatas fritas',
                              'Croquetas', 'Canelones', 'Lasaña', 'Pizzas', 'Rebozados']),
    ('momento', 'Momento', ['Desayunos', 'Aperitivos', 'Comidas', 'Postres', 'Eventos/catering']),
    ('origen', 'Origen', ['Cerdo', 'Ternera', 'Pollo', 'Pavo', 'Pato', 'Cordero', 'Salmón', 'Atún', 'Marisco', 'Vegetal']),
    ('preparacion', 'Preparación', ['Horno', 'Freidora', 'Plancha', 'Microondas', 'Solo descongelar', 'Listo para servir']),
    ('conservacion', 'Conservación', ['Congelado', 'Refrigerado', 'Ambiente']),
    ('alergenos', 'Alérgenos', ['Sin gluten', 'Sin lactosa', 'Sin huevo', 'Sin frutos secos']),
    ('caracteristicas', 'Características', ['Vegano', 'Vegetariano', 'Halal', 'Ecológico']),
    ('calidad', 'Calidad', ['Ibérico', 'Bellota', 'DOP', 'Artesano', 'Gourmet']),
]
CODIGOS = [g[0] for g in GRUPOS]
# Orden en pantalla (Producto va el primero aunque se añadiera después)
SECUENCIA = {codigo: (i + 1) * 10 for i, codigo in enumerate(CODIGOS)}
# Complementarias de partida (de ida y vuelta)
COMPLEMENTARIAS = [
    ('Hamburguesas', ['Pan de hamburguesa', 'Salsas', 'Patatas fritas']),
]


class CatalogoGrupo(models.Model):
    _name = 'dji.catalogo.grupo'
    _description = 'Grupo de etiquetas de catálogo'
    _order = 'sequence, id'

    name = fields.Char(string='Grupo', required=True, translate=False)
    codigo = fields.Char(string='Código', readonly=True, copy=False,
                         help='Interno. Los grupos de partida tienen su propio apartado en la ficha.')
    sequence = fields.Integer(default=10)
    tag_ids = fields.One2many('product.tag', 'grupo_id', string='Etiquetas')
    tag_count = fields.Integer(string='Nº etiquetas', compute='_compute_tag_count')

    _codigo_unico = models.Constraint('unique(codigo)', 'Ya existe un grupo con ese código.')

    def _compute_tag_count(self):
        for grupo in self:
            grupo.tag_count = len(grupo.tag_ids)

    @api.model
    def _cargar_grupos_iniciales(self):
        """Crea los grupos y etiquetas de partida (una sola vez). Si ya existe una
        etiqueta con el mismo nombre (sin mirar mayúsculas ni tildes), se le
        asigna el grupo en vez de crear otra."""
        param = self.env['ir.config_parameter'].sudo()
        cargados = param.get_param('dji_catalogo.grupos_cargados') or ''
        if cargados == '1':  # versión 19.0.1.2.0: se cargaron los 7 primeros grupos
            cargados = ','.join(c for c in CODIGOS if c != 'producto')
        hechos = set(filter(None, cargados.split(',')))
        pendientes = [g for g in GRUPOS if g[0] not in hechos]
        # El orden de pantalla se ajusta siempre (Producto, el primero)
        for grupo in self.search([('codigo', 'in', CODIGOS)]):
            if grupo.sequence != SECUENCIA[grupo.codigo]:
                grupo.sequence = SECUENCIA[grupo.codigo]
        if not pendientes:
            return
        Tag = self.env['product.tag'].with_context(active_test=False)
        todas = {normalizar(t.name): t for t in Tag.search([])}
        for codigo, nombre, etiquetas in pendientes:
            orden = CODIGOS.index(codigo)
            grupo = self.search([('codigo', '=', codigo)], limit=1) or self.create(
                {'name': nombre, 'codigo': codigo, 'sequence': SECUENCIA[codigo]})
            for i, etiqueta in enumerate(etiquetas):
                tag = todas.get(normalizar(etiqueta))
                if tag:
                    if not tag.grupo_id:
                        # p. ej. "cerdo" creada a mano → pasa a "Cerdo", en Origen
                        tag.write({'grupo_id': grupo.id, 'name': etiqueta})
                else:
                    todas[normalizar(etiqueta)] = Tag.create(
                        {'name': etiqueta, 'grupo_id': grupo.id, 'sequence': (orden + 1) * 100 + i})
            hechos.add(codigo)
        if 'producto' in {g[0] for g in pendientes}:
            for principal, otras in COMPLEMENTARIAS:
                tag = todas.get(normalizar(principal))
                comp = Tag.browse([todas[normalizar(o)].id for o in otras if normalizar(o) in todas])
                if tag and comp:
                    tag.complementaria_ids = [(4, c.id) for c in comp]
        param.set_param('dji_catalogo.grupos_cargados', ','.join(c for c in CODIGOS if c in hechos))
