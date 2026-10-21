{
    'name': 'DJI · Catálogo de artículos',
    'version': '19.0.1.3.0',
    'summary': 'Completar etiquetas, foto y ficha técnica de los artículos al recibir la mercancía',
    'description': """
Al recibir mercancía, administración completa los artículos del albarán:
etiquetas de catálogo (postre, sin gluten, solo congelar…), foto, ficha
técnica en PDF y unidades por defecto, y los marca como "Revisado para
catálogo". Copiloto solo usa los artículos revisados para generar los
catálogos a medida.
    """,
    'author': 'DJI',
    'category': 'Inventory/Inventory',
    'license': 'LGPL-3',
    'depends': ['stock', 'purchase_stock'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/completar_articulos_views.xml',
        'views/product_template_views.xml',
        'views/product_tag_views.xml',
        'views/stock_picking_views.xml',
        'views/menus.xml',
        'data/grupos.xml',
    ],
    'installable': True,
    'application': False,
}
