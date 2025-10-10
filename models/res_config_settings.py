# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # General Settings
    voice_command_enabled = fields.Boolean(
        string='Enable Voice Commands',
        config_parameter='voice_command_hub.enabled',
        default=True
    )
    voice_command_language = fields.Selection([
        ('en', 'English'),
        ('fr', 'French'),
        ('es', 'Spanish'),
        ('de', 'German'),
        ('ar', 'Arabic'),
    ], string='Command Language',
        config_parameter='voice_command_hub.language',
        default='en'
    )

    # Confirmation Policy
    confirm_high_risk = fields.Boolean(
        string='Confirm High-Risk Actions',
        config_parameter='voice_command_hub.confirm_high_risk',
        default=True,
        help='Require confirmation for high-risk actions (posting, payments, etc.)'
    )
    confirm_medium_risk = fields.Boolean(
        string='Confirm Medium-Risk Actions',
        config_parameter='voice_command_hub.confirm_medium_risk',
        default=True,
        help='Require confirmation for medium-risk actions (confirmations, validations)'
    )

    # Auto-creation Settings
    auto_create_partner = fields.Boolean(
        string='Auto-create Partners',
        config_parameter='voice_command_hub.auto_create_partner',
        default=False,
        help='Automatically create partners if not found (requires unique identifier)'
    )
    auto_create_product = fields.Boolean(
        string='Auto-create Products',
        config_parameter='voice_command_hub.auto_create_product',
        default=False,
        help='Automatically create products if not found'
    )

    # Default Values
    voice_default_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Default Warehouse for Voice Commands',
        help='Default warehouse to use when creating orders via voice'
    )
    voice_default_location_id = fields.Many2one(
        'stock.location',
        string='Default Location for Voice Commands',
        help='Default location for inventory adjustments via voice'
    )
    voice_default_pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Default Pricelist for Voice Commands',
        help='Default pricelist for sale orders created via voice'
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        params = self.env['ir.config_parameter'].sudo()

        # Many2one fields
        res.update(
            voice_default_warehouse_id=int(params.get_param('voice_command_hub.default_warehouse_id', 0)) or False,
            voice_default_location_id=int(params.get_param('voice_command_hub.default_location_id', 0)) or False,
            voice_default_pricelist_id=int(params.get_param('voice_command_hub.default_pricelist_id', 0)) or False,
        )

        # Many2many field
        group_ids_str = params.get_param('voice_command_hub.allowed_group_ids', '')
        if group_ids_str:
            group_ids = [int(gid) for gid in group_ids_str.split(',') if gid]
            res['allowed_group_ids'] = [(6, 0, group_ids)]

        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        params = self.env['ir.config_parameter'].sudo()

        # Many2one fields
        params.set_param('voice_command_hub.default_warehouse_id', self.voice_default_warehouse_id.id or 0)
        params.set_param('voice_command_hub.default_location_id', self.voice_default_location_id.id or 0)
        params.set_param('voice_command_hub.default_pricelist_id', self.voice_default_pricelist_id.id or 0)

        # Many2many field
        if self.allowed_group_ids:
            group_ids_str = ','.join(str(gid) for gid in self.allowed_group_ids.ids)
            params.set_param('voice_command_hub.allowed_group_ids', group_ids_str)
        else:
            params.set_param('voice_command_hub.allowed_group_ids', '')

    # NLU Settings
    nlu_provider = fields.Selection([
        ('builtin', 'Built-in (Rule-based + Fuzzy)'),
        ('spacy', 'spaCy'),
        ('transformer', 'Transformer (Hugging Face)'),
        ('custom', 'Custom Provider'),
    ], string='NLU Provider',
        config_parameter='voice_command_hub.nlu_provider',
        default='builtin'
    )
    fuzzy_match_threshold = fields.Float(
        string='Fuzzy Match Threshold',
        config_parameter='voice_command_hub.fuzzy_match_threshold',
        default=0.8,
        help='Minimum similarity ratio for fuzzy matching (0.0 to 1.0)'
    )

    # Synonyms Management
    product_synonyms = fields.Char(
        string='Product Synonyms',
        config_parameter='voice_command_hub.product_synonyms',
        help='Product name synonyms (comma-separated)'
    )
    action_synonyms = fields.Char(
        string='Action Synonyms',
        config_parameter='voice_command_hub.action_synonyms',
        help='Action verb synonyms (comma-separated)'
    )

    # Security Settings
    restrict_to_groups = fields.Boolean(
        string='Restrict to Specific Groups',
        config_parameter='voice_command_hub.restrict_to_groups',
        default=False
    )
    allowed_group_ids = fields.Many2many(
        'res.groups',
        'voice_command_allowed_groups_rel',
        'config_id',
        'group_id',
        string='Allowed Groups'
    )

    # Audit Settings
    log_retention_days = fields.Integer(
        string='Log Retention (Days)',
        config_parameter='voice_command_hub.log_retention_days',
        default=90,
        help='Number of days to retain command logs (0 = forever)'
    )
