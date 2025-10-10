# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class VoiceCommandSession(models.Model):
    _name = 'voice.command.session'
    _description = 'Voice Command Session'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Session Reference',
        required=True,
        default='/',
        readonly=True,
        copy=False
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
        tracking=True
    )
    state = fields.Selection([
        ('collecting', 'Collecting Information'),
        ('ready', 'Ready to Execute'),
        ('executed', 'Executed'),
        ('aborted', 'Aborted'),
    ], string='State', default='collecting', required=True, tracking=True)

    transcript = fields.Text(
        string='Original Transcript',
        required=True,
        help='The original voice command text'
    )
    intent_key = fields.Char(
        string='Intent Key',
        help='The identified intent (e.g., sale_create, inventory_adjust)'
    )
    slots_json = fields.Json(
        string='Slots',
        default={},
        help='Extracted and filled slot values as JSON'
    )
    missing_slots_json = fields.Json(
        string='Missing Slots',
        default=[],
        help='List of slots still needing values'
    )
    result_summary = fields.Html(
        string='Result Summary',
        readonly=True,
        help='HTML summary of execution results with record links'
    )
    dry_run = fields.Boolean(
        string='Dry Run Mode',
        default=True,
        help='If True, simulate without making changes'
    )
    risk_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], string='Risk Level', default='low', required=True)

    log_ids = fields.One2many(
        'voice.command.log',
        'session_id',
        string='Logs'
    )

    # Additional useful fields
    execution_plan = fields.Json(
        string='Execution Plan',
        help='Dry-run simulation plan before execution'
    )
    execution_result = fields.Json(
        string='Execution Result',
        help='Actual execution results with record IDs'
    )
    error_message = fields.Text(
        string='Error Message',
        readonly=True
    )
    confirmation_required = fields.Boolean(
        string='Confirmation Required',
        compute='_compute_confirmation_required',
        store=True
    )
    confirmed_by_user = fields.Boolean(
        string='User Confirmed',
        default=False
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('voice.command.session') or '/'
        return super().create(vals_list)

    @api.depends('risk_level', 'state')
    def _compute_confirmation_required(self):
        for record in self:
            # High-risk actions always require confirmation
            # Medium-risk may require based on settings
            if record.risk_level == 'high':
                record.confirmation_required = True
            elif record.risk_level == 'medium':
                record.confirmation_required = self.env['ir.config_parameter'].sudo().get_param(
                    'voice_command_hub.confirm_medium_risk', default='True'
                ) == 'True'
            else:
                record.confirmation_required = False

    def action_parse(self):
        """Parse the transcript and extract intent + slots"""
        self.ensure_one()
        router = self.env['voice.intent.router']

        try:
            result = router.parse(self.transcript)
            self.write({
                'intent_key': result.get('intent_key'),
                'slots_json': result.get('slots', {}),
                'missing_slots_json': result.get('missing_slots', []),
                'risk_level': result.get('risk_level', 'low'),
            })
            self._log('info', 'Parsing completed', result)

            # Check if we have all required slots
            if not self.missing_slots_json or len(self.missing_slots_json) == 0:
                self.state = 'ready'

        except Exception as e:
            _logger.exception("Error parsing transcript")
            self._log('error', f'Parsing failed: {str(e)}')
            raise UserError(_('Failed to parse command: %s') % str(e))

        return True

    def action_simulate(self):
        """Run dry-run simulation"""
        self.ensure_one()
        if not self.intent_key:
            raise UserError(_('No intent identified. Please parse the command first.'))

        router = self.env['voice.intent.router']

        try:
            with self.env.cr.savepoint():
                plan = router.simulate(self.intent_key, self.slots_json)
                self.write({
                    'execution_plan': plan,
                    'state': 'ready',
                })
                self._log('info', 'Simulation completed', plan)

        except Exception as e:
            _logger.exception("Error simulating command")
            self._log('error', f'Simulation failed: {str(e)}')
            raise UserError(_('Simulation failed: %s') % str(e))

        return True

    def action_execute(self):
        """Execute the command"""
        self.ensure_one()

        if self.state != 'ready':
            raise UserError(_('Session is not ready for execution. Current state: %s') % self.state)

        if self.confirmation_required and not self.confirmed_by_user:
            raise UserError(_('This action requires user confirmation. Please confirm before executing.'))

        router = self.env['voice.intent.router']

        try:
            with self.env.cr.savepoint():
                result = router.execute(self.intent_key, self.slots_json)

                self.write({
                    'execution_result': result,
                    'result_summary': self._format_result_summary(result),
                    'state': 'executed',
                    'dry_run': False,
                })
                self._log('info', 'Execution completed', result)

        except Exception as e:
            _logger.exception("Error executing command")
            error_msg = str(e)
            self.write({
                'error_message': error_msg,
                'state': 'aborted',
            })
            self._log('error', f'Execution failed: {error_msg}')
            raise UserError(_('Execution failed: %s') % error_msg)

        return True

    def action_confirm(self):
        """User confirms the action"""
        self.ensure_one()
        self.confirmed_by_user = True
        self._log('info', 'User confirmed action')
        return True

    def action_abort(self):
        """Abort the session"""
        self.ensure_one()
        self.state = 'aborted'
        self._log('info', 'Session aborted by user')
        return True

    def action_fill_slot(self, slot_name, slot_value):
        """Fill a specific slot with a value"""
        self.ensure_one()

        slots = self.slots_json or {}
        slots[slot_name] = slot_value

        missing = list(self.missing_slots_json or [])
        if slot_name in missing:
            missing.remove(slot_name)

        self.write({
            'slots_json': slots,
            'missing_slots_json': missing,
        })

        self._log('info', f'Slot filled: {slot_name}', {'slot': slot_name, 'value': slot_value})

        # If all slots filled, move to ready
        if not missing:
            self.state = 'ready'

        return True

    def get_next_question(self):
        """Get the next follow-up question for missing slots"""
        self.ensure_one()

        if not self.missing_slots_json or len(self.missing_slots_json) == 0:
            return None

        # Get the next missing slot
        next_slot = self.missing_slots_json[0]

        # Get the intent template for context
        if self.intent_key:
            template = self.env['voice.intent.template'].search([
                ('key', '=', self.intent_key)
            ], limit=1)

            if template:
                slot_schema = template.slot_schema_json or {}
                slot_info = slot_schema.get(next_slot, {})
                question = slot_info.get('question', f'What is the {next_slot}?')
                return {
                    'slot': next_slot,
                    'question': question,
                    'type': slot_info.get('type', 'text'),
                    'help': slot_info.get('help', ''),
                }

        return {
            'slot': next_slot,
            'question': f'Please provide: {next_slot}',
            'type': 'text',
        }

    def _log(self, level, message, payload=None):
        """Create a log entry"""
        self.ensure_one()
        self.env['voice.command.log'].create({
            'session_id': self.id,
            'level': level,
            'message': message,
            'payload_json': payload or {},
        })

    def _format_result_summary(self, result):
        """Format execution result as HTML summary"""
        self.ensure_one()

        html_parts = ['<div class="voice_command_result">']
        html_parts.append('<h3>Execution Results</h3>')

        if result.get('created_records'):
            html_parts.append('<h4>Created Records:</h4><ul>')
            for record_info in result['created_records']:
                model = record_info.get('model')
                res_id = record_info.get('id')
                name = record_info.get('name', 'Unnamed')
                html_parts.append(
                    f'<li><a href="/web#model={model}&id={res_id}" target="_blank">'
                    f'{model}: {name}</a></li>'
                )
            html_parts.append('</ul>')

        if result.get('updated_records'):
            html_parts.append('<h4>Updated Records:</h4><ul>')
            for record_info in result['updated_records']:
                model = record_info.get('model')
                res_id = record_info.get('id')
                name = record_info.get('name', 'Unnamed')
                html_parts.append(
                    f'<li><a href="/web#model={model}&id={res_id}" target="_blank">'
                    f'{model}: {name}</a></li>'
                )
            html_parts.append('</ul>')

        if result.get('message'):
            html_parts.append(f'<p><strong>Message:</strong> {result["message"]}</p>')

        html_parts.append('</div>')
        return ''.join(html_parts)
