# Voice Command Hub - Installation & Quick Start Guide

## Prerequisites

- Odoo 16 or 17 (Community or Enterprise)
- Python 3.8+
- The following Odoo modules installed:
  - `sale_management`
  - `purchase`
  - `stock`
  - `account`
  - `crm`

## Installation Steps

### 1. Copy Module to Addons Directory

```bash
# Navigate to your Odoo addons directory
cd /path/to/odoo/addons

# Copy the voice_command_hub module
cp -r /path/to/voice_command_hub ./
```

### 2. Set Permissions (if needed)

```bash
sudo chown -R odoo:odoo voice_command_hub
sudo chmod -R 755 voice_command_hub
```

### 3. Update Apps List

**Option A: Via UI**
1. Log in to Odoo as administrator
2. Go to `Settings → Apps → Update Apps List`
3. Wait for the update to complete

**Option B: Via CLI**
```bash
odoo-bin -c /path/to/odoo.conf -d your_database -u all --stop-after-init
```

### 4. Install the Module

**Via UI:**
1. Go to `Apps`
2. Remove the "Apps" filter
3. Search for "Voice Command Hub"
4. Click `Install`

**Via CLI:**
```bash
odoo-bin -c /path/to/odoo.conf -d your_database -i voice_command_hub --stop-after-init
```

### 5. Verify Installation

After installation, you should see:
- New menu item: `Voice Commands` in the main menu bar
- Sub-menus: `Command Sessions`, `Intent Templates`, `Logs`

## Initial Configuration

### 1. Access Settings

1. Go to `Settings → General Settings`
2. Scroll down to find `Voice Command Hub` section

### 2. Recommended Initial Settings

```
✓ Enable Voice Commands
Language: English
✓ Confirm High-Risk Actions
✓ Confirm Medium-Risk Actions
Fuzzy Match Threshold: 0.8
NLU Provider: Built-in (Rule-based + Fuzzy)
```

### 3. Set Default Values (Optional)

- Default Warehouse: Select your main warehouse
- Default Pricelist: Select default pricelist
- Default Location: Select default stock location

### 4. Save Configuration

Click `Save` to apply settings.

## Quick Start Testing

### Test 1: Simple Sale Order Creation

1. **Navigate to Voice Commands**
   - Main Menu → Voice Commands → Command Sessions

2. **Create New Session**
   - Click `Create`
   - In `Transcript` field, enter:
     ```
     Toufik buy 2 chocolates from me
     ```
   - Click `Save`

3. **Parse the Command**
   - Click `Parse Command` button
   - Verify that:
     - Intent Key shows: `sale_create`
     - Slots shows customer and product info
     - State changes to `Ready to Execute`

4. **Simulate (Dry Run)**
   - Click `Simulate` button
   - Check the `Execution Plan` tab
   - Review what will be created

5. **Execute**
   - Click `Confirm` (if required)
   - Click `Execute`
   - State changes to `Executed`

6. **View Results**
   - Go to `Result` tab
   - Click the sale order link to view
   - Check that order was created and confirmed

### Test 2: Using the HTTP API

```bash
# Create a command via API
curl -X POST http://localhost:8069/voice/command \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d '{
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
      "text": "Toufik buy 5 chocolates from me",
      "dry_run": false
    },
    "id": 1
  }'
```

### Test 3: Command with Missing Information

1. Create session with incomplete command:
   ```
   I want to buy something
   ```

2. Click `Parse Command`

3. System will identify missing information and show questions:
   - "What products and quantities?"
   - "Who is the customer?"

4. Fill in missing information through the UI or API

## Demo Data

The module includes demo data:

**Partner:**
- Name: Toufik
- Email: toufik@example.com
- Phone: +1234567890

**Products:**
- Chocolate (CHOC-001): $10.00
- Apple (APPLE-001): $2.50
- Orange (ORANGE-001): $3.00

Use these for initial testing!

## Troubleshooting

### Module Won't Install

**Check dependencies:**
```bash
odoo-bin -c odoo.conf -d database --show-depends voice_command_hub
```

**Common issues:**
- Missing required modules (sale_management, etc.)
- Python syntax errors (check logs)
- XML validation errors

### Commands Not Parsing

**Check:**
1. Intent templates are active
   - Go to Voice Commands → Intent Templates
   - Ensure all have green status

2. Demo data loaded correctly
   - Go to Contacts → Search "Toufik"
   - Go to Products → Search "Chocolate"

3. Fuzzy match threshold
   - Settings → Voice Command Hub
   - Try lowering threshold to 0.6

### Permission Errors

**Assign groups:**
1. Go to Settings → Users
2. Select user
3. Under Voice Command Hub tab, assign:
   - `Voice Command User` (for regular users)
   - `Voice Command Manager` (for admins)

### Logs Show Errors

**View detailed logs:**
```bash
tail -f /var/log/odoo/odoo.log | grep voice_command
```

**Common errors:**
- Partner/Product not found: Check fuzzy match threshold
- Missing slots: Command too vague, needs more info
- Permission denied: Check user groups

## Verification Checklist

After installation, verify:

- [ ] Module appears in Apps list
- [ ] Voice Commands menu visible
- [ ] Can create new command session
- [ ] Can parse "Toufik buy chocolate from me"
- [ ] Intent recognized as sale_create
- [ ] Can simulate command
- [ ] Can execute command
- [ ] Sale order created successfully
- [ ] Logs recorded properly
- [ ] Settings panel accessible

## Next Steps

### For Users

1. **Try More Commands:**
   - "I buy 100 apples for selling, update inventory"
   - "Create lead for John Doe"
   - "John bought 3 oranges from me"

2. **Explore Intent Templates:**
   - Voice Commands → Intent Templates
   - Review available commands
   - Add custom training phrases

3. **Check Logs:**
   - Voice Commands → Logs
   - Monitor command execution
   - Debug any issues

### For Developers

1. **Review Code:**
   - Read `README.md` for architecture overview
   - Read `PROJECT_SUMMARY.md` for implementation details
   - Study `sale_create_handler.py` as reference

2. **Implement Remaining Handlers:**
   - `inventory_adjust_handler.py`
   - `purchase_create_handler.py`
   - `crm_lead_handler.py`
   - `invoice_payment_handler.py`

3. **Add Custom Intents:**
   - Create new intent template
   - Register custom handler
   - Add training phrases

4. **Write Tests:**
   - Unit tests for handlers
   - Integration tests for workflows
   - Edge case coverage

## Getting Help

### Documentation

- `README.md` - User and developer guide
- `PROJECT_SUMMARY.md` - Complete implementation details
- Code comments in Python files

### Support

For issues or questions:
1. Check the logs for error details
2. Review the troubleshooting section
3. Examine handler code for examples
4. Consult Odoo documentation for ORM usage

## Uninstallation

If needed, to uninstall:

1. **Via UI:**
   - Apps → Voice Command Hub → Uninstall

2. **Via CLI:**
   ```bash
   odoo-bin -c odoo.conf -d database -u voice_command_hub --stop-after-init
   ```

**Note:** This will remove all voice command sessions, logs, and intent templates.

## Upgrade Instructions

When upgrading to a new version:

1. Backup your database
2. Replace module files
3. Update via Apps list
4. Test with simple command
5. Review logs for any errors

---

**Congratulations!** Your Voice Command Hub is now installed and ready to use. Start with the demo data and simple commands, then gradually explore more complex scenarios.

**Pro Tip:** Watch the Logs tab while executing commands to see exactly what's happening under the hood!
