{
    'name': 'DJI - Devoluciones masivas',
    'version': '19.0.1.4.0',
    'summary': 'Devoluciones masivas de clientes (hoteles) repartidas automáticamente contra las ventas originales',
    'description': """
Presupuesto con etiqueta DEVOLUCION como documento de entrada:
- Calcula contra qué ventas/albaranes devolver cada producto en el mínimo número de ventas.
- Genera y valida las devoluciones de albarán (actualiza stock y cantidades entregadas).
- Genera las facturas rectificativas en borrador enlazadas a las líneas de venta y a la factura original.
""",
    'author': 'DJI',
    'category': 'Sales',
    'license': 'LGPL-3',
    'depends': ['sale_stock', 'stock_account', 'xtendoo_sale_order_tag'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
}
