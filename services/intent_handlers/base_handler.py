# -*- coding: utf-8 -*-

import logging
from odoo import models, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class VoiceIntentHandler(models.AbstractModel):
    """Base class for all intent handlers"""
    _name = 'voice.intent.handler'
    _description = 'Voice Intent Handler Base'

    # Registry of handlers
    _handlers = {}

    @classmethod
    def register_handler(cls, intent_key, handler_class):
        """Register a handler for an intent"""
        cls._handlers[intent_key] = handler_class
        _logger.info(f"Registered handler for intent: {intent_key}")

    @api.model
    def get_handler(self, intent_key):
        """Get handler instance for an intent"""
        handler_class = self._handlers.get(intent_key)
        if not handler_class:
            return None
        return handler_class(self.env)

    def validate_slots(self, slots, schema):
        """
        Validate that required slots are present

        Args:
            slots (dict): Provided slot values
            schema (dict): Slot schema

        Raises:
            ValidationError: If required slots are missing
        """
        missing = []
        for slot_name, slot_def in schema.items():
            if slot_def.get('required', False) and slot_name not in slots:
                missing.append(slot_name)

        if missing:
            raise ValidationError(_(
                'Missing required information: %s'
            ) % ', '.join(missing))

    def simulate(self, slots):
        """
        Simulate execution (dry-run) without making changes

        Args:
            slots (dict): Slot values

        Returns:
            dict: Execution plan
        """
        raise NotImplementedError('Handler must implement simulate()')

    def execute(self, slots):
        """
        Execute the command for real

        Args:
            slots (dict): Slot values

        Returns:
            dict: Execution result
        """
        raise NotImplementedError('Handler must implement execute()')

    def _prepare_result(self, records, message=''):
        """
        Prepare standardized result dict

        Args:
            records (dict): {'created': recordset, 'updated': recordset}
            message (str): Result message

        Returns:
            dict: Standardized result
        """
        result = {
            'success': True,
            'message': message,
            'created_records': [],
            'updated_records': [],
        }

        if records.get('created'):
            for record in records['created']:
                result['created_records'].append({
                    'model': record._name,
                    'id': record.id,
                    'name': record.display_name,
                })

        if records.get('updated'):
            for record in records['updated']:
                result['updated_records'].append({
                    'model': record._name,
                    'id': record.id,
                    'name': record.display_name,
                })

        return result
