{
    'name': 'DJI · Comprobación de tarifas de proveedor',
    'summary': 'Comprueba los precios de los pedidos de compra contra la tarifa del proveedor guardada en la app de Tarifas',
    'description': """
Al meter artículos en un pedido de compra, compara el precio con la tarifa vigente del proveedor
(app de Tarifas de Proveedores en Supabase) y marca cada línea como correcta o con precio distinto.
También añade un botón para comprobar todo el pedido y otro para aplicar los precios de tarifa.
Al confirmar el pedido deja una nota en el historial si hay diferencias. No bloquea nada.
""",
    'version': '19.0.1.0.0',
    'category': 'Inventory/Purchase',
    'author': 'DJI',
    'license': 'LGPL-3',
    'depends': ['purchase'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'data/parametros.xml',
        'views/purchase_order_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}
