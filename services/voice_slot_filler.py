# -*- coding: utf-8 -*-

import re
import logging
from datetime import datetime, timedelta
import difflib
from odoo import models, api, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

_logger = logging.getLogger(__name__)


class VoiceSlotFiller(models.AbstractModel):
    """Service class for extracting and normalizing entities from text"""
    _name = 'voice.slot.filler'
    _description = 'Voice Slot Filler Service'

    @api.model
    def extract_partner(self, text):
        """
        Extract partner from text by name, email, or phone

        Args:
            text (str): Text to extract from

        Returns:
            int: Partner ID or None
        """
        # Try to find partner name in text
        partners = self.env['res.partner'].search([])

        threshold = float(self.env['ir.config_parameter'].sudo().get_param(
            'voice_command_hub.fuzzy_match_threshold', default='0.8'
        ))

        best_match = None
        best_score = 0.0

        for partner in partners:
            if not partner.name:
                continue

            partner_name = partner.name.lower()
            text_lower = text.lower()

            # Exact match
            if partner_name in text_lower:
                return partner.id

            # Fuzzy match
            score = difflib.SequenceMatcher(None, partner_name, text_lower).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_match = partner.id

        # Try email pattern
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        if emails:
            partner = self.env['res.partner'].search([
                ('email', 'ilike', emails[0])
            ], limit=1)
            if partner:
                return partner.id

        # Try phone pattern
        phone_pattern = r'\+?\d[\d\s\-\(\)]{7,}\d'
        phones = re.findall(phone_pattern, text)
        if phones:
            phone = phones[0].replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            partner = self.env['res.partner'].search([
                '|', ('phone', 'like', phone), ('mobile', 'like', phone)
            ], limit=1)
            if partner:
                return partner.id

        return best_match

    @api.model
    def extract_product(self, text):
        """
        Extract product from text by name or reference

        Args:
            text (str): Text to extract from

        Returns:
            int: Product ID or None
        """
        products = self.env['product.product'].search([
            '|', ('sale_ok', '=', True), ('purchase_ok', '=', True)
        ])

        threshold = float(self.env['ir.config_parameter'].sudo().get_param(
            'voice_command_hub.fuzzy_match_threshold', default='0.8'
        ))

        best_match = None
        best_score = 0.0

        for product in products:
            product_name = (product.name or '').lower()
            text_lower = text.lower()

            # Exact match
            if product_name in text_lower:
                return product.id

            # Check default_code (internal reference)
            if product.default_code and product.default_code.lower() in text_lower:
                return product.id

            # Fuzzy match
            score = difflib.SequenceMatcher(None, product_name, text_lower).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_match = product.id

        return best_match

    @api.model
    def extract_product_lines(self, text):
        """
        Extract product lines (product + quantity) from text

        Args:
            text (str): Text to extract from

        Returns:
            list: [{product_id, qty, uom_id}]
        """
        lines = []

        # Pattern: number + product name
        # e.g., "100 chocolate", "5 kg apples"
        pattern = r'(\d+(?:\.\d+)?)\s+([a-zA-Z\s]+?)(?:\s|$|,|\.)'
        matches = re.findall(pattern, text, re.IGNORECASE)

        for qty_str, product_text in matches:
            try:
                qty = float(qty_str)
                product_id = self.extract_product(product_text.strip())

                if product_id:
                    product = self.env['product.product'].browse(product_id)
                    lines.append({
                        'product_id': product_id,
                        'qty': qty,
                        'uom_id': product.uom_id.id,
                        'product_name': product.name,
                    })
            except ValueError:
                continue

        # If no lines found, try to find just product without quantity
        if not lines:
            product_id = self.extract_product(text)
            if product_id:
                product = self.env['product.product'].browse(product_id)
                lines.append({
                    'product_id': product_id,
                    'qty': 1.0,  # Default quantity
                    'uom_id': product.uom_id.id,
                    'product_name': product.name,
                })

        return lines

    @api.model
    def extract_quantity(self, text):
        """
        Extract quantity/number from text

        Args:
            text (str): Text to extract from

        Returns:
            float: Quantity or None
        """
        # Pattern: number (with optional decimal)
        pattern = r'\b(\d+(?:\.\d+)?)\b'
        matches = re.findall(pattern, text)

        if matches:
            try:
                return float(matches[0])
            except ValueError:
                pass

        return None

    @api.model
    def extract_money(self, text):
        """
        Extract monetary amount from text

        Args:
            text (str): Text to extract from

        Returns:
            dict: {amount: float, currency: str} or None
        """
        # Patterns for money: $100, 100 USD, 100.50 EUR
        patterns = [
            r'\$(\d+(?:\.\d{2})?)',  # $100.50
            r'(\d+(?:\.\d{2})?)\s*(USD|EUR|GBP|usd|eur|gbp)',  # 100.50 USD
            r'(USD|EUR|GBP)\s*(\d+(?:\.\d{2})?)',  # USD 100.50
        ]

        for pattern in patterns:
            matches = re.search(pattern, text)
            if matches:
                groups = matches.groups()
                if pattern == patterns[0]:  # $100.50
                    return {'amount': float(groups[0]), 'currency': 'USD'}
                elif pattern == patterns[1]:  # 100.50 USD
                    return {'amount': float(groups[0]), 'currency': groups[1].upper()}
                elif pattern == patterns[2]:  # USD 100.50
                    return {'amount': float(groups[1]), 'currency': groups[0].upper()}

        # Try to extract just a number
        qty = self.extract_quantity(text)
        if qty:
            # Use company currency as default
            currency = self.env.company.currency_id
            return {'amount': qty, 'currency': currency.name}

        return None

    @api.model
    def extract_date(self, text):
        """
        Extract date from text

        Args:
            text (str): Text to extract from

        Returns:
            str: Date in Odoo format or None
        """
        text_lower = text.lower()
        today = datetime.now().date()

        # Relative dates
        if 'today' in text_lower:
            return today.strftime(DEFAULT_SERVER_DATE_FORMAT)
        elif 'tomorrow' in text_lower:
            return (today + timedelta(days=1)).strftime(DEFAULT_SERVER_DATE_FORMAT)
        elif 'yesterday' in text_lower:
            return (today - timedelta(days=1)).strftime(DEFAULT_SERVER_DATE_FORMAT)

        # Pattern: YYYY-MM-DD
        pattern = r'(\d{4})-(\d{2})-(\d{2})'
        matches = re.search(pattern, text)
        if matches:
            return matches.group(0)

        # Pattern: DD/MM/YYYY or MM/DD/YYYY
        pattern = r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})'
        matches = re.search(pattern, text)
        if matches:
            day, month, year = matches.groups()
            try:
                date = datetime(int(year), int(month), int(day))
                return date.strftime(DEFAULT_SERVER_DATE_FORMAT)
            except ValueError:
                pass

        return None

    @api.model
    def extract_boolean(self, text, slot_name):
        """
        Extract boolean value from text

        Args:
            text (str): Text to extract from
            slot_name (str): Name of the boolean slot

        Returns:
            bool: True/False or None
        """
        text_lower = text.lower()

        # Positive indicators
        positive = ['yes', 'true', 'confirm', 'do it', 'proceed', 'invoice now', 'bill now']
        for word in positive:
            if word in text_lower:
                return True

        # Negative indicators
        negative = ['no', 'false', 'cancel', 'abort', 'don\'t', 'do not']
        for word in negative:
            if word in text_lower:
                return False

        # Context-specific for common slots
        if slot_name in ['confirm', 'invoice_now', 'bill_now']:
            if 'invoice' in text_lower or 'bill' in text_lower:
                return 'now' in text_lower or 'immediately' in text_lower

        return None

    @api.model
    def extract_text(self, text, slot_name, slot_def):
        """
        Extract general text value

        Args:
            text (str): Text to extract from
            slot_name (str): Slot name
            slot_def (dict): Slot definition

        Returns:
            str: Extracted text or None
        """
        # Look for patterns in slot definition
        patterns = slot_def.get('patterns', [])

        for pattern in patterns:
            matches = re.search(pattern, text, re.IGNORECASE)
            if matches:
                return matches.group(1) if matches.groups() else matches.group(0)

        # Try to extract based on keywords
        keywords = slot_def.get('keywords', [])
        for keyword in keywords:
            if keyword.lower() in text.lower():
                # Extract text after keyword
                idx = text.lower().find(keyword.lower())
                after_keyword = text[idx + len(keyword):].strip()
                # Take first few words
                words = after_keyword.split()[:3]
                return ' '.join(words)

        return None

    @api.model
    def normalize_partner(self, partner_value):
        """
        Normalize partner value to partner record

        Args:
            partner_value: Can be ID, name, email, or phone

        Returns:
            recordset: res.partner record
        """
        if isinstance(partner_value, int):
            return self.env['res.partner'].browse(partner_value)

        if isinstance(partner_value, str):
            # Try by exact name
            partner = self.env['res.partner'].search([
                ('name', '=ilike', partner_value)
            ], limit=1)
            if partner:
                return partner

            # Try by email
            if '@' in partner_value:
                partner = self.env['res.partner'].search([
                    ('email', '=ilike', partner_value)
                ], limit=1)
                if partner:
                    return partner

            # Try fuzzy name search
            partner_id = self.extract_partner(partner_value)
            if partner_id:
                return self.env['res.partner'].browse(partner_id)

        return self.env['res.partner']

    @api.model
    def normalize_product(self, product_value):
        """
        Normalize product value to product record

        Args:
            product_value: Can be ID, name, or reference

        Returns:
            recordset: product.product record
        """
        if isinstance(product_value, int):
            return self.env['product.product'].browse(product_value)

        if isinstance(product_value, str):
            # Try by exact name
            product = self.env['product.product'].search([
                ('name', '=ilike', product_value)
            ], limit=1)
            if product:
                return product

            # Try by default_code
            product = self.env['product.product'].search([
                ('default_code', '=ilike', product_value)
            ], limit=1)
            if product:
                return product

            # Try fuzzy search
            product_id = self.extract_product(product_value)
            if product_id:
                return self.env['product.product'].browse(product_id)

        return self.env['product.product']
