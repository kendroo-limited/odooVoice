# -*- coding: utf-8 -*-

import logging
from odoo import _
from odoo.exceptions import ValidationError, UserError
from .base_handler import VoiceIntentHandler

_logger = logging.getLogger(__name__)


class PurchaseCreateHandler:
    """Handler for creating purchase orders"""

    INTENT_KEY = 'purchase_create'

    SCHEMA = {
        'vendor': {
            'required': True,
            'type': 'partner',
            'question': 'Who is the vendor?',
            'help': 'Vendor name, email, or phone number'
        },
        'product_lines': {
            'required': True,
            'type': 'product_lines',
            'question': 'What products and quantities?',
            'help': 'Product name and quantity (e.g., "100 chocolates")'
        },
        'confirm': {
            'required': False,
            'type': 'boolean',
            'default': False,
            'question': 'Confirm the purchase order immediately?',
        },
        'bill_now': {
            'required': False,
            'type': 'boolean',
            'default': False,
            'question': 'Create vendor bill now?',
        },
        'expected_date': {
            'required': False,
            'type': 'date',
            'question': 'When do you expect delivery?',
        },
    }

    def __init__(self, env):
        self.env = env
        self.slot_filler = env['voice.slot.filler']

    def validate_slots(self, slots):
        """Validate slots"""
        if 'vendor' not in slots:
            raise ValidationError(_('Vendor is required'))

        if 'product_lines' not in slots or not slots['product_lines']:
            raise ValidationError(_('At least one product is required'))

    def simulate(self, slots):
        """Simulate PO creation"""
        self.validate_slots(slots)

        # Get vendor
        vendor = self.slot_filler.normalize_partner(slots['vendor'])
        if not vendor:
            raise UserError(_('Vendor not found: %s') % slots['vendor'])

        if not vendor.supplier_rank and not vendor.is_company:
            raise UserError(_('Partner "%s" is not configured as a vendor') % vendor.name)

        # Prepare order lines
        lines = []
        for line_data in slots['product_lines']:
            product = self.slot_filler.normalize_product(line_data.get('product_id'))
            if not product:
                raise UserError(_('Product not found: %s') % line_data.get('product_name', 'Unknown'))

            if not product.purchase_ok:
                raise UserError(_('Product "%s" is not available for purchase') % product.name)

            # Use standard price or get from vendor pricelist
            unit_price = line_data.get('unit_price') or product.standard_price

            lines.append({
                'product': product.display_name,
                'quantity': line_data.get('qty', 1.0),
                'uom': product.uom_po_id.name,
                'price_unit': unit_price,
            })

        plan = {
            'action': 'create_purchase_order',
            'vendor': vendor.display_name,
            'lines': lines,
            'will_confirm': slots.get('confirm', False),
            'will_create_bill': slots.get('bill_now', False),
            'expected_date': slots.get('expected_date'),
            'estimated_total': sum(l['quantity'] * l['price_unit'] for l in lines),
        }

        return plan

    def execute(self, slots):
        """Execute PO creation"""
        self.validate_slots(slots)

        _logger.info(f"Creating purchase order with slots: {slots}")

        # Get vendor
        vendor = self.slot_filler.normalize_partner(slots['vendor'])
        if not vendor:
            raise UserError(_('Vendor not found: %s') % slots['vendor'])

        # Ensure vendor is marked as supplier
        if not vendor.supplier_rank:
            vendor.write({'supplier_rank': 1})

        # Prepare order values
        order_vals = {
            'partner_id': vendor.id,
        }

        # Optional fields
        if slots.get('expected_date'):
            order_vals['date_planned'] = slots['expected_date']

        # Create order
        order = self.env['purchase.order'].create(order_vals)
        _logger.info(f"Created purchase order: {order.name}")

        # Add order lines
        for line_data in slots['product_lines']:
            product = self.slot_filler.normalize_product(line_data.get('product_id'))
            if not product:
                raise UserError(_('Product not found: %s') % line_data.get('product_name', 'Unknown'))

            # Get price from vendor or use standard price
            unit_price = line_data.get('unit_price')
            if not unit_price:
                # Try to get from supplier info
                supplier_info = self.env['product.supplierinfo'].search([
                    ('product_tmpl_id', '=', product.product_tmpl_id.id),
                    ('partner_id', '=', vendor.id)
                ], limit=1)
                unit_price = supplier_info.price if supplier_info else product.standard_price

            line_vals = {
                'order_id': order.id,
                'product_id': product.id,
                'product_qty': line_data.get('qty', 1.0),
                'price_unit': unit_price,
                'date_planned': slots.get('expected_date') or order.date_planned,
            }

            self.env['purchase.order.line'].create(line_vals)

        result_records = {'created': order}

        # Confirm if requested
        if slots.get('confirm', False):
            order.button_confirm()
            _logger.info(f"Confirmed purchase order: {order.name}")

        # Create bill if requested
        bill = self.env['account.move']
        if slots.get('bill_now', False):
            if order.state not in ['purchase', 'done']:
                raise UserError(_('Order must be confirmed before creating bill'))

            # Create vendor bill
            bill = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': vendor.id,
                'invoice_origin': order.name,
                'purchase_id': order.id,
            })

            # Add bill lines from PO
            for po_line in order.order_line:
                self.env['account.move.line'].create({
                    'move_id': bill.id,
                    'product_id': po_line.product_id.id,
                    'quantity': po_line.product_qty,
                    'price_unit': po_line.price_unit,
                    'purchase_line_id': po_line.id,
                })

            # Recompute invoice
            bill._recompute_dynamic_lines()

            if bill:
                result_records['created'] |= bill
                _logger.info(f"Created vendor bill: {bill.name}")

        message = _('Purchase order %s created successfully') % order.name
        if bill:
            message += _('. Vendor bill %s created') % bill.name

        result = {
            'success': True,
            'message': message,
            'created_records': [
                {
                    'model': 'purchase.order',
                    'id': order.id,
                    'name': order.name,
                }
            ],
        }

        if bill:
            result['created_records'].append({
                'model': 'account.move',
                'id': bill.id,
                'name': bill.name,
            })

        return result


# Register handler
VoiceIntentHandler.register_handler(
    PurchaseCreateHandler.INTENT_KEY,
    PurchaseCreateHandler
)
