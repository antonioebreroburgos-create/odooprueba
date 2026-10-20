{
    'name': 'DJI - Volver a presupuesto',
    'version': '19.0.1.0.0',
    'summary': 'Deshace el picking preparado, cancela la venta y la deja en presupuesto en un clic',
    'author': 'DJI',
    'category': 'Sales',
    'license': 'LGPL-3',
    'depends': ['sale_stock'],
    'data': [
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
        'data/acciones.xml',
    ],
    'installable': True,
}
