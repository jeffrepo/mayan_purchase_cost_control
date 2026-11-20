import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    mayan_purchase_cost_tolerance = fields.Float(
        string="Variación de costo permitida (%)", default=20.0, digits=(16, 6),
        required=True,
        help="Margen permitido por encima y por debajo del costo de referencia. "
             "Por ejemplo, 15,5 permite desde -15,5% hasta +15,5%, incluidos los límites. "
             "Con 0, cualquier variación requiere justificación.",
    )

    @api.constrains("mayan_purchase_cost_tolerance")
    def _check_mayan_purchase_cost_tolerance(self):
        for company in self:
            value = company.mayan_purchase_cost_tolerance
            if not math.isfinite(value) or value < 0:
                raise ValidationError(_("La variación de costo permitida debe ser un número finito mayor o igual a cero."))
