# -*- coding: utf-8 -*-

import json
import logging
from odoo import models, api, _

_logger = logging.getLogger(__name__)


class VoiceLLMAssistant(models.AbstractModel):
    """LLM-powered conversational assistant for voice commands"""
    _name = 'voice.llm.assistant'
    _description = 'Voice LLM Assistant'

    @api.model
    def generate_natural_question(self, slot_name, slot_def, intent_key, current_transcript):
        """
        Generate a natural, conversational question for a missing slot

        Args:
            slot_name (str): Name of the missing slot
            slot_def (dict): Slot definition from intent template
            intent_key (str): The intent being processed
            current_transcript (str): What the user has said so far

        Returns:
            str: Natural language question
        """
        # Check if LLM is available (e.g., OpenAI, local LLM, etc.)
        use_llm = self.env['ir.config_parameter'].sudo().get_param(
            'voice_command_hub.use_llm_questions', default='False'
        ) == 'True'

        if use_llm:
            return self._generate_llm_question(slot_name, slot_def, intent_key, current_transcript)
        else:
            return self._generate_template_question(slot_name, slot_def, intent_key)

    @api.model
    def _generate_template_question(self, slot_name, slot_def, intent_key):
        """Generate question from templates (fallback when no LLM)"""
        base_question = slot_def.get('question', f'Please provide {slot_name}')
        help_text = slot_def.get('help', '')

        # Add context based on intent type
        intent_context = {
            'sale_create': 'for this sale order',
            'purchase_create': 'for this purchase order',
            'inventory_adjust': 'for this inventory adjustment',
            'crm_lead_create': 'for this lead',
            'invoice_register_payment': 'for this payment',
        }

        context = intent_context.get(intent_key, '')

        # Build conversational question
        if slot_name == 'contact':
            return f"📋 {base_question}\n\n💡 {help_text}" if help_text else base_question
        elif slot_name == 'partner':
            return f"👤 Who is the customer {context}?"
        elif slot_name == 'vendor':
            return f"🏢 Who is the supplier/vendor {context}?"
        elif slot_name == 'product':
            return f"📦 Which product {context}?"
        elif slot_name == 'product_lines':
            return f"📦 What products and quantities would you like {context}?\n\n💡 Example: '5 apples and 10 oranges'"
        elif slot_name == 'quantity' or slot_name == 'qty_delta':
            return f"🔢 How many units {context}?"
        elif slot_name == 'amount':
            return f"💰 What is the payment amount?"
        elif slot_name == 'title':
            return f"📝 What title would you like to give this {intent_key.replace('_', ' ')}?"
        else:
            return f"{base_question}\n\n{help_text}" if help_text else base_question

    @api.model
    def _generate_llm_question(self, slot_name, slot_def, intent_key, current_transcript):
        """
        Use LLM to generate contextual, conversational question

        This method can be extended to call OpenAI, Anthropic Claude,
        or a local LLM like Llama/Mistral
        """
        try:
            # Get LLM provider configuration
            llm_provider = self.env['ir.config_parameter'].sudo().get_param(
                'voice_command_hub.llm_provider', default='openai'
            )

            if llm_provider == 'openai':
                return self._generate_openai_question(slot_name, slot_def, intent_key, current_transcript)
            elif llm_provider == 'anthropic':
                return self._generate_anthropic_question(slot_name, slot_def, intent_key, current_transcript)
            elif llm_provider == 'local':
                return self._generate_local_llm_question(slot_name, slot_def, intent_key, current_transcript)
            else:
                # Fallback to template
                return self._generate_template_question(slot_name, slot_def, intent_key)

        except Exception as e:
            _logger.warning(f"LLM question generation failed: {e}, using template fallback")
            return self._generate_template_question(slot_name, slot_def, intent_key)

    @api.model
    def _generate_openai_question(self, slot_name, slot_def, intent_key, current_transcript):
        """Generate question using OpenAI API"""
        try:
            import openai

            api_key = self.env['ir.config_parameter'].sudo().get_param(
                'voice_command_hub.openai_api_key'
            )

            if not api_key:
                return self._generate_template_question(slot_name, slot_def, intent_key)

            openai.api_key = api_key

            prompt = f"""You are a helpful assistant for an Odoo ERP system. A user is trying to {intent_key.replace('_', ' ')}.

User's command so far: "{current_transcript}"

We need to collect: {slot_name} ({slot_def.get('type', 'text')})
Description: {slot_def.get('help', slot_def.get('question', ''))}

Generate a single, friendly, conversational question (one sentence) to ask the user for this information.
Be natural and helpful. Don't use technical terms. Just ask the question directly."""

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.7
            )

            question = response.choices[0].message.content.strip()
            return question

        except Exception as e:
            _logger.error(f"OpenAI API error: {e}")
            return self._generate_template_question(slot_name, slot_def, intent_key)

    @api.model
    def _generate_anthropic_question(self, slot_name, slot_def, intent_key, current_transcript):
        """Generate question using Anthropic Claude API"""
        try:
            import anthropic

            api_key = self.env['ir.config_parameter'].sudo().get_param(
                'voice_command_hub.anthropic_api_key'
            )

            if not api_key:
                return self._generate_template_question(slot_name, slot_def, intent_key)

            client = anthropic.Anthropic(api_key=api_key)

            prompt = f"""You are a helpful assistant for an Odoo ERP system. A user is trying to {intent_key.replace('_', ' ')}.

User's command so far: "{current_transcript}"

We need to collect: {slot_name} ({slot_def.get('type', 'text')})
Description: {slot_def.get('help', slot_def.get('question', ''))}

Generate a single, friendly, conversational question (one sentence) to ask the user for this information."""

            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )

            question = message.content[0].text.strip()
            return question

        except Exception as e:
            _logger.error(f"Anthropic API error: {e}")
            return self._generate_template_question(slot_name, slot_def, intent_key)

    @api.model
    def _generate_local_llm_question(self, slot_name, slot_def, intent_key, current_transcript):
        """
        Generate question using local LLM (e.g., Ollama, llama.cpp)

        This can be extended to use local models via:
        - Ollama API
        - llama.cpp server
        - Hugging Face Transformers
        """
        try:
            import requests

            ollama_url = self.env['ir.config_parameter'].sudo().get_param(
                'voice_command_hub.ollama_url', default='http://localhost:11434'
            )

            model = self.env['ir.config_parameter'].sudo().get_param(
                'voice_command_hub.ollama_model', default='llama2'
            )

            prompt = f"""You are a helpful assistant. A user said: "{current_transcript}"

We need to know: {slot_def.get('help', slot_name)}

Ask a friendly question (one sentence only):"""

            response = requests.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.7, "max_tokens": 50}
                },
                timeout=5
            )

            if response.status_code == 200:
                result = response.json()
                question = result.get('response', '').strip()
                # Take only first sentence
                question = question.split('.')[0] + '?'
                return question

        except Exception as e:
            _logger.warning(f"Local LLM error: {e}")

        return self._generate_template_question(slot_name, slot_def, intent_key)

    @api.model
    def extract_slot_with_llm(self, text, slot_name, slot_def, intent_key):
        """
        Use LLM to intelligently extract slot value from text

        This is more powerful than regex patterns for complex extractions
        """
        use_llm = self.env['ir.config_parameter'].sudo().get_param(
            'voice_command_hub.use_llm_extraction', default='False'
        ) == 'True'

        if not use_llm:
            return None

        try:
            llm_provider = self.env['ir.config_parameter'].sudo().get_param(
                'voice_command_hub.llm_provider', default='openai'
            )

            if llm_provider == 'openai':
                return self._extract_with_openai(text, slot_name, slot_def, intent_key)
            elif llm_provider == 'local':
                return self._extract_with_local_llm(text, slot_name, slot_def, intent_key)

        except Exception as e:
            _logger.warning(f"LLM extraction failed: {e}")

        return None

    @api.model
    def _extract_with_openai(self, text, slot_name, slot_def, intent_key):
        """Extract slot using OpenAI structured outputs"""
        try:
            import openai

            api_key = self.env['ir.config_parameter'].sudo().get_param(
                'voice_command_hub.openai_api_key'
            )

            if not api_key:
                return None

            openai.api_key = api_key

            prompt = f"""Extract the {slot_name} from this text: "{text}"

{slot_name} should be a {slot_def.get('type', 'text')}.
{slot_def.get('help', '')}

Return ONLY the extracted value, nothing else. If not found, return "NOT_FOUND"."""

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0
            )

            result = response.choices[0].message.content.strip()

            if result and result != "NOT_FOUND":
                return result

        except Exception as e:
            _logger.error(f"OpenAI extraction error: {e}")

        return None

    @api.model
    def _extract_with_local_llm(self, text, slot_name, slot_def, intent_key):
        """Extract slot using local LLM (Ollama)"""
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

            # Build extraction prompt
            slot_type = slot_def.get('type', 'text')
            slot_description = slot_def.get('help', f'the {slot_name}')

            prompt = f"""Extract {slot_description} from the following text.

Intent: {intent_key}
Text: "{text}"
Slot to extract: {slot_name} (type: {slot_type})

Instructions:
- Extract ONLY the {slot_name} value
- Return just the extracted value, nothing else
- If multiple values exist, return the most relevant one
- If not found or unclear, return "NOT_FOUND"

Examples:
- Text: "sell 5 apples to John" → partner: John, product: apples, quantity: 5
- Text: "I bought 100 chocolates from vendor ABC" → vendor: ABC, product: chocolates, quantity: 100
- Text: "increase chocolate stock by 200" → product: chocolate, quantity: 200

Now extract {slot_name} from: "{text}"
{slot_name}: """

            response = requests.post(
                f"{ollama_url}/api/generate",
                json={
                    'model': ollama_model,
                    'prompt': prompt,
                    'stream': False,
                    'options': {
                        'temperature': 0.1,  # Low temperature for consistency
                        'num_predict': 50,   # Short responses only
                    }
                },
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                extracted = result.get('response', '').strip()

                # Clean up response - remove quotes
                extracted = extracted.replace('"', '').replace("'", '').strip()

                # Check for not found indicators
                if extracted.upper() in ['NOT_FOUND', 'NONE', 'N/A', 'NULL', '']:
                    return None

                # Clean up common artifacts
                extracted = extracted.split('.')[0].strip()  # Take first sentence only
                extracted = extracted.split(',')[0].strip()  # Take first item if multiple

                _logger.info(f"LLM extracted {slot_name}: {extracted}")
                return extracted

        except requests.exceptions.Timeout:
            _logger.warning(f"Ollama timeout for {slot_name} extraction")
            return None
        except requests.exceptions.ConnectionError:
            _logger.warning(f"Cannot connect to Ollama at {ollama_url}")
            return None
        except Exception as e:
            _logger.warning(f"Ollama extraction failed for {slot_name}: {e}")
            return None
