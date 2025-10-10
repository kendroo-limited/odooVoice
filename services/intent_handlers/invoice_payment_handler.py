# -*- coding: utf-8 -*-

import logging
from odoo import _
from odoo.exceptions import ValidationError, UserError
from .base_handler import VoiceIntentHandler

_logger = logging.getLogger(__name__)


class InvoicePaymentHandler:
    """Handler for registering invoice payments"""

    INTENT_KEY = 'invoice_register_payment'

    SCHEMA = {
        'invoice_ref': {
            'required': True,
            'type': 'text',
            'question': 'Invoice reference or number?',
            'help': 'The invoice number to register payment for'
        },
        'amount': {
            'required': False,
            'type': 'money',
            'question': 'Payment amount?',
            'help': 'Amount to pay (leave empty for full amount)'
        },
        'journal': {
            'required': False,
            'type': 'text',
            'question': 'Payment method/journal?',
            'help': 'e.g., Bank, Cash, Credit Card'
        },
        'date': {
            'required': False,
            'type': 'date',
            'question': 'Payment date?',
            'help': 'Date of payment (default: today)'
        },
        'communication': {
            'required': False,
            'type': 'text',
            'question': 'Payment reference/memo?',
        },
    }

    def __init__(self, env):
        self.env = env
        self.slot_filler = env['voice.slot.filler']

    def validate_slots(self, slots):
        """Validate slots"""
        if 'invoice_ref' not in slots:
            raise ValidationError(_('Invoice reference is required'))

    def simulate(self, slots):
        """Simulate payment registration"""
        self.validate_slots(slots)

        # Find invoice
        invoice_ref = slots['invoice_ref']
        invoice = self._find_invoice(invoice_ref)

        if not invoice:
            raise UserError(_('Invoice not found: %s') % invoice_ref)

        if invoice.state != 'posted':
            raise UserError(_('Invoice "%s" is not posted. Current state: %s') % (
                invoice.name, invoice.state
            ))

        if invoice.payment_state in ['paid', 'in_payment']:
            raise UserError(_('Invoice "%s" is already paid or has payments registered') % invoice.name)

        # Calculate amount
        amount_to_pay = self._get_payment_amount(slots, invoice)

        # Get journal
        journal_name = slots.get('journal', 'Bank')
        journal = self._find_journal(journal_name, invoice.move_type)

        plan = {
            'action': 'register_invoice_payment',
            'invoice': invoice.name,
            'invoice_type': invoice.move_type,
            'partner': invoice.partner_id.name,
            'total_amount': invoice.amount_total,
            'amount_due': invoice.amount_residual,
            'payment_amount': amount_to_pay,
            'journal': journal.name if journal else journal_name,
            'payment_date': slots.get('date', 'Today'),
            'will_post': True,
        }

        return plan

    def execute(self, slots):
        """Execute payment registration"""
        self.validate_slots(slots)

        _logger.info(f"Registering invoice payment with slots: {slots}")

        # Find invoice
        invoice_ref = slots['invoice_ref']
        invoice = self._find_invoice(invoice_ref)

        if not invoice:
            raise UserError(_('Invoice not found: %s') % invoice_ref)

        if invoice.state != 'posted':
            raise UserError(_('Invoice must be posted before registering payment'))

        if invoice.payment_state in ['paid']:
            raise UserError(_('Invoice is already fully paid'))

        # Calculate amount
        amount_to_pay = self._get_payment_amount(slots, invoice)

        # Validate amount
        if amount_to_pay > invoice.amount_residual:
            raise UserError(_(
                'Payment amount (%.2f) exceeds amount due (%.2f)'
            ) % (amount_to_pay, invoice.amount_residual))

        # Get or find journal
        journal_name = slots.get('journal', 'Bank')
        journal = self._find_journal(journal_name, invoice.move_type)

        if not journal:
            raise UserError(_('Payment journal not found: %s') % journal_name)

        # Prepare payment values
        payment_vals = {
            'payment_type': 'inbound' if invoice.move_type == 'out_invoice' else 'outbound',
            'partner_type': 'customer' if invoice.move_type == 'out_invoice' else 'supplier',
            'partner_id': invoice.partner_id.id,
            'amount': amount_to_pay,
            'journal_id': journal.id,
            'currency_id': invoice.currency_id.id,
            'date': slots.get('date') or self.env.context.get('payment_date'),
            'ref': slots.get('communication') or invoice.name,
        }

        # Create payment
        payment = self.env['account.payment'].create(payment_vals)
        _logger.info(f"Created payment: {payment.name}")

        # Post the payment
        payment.action_post()
        _logger.info(f"Posted payment: {payment.name}")

        # Reconcile with invoice
        lines = payment.line_ids + invoice.line_ids
        lines = lines.filtered(
            lambda l: l.account_id == invoice.line_ids.account_id
            and not l.reconciled
        )

        if lines:
            lines.reconcile()
            _logger.info(f"Reconciled payment with invoice")

        message = _('Payment registered for invoice %s: %.2f %s') % (
            invoice.name,
            amount_to_pay,
            invoice.currency_id.name
        )

        if invoice.payment_state == 'paid':
            message += _(' - Invoice is now fully paid')
        elif invoice.payment_state == 'partial':
            message += _(' - Partial payment registered')

        result = {
            'success': True,
            'message': message,
            'created_records': [
                {
                    'model': 'account.payment',
                    'id': payment.id,
                    'name': payment.name,
                },
            ],
            'updated_records': [
                {
                    'model': 'account.move',
                    'id': invoice.id,
                    'name': invoice.name,
                }
            ],
        }

        return result

    def _find_invoice(self, invoice_ref):
        """Find invoice by reference, name, or partial match"""
        # Try exact match first
        invoice = self.env['account.move'].search([
            ('name', '=', invoice_ref),
            ('move_type', 'in', ['out_invoice', 'in_invoice']),
            ('state', '=', 'posted')
        ], limit=1)

        if not invoice:
            # Try partial match
            invoice = self.env['account.move'].search([
                ('name', 'ilike', invoice_ref),
                ('move_type', 'in', ['out_invoice', 'in_invoice']),
                ('state', '=', 'posted')
            ], limit=1)

        if not invoice:
            # Try by payment reference
            invoice = self.env['account.move'].search([
                ('payment_reference', 'ilike', invoice_ref),
                ('move_type', 'in', ['out_invoice', 'in_invoice']),
                ('state', '=', 'posted')
            ], limit=1)

        return invoice

    def _get_payment_amount(self, slots, invoice):
        """Get payment amount from slots or use full amount due"""
        if slots.get('amount'):
            amount = slots['amount']
            if isinstance(amount, dict):
                return float(amount.get('amount', invoice.amount_residual))
            return float(amount)

        # Default to full amount due
        return invoice.amount_residual

    def _find_journal(self, journal_name, invoice_type):
        """Find appropriate payment journal"""
        # Determine journal type based on invoice type
        journal_type = 'bank'  # Default to bank
        if 'cash' in journal_name.lower():
            journal_type = 'cash'

        # Search for journal
        journal = self.env['account.journal'].search([
            ('name', 'ilike', journal_name),
            ('type', 'in', ['bank', 'cash'])
        ], limit=1)

        if not journal:
            # Get default journal of specified type
            journal = self.env['account.journal'].search([
                ('type', '=', journal_type)
            ], limit=1)

        return journal


# Register handler
VoiceIntentHandler.register_handler(
    InvoicePaymentHandler.INTENT_KEY,
    InvoicePaymentHandler
)
