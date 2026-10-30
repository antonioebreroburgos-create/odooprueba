# -*- coding: utf-8 -*-
{
    'name': 'DJI Sale Order Sort Lines',
    'version': '19.0.1.0.0',
    'summary': 'Botón para ordenar líneas de pedido por producto, precio, margen o importe',
    'author': 'DJI',
    'category': 'Sales',
    'depends': ['sale_management', 'sale_margin'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
