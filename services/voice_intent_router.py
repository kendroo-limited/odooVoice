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

        Uses LLM disambiguation when top 2 intents have similar scores.

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

        # Find matching intents (get all scores, not just top)
        matches = []
        for template in templates:
            score = self._match_intent(text, template)
            if score > 0.0:  # Include any match for disambiguation
                matches.append({
                    'template': template,
                    'intent_key': template.key,
                    'confidence': score
                })

        if not matches:
            raise UserError(_(
                'Could not understand the command. Please try rephrasing or check available commands.'
            ))

        # Sort by confidence
        matches.sort(key=lambda x: x['confidence'], reverse=True)

        # Check if top 2 intents are close (might need LLM disambiguation)
        best_match = matches[0]

        if len(matches) >= 2:
            top1_score = matches[0]['confidence']
            top2_score = matches[1]['confidence']
            confidence_gap = top1_score - top2_score

            # If gap is small (< 0.15), try LLM to disambiguate
            disambiguation_gap = float(self.env['ir.config_parameter'].sudo().get_param(
                'voice_command_hub.intent_disambiguation_gap',
                '0.15'
            ))

            if confidence_gap < disambiguation_gap:
                llm_choice = self._disambiguate_intent_with_llm(
                    text,
                    matches[:2]  # Top 2 closest matches
                )
                if llm_choice:
                    best_match = llm_choice
                    _logger.info(f"LLM disambiguated: {best_match['intent_key']} (gap was {confidence_gap:.2f})")

        if not best_match or best_match['confidence'] < 0.3:
            raise UserError(_(
                'Could not understand the command. Please try rephrasing or check available commands.'
            ))

        _logger.info(f"Matched intent: {best_match['intent_key']} (confidence: {best_match['confidence']:.2f})")

        # Extract slots from the text
        slots = self._extract_slots(text, best_match['template'])

        # Determine missing required slots
        schema = best_match['template'].get_slot_schema()
        missing_slots = []

        for slot_name, slot_def in schema.items():
            is_required = slot_def.get('required', False)
            if is_required and slot_name not in slots:
                missing_slots.append(slot_name)

        return {
            'intent_key': best_match['intent_key'],
            'slots': slots,
            'missing_slots': missing_slots,
            'risk_level': best_match['template'].risk_level_default,
            'confidence': best_match['confidence'],
            'template_id': best_match['template'].id,
        }

    @api.model
    def _match_intent(self, text, template):
        """
        Calculate match score between text and intent template

        Uses context-aware keyword weighting to resolve ambiguity.
        Example: "buy" matches differently based on context:
        - "customer buy from me" → sale_create (customer buying FROM me)
        - "i buy from vendor" → purchase_create (I buying FROM vendor)

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

        # Context-aware keyword weighting
        intent_keywords = self._get_intent_keywords(template.key)

        # Check for negative keywords (strong penalty)
        has_negative = any(neg in text for neg in intent_keywords.get('negative', []))
        if has_negative:
            max_score = max(0.0, max_score - 0.25)  # Strong penalty

        # Check for strong keywords
        for keyword in intent_keywords.get('strong', []):
            if keyword in text:
                max_score = min(1.0, max_score + 0.2)  # Stronger boost

        # Check for weak keywords (only if no negative keywords)
        if not has_negative:
            for keyword in intent_keywords.get('weak', []):
                if keyword in text:
                    max_score = min(1.0, max_score + 0.08)  # Weaker boost

        return max_score

    @api.model
    def _get_intent_keywords(self, intent_key):
        """
        Get context-aware keywords for intent disambiguation

        Returns dict with 'strong', 'weak', and 'negative' keywords for each intent.
        This prevents ambiguity: "buy" means different things depending on context.
        """
        keyword_map = {
            'sale_create': {
                'strong': ['sell', 'sold', 'sold to', 'customer', 'customer bought', 'invoice'],
                'weak': ['buy', 'bought'],  # Only if customer is buying FROM me
                'negative': ['from', 'vendor', 'supplier', 'i buy', 'i purchase']  # These indicate purchase
            },
            'purchase_create': {
                'strong': ['purchase', 'purchased', 'buy from', 'vendor', 'supplier', 'from vendor'],
                'weak': ['buy', 'bought'],  # Only if I'm buying FROM vendor/supplier
                'negative': ['sell', 'customer', 'to', 'invoice', 'sold to']  # These indicate sale
            },
            'inventory_adjust': {
                'strong': ['inventory', 'stock', 'warehouse', 'adjust', 'update'],
                'weak': ['increase', 'decrease', 'add', 'remove'],
                'negative': ['sell', 'buy', 'purchase', 'vendor', 'customer']
            },
            'crm_lead_create': {
                'strong': ['lead', 'opportunity', 'prospect', 'new lead', 'new opportunity'],
                'weak': ['contact', 'company'],
                'negative': ['sell', 'buy', 'inventory', 'purchase']
            },
            'invoice_register_payment': {
                'strong': ['payment', 'pay', 'settle', 'receive payment', 'payment received'],
                'weak': ['paid', 'amount'],
                'negative': ['sell', 'buy', 'inventory', 'lead']
            },
        }
        return keyword_map.get(intent_key, {'strong': [], 'weak': [], 'negative': []})

    @api.model
    def _disambiguate_intent_with_llm(self, text, top_matches):
        """
        Use LLM to disambiguate between close-scoring intents

        Args:
            text (str): The command text
            top_matches (list): List of top 2 match dicts with 'intent_key', 'confidence'

        Returns:
            dict: The chosen match dict, or None if LLM can't decide
        """
        # Check if LLM is enabled
        use_llm = self.env['ir.config_parameter'].sudo().get_param(
            'voice_command_hub.use_llm_extraction',
            'False'
        ) == 'True'

        if not use_llm:
            return None  # Fall back to rule-based choice

        try:
            import requests

            # Get Ollama configuration
            ollama_url = self.env['ir.config_parameter'].sudo().get_param(
                'voice_command_hub.ollama_url',
                'http://host.docker.internal:11434'
            )
            ollama_model = self.env['ir.config_parameter'].sudo().get_param(
                'voice_command_hub.ollama_model',
                'llama2'
            )

            # Build intent descriptions
            intent_descriptions = {
                'sale_create': 'Customer is BUYING FROM me (I am selling to customer)',
                'purchase_create': 'I am BUYING FROM a vendor (vendor is selling to me)',
                'inventory_adjust': 'Adjusting stock levels in warehouse (no sale/purchase)',
                'crm_lead_create': 'Creating a new CRM lead or opportunity',
                'invoice_register_payment': 'Registering a payment for an invoice',
            }

            # Build prompt
            options_text = ""
            for i, match in enumerate(top_matches, 1):
                intent_key = match['intent_key']
                desc = intent_descriptions.get(intent_key, intent_key)
                options_text += f"{i}. {intent_key}: {desc}\n"

            prompt = f"""Given the user's command, determine which business intent it represents.

