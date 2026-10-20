{
    'name': 'DJI · Albarán de entrega',
    'version': '19.0.1.3.0',
    'summary': 'Albarán de entrega con el diseño corporativo de DJI (sustituye al de serie)',
    'description': 'Albarán de entrega rediseñado para Distribuciones Joaquín Infante: número del traslado de salida (ALB/OUT), lote y caducidad por línea, precios del pedido, comercial, observaciones y recibí conforme. Opción por cliente de albarán sin precios.',
    'author': 'DJI',
    'category': 'Inventory/Inventory',
    'license': 'LGPL-3',
    'depends': ['stock', 'sale_stock'],
    'data': [
        'views/res_partner_views.xml',
        'report/paperformat.xml',
        'report/albaran_templates.xml',
        'report/albaran_action.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'dji_albaran/static/src/scss/albaran.scss',
        ],
    },
    'installable': True,
    'application': False,
}
