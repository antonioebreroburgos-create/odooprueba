{
    "name": "DJI Registro de Entrega",
    "summary": "Fotos de carga y entrega con análisis IA vinculadas al albarán",
    "version": "19.0.1.0.0",
    "author": "DJI",
    "company": "Distribuciones Joaquín Infante",
    "category": "Inventory",
    "depends": [
        "stock",
        "sale_stock",
    ],
    "license": "AGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/stock_picking_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "dji_registro_entrega/static/src/css/registro_entrega.css",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
