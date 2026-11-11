{
    "name": "Mayan - Control de costos de compra",
    "summary": "Variación de costos, justificación por línea y solicitudes obligatorias",
    "version": "18.0.1.0.0",
    "category": "Inventory/Purchase",
    "author": "Mayan Golf Club",
    "website": "https://github.com/jeffrepo/mayan_purchase_cost_control",
    "license": "LGPL-3",
    "depends": ["purchase_stock", "purchase_request_app"],
    "data": ["views/product_category_views.xml", "views/purchase_order_views.xml"],
    "assets": {
        "web.assets_backend": ["mayan_purchase_cost_control/static/src/js/cost_order_lines.js"],
        "web.assets_tests": ["mayan_purchase_cost_control/static/tests/tours/cost_control.js"],
    },
    "application": True,
    "installable": True,
}
