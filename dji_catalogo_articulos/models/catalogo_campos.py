"""Un apartado de etiquetas por grupo (Momento, Origen, Preparación…) en la
ficha del artículo y en el asistente "Completar artículos". Las etiquetas de
grupos creados después a mano, o sin grupo, van al apartado "Otras"."""
from .catalogo_grupo import CODIGOS


def dominio_grupo(codigo):
    if codigo == 'otras':
        return ['|', ('grupo_id', '=', False), ('grupo_id.codigo', 'not in', CODIGOS)]
    return [('grupo_id.codigo', '=', codigo)]


def es_del_grupo(tag, codigo):
    if codigo == 'otras':
        return not tag.grupo_id or tag.grupo_id.codigo not in CODIGOS
    return tag.grupo_id.codigo == codigo


APARTADOS = CODIGOS + ['otras']