User command: "{text}"

Which of these intents matches best?

{options_text}

Answer with ONLY the intent key (e.g., "sale_create" or "purchase_create"), nothing else. No explanation needed.
"""

            # Call Ollama
            response = requests.post(
                f"{ollama_url}/api/generate",
                json={
                    'model': ollama_model,
                    'prompt': prompt,
                    'stream': False,
                    'options': {
                        'temperature': 0.1,  # Low temp for consistency
                        'num_predict': 30,   # Short response
                    }
                },
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                llm_choice = result.get('response', '').strip().lower()

                # Clean up response
                llm_choice = llm_choice.replace('*', '').replace('"', '').strip()

                # Find matching intent from top_matches
                for match in top_matches:
                    if match['intent_key'].lower() in llm_choice or llm_choice.endswith(match['intent_key'].lower()):
                        _logger.info(f"LLM selected intent: {match['intent_key']}")
                        return match

        except Exception as e:
            _logger.warning(f"LLM intent disambiguation failed: {e}")

        return None

    @api.model
    def _extract_slots(self, text, template):
        """
        Extract slot values from text based on intent template

        Uses LLM extraction (if enabled) with rule-based fallback for accuracy.

        Args:
            text (str): Command text
            template (voice.intent.template): Intent template

        Returns:
            dict: Extracted slot values
        """
        slots = {}
        schema = template.get_slot_schema()

        # Check if LLM extraction is enabled
        use_llm = self.env['ir.config_parameter'].sudo().get_param(
            'voice_command_hub.use_llm_extraction',
            'False'
        ) == 'True'

        llm_assistant = self.env['voice.llm.assistant']
        slot_filler = self.env['voice.slot.filler']

        for slot_name, slot_def in schema.items():
            slot_type = slot_def.get('type', 'text')
            value = None

            # Try LLM extraction first if enabled
            if use_llm:
                try:
                    value = llm_assistant.extract_slot_with_llm(
                        text,
                        slot_name,
                        slot_def,
                        template.key
                    )
                    if value:
                        _logger.info(f"LLM extracted {slot_name}: {value}")
                except Exception as e:
                    _logger.warning(f"LLM extraction failed for {slot_name}: {e}")
                    value = None  # Fall through to rule-based

            # Fallback to rule-based if LLM didn't extract
            if not value:
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

                if value:
                    _logger.debug(f"Rule-based extraction for {slot_name}: {value}")

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
