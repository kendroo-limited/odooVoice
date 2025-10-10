# -*- coding: utf-8 -*-

import re
import logging
import difflib
from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class VoiceIntentRouter(models.AbstractModel):
    """Service class for parsing voice commands and routing to appropriate handlers"""
    _name = 'voice.intent.router'
    _description = 'Voice Intent Router Service'

    @api.model
    def parse(self, text):
        """
        Parse natural language text into intent + slots

        Args:
            text (str): The command text to parse

        Returns:
            dict: {
                'intent_key': str,
                'slots': dict,
                'missing_slots': list,
                'risk_level': str,
                'confidence': float
            }
        """
        if not text or not text.strip():
            raise UserError(_('No command text provided'))

        text = text.strip().lower()
        _logger.info(f"Parsing command: {text}")

        # Get all active intent templates
        templates = self.env['voice.intent.template'].search([('active', '=', True)])

        if not templates:
            raise UserError(_('No intent templates configured. Please configure intents first.'))

        # Find matching intent
        best_match = None
        best_score = 0.0

        for template in templates:
            score = self._match_intent(text, template)
            if score > best_score:
                best_score = score
                best_match = template

        if not best_match or best_score < 0.3:
            raise UserError(_(
                'Could not understand the command. Please try rephrasing or check available commands.'
            ))

        _logger.info(f"Matched intent: {best_match.key} (confidence: {best_score:.2f})")

        # Extract slots from the text
        slots = self._extract_slots(text, best_match)

        # Determine missing required slots
        schema = best_match.get_slot_schema()
        missing_slots = []

        for slot_name, slot_def in schema.items():
            is_required = slot_def.get('required', False)
            if is_required and slot_name not in slots:
                missing_slots.append(slot_name)

        return {
            'intent_key': best_match.key,
            'slots': slots,
            'missing_slots': missing_slots,
            'risk_level': best_match.risk_level_default,
            'confidence': best_score,
            'template_id': best_match.id,
        }

    @api.model
    def _match_intent(self, text, template):
        """
        Calculate match score between text and intent template

        Args:
            text (str): Command text
            template (voice.intent.template): Template to match against

        Returns:
            float: Confidence score (0.0 to 1.0)
        """
        phrases = template.get_training_phrases_list()
        if not phrases:
            return 0.0

        max_score = 0.0

        for phrase in phrases:
            phrase = phrase.lower()

            # Exact match
            if text == phrase:
                return 1.0

            # Substring match
            if phrase in text or text in phrase:
                max_score = max(max_score, 0.9)

            # Word-based matching
            text_words = set(text.split())
            phrase_words = set(phrase.split())

            common_words = text_words & phrase_words
            if common_words:
                word_score = len(common_words) / max(len(text_words), len(phrase_words))
                max_score = max(max_score, word_score * 0.8)

            # Fuzzy string matching
            ratio = difflib.SequenceMatcher(None, text, phrase).ratio()
            max_score = max(max_score, ratio * 0.7)

        # Boost score based on keyword matching
        intent_keywords = self._get_intent_keywords(template.key)
        for keyword in intent_keywords:
            if keyword in text:
                max_score = min(1.0, max_score + 0.1)

        return max_score

    @api.model
    def _get_intent_keywords(self, intent_key):
        """Get keywords associated with an intent"""
        keyword_map = {
            'sale_create': ['sell', 'sale', 'buy', 'purchase', 'from me', 'invoice'],
            'purchase_create': ['i buy', 'i purchase', 'i order', 'procure', 'vendor'],
            'inventory_adjust': ['inventory', 'stock', 'update', 'adjust', 'warehouse'],
            'crm_lead_create': ['lead', 'opportunity', 'prospect', 'contact'],
            'invoice_register_payment': ['payment', 'pay', 'receive', 'settle'],
        }
        return keyword_map.get(intent_key, [])

    @api.model
    def _extract_slots(self, text, template):
        """
        Extract slot values from text based on intent template

        Args:
            text (str): Command text
            template (voice.intent.template): Intent template

        Returns:
            dict: Extracted slot values
        """
        slots = {}
        schema = template.get_slot_schema()

        # Use slot filler service for entity extraction
        slot_filler = self.env['voice.slot.filler']

        for slot_name, slot_def in schema.items():
            slot_type = slot_def.get('type', 'text')
            value = None

            if slot_type == 'partner':
                value = slot_filler.extract_partner(text)
            elif slot_type == 'product':
                value = slot_filler.extract_product(text)
            elif slot_type == 'product_lines':
                value = slot_filler.extract_product_lines(text)
            elif slot_type == 'quantity':
                value = slot_filler.extract_quantity(text)
            elif slot_type == 'money':
                value = slot_filler.extract_money(text)
            elif slot_type == 'date':
                value = slot_filler.extract_date(text)
            elif slot_type == 'boolean':
                value = slot_filler.extract_boolean(text, slot_name)
            elif slot_type == 'text':
                # Extract text based on patterns or keywords
                value = slot_filler.extract_text(text, slot_name, slot_def)

            if value is not None:
                slots[slot_name] = value

        return slots

    @api.model
    def route(self, intent_key):
        """
        Get the handler for a specific intent

        Args:
            intent_key (str): Intent key

        Returns:
            callable: Handler function
        """
        template = self.env['voice.intent.template'].search([
            ('key', '=', intent_key),
            ('active', '=', True)
        ], limit=1)

        if not template:
            raise UserError(_('Intent "%s" not found or inactive') % intent_key)

        # Check user access
        has_access, error_msg = template.check_user_access()
        if not has_access:
            raise UserError(error_msg)

        # Get handler - look up in intent_handlers registry
        handler_registry = self.env['voice.intent.handler']
        handler = handler_registry.get_handler(intent_key)

        if not handler:
            raise UserError(_('No handler found for intent "%s"') % intent_key)

        return handler

    @api.model
    def simulate(self, intent_key, slots):
        """
        Simulate command execution without making changes

        Args:
            intent_key (str): Intent key
            slots (dict): Slot values

        Returns:
            dict: Execution plan
        """
        handler = self.route(intent_key)

        # Run in simulation mode
        with self.env.cr.savepoint():
            plan = handler.simulate(slots)

        return plan

    @api.model
    def execute(self, intent_key, slots):
        """
        Execute the command for real

        Args:
            intent_key (str): Intent key
            slots (dict): Slot values

        Returns:
            dict: Execution result
        """
        handler = self.route(intent_key)

        # Increment usage counter
        template = self.env['voice.intent.template'].search([
            ('key', '=', intent_key)
        ], limit=1)
        if template:
            template.increment_usage()

        # Execute with savepoint for safety
        with self.env.cr.savepoint():
            result = handler.execute(slots)

        return result
