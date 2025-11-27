# Voice Command Transcript: "Sell a chocolate to topu"

## Complete Interaction Flow

### 1. Initial Command
**User Input:** "sell a chocolate to topu"

**System Processing:**
```
[Intent Router] Parsing command: "sell a chocolate to topu"
[Intent Router] Matched intent: sale_create (confidence: 0.85)
[NLU Parser] Extracting slots...
[NLU Parser] Found slots:
  - product: "chocolate" (partial match)
  - partner: "topu" (name detected)
  - quantity: NOT FOUND
```

**Session Created:**
- **Intent:** `sale_create` (Create Sale Order)
- **Transcript:** "sell a chocolate to topu"
- **Status:** `slot_filling` (Missing information)
- **Extracted Slots:**
  ```json
  {
    "product": "chocolate",
    "partner": "topu"
  }
  ```
- **Missing Slots:** `["quantity"]`

---

### 2. First Follow-up Question (Quantity)

**System Question:**
> "How many chocolates would you like to sell?"
>
> *Type: quantity*
> *Help: Please provide the quantity*

**User Response:** "5"

**System Processing:**
```
[Slot Filler] Received answer: "5"
[Slot Filler] Extracting quantity...
[Slot Filler] Parsed quantity: 5.0
[Slot Filler] Updated slots:
  {
    "product": "chocolate",
    "partner": "topu",
    "quantity": 5.0
  }
[Slot Filler] Missing slots: []
[Slot Filler] All required slots filled!
```

**Session Updated:**
- **Status:** `ready_to_execute` (All information collected)
- **Extracted Slots:**
  ```json
  {
    "product": "chocolate",
    "partner": "topu",
    "quantity": 5.0
  }
  ```

---

### 3. Dry-Run Simulation (Safety Check)

**System:** *Performing dry-run to preview changes...*

**Dry-Run Execution:**
```python
# Handler: SaleCreateHandler
# Mode: simulation (no database changes)

# Step 1: Search for partner "topu"
partner = env['res.partner'].search([
    '|', '|',
    ('name', 'ilike', 'topu'),
    ('email', 'ilike', 'topu'),
    ('phone', 'ilike', 'topu')
], limit=1)

# Result: Partner found - "Topu Rahman" (ID: 42)

# Step 2: Search for product "chocolate"
product = env['product.product'].search([
    ('name', 'ilike', 'chocolate')
], limit=1)

# Result: Product found - "Dark Chocolate" (ID: 15)
# Price: $2.50
# Available quantity: 100 units

# Step 3: Create sale order (simulation)
sale_order = {
    'partner_id': 42,  # Topu Rahman
    'order_line': [(0, 0, {
        'product_id': 15,  # Dark Chocolate
        'product_uom_qty': 5.0,
        'price_unit': 2.50
    })]
}

# Calculated total: 5 × $2.50 = $12.50
```

**Dry-Run Result Summary:**
```
✅ DRY-RUN SUCCESSFUL

📊 Planned Changes:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Create Sale Order
  Customer: Topu Rahman
  Products:
    • Dark Chocolate × 5 @ $2.50 = $12.50

  Total: $12.50

⚠️ Risk Level: MEDIUM
  - This will create a confirmed sale order
  - Inventory will be reserved

🔒 Confirmation Required
```

---

### 4. User Confirmation

**System Prompt:**
> **⚠️ Confirmation Required**
>
> This action will create a sale order for Topu Rahman:
> - 5 × Dark Chocolate @ $2.50 = $12.50
>
> Do you want to proceed?
>
> [✓ Confirm]  [✗ Cancel]

**User Action:** Clicks **[✓ Confirm]**

---

### 5. Final Execution

**System:** *Executing command...*

**Real Execution:**
```python
# Handler: SaleCreateHandler
# Mode: execute (real database changes)

# Create sale order
sale_order = env['sale.order'].create({
    'partner_id': 42,
    'order_line': [(0, 0, {
        'product_id': 15,
        'product_uom_qty': 5.0,
        'price_unit': 2.50
    })]
})
# Result: Sale Order SO00123 created

# Auto-confirm based on settings
sale_order.action_confirm()
# Result: Order confirmed, inventory reserved

# Create audit log
env['voice.command.log'].create({
    'session_id': session.id,
    'level': 'success',
    'message': 'Sale order SO00123 created and confirmed',
    'payload_json': {
        'sale_order_id': sale_order.id,
        'partner': 'Topu Rahman',
        'total': 12.50
    }
})
```

**Execution Result:**
```
✅ EXECUTION SUCCESSFUL

📄 Sale Order Created: SO00123
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Customer: Topu Rahman
Status: Confirmed
Total: $12.50

Products:
  • Dark Chocolate × 5 @ $2.50 = $12.50

📦 Inventory Status:
  - Reserved: 5 units of Dark Chocolate
  - Remaining stock: 95 units

🔗 Quick Actions:
  [View Order] [Print Invoice] [Send Email]
```

**Session Updated:**
- **Status:** `completed`
- **Execution Success:** `True`
- **Result Summary:**
  ```json
  {
    "success": true,
    "sale_order_id": 123,
    "sale_order_name": "SO00123",
    "partner_name": "Topu Rahman",
    "total_amount": 12.50,
    "message": "Sale order SO00123 created and confirmed"
  }
  ```

---

## 📊 Complete Timeline

