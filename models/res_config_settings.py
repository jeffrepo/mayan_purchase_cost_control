from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mayan_purchase_cost_tolerance = fields.Float(
        related="company_id.mayan_purchase_cost_tolerance", readonly=False,
    )
