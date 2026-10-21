{
    'name': 'DJI · Avisos de compras por WhatsApp',
    'version': '19.0.1.1.0',
    'summary': 'Avisa por WhatsApp al proveedor al confirmar una compra y nos informa de todo lo que responda',
    'description': (
        'Al confirmar un pedido de compra se envía un WhatsApp (plantilla con el PDF del pedido y '
        'botones Recibido / No lo he recibido) al número "WhatsApp pedidos" de la ficha del proveedor. '
        'Las respuestas del proveedor (botones, textos y fotos por WhatsApp, y los correos que entran '
        'en el historial del pedido) se anotan en el pedido y se avisan por WhatsApp al comprador. '
        'Si no contesta en 24 horas, se le recuerda. El envío lo hace Copiloto (Netlify + Twilio); '
        'parámetros del sistema: dji_avisos_compras.webhook_url, dji_avisos_compras.webhook_secret '
        'y dji_avisos_compras.empresa (DJI o SYL).'
    ),
    'author': 'DJI',
    'category': 'Inventory/Purchase',
    'license': 'LGPL-3',
    'depends': ['purchase', 'mail'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'data/parametros.xml',
        'data/cron.xml',
        'views/res_partner_views.xml',
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'application': False,
}
