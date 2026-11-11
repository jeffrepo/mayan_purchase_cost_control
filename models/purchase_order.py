from odoo import api, fields, models

from .purchase_order_line import ORDER_BATCH, REQUEST_GENERATION


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _mayan_lock_cost_control(self):
        if not self:
            return
        self.check_access("write")
        self.flush_recordset()
        self.env.cr.execute("SELECT id FROM purchase_order WHERE id IN %s ORDER BY id FOR UPDATE", [tuple(self.ids)])

    def _mayan_validate_cost_control(self, allow_pending=False):
        self.order_line._mayan_check_request()
        if not allow_pending:
            self.order_line._mayan_check_justification()

    @api.model_create_multi
    def create(self, vals_list):
        batch = self.with_context(_mayan_order_batch=ORDER_BATCH)
        orders = super(PurchaseOrder, batch).create(vals_list).with_env(self.env)
        generated = self.env.context.get("_mayan_request_generation") is REQUEST_GENERATION
        orders._mayan_validate_cost_control(allow_pending=generated)
        confirmed = orders.filtered(lambda order: order.state in ("purchase", "done", "to approve"))
        confirmed._mayan_validate_cost_control()
        confirmed.order_line._mayan_set_snapshot()
        return orders

    def write(self, vals):
        relevant = {"order_line", "purchase_request_id", "company_id", "currency_id", "date_order", "partner_id", "state"}
        if not relevant & vals.keys():
            return super().write(vals)
        self._mayan_lock_cost_control()
        # Changing currency/date/company invalidates the monetary reference and its reason.
        changed = self.filtered(lambda order: any(
            key in vals and (fields.Datetime.to_datetime(vals[key]) if key == "date_order" else vals[key])
            != (order[key].id if order._fields[key].type == "many2one" else order[key])
            for key in ("company_id", "currency_id", "date_order")
        ))
        batch = self.with_context(_mayan_order_batch=ORDER_BATCH)
        if changed:
            changed.order_line._mayan_clear_snapshot()
            changed.order_line.with_context(_mayan_order_batch=ORDER_BATCH).write({"mayan_cost_justification": False})
        result = super(PurchaseOrder, batch).write(vals)
        # Cancellation is always available, including an incomplete generated quotation.
        active = self.filtered(lambda order: order.state != "cancel")
        active._mayan_validate_cost_control()
        active.filtered(lambda order: order.state in ("purchase", "done")).order_line._mayan_set_snapshot()
        return result

    def button_confirm(self):
        self._mayan_lock_cost_control()
        self._mayan_validate_cost_control()
        return super().button_confirm()

    def button_approve(self, force=False):
        self._mayan_lock_cost_control()
        self._mayan_validate_cost_control()
        return super().button_approve(force=force)

    def action_add_from_catalog(self):
        self._mayan_validate_cost_control()
        return super().action_add_from_catalog()
