from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestPurchaseCostControl(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.sudo().write({"groups_id": [Command.link(
            cls.env.ref("purchase_request_app.group_purchase_request_user").id,
        )]})
        cls.company = cls.env.company
        cls.company.write({"po_double_validation": "one_step", "po_lock": "edit"})
        cls.category = cls.env["product.category"].create({
            "name": "Alimentos QA", "property_cost_method": "average",
        })
        cls.child = cls.env["product.category"].create({"name": "Bebidas QA", "parent_id": cls.category.id})
        cls.product = cls.env["product.product"].create({
            "name": "Bebida QA", "default_code": "COST-001", "standard_price": 5.5,
            "categ_id": cls.child.id, "type": "consu", "is_storable": True,
            "supplier_taxes_id": [Command.clear()],
        })
        cls.vendor = cls.env["res.partner"].create({"name": "Proveedor costos QA", "supplier_rank": 1})
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        cls.company.write({
            "purchase_request_ab_category_id": cls.category.id,
            "purchase_request_ab_picking_type_id": cls.warehouse.in_type_id.id,
            "purchase_request_supplies_picking_type_id": cls.warehouse.in_type_id.id,
        })

    def _line(self, **values):
        return {
            "product_id": self.product.id, "product_uom": self.product.uom_id.id,
            "product_qty": 2, "price_unit": 5.5, "discount": 0,
            "name": self.product.display_name, "date_planned": fields.Datetime.now(),
            "taxes_id": [Command.clear()], **values,
        }

    def _order(self, line_values=None, **values):
        return self.env["purchase.order"].create({
            "partner_id": self.vendor.id, "company_id": self.company.id,
            "currency_id": self.company.currency_id.id,
            "order_line": [Command.create(self._line(**(line_values or {})))], **values,
        })

    def _request(self, **line_values):
        return self.env["purchase.request"].create({
            "company_id": self.company.id, "category_id": self.category.id,
            "location_id": self.warehouse.lot_stock_id.id,
            "line_ids": [Command.create({
                "product_id": self.product.id, "vendor_id": self.vendor.id,
                "selected_for_action": True, "qty_requested": 2, **line_values,
            })],
        })

    def _tax(self, included=False):
        return self.env["account.tax"].create({
            "name": "IVA incluido QA" if included else "IVA excluido QA",
            "amount": 12, "amount_type": "percent", "type_tax_use": "purchase",
            "company_id": self.company.id,
            "price_include_override": "tax_included" if included else "tax_excluded",
        })

    def test_inclusive_boundaries_and_both_directions(self):
        for price, variation in ((4.4, -20), (5.5, 0), (6.6, 20)):
            with self.subTest(price=price):
                order = self._order({"price_unit": price})
                self.assertAlmostEqual(order.order_line.mayan_cost_variation, variation)
                self.assertFalse(order.order_line.mayan_requires_justification)
                order.button_confirm()
                self.assertEqual(order.state, "purchase")
        for price in (4.39, 6.61):
            with self.subTest(price=price), self.assertRaisesRegex(ValidationError, "COST-001"), self.cr.savepoint():
                self._order({"price_unit": price})

    def test_justified_high_and_low_prices_with_audit(self):
        for price in (4, 7):
            order = self._order({"price_unit": price, "mayan_cost_justification": "Cambio de presentación"})
            line = order.order_line
            self.assertTrue(line.mayan_requires_justification)
            self.assertEqual(line.mayan_justified_by, self.env.user)
            self.assertTrue(line.mayan_justified_at)
            self.assertTrue(order.message_ids.filtered(lambda message: "Cambio de presentación" in str(message.body)))
            order.button_confirm()
            self.assertEqual(order.state, "purchase")

    def test_whitespace_and_zero_reference_need_real_reason(self):
        for reason in (False, "", " \n\t "):
            with self.subTest(reason=reason), self.assertRaises(ValidationError), self.cr.savepoint():
                self._order({"price_unit": 7, "mayan_cost_justification": reason})
        self.product.standard_price = 0
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._order()
        line = self._order({"mayan_cost_justification": "Primera compra; aún no hay costo"}).order_line
        self.assertEqual(line.mayan_cost_status, "no_cost")
        self.assertEqual(line.mayan_cost_variation, 0)

    def test_tax_included_excluded_and_discount_compare_net(self):
        for included, price in ((False, 6.6), (True, 7.392)):
            tax = self._tax(included)
            line = self._order({"price_unit": price, "taxes_id": [Command.set(tax.ids)]}).order_line
            self.assertAlmostEqual(line.mayan_net_unit_price, 6.6)
            self.assertAlmostEqual(line.mayan_cost_variation, 20)
        line = self._order({"price_unit": 11, "discount": 50}).order_line
        self.assertAlmostEqual(line.mayan_cost_variation, 0)
        self.assertAlmostEqual(line.mayan_net_unit_price, 5.5)

    def test_units_and_currency_use_same_basis(self):
        dozen = self.env.ref("uom.product_uom_dozen")
        line = self._order({"product_uom": dozen.id, "price_unit": 79.2}).order_line
        self.assertAlmostEqual(line.mayan_average_cost, 66)
        self.assertAlmostEqual(line.mayan_cost_variation, 20)
        currency = self.env["res.currency"].create({"name": "MQA", "symbol": "M", "rounding": 0.01})
        self.env["res.currency.rate"].create({
            "currency_id": currency.id, "company_id": self.company.id, "name": "2026-01-01", "rate": 2,
        })
        expected = self.company.currency_id._convert(5.5, currency, self.company, fields.Date.to_date("2026-06-01"), round=False)
        line = self._order({"price_unit": expected}, currency_id=currency.id, date_order="2026-06-01 12:00:00").order_line
        self.assertAlmostEqual(line.mayan_average_cost, expected)
        self.assertAlmostEqual(line.mayan_cost_variation, 0)

    def test_draft_rechecks_current_cost_and_confirmation_freezes_reference(self):
        order = self._order()
        self.product.standard_price = 4
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.button_confirm()
        order.order_line.mayan_cost_justification = "Costo actualizado; proveedor mantiene precio"
        order.button_confirm()
        line = order.order_line
        self.assertEqual(line.mayan_cost_snapshot, 4)
        self.product.standard_price = 20
        line.invalidate_recordset()
        self.assertEqual(line.mayan_average_cost, 4)
        self.assertAlmostEqual(line.mayan_cost_variation, 37.5)

    def test_receipt_does_not_reprice_historical_comparison(self):
        self.product.categ_id = self.category
        order = self._order({"price_unit": 6.6})
        order.button_confirm()
        picking = order.picking_ids
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        self.assertEqual(order.order_line.mayan_average_cost, 5.5)
        self.assertAlmostEqual(order.order_line.mayan_cost_variation, 20)

    def test_price_change_requires_fresh_justification_even_after_confirmation(self):
        order = self._order({"price_unit": 7, "mayan_cost_justification": "Proveedor único"})
        order.button_confirm()
        line = order.order_line
        with self.assertRaises(ValidationError), self.cr.savepoint():
            line.price_unit = 8
        line.write({"price_unit": 8, "mayan_cost_justification": "Nuevo precio cotizado; compra urgente"})
        self.assertEqual(line.mayan_cost_snapshot, 5.5)
        self.assertEqual(line.mayan_cost_justification, "Nuevo precio cotizado; compra urgente")
        # Odoo can reapply the supplier tariff when quantity changes. That is
        # a real price change and must not silently reuse the previous reason.
        with self.assertRaises(ValidationError), self.cr.savepoint():
            line.product_qty = 3
        line.write({"product_qty": 3, "price_unit": line.price_unit, "discount": line.discount})
        self.assertEqual(line.mayan_cost_justification, "Nuevo precio cotizado; compra urgente")

    def test_server_guards_direct_create_write_state_and_context(self):
        order = self._order()
        for operation in (
            lambda: order.order_line.write({"price_unit": 7}),
            lambda: order.write({"order_line": [Command.create(self._line(price_unit=7))]}),
            lambda: self.env["purchase.order.line"].create(self._line(order_id=order.id, price_unit=7)),
            lambda: order.order_line.with_context(_mayan_order_batch=True).write({"price_unit": 7}),
            lambda: self.env["purchase.order"].with_context(_mayan_request_generation=True).create({
                "partner_id": self.vendor.id, "order_line": [Command.create(self._line(price_unit=7))],
            }),
            lambda: order.order_line.write({"mayan_cost_snapshot": 7, "mayan_cost_snapshot_set": True}),
        ):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                operation()
        self.product.standard_price = 3
        for operation in (lambda: order.write({"state": "purchase"}), order.button_approve):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                operation()

    def test_default_context_and_downpayment_flag_cannot_skip_cost_check(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["purchase.order.line"].with_context(
                default_mayan_cost_snapshot=7, default_mayan_cost_snapshot_set=True,
            ).create(self._line(order_id=self._order().id, price_unit=7))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._order({"price_unit": 7, "is_downpayment": True})

    def test_categories_include_descendants_and_block_manual_orders(self):
        self.category.mayan_require_purchase_request = True
        with self.assertRaisesRegex(ValidationError, "solicitud de compra"), self.cr.savepoint():
            self._order()
        request = self._request()
        request.action_generate_purchase_orders()
        order = request.purchase_order_ids
        self.assertEqual(order.purchase_request_id, request)
        self.assertEqual(order.order_line.mayan_request_line_id, request.line_ids)
        order.button_confirm()
        self.assertEqual(order.state, "purchase")

    def test_existing_header_link_needs_matching_requested_product_and_vendor(self):
        self.category.mayan_require_purchase_request = True
        request = self._request()
        order = self._order(purchase_request_id=request.id)
        self.assertFalse(order.order_line.mayan_request_line_id)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.purchase_request_id = False
        other_vendor = self.vendor.copy({"name": "Otro proveedor"})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._order(purchase_request_id=request.id, partner_id=other_vendor.id)
        request.action_cancel()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.button_confirm()

    def test_wrong_source_line_and_transfer_are_rejected(self):
        request = self._request()
        other = self._request(request_type="transfer", source_location_id=self.warehouse.lot_stock_id.id)
        for source in (other.line_ids,):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self._order({"mayan_request_line_id": source.id}, purchase_request_id=request.id)

    def test_generator_zero_cost_draft_must_be_justified_before_add_or_confirm(self):
        self.product.standard_price = 0
        request = self._request()
        request.action_generate_purchase_orders()
        order = request.purchase_order_ids
        self.assertTrue(order.order_line.mayan_requires_justification)
        self.assertEqual(order.state, "draft")
        for operation in (
            order.button_confirm, order.action_add_from_catalog,
            lambda: self.env["purchase.order.line"].create(self._line(order_id=order.id, mayan_cost_justification="Compra nueva")),
            lambda: order.write({"order_line": [Command.create(self._line(mayan_cost_justification="Compra nueva"))]}),
        ):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                operation()
        order.order_line.write({"price_unit": 5, "mayan_cost_justification": "Primera compra; cotización adjunta"})
        order.button_confirm()
        self.assertEqual(order.state, "purchase")

    def test_generation_preserves_unit_cost_included_tax_and_source(self):
        self.product.uom_po_id = self.env.ref("uom.product_uom_dozen")
        self.product.supplier_taxes_id = self._tax(included=True)
        self.category.mayan_require_purchase_request = True
        request = self._request()
        request.action_generate_purchase_orders()
        line = request.purchase_order_ids.order_line
        self.assertEqual(line.product_uom, self.product.uom_po_id)
        self.assertAlmostEqual(line.price_unit, 73.92)
        self.assertAlmostEqual(line.mayan_net_unit_price, 66)
        self.assertAlmostEqual(line.mayan_cost_variation, 0)
        self.assertFalse(line.mayan_requires_justification)
        self.assertEqual(line.mayan_request_line_id, request.line_ids)

    def test_multiple_lines_are_checked_individually_and_sections_are_exempt(self):
        commands = [Command.create(self._line()) for _ in range(19)]
        commands.append(Command.create(self._line(price_unit=7)))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._order(order_line=commands)
        order = self._order(order_line=[Command.create({"display_type": "line_section", "name": "Alimentos", "product_qty": 0}),
                                        Command.create(self._line())])
        order.button_confirm()
        self.assertEqual(order.state, "purchase")

    def test_form_exposes_mandatory_justification(self):
        order = self._order()
        with Form(order) as form:
            with form.order_line.edit(0) as line:
                line.price_unit = 7
                self.assertTrue(line.mayan_requires_justification)
                line.mayan_cost_justification = "Cambio de proveedor"
        self.assertEqual(order.order_line.mayan_cost_justification, "Cambio de proveedor")

    def test_normal_buyer_can_justify_without_manager_approval(self):
        buyer = new_test_user(self.env, login="mayan_cost_buyer", groups="purchase.group_purchase_user,stock.group_stock_user,purchase_request_app.group_purchase_request_user")
        order = self._order().with_user(buyer)
        order.order_line.write({"price_unit": 7, "mayan_cost_justification": "Compra urgente"})
        self.assertEqual(order.order_line.mayan_justified_by, buyer)
        order.button_confirm()
        self.assertEqual(order.state, "purchase")

    def test_multi_company_cost_and_category_configuration(self):
        other = self.env["res.company"].create({"name": "Mayan Otra QA", "currency_id": self.company.currency_id.id})
        self.product.with_company(other).standard_price = 25
        self.category.mayan_require_purchase_request = True
        self.assertFalse(self.category.with_company(other).mayan_require_purchase_request)
        order = self._order({"price_unit": 25}, company_id=other.id)
        self.assertEqual(order.order_line.mayan_average_cost, 25)
        self.assertFalse(order.order_line.mayan_requires_justification)
        request = self._request()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._order({"price_unit": 25}, company_id=other.id, purchase_request_id=request.id)

    def test_cancellation_remains_possible_with_pending_reason(self):
        order = self._order()
        self.product.standard_price = 0
        order.button_cancel()
        self.assertEqual(order.state, "cancel")

    def test_reopened_draft_uses_current_cost_and_needs_new_reason(self):
        order = self._order()
        order.button_confirm()
        order.button_cancel()
        self.product.standard_price = 3
        order.button_draft()
        self.assertEqual(order.state, "draft")
        self.assertFalse(order.order_line.mayan_cost_snapshot_set)
        self.assertEqual(order.order_line.mayan_average_cost, 3)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.button_confirm()
        order.order_line.mayan_cost_justification = "Nueva revisión del costo"
        order.button_confirm()
        self.assertEqual(order.order_line.mayan_cost_snapshot, 3)

    def test_noop_edit_preserves_reason_but_copy_cannot_reuse_audit(self):
        order = self._order({"price_unit": 7, "mayan_cost_justification": "Cotización vigente"})
        line = order.order_line
        line.write({"price_unit": 7, "taxes_id": [Command.set(line.taxes_id.ids)]})
        self.assertEqual(line.mayan_cost_justification, "Cotización vigente")
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.copy()
