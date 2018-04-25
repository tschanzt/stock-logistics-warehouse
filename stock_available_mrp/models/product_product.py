# Copyright 2014 Numérigraphe SARL
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from collections import Counter

from odoo import models, fields, api
from odoo.addons import decimal_precision as dp

from odoo.exceptions import AccessError, UserError


class ProductProduct(models.Model):
    _inherit = 'product.product'

    potential_qty = fields.Float(
        compute='_get_potential_qty',
        type='float',
        digits=dp.get_precision('Product Unit of Measure'),
        string='Potential',
        help="Quantity of this Product that could be produced using "
             "the materials already at hand.")

    # Needed for fields dependencies
    # When self.potential_qty is compute, we want to force the ORM
    # to compute all the components potential_qty too.
    component_ids = fields.Many2many(
        comodel_name='product.product',
        compute='_get_component_ids',
    )

    @api.multi
    @api.depends('potential_qty')
    def _immediately_usable_qty(self):
        """Add the potential quantity to the quantity available to promise.

        This is the same implementation as for templates."""
        super(ProductProduct, self)._immediately_usable_qty()
        for product in self:
            product.immediately_usable_qty += product.potential_qty

    @api.multi
    @api.depends('component_ids.potential_qty')
    def _get_potential_qty(self):
        """Compute the potential qty based on the available components."""
        bom_obj = self.env['mrp.bom']
        uom_obj = self.env['product.uom']
        for product in self:
            bom = bom_obj._bom_find(product=product)
            if not bom:
                product.potential_qty = 0.0
                continue

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
                import pdb; pdb.set_trace()
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
                product.potential_qty = bom_qty * components_potential_qty

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
            product_uom = bom_component[1]['product'].uom_id
            component = bom_component[0]['product_id']
            try:
                component_qty = bom_component[0].product_uom_id._compute_quantity(
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
