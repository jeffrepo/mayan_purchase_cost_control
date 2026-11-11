from odoo import Command, fields
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCostControlUI(HttpCase):
    def test_no_new_line_until_justification_is_completed(self):
        vendor = self.env["res.partner"].create({"name": "Proveedor prueba UI"})
        product = self.env["product.product"].create({"name": "Producto prueba UI", "standard_price": 10})
        order = self.env["purchase.order"].create({
            "partner_id": vendor.id,
            "order_line": [Command.create({
                "product_id": product.id, "product_uom": product.uom_id.id,
                "product_qty": 1, "price_unit": 10, "discount": 0,
                "taxes_id": [Command.clear()], "date_planned": fields.Datetime.now(),
                "name": product.display_name,
            })],
        })
        self.start_tour(
            "/odoo/purchase/%s" % order.id, "mayan_cost_control_justification", login="admin",
        )
