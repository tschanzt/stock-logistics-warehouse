# Copyright 2014 Numérigraphe SARL
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from collections import Counter

from odoo import models, fields, api
from odoo.addons import decimal_precision as dp

from odoo.exceptions import AccessError, UserError


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # Needed for fields dependencies
    # When self.potential_qty is compute, we want to force the ORM
    # to compute all the components potential_qty too.
    component_ids = fields.Many2many(
        comodel_name='product.product',
        compute='_get_component_ids',
    )

    @api.multi
    def _compute_available_quantities_dict(self):
        """Add the potential quantity to the quantity available to promise.

        This is the same implementation as for templates."""
        res = {}
        for product in self:
            potential_qty = self._get_potential_qty(product)
            res[product.id] = {
                'immediately_usable_qty': product.virtual_available +
                potential_qty,
                'potential_qty': potential_qty
            }
        return res

    @api.multi
    @api.depends('virtual_available',
                 'component_ids.potential_qty',
                 'component_ids.virtual_available')
    def _compute_available_quantities(self):
        super()._compute_available_quantities()

    def _get_potential_qty(self, product):
        """Compute the potential qty based on the available components."""
        bom_obj = self.env['mrp.bom']
        bom = bom_obj._bom_find(product=product)
        if not bom:
            return 0.0

        # Need by product (same product can be in many BOM lines/levels)
        try:
            component_needs = self._get_components_needs(product, bom)
        except AccessError:
            # If user doesn't have access to BOM
            # he can't see potential_qty
            component_needs = None
        if not component_needs:
            # The BoM has no line we can use
            product.potential_qty = 0.0

        else:
            # Find the lowest quantity we can make with the stock at hand
            components_potential_qty = min(
                [self._get_component_qty(component) // need
                 for component, need in component_needs.items()]
            )

            # Compute with bom quantity
            bom_qty = bom.product_uom_id._compute_quantity(
                bom.product_qty,
                bom.product_tmpl_id.uom_id
            )
            return bom_qty * components_potential_qty

    def _get_component_qty(self, component):
        """ Return the component qty to use based en company settings.

        :type component: product_product
        :rtype: float
        """
        icp = self.env['ir.config_parameter'].sudo()
        stock_available_mrp_based_on = icp.get_param(
            'stock_available_mrp_based_on', 'qty_available'
        )

        return component[stock_available_mrp_based_on]

    def _get_components_needs(self, product, bom):
        """ Return the needed qty of each compoments in the *bom* of *product*.

        :type product: product_product
        :type bom: mrp_bom
        :rtype: collections.Counter
        """
        needs = Counter()
        for bom_component in bom.explode(product, 1.0)[1]:
            component = bom_component[0]['product_id']
            try:
                line_uom = bom_component[0].product_uom_id
                component_qty = line_uom._compute_quantity(
                    bom_component[1]['original_qty'],
                    component.uom_id
                )
            except UserError:
                # This occurs, when we have components
                # which are in a different cateogry.
                continue
            component_qty = component_qty * bom_component[1]['qty']
            needs += Counter(
                {component: component_qty}
            )

        return needs

    def _get_component_ids(self):
        """ Compute component_ids by getting all the components for
        this product.
        """
        bom_obj = self.env['mrp.bom']

        bom_id = bom_obj._bom_find(product_id=self.id)
        if bom_id:
            bom = bom_obj.browse(bom_id)
            for bom_component in bom_obj._bom_explode(bom, self, 1.0)[0]:
                self.component_ids |= self.browse(bom_component['product_id'])
