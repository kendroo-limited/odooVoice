# Upgrade and Test Instructions

## Fixed Issues:
✅ Docker networking for Ollama (`host.docker.internal`)
✅ Thread-safe database operations
✅ Removed concurrent update conflicts

## Quick Upgrade Commands:

### Option 1: Restart Docker and Upgrade Module
```bash
cd /k/Odoo
docker-compose restart
docker-compose exec odoo odoo-bin -d qwer -u voice_command_hub --stop-after-init
docker-compose restart
```

### Option 2: Upgrade via Odoo UI
1. Go to Apps
2. Search "Voice Command Hub"
3. Click "Upgrade" button
4. Restart Odoo container

## Test Download via CLI:

After upgrading, test the download from Python console:

```python
# In Odoo shell: docker-compose exec odoo odoo-bin shell -d qwer
env['voice.llm.model.downloader'].create({
    'llm_provider': 'ollama',
    'ollama_url': 'http://host.docker.internal:11434',
    'selected_model': 'llama2',
}).action_download_model()
```

## Or Test via UI:

1. Settings > Voice Command Hub
2. Scroll to "LLM/AI Settings"
3. Click "Download LLM Models"
4. Select model: `llama2` or `mistral`
5. Click "⬇️ Download Selected Model"
6. Click "🔄 REFRESH STATUS" to see progress

## Expected Results:

✅ No concurrent update errors
✅ Download starts successfully
✅ Progress bar shows real-time updates
✅ Status log shows all steps
✅ Download speed displayed
