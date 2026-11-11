from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    mayan_require_purchase_request = fields.Boolean(
        string="Solicitud de compra obligatoria", company_dependent=True,
        help="En la compañía activa, exige una solicitud para esta categoría y todas sus subcategorías.",
    )

    def _mayan_requires_request(self, company):
        self.ensure_one()
        category = self.with_company(company)
        while category:
            if category.mayan_require_purchase_request:
                return True
            category = category.parent_id
        return False
