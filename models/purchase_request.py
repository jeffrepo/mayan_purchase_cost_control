from odoo import _, models
from odoo.exceptions import UserError

from .purchase_order_line import REQUEST_GENERATION


class PurchaseRequest(models.Model):
    _inherit = "purchase.request"

    def action_generate_purchase_orders(self):
        if not hasattr(super(PurchaseRequestLine, self.env["purchase.request.line"]), "_prepare_purchase_order_line_values"):
            raise UserError(_("Actualiza purchase_request_app a 18.0.1.6.0 o posterior antes de generar compras."))
        if any(request.state == "cancelled" for request in self):
            raise UserError(_("No se pueden generar compras desde una solicitud cancelada."))
        # Automated generation may produce a draft without reference cost. The
        # buyer must justify it on the order before adding products or confirming.
        return super(PurchaseRequest, self.with_context(_mayan_request_generation=REQUEST_GENERATION)).action_generate_purchase_orders()


class PurchaseRequestLine(models.Model):
    _inherit = "purchase.request.line"

    def _prepare_purchase_order_line_values(self, order):
        values = super()._prepare_purchase_order_line_values(order)
        values["mayan_request_line_id"] = self.id
        return values
