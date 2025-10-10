# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class VoiceIntentTemplate(models.Model):
    _name = 'voice.intent.template'
    _description = 'Voice Intent Template'
    _order = 'sequence, name'

    name = fields.Char(
        string='Intent Name',
        required=True,
        translate=True,
        help='Human-readable name of the intent'
    )
    key = fields.Char(
        string='Intent Key',
        required=True,
        index=True,
        help='Unique identifier for the intent (e.g., sale_create, inventory_adjust)'
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Enable/disable this intent'
    )

    description = fields.Text(
        string='Description',
        translate=True
    )
    training_phrases = fields.Text(
        string='Training Phrases',
        help='Example phrases (one per line or YAML format) to recognize this intent'
    )
    slot_schema_json = fields.Json(
        string='Slot Schema',
        default={},
        help='JSON schema defining required/optional slots and their types'
    )
    handler_python = fields.Text(
        string='Handler Code',
        help='Python code or dotted path to handler function'
    )

    risk_level_default = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], string='Default Risk Level', default='low', required=True)

    confirm_policy = fields.Selection([
        ('always', 'Always Confirm'),
        ('threshold', 'Based on Risk Threshold'),
        ('never', 'Never Confirm'),
    ], string='Confirmation Policy', default='threshold', required=True)

    # Additional metadata
    category = fields.Selection([
        ('sales', 'Sales'),
        ('purchase', 'Purchase'),
        ('inventory', 'Inventory'),
        ('accounting', 'Accounting'),
        ('crm', 'CRM'),
        ('manufacturing', 'Manufacturing'),
        ('custom', 'Custom'),
    ], string='Category', default='custom')

    required_modules = fields.Char(
        string='Required Modules',
        help='Comma-separated list of required Odoo modules'
    )
    required_groups = fields.Many2many(
        'res.groups',
        string='Required Groups',
        help='User must belong to these groups to use this intent'
    )

    # Statistics
    usage_count = fields.Integer(
        string='Usage Count',
        readonly=True,
        default=0
    )
    last_used = fields.Datetime(
        string='Last Used',
        readonly=True
    )

    _sql_constraints = [
        ('key_unique', 'UNIQUE(key)', 'Intent key must be unique!'),
    ]

    @api.constrains('key')
    def _check_key(self):
        for record in self:
            if not record.key:
                continue
            # Check if key contains only valid characters
            if not record.key.replace('_', '').replace('.', '').isalnum():
                raise ValidationError(_(
                    'Intent key can only contain letters, numbers, underscores, and dots.'
                ))

    def action_test_intent(self):
        """Test this intent with sample data"""
        self.ensure_one()
        # This could open a wizard for testing
        return {
            'type': 'ir.actions.act_window',
            'name': _('Test Intent: %s') % self.name,
            'res_model': 'voice.command.session',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_intent_key': self.key,
                'default_transcript': self.training_phrases.split('\n')[0] if self.training_phrases else '',
            }
        }

    def increment_usage(self):
        """Increment usage counter"""
        self.ensure_one()
        self.sudo().write({
            'usage_count': self.usage_count + 1,
            'last_used': fields.Datetime.now(),
        })

    def get_slot_schema(self):
        """Get the slot schema as a Python dict"""
        self.ensure_one()
        schema = self.slot_schema_json
        if not schema:
            return {}
        # Handle case where it might be a string (from XML-RPC or old data)
        if isinstance(schema, str):
            import json
            try:
                return json.loads(schema)
            except (json.JSONDecodeError, ValueError):
                _logger.error(f"Failed to parse slot schema for intent {self.key}: {schema}")
                return {}
        return schema

    def get_training_phrases_list(self):
        """Get training phrases as a list"""
        self.ensure_one()
        if not self.training_phrases:
            return []
        return [
            phrase.strip()
            for phrase in self.training_phrases.split('\n')
            if phrase.strip()
        ]

    def check_user_access(self, user=None):
        """Check if user has access to this intent"""
        self.ensure_one()
        if not user:
            user = self.env.user

        # Check required groups
        if self.required_groups:
            user_groups = user.groups_id
            if not any(group in user_groups for group in self.required_groups):
                return False, _('You do not have the required permissions for this action.')

        # Check required modules
        if self.required_modules:
            required = [m.strip() for m in self.required_modules.split(',')]
            for module_name in required:
                module = self.env['ir.module.module'].search([
                    ('name', '=', module_name),
                    ('state', '=', 'installed')
                ], limit=1)
                if not module:
                    return False, _('Required module "%s" is not installed.') % module_name

        return True, None
