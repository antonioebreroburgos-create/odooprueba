# -*- coding: utf-8 -*-
{
    'name': 'DJI Planificador de Rutas',
    'version': '19.0.1.3.1',
    'summary': 'Planificador visual de rutas y días de reparto para pedidos de venta',
    'author': 'DJI',
    'category': 'Sales',
    'depends': ['sale_management', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/planificador_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dji_planificador_rutas/static/src/css/planificador.css',
            'dji_planificador_rutas/static/src/js/planificador.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
