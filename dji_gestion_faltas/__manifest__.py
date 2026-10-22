{
    "name": "DJI Gestión de Faltas",
    "summary": """Pasa las faltas de un presupuesto a un presupuesto FALTAS y avisa al comercial""",
    "version": "19.0.1.0.6",
    "author": "DJI",
    "company": "Distribuciones Joaquín Infante",
    "category": "Sales",
    "depends": [
        "sale",
        "xtendoo_sale_order_tag",
    ],
    "license": "AGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "wizard/dji_faltas_wizard_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
