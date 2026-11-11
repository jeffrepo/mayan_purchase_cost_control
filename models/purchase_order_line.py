import math

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


# Identity-based capabilities are never accepted from JSON/RPC context values.
ORDER_BATCH = object()
REQUEST_GENERATION = object()
INTERNAL_FIELDS = {
    "mayan_cost_snapshot", "mayan_cost_snapshot_set",
    "mayan_justified_by", "mayan_justified_at",
}
PRICE_FIELDS = {"product_id", "product_uom", "price_unit", "discount", "taxes_id", "order_id"}
CHECK_FIELDS = PRICE_FIELDS | {"product_qty", "mayan_cost_justification", "mayan_request_line_id"}


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    mayan_average_cost = fields.Float(
        string="Costo promedio / referencia", digits="Product Price", compute="_compute_mayan_cost",
        help="Costo del producto en la compañía, convertido a la moneda y unidad de la orden. "
             "Es costo promedio cuando la categoría usa AVCO. Se conserva al confirmar.",
    )
    mayan_net_unit_price = fields.Float(
        string="Precio neto sin impuestos", digits="Product Price", compute="_compute_mayan_cost",
    )
    mayan_cost_difference = fields.Float(
        string="Diferencia unitaria", digits="Product Price", compute="_compute_mayan_cost",
    )
    mayan_cost_variation = fields.Float(
        string="Variación (%)", digits=(16, 4), compute="_compute_mayan_cost",
    )
    mayan_cost_status = fields.Selection([
        ("within", "Dentro del rango"), ("outside", "Fuera de ±20%"),
        ("no_cost", "Sin costo de referencia"),
    ], string="Control de costo", compute="_compute_mayan_cost")
    mayan_requires_justification = fields.Boolean(compute="_compute_mayan_cost")
    mayan_cost_justification = fields.Text(string="Justificación", copy=False)
    mayan_justified_by = fields.Many2one("res.users", string="Justificado por", readonly=True, copy=False)
    mayan_justified_at = fields.Datetime(string="Fecha de justificación", readonly=True, copy=False)
    mayan_cost_snapshot = fields.Float(readonly=True, copy=False)
    mayan_cost_snapshot_set = fields.Boolean(readonly=True, copy=False)
    mayan_request_line_id = fields.Many2one(
        "purchase.request.line", string="Línea de solicitud", copy=False,
        ondelete="restrict", check_company=True,
        help="Producto de la solicitud que origina esta línea de compra.",
    )

    def _mayan_cost_values(self):
        self.ensure_one()
        if self.display_type or not self.product_id:
            return 0.0, 0.0, 0.0, 0.0, False
        company = self.order_id.company_id or self.env.company
        currency = self.order_id.currency_id or company.currency_id
        product = self.product_id.with_company(company)
        unit = self.product_uom or product.uom_id
        if unit.category_id != product.uom_id.category_id:
            raise ValidationError(_("La unidad de %(product)s debe ser compatible con la unidad de inventario.",
                                    product=product.display_name))
        if self.mayan_cost_snapshot_set:
            cost = self.mayan_cost_snapshot
        else:
            cost = product.uom_id._compute_price(product.standard_price, unit)
            cost = company.currency_id._convert(
                cost, currency, company,
                fields.Date.to_date(self.order_id.date_order) or fields.Date.context_today(self),
                round=False,
            )
        base_line = self._prepare_base_line_for_taxes_computation()
        base_line["quantity"] = 1.0
        self.env["account.tax"]._add_tax_details_in_base_line(base_line, company, rounding_method="round_globally")
        net = base_line["tax_details"]["raw_total_excluded_currency"]
        if not math.isfinite(cost) or not math.isfinite(net):
            raise ValidationError(_("El costo y el precio de compra deben ser números finitos."))
        difference = net - cost
        variation = difference / cost * 100 if cost > 0 else 0.0
        status = "no_cost" if cost <= 0 else (
            "outside" if float_compare(abs(variation), 20.0, precision_digits=6) > 0 else "within"
        )
        return cost, net, difference, variation, status

    @api.depends(
        "product_id", "product_id.standard_price", "product_uom", "price_unit", "discount", "taxes_id",
        "display_type", "is_downpayment", "order_id.currency_id", "order_id.company_id", "order_id.date_order",
        "mayan_cost_snapshot", "mayan_cost_snapshot_set",
    )
    @api.depends_context("company")
    def _compute_mayan_cost(self):
        for line in self:
            cost, net, difference, variation, status = line._mayan_cost_values()
            line.mayan_average_cost = cost
            line.mayan_net_unit_price = net
            line.mayan_cost_difference = difference
            line.mayan_cost_variation = variation
            line.mayan_cost_status = status
            line.mayan_requires_justification = status in ("outside", "no_cost")

    def _mayan_missing_justification(self):
        # Calculate from business inputs; client-supplied computed values cannot bypass this.
        return self.filtered(lambda line: line._mayan_cost_values()[4] in ("outside", "no_cost")
                             and not (line.mayan_cost_justification or "").strip())

    def _mayan_check_justification(self):
        missing = self._mayan_missing_justification()
        if missing:
            raise ValidationError(_(
                "Completa la justificación de los productos fuera de ±20%% o sin costo de referencia "
                "antes de agregar productos, guardar cambios o confirmar: %s.",
                ", ".join(missing.product_id.mapped("display_name")),
            ))

    def _mayan_check_request(self):
        for line in self.filtered(lambda item: item.product_id and not item.display_type):
            order = line.order_id
            request = order.purchase_request_id
            source = line.mayan_request_line_id
            required = line.product_id.categ_id._mayan_requires_request(order.company_id)
            if required and not request:
                raise ValidationError(_(
                    "%(product)s requiere solicitud de compra. Genera la orden desde la solicitud; "
                    "no se permite guardar una compra manual de esta categoría.", product=line.product_id.display_name,
                ))
            if request and (request.company_id != order.company_id or request.state == "cancelled"):
                raise ValidationError(_("La solicitud debe ser de la misma compañía y no estar cancelada."))
            # Old orders without a line link remain valid when the header's request
            # contains a matching purchase product/vendor. Never invent a historical link.
            candidates = source or request.line_ids.filtered(lambda item:
                item.request_type == "purchase" and item.product_id == line.product_id
                and item.vendor_id == order.partner_id and item.qty_requested > 0
            )
            if source and (
                source.request_id != request or source.request_type != "purchase"
                or source.product_id != line.product_id or source.vendor_id != order.partner_id
                or source.qty_requested <= 0
            ):
                raise ValidationError(_("La línea de solicitud no corresponde a este producto, proveedor y solicitud."))
            if required and not candidates:
                raise ValidationError(_("El producto %s no está solicitado para este proveedor.", line.product_id.display_name))

    def _mayan_set_snapshot(self):
        for line in self.filtered(lambda item: item.product_id and not item.display_type and not item.mayan_cost_snapshot_set):
            super(PurchaseOrderLine, line).write({
                "mayan_cost_snapshot": line._mayan_cost_values()[0], "mayan_cost_snapshot_set": True,
            })

    def _mayan_clear_snapshot(self):
        super(PurchaseOrderLine, self).write({"mayan_cost_snapshot_set": False, "mayan_cost_snapshot": 0})

    def _mayan_audit_justification(self):
        for line in self.filtered(lambda item: item.product_id and not item.display_type):
            reason = (line.mayan_cost_justification or "").strip()
            super(PurchaseOrderLine, line).write({
                "mayan_justified_by": self.env.uid if reason else False,
                "mayan_justified_at": fields.Datetime.now() if reason else False,
            })
            cost, net, difference, variation, status = line._mayan_cost_values()
            line.order_id.message_post(body=Markup("<p><strong>%s</strong></p><p>%s</p><p>%s</p><p>%s</p>") % (
                _("Justificación de variación de costo"), line.product_id.display_name,
                _("Costo: %(cost).6f; precio neto: %(net).6f; diferencia: %(difference).6f; "
                  "variación: %(variation)s. Moneda: %(currency)s; unidad: %(unit)s.",
                  cost=cost, net=net, difference=difference,
                  variation=_("No calculable") if status == "no_cost" else "%.6f%%" % variation,
                  currency=line.currency_id.name, unit=line.product_uom.display_name),
                reason or _("Justificación retirada; debe completarse si corresponde."),
            ), subtype_xmlid="mail.mt_note")

    @api.onchange("product_id", "product_uom", "price_unit", "discount", "taxes_id")
    def _onchange_mayan_cost_inputs(self):
        for line in self:
            if line._origin and line.mayan_cost_justification:
                line.mayan_cost_justification = False

    @api.model_create_multi
    def create(self, vals_list):
        if any(INTERNAL_FIELDS & vals.keys() for vals in vals_list):
            raise ValidationError(_("Los datos de auditoría del costo se asignan automáticamente."))
        vals_list = [dict(vals, mayan_cost_snapshot=0, mayan_cost_snapshot_set=False,
                          mayan_justified_by=False, mayan_justified_at=False) for vals in vals_list]
        batched = self.env.context.get("_mayan_order_batch") is ORDER_BATCH
        if not batched:
            orders = self.env["purchase.order"].browse({
                vals.get("order_id") or self.env.context.get("default_order_id")
                for vals in vals_list if vals.get("order_id") or self.env.context.get("default_order_id")
            })
            orders._mayan_lock_cost_control()
            orders.order_line._mayan_check_justification()
        lines = super().create(vals_list)
        if not batched:
            lines._mayan_check_request()
            lines._mayan_check_justification()
            lines.filtered(lambda line: line.order_id.state in ("purchase", "done"))._mayan_set_snapshot()
        lines.filtered("mayan_cost_justification")._mayan_audit_justification()
        return lines

    def write(self, vals):
        if INTERNAL_FIELDS & vals.keys():
            raise ValidationError(_("Los datos de auditoría del costo se asignan automáticamente."))
        if not CHECK_FIELDS & vals.keys():
            return super().write(vals)
        if self.env.context.get("_mayan_order_batch") is not ORDER_BATCH:
            (self.order_id | self.env["purchase.order"].browse(vals.get("order_id")))._mayan_lock_cost_control()
        for line in self:
            values = dict(vals)
            # Compare the actual result, including M2M tax commands, before invalidating a reason.
            before = (line.product_id.id, line.product_uom.id, line.price_unit,
                      line.discount, frozenset(line.taxes_id.ids), line.order_id.id)
            old_reason = line.mayan_cost_justification
            super(PurchaseOrderLine, line).write(values)
            after = (line.product_id.id, line.product_uom.id, line.price_unit,
                     line.discount, frozenset(line.taxes_id.ids), line.order_id.id)
            if before != after and "mayan_cost_justification" not in values:
                super(PurchaseOrderLine, line).write({"mayan_cost_justification": False})
            if before[:2] != after[:2] or before[-1] != after[-1]:
                line._mayan_clear_snapshot()
            if self.env.context.get("_mayan_order_batch") is not ORDER_BATCH:
                line._mayan_check_request()
                line._mayan_check_justification()
                if line.order_id.state in ("purchase", "done"):
                    line._mayan_set_snapshot()
            if old_reason != line.mayan_cost_justification or (
                before != after and line.mayan_cost_justification
            ):
                line._mayan_audit_justification()
        return True