| Step | Action | Duration | Status |
|------|--------|----------|--------|
| 1 | Parse command | 0.05s | ✅ |
| 2 | Match intent | 0.02s | ✅ |
| 3 | Extract slots | 0.12s | ✅ Partial (2/3) |
| 4 | Ask for quantity | - | ⏸️ Waiting |
| 5 | Receive answer | 0.03s | ✅ |
| 6 | Validate slots | 0.04s | ✅ Complete |
| 7 | Run dry-run | 0.25s | ✅ Safe |
| 8 | Wait confirmation | - | ⏸️ User input |
| 9 | Execute command | 0.45s | ✅ Success |
| **Total** | **End-to-end** | **~1.0s** | **✅ Complete** |

---

## 🎯 Key Features Demonstrated

### 1. **Natural Language Understanding (NLU)**
- Recognized intent: "sale_create" from "sell"
- Extracted product: "chocolate"
- Extracted partner: "topu"
- Identified missing slot: "quantity"

### 2. **Intelligent Slot Filling**
- Generated natural follow-up question
- Validated user input (quantity: 5)
- Continued until all required information collected

### 3. **Fuzzy Matching**
- "topu" matched to "Topu Rahman" (partial name match)
- "chocolate" matched to "Dark Chocolate" (product search)

### 4. **Safety & Auditing**
- Dry-run simulation before execution
- Risk assessment (MEDIUM risk)
- User confirmation required
- Complete audit trail

### 5. **Smart Execution**
- Created sale order
- Auto-confirmed based on settings
- Reserved inventory
- Generated human-readable result

---

## 💬 Alternative Conversation Flows

### Scenario A: Ambiguous Product

**User:** "sell chocolate to topu"

**System:**
> "I found 3 chocolate products. Which one?"
> 1. Dark Chocolate ($2.50)
> 2. Milk Chocolate ($2.00)
> 3. White Chocolate ($3.00)

**User:** "the dark one"

**System:** ✅ Selected "Dark Chocolate"

---

### Scenario B: Customer Not Found

**User:** "sell chocolate to john doe"

**System:**
> ⚠️ Customer "john doe" not found.
>
> Would you like to:
> 1. Create new customer
> 2. Try different name
> 3. Cancel

**User:** "create new customer"

**System:**
> "What's the email for John Doe?"

---

### Scenario C: Out of Stock

**User:** "sell 1000 chocolates to topu"

**Dry-run Result:**
```
⚠️ WARNING: Insufficient stock!

Requested: 1000 units
Available: 100 units
Shortfall: 900 units

Do you want to:
1. Proceed anyway (backorder)
2. Change quantity to 100
3. Cancel
```

---

## 📝 Session Logs (Behind the Scenes)

```
[2025-11-27 02:43:18] INFO  - Session VCMD-00042 created
[2025-11-27 02:43:18] INFO  - Intent matched: sale_create (confidence: 85%)
[2025-11-27 02:43:18] DEBUG - Slots extracted: {product: chocolate, partner: topu}
[2025-11-27 02:43:18] INFO  - Missing slots: [quantity]
[2025-11-27 02:43:18] INFO  - Status: slot_filling → Asking for quantity
[2025-11-27 02:43:25] INFO  - User response: "5"
[2025-11-27 02:43:25] DEBUG - Quantity parsed: 5.0
[2025-11-27 02:43:25] INFO  - All slots filled
[2025-11-27 02:43:25] INFO  - Status: ready_to_execute
[2025-11-27 02:43:25] INFO  - Running dry-run simulation...
[2025-11-27 02:43:25] DEBUG - Partner search: "topu" → Found ID 42 (Topu Rahman)
[2025-11-27 02:43:25] DEBUG - Product search: "chocolate" → Found ID 15 (Dark Chocolate)
[2025-11-27 02:43:25] INFO  - Dry-run successful. Total: $12.50
[2025-11-27 02:43:25] INFO  - Status: awaiting_confirmation (MEDIUM risk)
[2025-11-27 02:43:32] INFO  - User confirmed execution
[2025-11-27 02:43:32] INFO  - Executing command...
[2025-11-27 02:43:32] DEBUG - Creating sale.order record...
[2025-11-27 02:43:32] SUCCESS - Sale order SO00123 created
[2025-11-27 02:43:32] DEBUG - Auto-confirming order...
[2025-11-27 02:43:32] SUCCESS - Order confirmed. Inventory reserved.
[2025-11-27 02:43:32] INFO  - Status: completed
[2025-11-27 02:43:32] INFO  - Session closed successfully
```

---

## 🎓 What This Demonstrates

### Voice Command Hub Capabilities:
✅ **Natural Language Processing** - Understands casual language
✅ **Intent Recognition** - Identifies what user wants to do
✅ **Slot Extraction** - Pulls out key information
✅ **Conversational Flow** - Asks follow-up questions naturally
✅ **Fuzzy Matching** - Finds records even with partial/misspelled names
✅ **Safety Checks** - Dry-run before real changes
✅ **Risk Assessment** - Categorizes actions by risk level
✅ **User Confirmation** - Requires approval for important actions
✅ **Full Audit Trail** - Complete logging of all steps
✅ **Error Handling** - Graceful handling of edge cases

---

## 🚀 Try It Yourself!

1. Go to **Voice Command Hub → New Command Session**
2. Type: **"sell a chocolate to topu"**
3. Follow the prompts
4. Review the result

**More Examples to Try:**
- "I bought 50 chocolates from supplier"
- "Add 100 units of chocolate to inventory"
- "Create a lead for ABC Company"
- "Register payment for invoice INV/2025/0042"

---

*Generated by Voice Command Hub - Production-grade voice commands for Odoo*
