# -*- coding: utf-8 -*-

import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class VoiceCommandTraining(models.Model):
    _name = 'voice.command.training'
    _description = 'Voice Command Training Data'
    _order = 'create_date desc'

    name = fields.Char(
        string='Training Example',
        required=True,
        help='The voice command example for training'
    )
    intent_id = fields.Many2one(
        'voice.intent.template',
        string='Intent',
        required=True,
        help='Which intent this example belongs to'
    )
    intent_key = fields.Char(
        related='intent_id.key',
        string='Intent Key',
        store=True
    )

    # Extracted slots (what we expect to extract from this example)
    expected_slots = fields.Json(
        string='Expected Slots',
        help='JSON object with expected slot values'
    )

    # Training metadata
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        help='User who provided this training example'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    # Quality metrics
    times_used = fields.Integer(
        string='Times Matched',
        default=0,
        help='How many times this example was matched'
    )
    success_rate = fields.Float(
        string='Success Rate',
        compute='_compute_success_rate',
        store=True,
        help='Percentage of successful executions when matched'
    )
    successful_matches = fields.Integer(
        string='Successful Matches',
        default=0
    )
    failed_matches = fields.Integer(
        string='Failed Matches',
        default=0
    )

    # Learning data
    alternative_phrasings = fields.Text(
        string='Alternative Phrasings',
        help='Other ways users have said the same thing (one per line)'
    )
    common_errors = fields.Text(
        string='Common Errors',
        help='Common mistakes when using this example'
    )

    # Status
    active = fields.Boolean(
        string='Active',
        default=True
    )
    verified = fields.Boolean(
        string='Verified',
        default=False,
        help='Has this training example been verified by a manager?'
    )

    @api.depends('successful_matches', 'failed_matches', 'times_used')
    def _compute_success_rate(self):
        for record in self:
            total = record.successful_matches + record.failed_matches
            if total > 0:
                record.success_rate = (record.successful_matches / total) * 100
            else:
                record.success_rate = 0.0

    def action_verify(self):
        """Mark this training example as verified"""
        self.write({'verified': True})

    def action_add_to_intent(self):
        """Add this example to the intent's training phrases"""
        for record in self:
            if record.intent_id:
                current_phrases = record.intent_id.training_phrases or ''
                if record.name not in current_phrases:
                    new_phrases = current_phrases + '\n' + record.name
                    record.intent_id.write({'training_phrases': new_phrases.strip()})
                    _logger.info(f"Added training phrase '{record.name}' to intent {record.intent_id.key}")

    def increment_usage(self, success=True):
        """Increment usage statistics"""
        self.ensure_one()
        vals = {'times_used': self.times_used + 1}
        if success:
            vals['successful_matches'] = self.successful_matches + 1
        else:
            vals['failed_matches'] = self.failed_matches + 1
        self.write(vals)


class VoiceUserPreference(models.Model):
    _name = 'voice.user.preference'
    _description = 'Voice Command User Preferences'
    _sql_constraints = [
        ('user_unique', 'UNIQUE(user_id)', 'Only one preference record per user!'),
    ]

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user
    )

    # Preferred terminology
    preferred_product_names = fields.Json(
        string='Preferred Product Names',
        default={},
        help='User-specific product name mappings {"chocolate": "product_id"}'
    )
    preferred_partner_names = fields.Json(
        string='Preferred Partner Names',
        default={},
        help='User-specific partner name mappings'
    )

    # Behavioral preferences
    auto_confirm = fields.Boolean(
        string='Auto-Confirm Low Risk',
        default=False,
        help='Automatically confirm low-risk actions without prompting'
    )
    default_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Default Warehouse'
    )
    default_pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Default Pricelist'
    )

    # Learning preferences
    learn_from_corrections = fields.Boolean(
        string='Learn from Corrections',
        default=True,
        help='Automatically learn when you correct parsed commands'
    )
    suggest_alternatives = fields.Boolean(
        string='Suggest Alternatives',
        default=True,
        help='Show alternative interpretations if confidence is low'
    )

    # Command history for personalization
    command_history = fields.Json(
        string='Command History',
        default={},
        help='Stores frequently used commands and patterns'
    )
    favorite_commands = fields.Text(
        string='Favorite Commands',
        help='Quick access to frequently used commands (one per line)'
    )

    # Statistics
    total_commands = fields.Integer(
        string='Total Commands',
        default=0,
        readonly=True
    )
    successful_commands = fields.Integer(
        string='Successful Commands',
        default=0,
        readonly=True
    )

    def increment_command_stats(self, success=True):
        """Update user command statistics"""
        self.ensure_one()
        vals = {'total_commands': self.total_commands + 1}
        if success:
            vals['successful_commands'] = self.successful_commands + 1
        self.write(vals)

    def add_to_history(self, command, intent_key):
        """Add command to user's history for learning"""
        self.ensure_one()
        history = self.command_history or {}

        # Track frequency of intent usage
        if intent_key not in history:
            history[intent_key] = {'count': 0, 'examples': []}

        history[intent_key]['count'] += 1

        # Store recent examples (max 10 per intent)
        if command not in history[intent_key]['examples']:
            history[intent_key]['examples'].append(command)
            if len(history[intent_key]['examples']) > 10:
                history[intent_key]['examples'].pop(0)

        self.write({'command_history': history})


class VoiceCommandFeedback(models.Model):
    _name = 'voice.command.feedback'
    _description = 'Voice Command Feedback'
    _order = 'create_date desc'

    session_id = fields.Many2one(
        'voice.command.session',
        string='Session',
        required=True,
        ondelete='cascade'
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        required=True
    )

    # Feedback type
    feedback_type = fields.Selection([
        ('correction', 'Correction'),
        ('suggestion', 'Suggestion'),
        ('error_report', 'Error Report'),
        ('praise', 'Positive Feedback'),
    ], string='Type', required=True)

    # What was wrong/right
    original_intent = fields.Char(
        string='Detected Intent'
    )
    correct_intent = fields.Char(
        string='Correct Intent',
        help='What the intent should have been'
    )

    original_slots = fields.Json(
        string='Detected Slots'
    )
    correct_slots = fields.Json(
        string='Correct Slots'
    )

    # Feedback details
    description = fields.Text(
        string='Description',
        help='Detailed feedback from user'
    )

    # Processing
    processed = fields.Boolean(
        string='Processed',
        default=False,
        help='Has this feedback been used to improve the system?'
    )
    applied_date = fields.Datetime(
        string='Applied Date'
    )

    def action_apply_feedback(self):
        """Apply this feedback to improve the system"""
        for record in self:
            if record.feedback_type == 'correction' and record.correct_intent:
                # Create or update training example
                training_vals = {
                    'name': record.session_id.transcript,
                    'intent_id': self.env['voice.intent.template'].search([
                        ('key', '=', record.correct_intent)
                    ], limit=1).id,
                    'expected_slots': record.correct_slots or {},
                    'user_id': record.user_id.id,
                    'verified': False,
                }

                self.env['voice.command.training'].create(training_vals)

            record.write({
                'processed': True,
                'applied_date': fields.Datetime.now()
            })

            _logger.info(f"Applied feedback from user {record.user_id.name} for session {record.session_id.name}")
