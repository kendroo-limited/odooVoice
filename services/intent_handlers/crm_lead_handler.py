# -*- coding: utf-8 -*-

import logging
from odoo import _
from odoo.exceptions import ValidationError, UserError
from .base_handler import VoiceIntentHandler

_logger = logging.getLogger(__name__)


class CRMLeadHandler:
    """Handler for creating CRM leads/opportunities"""

    INTENT_KEY = 'crm_lead_create'

    SCHEMA = {
        'contact': {
            'required': True,
            'type': 'text',
            'question': 'Contact name or company?',
            'help': 'Name of person or company for this opportunity'
        },
        'title': {
            'required': False,
            'type': 'text',
            'question': 'Opportunity title?',
            'help': 'Brief description of the opportunity'
        },
        'expected_revenue': {
            'required': False,
            'type': 'money',
            'question': 'Expected revenue?',
            'help': 'Estimated value of this opportunity'
        },
        'probability': {
            'required': False,
            'type': 'quantity',
            'question': 'Probability (0-100)?',
            'help': 'Likelihood of closing this deal'
        },
        'phone': {
            'required': False,
            'type': 'text',
            'question': 'Phone number?',
        },
        'email': {
            'required': False,
            'type': 'text',
            'question': 'Email address?',
        },
        'source': {
            'required': False,
            'type': 'text',
            'question': 'Lead source?',
            'help': 'Where did this lead come from?'
        },
    }

    def __init__(self, env):
        self.env = env
        self.slot_filler = env['voice.slot.filler']

    def validate_slots(self, slots):
        """Validate slots"""
        if 'contact' not in slots:
            raise ValidationError(_('Contact name is required'))

    def simulate(self, slots):
        """Simulate lead creation"""
        self.validate_slots(slots)

        contact_name = slots['contact']

        # Try to find existing partner
        partner = None
        if slots.get('email'):
            partner = self.env['res.partner'].search([
                ('email', '=ilike', slots['email'])
            ], limit=1)

        if not partner:
            partner = self.env['res.partner'].search([
                ('name', 'ilike', contact_name)
            ], limit=1)

        plan = {
            'action': 'create_crm_lead',
            'contact': contact_name,
            'title': slots.get('title') or f'Opportunity for {contact_name}',
            'expected_revenue': slots.get('expected_revenue', {}).get('amount') if isinstance(slots.get('expected_revenue'), dict) else slots.get('expected_revenue'),
            'probability': slots.get('probability', 10.0),
            'phone': slots.get('phone'),
            'email': slots.get('email'),
            'source': slots.get('source'),
            'existing_partner': partner.name if partner else None,
        }

        return plan

    def execute(self, slots):
        """Execute lead creation"""
        self.validate_slots(slots)

        _logger.info(f"Creating CRM lead with slots: {slots}")

        contact_name = slots['contact']

        # Try to find or create partner
        partner = None
        if slots.get('email'):
            partner = self.env['res.partner'].search([
                ('email', '=ilike', slots['email'])
            ], limit=1)

        if not partner:
            # Search by name
            partner = self.env['res.partner'].search([
                ('name', 'ilike', contact_name)
            ], limit=1)

        # Prepare lead values
        lead_vals = {
            'name': slots.get('title') or f'Opportunity for {contact_name}',
            'type': 'opportunity',  # Create as opportunity directly
        }

        # Link to partner if found, otherwise store contact details
        if partner:
            lead_vals['partner_id'] = partner.id
            _logger.info(f"Linking to existing partner: {partner.name}")
        else:
            lead_vals['contact_name'] = contact_name
            if slots.get('phone'):
                lead_vals['phone'] = slots['phone']
            if slots.get('email'):
                lead_vals['email_from'] = slots['email']

        # Optional fields
        if slots.get('expected_revenue'):
            revenue = slots['expected_revenue']
            if isinstance(revenue, dict):
                lead_vals['expected_revenue'] = revenue.get('amount', 0.0)
            else:
                lead_vals['expected_revenue'] = float(revenue)

        if slots.get('probability'):
            prob = float(slots['probability'])
            # Ensure probability is between 0 and 100
            lead_vals['probability'] = max(0, min(100, prob))

        # Get or create source
        if slots.get('source'):
            source = self.env['utm.source'].search([
                ('name', 'ilike', slots['source'])
            ], limit=1)
            if not source:
                source = self.env['utm.source'].create({
                    'name': slots['source']
                })
            lead_vals['source_id'] = source.id

        # Assign to current user's sales team
        team = self.env['crm.team'].search([
            ('user_id', '=', self.env.user.id)
        ], limit=1)
        if not team:
            # Get any active sales team
            team = self.env['crm.team'].search([
                ('active', '=', True)
            ], limit=1)
        if team:
            lead_vals['team_id'] = team.id

        # Assign to current user
        lead_vals['user_id'] = self.env.user.id

        # Create lead
        lead = self.env['crm.lead'].create(lead_vals)
        _logger.info(f"Created CRM lead/opportunity: {lead.name}")

        # Create partner if not exists and email/phone provided
        created_partner = None
        if not partner and (slots.get('email') or slots.get('phone')):
            auto_create = self.env['ir.config_parameter'].sudo().get_param(
                'voice_command_hub.auto_create_partner', default='False'
            ) == 'True'

            if auto_create:
                partner_vals = {
                    'name': contact_name,
                    'customer_rank': 1,
                }
                if slots.get('email'):
                    partner_vals['email'] = slots['email']
                if slots.get('phone'):
                    partner_vals['phone'] = slots['phone']

                created_partner = self.env['res.partner'].create(partner_vals)
                lead.write({'partner_id': created_partner.id})
                _logger.info(f"Created new partner: {created_partner.name}")

        message = _('CRM opportunity "%s" created successfully') % lead.name
        if created_partner:
            message += _('. New contact "%s" also created') % created_partner.name

        result = {
            'success': True,
            'message': message,
            'created_records': [
                {
                    'model': 'crm.lead',
                    'id': lead.id,
                    'name': lead.name,
                }
            ],
        }

        if created_partner:
            result['created_records'].append({
                'model': 'res.partner',
                'id': created_partner.id,
                'name': created_partner.name,
            })

        return result


# Register handler
VoiceIntentHandler.register_handler(
    CRMLeadHandler.INTENT_KEY,
    CRMLeadHandler
)
