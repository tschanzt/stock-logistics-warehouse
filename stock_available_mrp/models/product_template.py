# Copyright 2014 Numérigraphe SARL
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
from odoo.addons import decimal_precision as dp


class ProductTemplate(models.Model):
    _inherit = 'product.template'

 
    @api.multi
    @api.multi
    @api.depends('product_variant_ids.immediately_usable_qty',
                 'product_variant_ids.potential_qty')
    def _compute_available_quantities_dict(self):
        """Compute the potential as the max of all the variants's potential.

        We can't add the potential of variants: if they share components we
        may not be able to make all the variants.
        So we set the arbitrary rule that we can promise up to the biggest
        variant's potential.
        """
        res = super(ProductTemplate, self)._compute_available_quantities_dict()
        for tmpl in self:
            if not tmpl.product_variant_ids:
                continue
            avail = res[tmpl.id]['immediately_usable_qty']
            potential = max(
                [v.potential_qty for v in tmpl.product_variant_ids])
            res[tmpl.id]['immediately_usable_qty'] = avail + potential
            res[tmpl.id]['potential_qty'] = potential
        return res
