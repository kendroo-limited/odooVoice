# -*- coding: utf-8 -*-
{
    'name': 'Voice Command Hub',
    'version': '17.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Turn natural language voice commands into safe, auditable Odoo actions',
    'description': """
Voice Command Hub
=================
Production-grade Odoo addon that enables users to perform Odoo operations using natural language voice commands.

Key Features:
* Natural language processing for intent recognition
* Multi-step slot filling with intelligent follow-up questions
* Dry-run simulation before execution
* Full audit trail of all actions
* Security-aware execution respecting ACLs
* Extensible skill system for custom intents
* Support for Odoo 16 and 17 (community & enterprise)

Built-in Intents:
* Sale order creation and confirmation
* Inventory adjustments and updates
* Purchase order creation
* CRM lead/opportunity creation
* Invoice payment registration

Examples:
* "Toufik buy a chocolate from me" → Creates and confirms a sale order
* "I buy 100 chocolate for selling, update the inventory" → Creates purchase or inventory adjustment
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale_management',
        'purchase',
        'stock',
        'account',
        'crm',
    ],
    'data': [
        # Security
        'security/voice_command_security.xml',
        'security/ir.model.access.csv',

        # Data - Sequence must be loaded first
        'data/ir_sequence.xml',
        'data/voice_intent_templates.xml',

        # Views
        'views/voice_command_session_views.xml',
        'views/voice_command_log_views.xml',
        'views/voice_intent_template_views.xml',
        'views/voice_llm_model_downloader_views.xml',  # Must load before settings (defines action)
        'views/res_config_settings_views.xml',  # References the downloader action

        # Root menu (must load before views that contain child menus)
        'views/menu_views.xml',

        # Training views (contains child menu items)
        'views/voice_training_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'voice_command_hub/static/src/js/**/*',
            'voice_command_hub/static/src/css/**/*',
        ],
        'web.assets_qweb': [
            'voice_command_hub/static/src/xml/**/*',
        ],
    },
    'demo': [
        'data/demo_data.xml',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
