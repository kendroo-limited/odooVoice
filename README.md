# Voice Command Hub for Odoo

## Overview

**Voice Command Hub** is a production-grade Odoo addon that turns natural language voice commands into safe, auditable Odoo actions. Compatible with Odoo 16 and 17 (Community & Enterprise).

## Features

- Natural language processing for intent recognition
- Multi-step slot filling with intelligent follow-up questions
- Dry-run simulation before execution
- Full audit trail of all actions
- Security-aware execution respecting ACLs
- Extensible skill system for custom intents
- Support for multiple business flows (Sales, Purchase, Inventory, CRM, Accounting)

## Examples

```
"Toufik buy a chocolate from me"
→ Creates and confirms a sale order

"I buy 100 chocolate for selling, update the inventory"
→ Creates purchase or inventory adjustment with follow-up questions
```

## Architecture

### Core Models

- **voice.command.session**: Manages command sessions with state tracking
- **voice.command.log**: Audit log for all operations
- **voice.intent.template**: Configurable intent definitions with training phrases

### Services

- **voice.intent.router**: Parses commands and routes to handlers
- **voice.slot.filler**: Extracts and normalizes entities (partners, products, quantities, etc.)
- **Intent Handlers**: Pluggable handlers for each business flow

### Built-in Intents

1. **sale_create**: Create and confirm sale orders
2. **inventory_adjust**: Update inventory quantities
3. **purchase_create**: Create purchase orders
4. **crm_lead_create**: Create CRM leads/opportunities
5. **invoice_register_payment**: Register invoice payments

## Installation

1. Copy the `voice_command_hub` directory to your Odoo addons path
2. Update the addons list: `Settings > Apps > Update Apps List`
3. Install the module: `Apps > Voice Command Hub > Install`

## Configuration

Navigate to `Settings > General Settings > Voice Command Hub`:

- Enable/disable voice commands
- Set confirmation policies for different risk levels
- Configure auto-creation of partners/products
- Set default warehouse, location, pricelist
- Configure NLU provider and fuzzy matching threshold
- Manage synonyms for products and actions

## Usage

### Via UI

1. Go to `Voice Commands > New Session`
2. Enter your command in the transcript field
3. Click "Parse" to extract intent and slots
4. Fill in any missing information
5. Review the dry-run simulation
6. Confirm and execute

### Via API

```python
# Using JSON-RPC or XML-RPC
session = env['voice.command.session'].create({
    'transcript': 'Toufik buy 5 chocolates from me'
})
session.action_parse()
session.action_simulate()
session.action_confirm()
session.action_execute()
```

### Via HTTP Endpoint

```bash
curl -X POST http://your-odoo-instance/voice/command \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Toufik buy 5 chocolates from me",
    "dry_run": true
  }'
```

## Extending with Custom Intents

### 1. Create a Handler Class

```python
# my_custom_addon/models/my_intent_handler.py

from odoo.addons.voice_command_hub.services.intent_handlers.base_handler import VoiceIntentHandler

class MyCustomHandler:
    INTENT_KEY = 'my_custom_intent'

    SCHEMA = {
        'field1': {'required': True, 'type': 'text'},
        'field2': {'required': False, 'type': 'partner'},
    }

    def __init__(self, env):
        self.env = env
        self.slot_filler = env['voice.slot.filler']

    def validate_slots(self, slots):
        # Validation logic
        pass

    def simulate(self, slots):
        # Return execution plan
        return {'action': 'my_action', 'details': '...'}

    def execute(self, slots):
        # Perform actual operations
        return {'success': True, 'message': 'Done!'}

# Register
VoiceIntentHandler.register_handler(
    MyCustomHandler.INTENT_KEY,
    MyCustomHandler
)
```

### 2. Create Intent Template Data

```xml
<odoo>
    <record id="intent_my_custom" model="voice.intent.template">
        <field name="name">My Custom Intent</field>
        <field name="key">my_custom_intent</field>
        <field name="category">custom</field>
        <field name="risk_level_default">low</field>
        <field name="training_phrases">
do my custom action
execute custom task
run my special command
        </field>
        <field name="slot_schema_json">{
            "field1": {"required": true, "type": "text", "question": "What is field1?"},
            "field2": {"required": false, "type": "partner", "question": "Which partner?"}
        }</field>
    </record>
</odoo>
```

## Security

- All operations respect Odoo's ACL and record rules
- No `sudo()` used except for system parameters
- High-risk actions require explicit confirmation
- Full audit trail with before/after diffs
- Savepoint-based execution for automatic rollback on errors

## Implementation Status

### ✅ Completed

- [x] Module structure and manifest
- [x] Core models (session, log, intent template)
- [x] Settings model extension
- [x] Intent router service (parsing & routing)
- [x] Slot filler service (entity extraction)
- [x] Base handler class
- [x] Sale create handler (full implementation)

### 🚧 To Be Completed

#### Critical Files

1. **Security Files**
   - `security/voice_command_security.xml` - Security groups and rules
   - `security/ir.model.access.csv` - Model access rights

