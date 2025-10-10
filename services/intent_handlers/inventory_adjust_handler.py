# -*- coding: utf-8 -*-

import logging
from odoo import _
from odoo.exceptions import ValidationError, UserError
from .base_handler import VoiceIntentHandler

_logger = logging.getLogger(__name__)


class InventoryAdjustHandler:
    """Handler for inventory adjustments"""

    INTENT_KEY = 'inventory_adjust'

    SCHEMA = {
        'product': {
            'required': True,
            'type': 'product',
            'question': 'Which product?',
            'help': 'Product name or reference'
        },
        'qty_delta': {
            'required': True,
            'type': 'quantity',
            'question': 'How many units to add or remove?',
            'help': 'Positive to add, negative to remove'
        },
        'location': {
            'required': False,
            'type': 'text',
            'question': 'Which location?',
            'help': 'Stock location name'
        },
        'lot': {
            'required': False,
            'type': 'text',
            'question': 'Lot or serial number?',
        },
        'reason': {
            'required': False,
            'type': 'text',
            'question': 'Reason for adjustment?',
        },
    }

    def __init__(self, env):
        self.env = env
        self.slot_filler = env['voice.slot.filler']

    def validate_slots(self, slots):
        """Validate slots"""
        if 'product' not in slots:
            raise ValidationError(_('Product is required'))

        if 'qty_delta' not in slots:
            raise ValidationError(_('Quantity is required'))

        try:
            qty_delta = float(slots['qty_delta'])
        except (ValueError, TypeError):
            raise ValidationError(_('Quantity must be a number'))

    def simulate(self, slots):
        """Simulate inventory adjustment"""
        self.validate_slots(slots)

        # Get product
        product = self.slot_filler.normalize_product(slots['product'])
        if not product:
            raise UserError(_('Product not found: %s') % slots['product'])

        # Get location
        location_name = slots.get('location', 'Stock')
        location = self.env['stock.location'].search([
            ('name', 'ilike', location_name),
            ('usage', '=', 'internal')
        ], limit=1)

        if not location:
            # Try to get default location
            location = self.env['stock.warehouse'].search([], limit=1).lot_stock_id
            if not location:
                raise UserError(_('Location not found: %s') % location_name)

        qty_delta = float(slots['qty_delta'])

        # Get current quantity
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', '=', location.id)
        ])
        current_qty = sum(quants.mapped('quantity'))
        new_qty = current_qty + qty_delta

        plan = {
            'action': 'inventory_adjustment',
            'product': product.display_name,
            'location': location.complete_name,
            'current_quantity': current_qty,
            'quantity_change': qty_delta,
            'new_quantity': new_qty,
            'lot': slots.get('lot'),
            'reason': slots.get('reason', 'Voice command adjustment'),
        }

        return plan

    def execute(self, slots):
        """Execute inventory adjustment"""
        self.validate_slots(slots)

        _logger.info(f"Creating inventory adjustment with slots: {slots}")

        # Get product
        product = self.slot_filler.normalize_product(slots['product'])
        if not product:
            raise UserError(_('Product not found: %s') % slots['product'])

        # Get location
        location_name = slots.get('location', 'Stock')
        location = self.env['stock.location'].search([
            ('name', 'ilike', location_name),
            ('usage', '=', 'internal')
        ], limit=1)

        if not location:
            # Get default warehouse location
            warehouse = self.env['stock.warehouse'].search([], limit=1)
            if warehouse:
                location = warehouse.lot_stock_id
            else:
                raise UserError(_('No stock location found'))

        qty_delta = float(slots['qty_delta'])

        # Get or create stock quant
        lot_id = False
        if slots.get('lot'):
            # Search for existing lot or create new one
            lot = self.env['stock.lot'].search([
                ('name', '=', slots['lot']),
                ('product_id', '=', product.id)
            ], limit=1)

            if not lot:
                lot = self.env['stock.lot'].create({
                    'name': slots['lot'],
                    'product_id': product.id,
                    'company_id': self.env.company.id,
                })
            lot_id = lot.id

        # Find existing quant
        quant_domain = [
            ('product_id', '=', product.id),
            ('location_id', '=', location.id),
        ]
        if lot_id:
            quant_domain.append(('lot_id', '=', lot_id))

        quant = self.env['stock.quant'].search(quant_domain, limit=1)

        if quant:
            # Update existing quant
            old_qty = quant.quantity
            new_qty = old_qty + qty_delta

            quant.write({
                'quantity': new_qty,
                'inventory_quantity': new_qty,
            })
            _logger.info(f"Updated stock quant for {product.name}: {old_qty} -> {new_qty}")
        else:
            # Create new quant
            quant_vals = {
                'product_id': product.id,
                'location_id': location.id,
                'quantity': max(0, qty_delta),  # Can't have negative stock
                'inventory_quantity': max(0, qty_delta),
            }
            if lot_id:
                quant_vals['lot_id'] = lot_id

            quant = self.env['stock.quant'].create(quant_vals)
            _logger.info(f"Created stock quant for {product.name}: {quant.quantity}")

        # Create inventory adjustment record for traceability (if module available)
        adjustment = None
        if 'stock.inventory' in self.env:
            # For older Odoo versions with stock.inventory
            try:
                adjustment = self.env['stock.inventory'].create({
                    'name': _('Voice Command Adjustment - %s') % product.name,
                    'location_ids': [(4, location.id)],
                    'product_ids': [(4, product.id)],
                })
                adjustment.action_start()
                _logger.info(f"Created inventory adjustment: {adjustment.name}")
            except Exception as e:
                _logger.warning(f"Could not create stock.inventory record: {e}")

        message = _('Inventory adjusted for %s: %+.2f units at %s') % (
            product.name,
            qty_delta,
            location.name
        )

        result = {
            'success': True,
            'message': message,
            'created_records': [
                {
                    'model': 'stock.quant',
                    'id': quant.id,
                    'name': f'{product.name} @ {location.name}',
                }
            ],
        }

        if adjustment:
            result['created_records'].append({
                'model': 'stock.inventory',
                'id': adjustment.id,
                'name': adjustment.name,
            })

        return result


# Register handler
VoiceIntentHandler.register_handler(
    InventoryAdjustHandler.INTENT_KEY,
    InventoryAdjustHandler
)
