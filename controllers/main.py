# -*- coding: utf-8 -*-

import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class VoiceCommandController(http.Controller):

    @http.route('/voice/command', type='json', auth='user', methods=['POST'], csrf=False)
    def voice_command(self, **kw):
        """
        Process a voice command via HTTP endpoint

        Args:
            text (str): Command text
            dry_run (bool, optional): If True, only simulate
            user_id (int, optional): User ID (defaults to current user)

        Returns:
            dict: {
                'success': bool,
                'session_id': int,
                'state': str,
                'next_questions': list,
                'plan': dict,
                'result': dict,
                'logs': list
            }
        """
        text = kw.get('text')
        if not text:
            return {
                'success': False,
                'error': 'No command text provided'
            }

        dry_run = kw.get('dry_run', True)
        user_id = kw.get('user_id', request.env.user.id)

        try:
            # Create session
            session = request.env['voice.command.session'].create({
                'transcript': text,
                'dry_run': dry_run,
                'user_id': user_id,
            })

            # Parse command
            session.action_parse()

            # Get next questions if any
            next_questions = []
            if session.missing_slots_json:
                next_question = session.get_next_question()
                if next_question:
                    next_questions.append(next_question)

            # If ready and not dry run, simulate
            plan = None
            if session.state == 'ready':
                session.action_simulate()
                plan = session.execution_plan

            # Prepare response
            response = {
                'success': True,
                'session_id': session.id,
                'state': session.state,
                'intent_key': session.intent_key,
                'slots': session.slots_json,
                'missing_slots': session.missing_slots_json,
                'next_questions': next_questions,
                'plan': plan,
                'risk_level': session.risk_level,
                'confirmation_required': session.confirmation_required,
            }

            # Get logs
            logs = []
            for log in session.log_ids:
                logs.append({
                    'timestamp': log.timestamp.isoformat() if log.timestamp else None,
                    'level': log.level,
                    'message': log.message,
                })
            response['logs'] = logs

            return response

        except Exception as e:
            _logger.exception("Error processing voice command")
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/voice/command/<int:session_id>/execute', type='json', auth='user', methods=['POST'])
    def voice_command_execute(self, session_id, **kw):
        """
        Execute a voice command session

        Args:
            session_id (int): Session ID
            confirm (bool, optional): User confirmation

        Returns:
            dict: Execution result
        """
        try:
            session = request.env['voice.command.session'].browse(session_id)

            if not session.exists():
                return {
                    'success': False,
                    'error': 'Session not found'
                }

            # Check confirmation if required
            if kw.get('confirm'):
                session.action_confirm()

            # Execute
            session.action_execute()

            return {
                'success': True,
                'session_id': session.id,
                'state': session.state,
                'result': session.execution_result,
                'result_summary': session.result_summary,
            }

        except Exception as e:
            _logger.exception("Error executing voice command")
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/voice/command/<int:session_id>/fill_slot', type='json', auth='user', methods=['POST'])
    def voice_command_fill_slot(self, session_id, slot_name, slot_value, **kw):
        """
        Fill a slot in a voice command session

        Args:
            session_id (int): Session ID
            slot_name (str): Slot name
            slot_value: Slot value

        Returns:
            dict: Updated session info
        """
        try:
            session = request.env['voice.command.session'].browse(session_id)

            if not session.exists():
                return {
                    'success': False,
                    'error': 'Session not found'
                }

            # Fill slot
            session.action_fill_slot(slot_name, slot_value)

            # Get next question if any
            next_question = session.get_next_question()

            return {
                'success': True,
                'session_id': session.id,
                'state': session.state,
                'slots': session.slots_json,
                'missing_slots': session.missing_slots_json,
                'next_question': next_question,
            }

        except Exception as e:
            _logger.exception("Error filling slot")
            return {
                'success': False,
                'error': str(e)
            }
