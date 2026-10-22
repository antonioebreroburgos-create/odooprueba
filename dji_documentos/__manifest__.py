{
    'name': 'DJI · Factura, rectificativa, presupuesto y pedido de compra',
    'version': '19.0.1.5.0',
    'summary': 'Facturas, rectificativas, presupuestos y pedidos de compra con el diseño corporativo de DJI',
    'description': 'Misma familia visual que el albarán de DJI (dji_albaran), pero distinguible: '
                   'factura con bloque azul oscuro y líneas agrupadas por albarán, rectificativa en '
                   'naranja con la factura que rectifica, presupuesto en verde con fecha de validez, pedido de compra en morado con la entrega prevista.',
    'author': 'DJI',
    'category': 'Accounting/Accounting',
    'license': 'LGPL-3',
    'depends': ['account', 'sale_stock', 'purchase_stock', 'dji_albaran'],
    'data': [
        'views/res_company_views.xml',
        'report/factura_templates.xml',
        'report/presupuesto_templates.xml',
        'report/compra_templates.xml',
        'report/acciones.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'dji_documentos/static/src/scss/documentos.scss',
        ],
    },
    'installable': True,
    'application': False,
}
