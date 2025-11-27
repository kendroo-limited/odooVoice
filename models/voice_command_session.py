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

    # Human-readable display fields
    slots_display = fields.Html(
        string='Extracted Information',
        compute='_compute_slots_display',
        help='Human-readable display of extracted slots'
    )
    execution_plan_display = fields.Html(
        string='Execution Plan Summary',
        compute='_compute_execution_plan_display',
        help='Human-readable display of execution plan'
    )
    execution_result_display = fields.Html(
        string='Execution Summary',
        compute='_compute_execution_result_display',
        help='Human-readable display of execution results'
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
    next_question_text = fields.Text(
        string='Next Question',
        compute='_compute_next_question',
        help='The next question to ask the user for missing information'
    )

    @api.depends('missing_slots_json', 'intent_key', 'transcript')
    def _compute_next_question(self):
        """Compute the next question to ask for missing information"""
        for record in self:
            if record.missing_slots_json and len(record.missing_slots_json) > 0:
                question_data = record.get_next_question()
                if question_data:
                    record.next_question_text = question_data.get('question', '')
                else:
                    record.next_question_text = False
            else:
                record.next_question_text = False

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
        """Parse the transcript and extract intent + slots with validation"""
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

            # Validate slots early (catch issues before state becomes "ready")
            validation_result = self._validate_slots()
            if validation_result and not validation_result.get('valid'):
                # Validation failed - ask clarification question
                clarification = validation_result.get('clarification', {})
                self.write({
                    'missing_slots_json': [clarification.get('slot_name', 'product')],
                    'next_question_text': clarification.get('question', ''),
                    'state': 'collecting',
                })
                self._log('warning', 'Validation failed during parse', {
                    'error': clarification.get('message', ''),
                    'suggestions': clarification.get('suggestions', [])
                })
                raise UserError(_(clarification.get('message', 'Validation failed')))

            # All slots valid - check if we have all required slots
            if not self.missing_slots_json or len(self.missing_slots_json) == 0:
                self.state = 'ready'

        except UserError:
            raise  # Re-raise UserError as-is
        except Exception as e:
            _logger.exception("Error parsing transcript")
            self._log('error', f'Parsing failed: {str(e)}')
            raise UserError(_('Failed to parse command: %s') % str(e))

        return True

    def action_simulate(self):
        """Run dry-run simulation (validation already done in parse)"""
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
                # Handle both dict and JSON string formats
                slot_schema = template.slot_schema_json or {}
                if isinstance(slot_schema, str):
                    import json
                    try:
                        slot_schema = json.loads(slot_schema)
                    except (json.JSONDecodeError, ValueError):
                        slot_schema = {}

                slot_info = slot_schema.get(next_slot, {})

                # Use LLM assistant to generate natural question
                llm_assistant = self.env['voice.llm.assistant']
                question = llm_assistant.generate_natural_question(
                    next_slot,
                    slot_info,
                    self.intent_key,
                    self.transcript or ''
                )

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

    @api.depends('slots_json')
    def _compute_slots_display(self):
        """Generate human-readable HTML display of extracted slots"""
        for record in self:
            if not record.slots_json or len(record.slots_json) == 0:
                record.slots_display = '<p style="color: #666; font-style: italic;">No information extracted yet</p>'
                continue

            html = '<div style="font-family: sans-serif;">'
            html += '<table style="width: 100%; border-collapse: collapse;">'

            for slot_name, slot_value in record.slots_json.items():
                # Format slot name (convert snake_case to Title Case)
                display_name = slot_name.replace('_', ' ').title()

                # Format slot value
                if isinstance(slot_value, dict):
                    display_value = '<br>'.join([f'<strong>{k}:</strong> {v}' for k, v in slot_value.items()])
                elif isinstance(slot_value, list):
                    display_value = ', '.join([str(item) for item in slot_value])
                else:
                    display_value = str(slot_value)

                html += f'''
                <tr style="border-bottom: 1px solid #e0e0e0;">
                    <td style="padding: 10px; font-weight: bold; color: #2c3e50; width: 30%;">
                        {display_name}
                    </td>
                    <td style="padding: 10px; color: #34495e;">
                        {display_value}
                    </td>
                </tr>
                '''

            html += '</table></div>'
            record.slots_display = html

    @api.depends('execution_plan')
    def _compute_execution_plan_display(self):
        """Generate human-readable HTML display of execution plan"""
        for record in self:
            if not record.execution_plan or len(record.execution_plan) == 0:
                record.execution_plan_display = '<p style="color: #666; font-style: italic;">No execution plan available</p>'
                continue

            plan = record.execution_plan
            html = '<div style="font-family: sans-serif; padding: 15px; background: #f8f9fa; border-radius: 5px;">'

            # Plan title/description
            if plan.get('description'):
                html += f'<p style="font-size: 16px; color: #2c3e50; margin-bottom: 15px;"><strong>{plan["description"]}</strong></p>'

            # Planned actions
            if plan.get('actions'):
                html += '<h4 style="color: #2c3e50; margin: 15px 0 10px 0;">📋 Planned Actions:</h4>'
                html += '<ul style="list-style: none; padding: 0;">'
                for action in plan['actions']:
                    if isinstance(action, dict):
                        action_text = action.get('description', str(action))
                    else:
                        action_text = str(action)
                    html += f'<li style="padding: 5px 0; border-left: 3px solid #007bff; padding-left: 10px; margin-bottom: 5px;">▶ {action_text}</li>'
                html += '</ul>'

            # Records to create/modify
            if plan.get('records_to_create'):
                html += '<h4 style="color: #2c3e50; margin: 15px 0 10px 0;">📝 Records to Create:</h4>'
                html += '<ul style="list-style: none; padding: 0;">'
                for record_info in plan['records_to_create']:
                    if isinstance(record_info, dict):
                        model = record_info.get('model', 'Unknown')
                        values = record_info.get('values', {})
                        html += f'<li style="padding: 8px; background: #e7f3ff; margin-bottom: 5px; border-radius: 3px;"><strong>{model}:</strong> {len(values)} fields</li>'
                    else:
                        html += f'<li style="padding: 8px; background: #e7f3ff; margin-bottom: 5px; border-radius: 3px;">{record_info}</li>'
                html += '</ul>'

            # Risk assessment
            if plan.get('risk_level'):
                risk_level = plan['risk_level'].upper()
                risk_colors = {
                    'LOW': '#28a745',
                    'MEDIUM': '#ffc107',
                    'HIGH': '#dc3545'
                }
                risk_color = risk_colors.get(risk_level, '#6c757d')
                html += f'''
                <div style="background: {risk_color}20; border-left: 4px solid {risk_color}; padding: 12px; margin-top: 15px; border-radius: 3px;">
                    <strong style="color: {risk_color};">⚠️ Risk Level: {risk_level}</strong>
                    {f"<p style='margin: 5px 0 0 0; color: #666;'>{plan.get('risk_message', '')}</p>" if plan.get('risk_message') else ''}
                </div>
                '''

            # Additional plan details
            for key, value in plan.items():
                if key in ['description', 'actions', 'records_to_create', 'risk_level', 'risk_message']:
                    continue
                if isinstance(value, (dict, list)):
                    continue

                display_key = key.replace('_', ' ').title()
                html += f'<p style="margin: 10px 0;"><strong>{display_key}:</strong> {value}</p>'

            html += '</div>'
            record.execution_plan_display = html

    @api.depends('execution_result')
    def _compute_execution_result_display(self):
        """Generate human-readable HTML display of execution results"""
        for record in self:
            if not record.execution_result or len(record.execution_result) == 0:
                record.execution_result_display = '<p style="color: #666; font-style: italic;">No execution results yet</p>'
                continue

            result = record.execution_result
            html = '<div style="font-family: sans-serif; padding: 15px; background: #f8f9fa; border-radius: 5px;">'

            # Success/failure message
            if result.get('success'):
                html += '''
                <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; padding: 12px; margin-bottom: 15px;">
                    <i class="fa fa-check-circle" style="color: #28a745; margin-right: 8px;"></i>
                    <strong style="color: #155724;">Execution Successful</strong>
                </div>
                '''
            else:
                html += '''
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 5px; padding: 12px; margin-bottom: 15px;">
                    <i class="fa fa-exclamation-circle" style="color: #dc3545; margin-right: 8px;"></i>
                    <strong style="color: #721c24;">Execution Failed</strong>
                </div>
                '''

            # Main message
            if result.get('message'):
                html += f'<p style="font-size: 16px; color: #2c3e50; margin-bottom: 15px;"><strong>{result["message"]}</strong></p>'

            # Created records
            if result.get('created_records'):
                html += '<h4 style="color: #2c3e50; margin: 15px 0 10px 0;">📄 Created Records:</h4>'
                html += '<ul style="list-style: none; padding: 0;">'
                for record_info in result['created_records']:
                    if isinstance(record_info, dict):
                        model = record_info.get('model', 'Unknown')
                        name = record_info.get('name', 'Unnamed')
                        record_id = record_info.get('id', '')
                        html += f'<li style="padding: 5px 0;">✓ <strong>{model}:</strong> {name} (ID: {record_id})</li>'
                    else:
                        html += f'<li style="padding: 5px 0;">✓ {record_info}</li>'
                html += '</ul>'

            # Other result details
            for key, value in result.items():
                if key in ['success', 'message', 'created_records']:
                    continue

                display_key = key.replace('_', ' ').title()

                if isinstance(value, (dict, list)):
                    continue  # Skip complex nested structures

                html += f'<p><strong>{display_key}:</strong> {value}</p>'

            html += '</div>'
            record.execution_result_display = html

    def _log(self, level, message, payload=None):
        """Create a log entry"""
        self.ensure_one()
        self.env['voice.command.log'].create({
            'session_id': self.id,
            'level': level,
            'message': message,
            'payload_json': payload or {},
        })

    def _validate_slots(self):
        """Validate extracted slots for logical consistency and data validity"""
        self.ensure_one()

        if not self.intent_key:
            return {'valid': True}  # Nothing to validate

        # Check product type compatibility for inventory_adjust
        if self.intent_key == 'inventory_adjust':
            product_id_or_name = self.slots_json.get('product')
            if product_id_or_name:
                Product = self.env['product.product']

                # Try to find product by ID or name
                product = None
                if isinstance(product_id_or_name, int):
                    product = Product.search([('id', '=', product_id_or_name)], limit=1)
                else:
                    product = Product.search([('name', 'ilike', product_id_or_name)], limit=1)

                if product and product.type == 'consu':  # Consumable
                    # Generate clarification
                    clarification = self._generate_product_clarification()
                    if clarification:
                        return {
                            'valid': False,
                            'clarification': {
                                'slot_name': 'product',
                                'question': clarification['question'],
                                'message': clarification['message'],
                                'suggestions': clarification['suggestions']
                            }
                        }

        return {'valid': True}

    def _generate_product_clarification(self):
        """Generate clarification question when product type is incompatible with intent"""
        self.ensure_one()

        if self.intent_key != 'inventory_adjust':
            return None  # Only handle inventory adjust for now

        # Get the selected product
        product_name = self.slots_json.get('product', '')
        if not product_name:
            return None

        # Find stockable alternatives
        Product = self.env['product.product']
        stockable_products = Product.search([
            ('type', '=', 'product'),  # Only stockable products
            ('active', '=', True),
        ], limit=10, order='name')

        if not stockable_products:
            return None

        # Build suggestion list
        suggestions = []
        for prod in stockable_products:
            suggestions.append({
                'id': prod.id,
                'name': prod.name,
                'type': 'Stockable'
            })

        # Generate conversational question
        suggestion_text = ", ".join([f'"{s["name"]}"' for s in suggestions[:5]])
        if len(suggestions) > 5:
            suggestion_text += f" and {len(suggestions) - 5} more..."

        question = f"""I found that "{product_name}" is a consumable product and can't track inventory adjustments.

Here are some stockable products you can adjust instead: {suggestion_text}

Which product did you actually mean to adjust?"""

        message = f'The product "{product_name}" is consumable. Suggesting alternatives...'

        return {
            'question': question,
            'message': message,
            'suggestions': suggestions,
            'product_name': product_name
        }

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