2. **Intent Handlers** (need implementation)
   - `services/intent_handlers/inventory_adjust_handler.py`
   - `services/intent_handlers/purchase_create_handler.py`
   - `services/intent_handlers/crm_lead_handler.py`
   - `services/intent_handlers/invoice_payment_handler.py`

3. **Controller**
   - `controllers/main.py` - HTTP endpoints for `/voice/command`

4. **Views**
   - `views/voice_command_session_views.xml`
   - `views/voice_command_log_views.xml`
   - `views/voice_intent_template_views.xml`
   - `views/res_config_settings_views.xml`
   - `views/menu_views.xml`

5. **Data**
   - `data/voice_intent_templates.xml` - Intent template records
   - `data/demo_data.xml` - Demo partners, products
   - `data/ir_sequence.xml` - Sequence for session names

6. **Tests**
   - `tests/__init__.py`
   - `tests/test_intent_router.py`
   - `tests/test_slot_filler.py`
   - `tests/test_sale_create.py`
   - `tests/test_inventory_adjust.py`

7. **Frontend Assets** (optional)
   - `static/src/js/voice_command_widget.js` - Chat-like widget
   - `static/src/css/voice_command.css` - Styling
   - `static/src/xml/voice_command_templates.xml` - QWeb templates

## Development Roadmap

### Phase 1: Core Functionality (Current)
- Complete remaining intent handlers
- Add security rules and access rights
- Create basic views and menus
- Add demo data

### Phase 2: Testing & Documentation
- Comprehensive unit tests
- Integration tests for each intent
- Developer documentation
- User guide

### Phase 3: Advanced Features
- Web widget with speech-to-text integration
- Multi-language support
- Advanced NLU with spaCy/Transformers
- Skill marketplace
- Voice response generation

### Phase 4: Enterprise Features
- Multi-company support
- Advanced analytics dashboard
- Voice command scheduling
- Integration with external STT services
- Mobile app support

## Technical Requirements

- Odoo 16 or 17
- Python 3.8+
- Modules: `sale_management`, `purchase`, `stock`, `account`, `crm`

## License

LGPL-3

## Author

Your Company

## Support

For issues, questions, or contributions, please contact [email or create issues on your repo]

---

## Quick Start Guide for Developers

### Testing the Sale Create Intent

```python
# In Odoo shell
env = api.Environment(cr, uid, {})

# Create a test session
session = env['voice.command.session'].create({
    'transcript': 'Toufik buy 2 chocolates from me'
})

# Parse the command
session.action_parse()
print(f"Intent: {session.intent_key}")
print(f"Slots: {session.slots_json}")
print(f"Missing: {session.missing_slots_json}")

# Simulate
session.action_simulate()
print(f"Plan: {session.execution_plan}")

# Execute
session.action_confirm()
session.action_execute()
print(f"Result: {session.result_summary}")
```

### Viewing Logs

```python
# View all logs for a session
for log in session.log_ids:
    print(f"[{log.level}] {log.message}")
```

## Next Steps

1. Complete the remaining intent handlers following the `sale_create_handler.py` pattern
2. Create security files to define access rights
3. Build views for user interaction
4. Add demo data for testing
5. Write comprehensive tests
6. Deploy to test environment
7. Iterate based on user feedback

## File Structure

```
voice_command_hub/
├── __init__.py
├── __manifest__.py
├── README.md (this file)
├── models/
│   ├── __init__.py
│   ├── voice_command_session.py ✅
│   ├── voice_command_log.py ✅
│   ├── voice_intent_template.py ✅
│   └── res_config_settings.py ✅
├── services/
│   ├── __init__.py
│   ├── voice_intent_router.py ✅
│   ├── voice_slot_filler.py ✅
│   └── intent_handlers/
│       ├── __init__.py ✅
│       ├── base_handler.py ✅
│       ├── sale_create_handler.py ✅
│       ├── inventory_adjust_handler.py ⏳
│       ├── purchase_create_handler.py ⏳
│       ├── crm_lead_handler.py ⏳
│       └── invoice_payment_handler.py ⏳
├── controllers/
│   ├── __init__.py
│   └── main.py ⏳
├── views/
│   ├── voice_command_session_views.xml ⏳
│   ├── voice_command_log_views.xml ⏳
│   ├── voice_intent_template_views.xml ⏳
│   ├── res_config_settings_views.xml ⏳
│   └── menu_views.xml ⏳
├── security/
│   ├── voice_command_security.xml ⏳
│   └── ir.model.access.csv ⏳
├── data/
│   ├── ir_sequence.xml ⏳
│   ├── voice_intent_templates.xml ⏳
│   └── demo_data.xml ⏳
├── static/
│   └── src/
│       ├── js/ ⏳
│       ├── css/ ⏳
│       └── xml/ ⏳
└── tests/
    ├── __init__.py ⏳
    └── test_*.py ⏳

✅ Completed
⏳ Pending
```
