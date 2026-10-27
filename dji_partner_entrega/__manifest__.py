# -*- coding: utf-8 -*-
{
    'name': 'DJI - Zona y Días de Servicio',
    'version': '19.0.1.0.0',
    'summary': 'Campos de zona y días de servicio en clientes, avisos en pedidos de venta',
    'author': 'DJI',
    'category': 'Sales',
    'depends': ['sale_management', 'dji_planificador_rutas'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dji_partner_entrega/static/src/css/partner_entrega.css',
            'dji_partner_entrega/static/src/js/sale_order_warnings.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
