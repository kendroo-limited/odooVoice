# -*- coding: utf-8 -*-

import logging
from odoo import _
from odoo.exceptions import ValidationError, UserError
from .base_handler import VoiceIntentHandler

_logger = logging.getLogger(__name__)


class SaleCreateHandler:
    """Handler for creating and confirming sale orders"""

    INTENT_KEY = 'sale_create'

    SCHEMA = {
        'partner': {
            'required': True,
            'type': 'partner',
            'question': 'Who is the customer?',
            'help': 'Customer name, email, or phone number'
        },
        'product_lines': {
            'required': True,
            'type': 'product_lines',
            'question': 'What products and quantities?',
            'help': 'Product name and quantity (e.g., "5 chocolates")'
        },
        'confirm': {
            'required': False,
            'type': 'boolean',
            'default': True,
            'question': 'Confirm the order immediately?',
        },
        'invoice_now': {
            'required': False,
            'type': 'boolean',
            'default': False,
            'question': 'Create and post invoice now?',
        },
        'warehouse': {
            'required': False,
            'type': 'text',
            'question': 'Which warehouse?',
        },
        'pricelist': {
            'required': False,
            'type': 'text',
            'question': 'Which pricelist?',
        },
    }

    def __init__(self, env):
        self.env = env
        self.slot_filler = env['voice.slot.filler']

    def validate_slots(self, slots):
        """Validate slots"""
        if 'partner' not in slots:
            raise ValidationError(_('Customer is required'))

        if 'product_lines' not in slots or not slots['product_lines']:
            raise ValidationError(_('At least one product is required'))

    def simulate(self, slots):
        """Simulate SO creation"""
        self.validate_slots(slots)

        # Get partner
        partner = self.slot_filler.normalize_partner(slots['partner'])
        if not partner:
            raise UserError(_('Customer not found: %s') % slots['partner'])

        # Prepare order lines
        lines = []
        for line_data in slots['product_lines']:
            product = self.slot_filler.normalize_product(line_data.get('product_id'))
            if not product:
                raise UserError(_('Product not found: %s') % line_data.get('product_name', 'Unknown'))

            if not product.sale_ok:
                raise UserError(_('Product "%s" is not available for sale') % product.name)

            lines.append({
                'product': product.display_name,
                'quantity': line_data.get('qty', 1.0),
                'uom': product.uom_id.name,
                'price_unit': product.list_price,
            })

        plan = {
            'action': 'create_sale_order',
            'customer': partner.display_name,
            'lines': lines,
            'will_confirm': slots.get('confirm', True),
            'will_invoice': slots.get('invoice_now', False),
            'estimated_total': sum(l['quantity'] * l['price_unit'] for l in lines),
        }

        return plan

    def execute(self, slots):
        """Execute SO creation"""
        self.validate_slots(slots)

        _logger.info(f"Creating sale order with slots: {slots}")

        # Get partner
        partner = self.slot_filler.normalize_partner(slots['partner'])
        if not partner:
            raise UserError(_('Customer not found: %s') % slots['partner'])

        # Prepare order values
        order_vals = {
            'partner_id': partner.id,
        }

        # Add date_order only if provided in context
        if self.env.context.get('date_order'):
            order_vals['date_order'] = self.env.context.get('date_order')

        # Optional fields
        if slots.get('warehouse'):
            warehouse = self.env['stock.warehouse'].search([
                ('name', 'ilike', slots['warehouse'])
            ], limit=1)
            if warehouse:
                order_vals['warehouse_id'] = warehouse.id

        if slots.get('pricelist'):
            pricelist = self.env['product.pricelist'].search([
                ('name', 'ilike', slots['pricelist'])
            ], limit=1)
            if pricelist:
                order_vals['pricelist_id'] = pricelist.id

        # Create order
        order = self.env['sale.order'].create(order_vals)
        _logger.info(f"Created sale order: {order.name}")

        # Add order lines
        for line_data in slots['product_lines']:
            product = self.slot_filler.normalize_product(line_data.get('product_id'))
            if not product:
                raise UserError(_('Product not found: %s') % line_data.get('product_name', 'Unknown'))

            line_vals = {
                'order_id': order.id,
                'product_id': product.id,
                'product_uom_qty': line_data.get('qty', 1.0),
            }

            # Override price/discount if provided
            if line_data.get('unit_price'):
                line_vals['price_unit'] = line_data['unit_price']

            if line_data.get('discount'):
                line_vals['discount'] = line_data['discount']

            self.env['sale.order.line'].create(line_vals)

        result_records = {'created': order}

        # Confirm if requested
        if slots.get('confirm', True):
            order.action_confirm()
            _logger.info(f"Confirmed sale order: {order.name}")

        # Create invoice if requested
        invoice = self.env['account.move']
        if slots.get('invoice_now', False):
            if order.state not in ['sale', 'done']:
                raise UserError(_('Order must be confirmed before creating invoice'))

            invoice = order._create_invoices()
            if invoice:
                result_records['created'] |= invoice
                _logger.info(f"Created invoice: {invoice.name}")

                # Post invoice if configured
                auto_post = self.env['ir.config_parameter'].sudo().get_param(
                    'voice_command_hub.auto_post_invoices', default='False'
                ) == 'True'

                if auto_post:
                    invoice.action_post()
                    _logger.info(f"Posted invoice: {invoice.name}")

        message = _('Sale order %s created successfully') % order.name
        if invoice:
            message += _('. Invoice %s created') % invoice.name

        result = {
            'success': True,
            'message': message,
            'created_records': [
                {
                    'model': 'sale.order',
                    'id': order.id,
                    'name': order.name,
                }
            ],
        }

        if invoice:
            result['created_records'].append({
                'model': 'account.move',
                'id': invoice.id,
                'name': invoice.name,
            })

        return result


# Register handler
VoiceIntentHandler.register_handler(
    SaleCreateHandler.INTENT_KEY,
    SaleCreateHandler
)
