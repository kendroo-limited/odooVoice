# -*- coding: utf-8 -*-

import json
import logging
import requests
import threading
from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class VoiceLLMModelDownloader(models.TransientModel):
    """Wizard for downloading and managing LLM models"""
    _name = 'voice.llm.model.downloader'
    _description = 'LLM Model Downloader'

    llm_provider = fields.Selection([
        ('ollama', 'Ollama (Local)'),
        ('huggingface', 'Hugging Face'),
    ], string='Provider', default='ollama', required=True)

    ollama_url = fields.Char(
        string='Ollama Server URL',
        default='http://host.docker.internal:11434',
        required=True,
        help='Use "host.docker.internal" if Odoo runs in Docker and Ollama on host machine'
    )

    available_models_json = fields.Json(
        string='Available Models',
        default=[]
    )

    selected_model = fields.Selection(
        selection='_get_model_selection',
        string='Select Model to Download',
        required=True
    )

    download_status = fields.Selection([
        ('idle', 'Ready'),
        ('checking', 'Checking availability...'),
        ('downloading', 'Downloading...'),
        ('completed', 'Completed'),
        ('error', 'Error'),
    ], string='Status', default='idle', readonly=True)

    progress_percentage = fields.Float(
        string='Progress',
        default=0.0,
        readonly=True
    )

    downloaded_bytes = fields.Float(
        string='Downloaded (MB)',
        default=0.0,
        readonly=True
    )

    total_bytes = fields.Float(
        string='Total Size (MB)',
        default=0.0,
        readonly=True
    )

    download_speed = fields.Char(
        string='Download Speed',
        readonly=True
    )

    download_message = fields.Text(
        string='Message',
        readonly=True,
        default='Click "Download Selected Model" to begin...'
    )

    status_log = fields.Html(
        string='Status Log',
        readonly=True,
        default='<div style="padding: 10px; background: #f8f9fa; font-family: monospace; font-size: 12px;">Ready to download. Select a model and click Download.</div>'
    )

    installed_models = fields.Text(
        string='Installed Models',
        compute='_compute_installed_models',
        readonly=True
    )

    def _add_log(self, message, level='info'):
        """Add a timestamped log entry (thread-safe)"""
        import datetime
        import threading

        timestamp = datetime.datetime.now().strftime('%H:%M:%S')

        color_map = {
            'info': '#17a2b8',
            'success': '#28a745',
            'warning': '#ffc107',
            'error': '#dc3545',
        }

        color = color_map.get(level, '#6c757d')
        icon_map = {
            'info': 'ℹ️',
            'success': '✅',
            'warning': '⚠️',
            'error': '❌',
        }
        icon = icon_map.get(level, '•')

        new_entry = f'<div style="margin: 5px 0; padding: 5px; border-left: 3px solid {color};">' \
                   f'<strong style="color: {color};">[{timestamp}] {icon} {message}</strong></div>'

        # Use thread-safe cursor if called from background thread
        is_main_thread = threading.current_thread() is threading.main_thread()

        if is_main_thread:
            # Main thread - use ORM to let Odoo handle transactions
            current_log = self.status_log or ''
            self.status_log = new_entry + current_log
        else:
            # Background thread - create new cursor
            try:
                registry = self.env.registry
                with registry.cursor() as cr:
                    cr.execute("""
                        SELECT status_log FROM voice_llm_model_downloader WHERE id = %s
                    """, (self.id,))
                    result = cr.fetchone()
                    current_log = result[0] if result and result[0] else ''

                    cr.execute("""
                        UPDATE voice_llm_model_downloader
                        SET status_log = %s
                        WHERE id = %s
                    """, (new_entry + current_log, self.id))
                    cr.commit()
            except Exception as e:
                _logger.error(f"Error logging from background thread: {e}")

    progress_bar_html = fields.Html(
        string='Progress Bar',
        compute='_compute_progress_bar_html',
        readonly=True
    )

    @api.depends('progress_percentage', 'download_status', 'downloaded_bytes', 'total_bytes', 'download_speed')
    def _compute_progress_bar_html(self):
        """Generate HTML progress bar"""
        for record in self:
            if record.download_status == 'downloading':
                percentage = record.progress_percentage or 0
                downloaded = record.downloaded_bytes or 0
                total = record.total_bytes or 0
                speed = record.download_speed or 'Calculating...'

                html = f"""
                <div style="margin: 20px 0;">
                    <div style="width: 100%; background-color: #e9ecef; border-radius: 5px; overflow: hidden; height: 40px; margin-bottom: 15px;">
                        <div style="width: {percentage}%; background: linear-gradient(90deg, #4CAF50, #45a049); height: 100%;
                             display: flex; align-items: center; justify-content: center; transition: width 0.3s ease;
                             box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);">
                            <span style="color: white; font-weight: bold; font-size: 16px; text-shadow: 1px 1px 2px rgba(0,0,0,0.3);">
                                {percentage:.1f}%
                            </span>
                        </div>
                    </div>
                    <div style="display: flex; justify-content: space-between; color: #666; font-size: 14px;">
                        <span><strong>📦 Downloaded:</strong> {downloaded:.1f} MB / {total:.1f} MB</span>
                        <span><strong>⚡ Speed:</strong> {speed}</span>
                    </div>
                </div>
                """
                record.progress_bar_html = html
            elif record.download_status == 'completed':
                record.progress_bar_html = """
                <div style="text-align: center; padding: 20px; background: #d4edda; border: 2px solid #c3e6cb; border-radius: 5px; margin: 20px 0;">
                    <i class="fa fa-check-circle" style="font-size: 48px; color: #28a745;"></i>
                    <h3 style="color: #155724; margin-top: 10px;">Download Complete!</h3>
                </div>
                """
            elif record.download_status == 'error':
                record.progress_bar_html = """
                <div style="text-align: center; padding: 20px; background: #f8d7da; border: 2px solid #f5c6cb; border-radius: 5px; margin: 20px 0;">
                    <i class="fa fa-exclamation-triangle" style="font-size: 48px; color: #dc3545;"></i>
                    <h3 style="color: #721c24; margin-top: 10px;">Download Failed</h3>
                </div>
                """
            else:
                record.progress_bar_html = False

    @api.model
    def _get_model_selection(self):
        """Return available models based on provider"""
        return [
            ('llama2', 'Llama 2 (7B) - General purpose, fast'),
            ('llama2:13b', 'Llama 2 (13B) - More accurate, slower'),
            ('mistral', 'Mistral (7B) - Excellent quality/speed'),
            ('mistral:instruct', 'Mistral Instruct - Better for tasks'),
            ('phi', 'Phi-2 (2.7B) - Tiny but capable'),
            ('codellama', 'Code Llama - Specialized for code'),
            ('neural-chat', 'Neural Chat - Conversational'),
            ('starling-lm', 'Starling LM - High quality responses'),
            ('orca-mini', 'Orca Mini (3B) - Small and fast'),
            ('tinyllama', 'Tiny Llama (1.1B) - Ultra lightweight'),
        ]

    @api.depends('ollama_url')
    def _compute_installed_models(self):
        """Check which models are already installed"""
        for record in self:
            try:
                if record.llm_provider == 'ollama':
                    models = record._get_ollama_installed_models()
                    if models:
                        record.installed_models = '✅ Installed models:\n' + '\n'.join(f"• {m}" for m in models)
                    else:
                        record.installed_models = '⚠️ No models installed yet'
                else:
                    record.installed_models = ''
            except Exception as e:
                record.installed_models = f'❌ Cannot connect to server: {str(e)}'

    def _get_ollama_installed_models(self):
        """Get list of installed Ollama models"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
        except Exception as e:
            _logger.warning(f"Failed to get Ollama models: {e}")
        return []

    def action_check_server(self):
        """Check if Ollama server is running"""
        self.ensure_one()

        self._add_log(f"Checking Ollama server at {self.ollama_url}...", 'info')

        try:
            if self.llm_provider == 'ollama':
                self._add_log("Sending request to /api/tags...", 'info')
                response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)

                if response.status_code == 200:
                    self._add_log("Server responded successfully!", 'success')
                    installed = self._get_ollama_installed_models()
                    count = len(installed)

                    self._add_log(f"Found {count} installed model(s)", 'success')

                    for model in installed:
                        self._add_log(f"  • {model}", 'info')

                    self.download_message = f"✅ Ollama server is running!\n\nFound {count} installed model(s)."
                    self.download_status = 'idle'

                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': '✅ Server Connected',
                            'message': f'Ollama is running! Found {count} models.',
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    self._add_log(f"Server error: HTTP {response.status_code}", 'error')
                    raise Exception(f"Server returned status {response.status_code}")

        except requests.exceptions.ConnectionError as e:
            self._add_log("❌ CONNECTION FAILED - Cannot reach Ollama!", 'error')
            self._add_log(f"Error details: {str(e)}", 'error')
            self._add_log(f"Tried URL: {self.ollama_url}", 'error')

            # Check if using localhost (Docker issue)
            docker_issue = 'localhost' in self.ollama_url or '127.0.0.1' in self.ollama_url

            if docker_issue:
                self._add_log("⚠️ Detected 'localhost' URL - this won't work in Docker!", 'warning')
                error_msg = (
                    "❌ Cannot connect to Ollama!\n\n"
                    "**🐳 DOCKER DETECTED - localhost won't work!**\n\n"
                    "Since Odoo runs in Docker and Ollama on Windows host:\n\n"
                    "✅ CHANGE Ollama Server URL to:\n"
                    "   http://host.docker.internal:11434\n\n"
                    "📝 Steps:\n"
                    "1. Close this dialog\n"
                    "2. Change 'Ollama Server URL' field at top\n"
                    "3. Click 'Check Server' again\n\n"
                    "💡 'host.docker.internal' = Windows host from Docker\n\n"
                    f"Current (wrong) URL: {self.ollama_url}\n"
                    "Correct URL: http://host.docker.internal:11434"
                )
            else:
                error_msg = (
                    "❌ Cannot connect to Ollama!\n\n"
                    "**Ollama might not be running.**\n\n"
                    "📥 Install Ollama:\n"
                    "• Windows: https://ollama.ai/download\n"
                    "• Linux/Mac: curl https://ollama.ai/install.sh | sh\n\n"
                    "▶️ Start Ollama:\n"
                    "• Run: ollama serve\n\n"
                    f"🔗 Trying URL: {self.ollama_url}\n\n"
                    "⚠️ Check Status Log in 'Download Progress' tab for details."
                )

            raise UserError(_(error_msg))
        except Exception as e:
            self._add_log(f"Error: {str(e)}", 'error')
            raise UserError(_(f"Error checking server: {str(e)}"))

    def action_download_model(self):
        """Download the selected model"""
        self.ensure_one()

        self._add_log("═" * 50, 'info')
        self._add_log(f"STARTING DOWNLOAD: {self.selected_model}", 'info')
        self._add_log("═" * 50, 'info')

        if not self.selected_model:
            self._add_log("ERROR: No model selected!", 'error')
            raise UserError(_("❌ Please select a model to download"))

        self._add_log(f"Selected model: {self.selected_model}", 'info')
        self._add_log(f"Ollama server: {self.ollama_url}", 'info')

        # First check if Ollama server is running
        self._add_log("Step 1: Checking if Ollama server is running...", 'info')
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code != 200:
                self._add_log(f"Server returned error code: {response.status_code}", 'error')
                raise Exception(f"Server not responding (HTTP {response.status_code})")

            self._add_log("✅ Ollama server is running!", 'success')

        except requests.exceptions.ConnectionError as e:
            self._add_log("❌ CANNOT CONNECT TO OLLAMA!", 'error')
            self._add_log(f"Connection error: {str(e)}", 'error')
            self._add_log("Ollama is NOT installed or NOT running", 'error')

            raise UserError(_(
                "❌ Cannot connect to Ollama!\n\n"
                "**Ollama is NOT installed or NOT running on your computer.**\n\n"
                "📥 INSTALL OLLAMA:\n"
                "• Windows: https://ollama.ai/download\n"
                "• Linux/Mac: curl https://ollama.ai/install.sh | sh\n\n"
                "▶️ START OLLAMA:\n"
                "• Run command: ollama serve\n\n"
                f"🔗 Server URL: {self.ollama_url}\n\n"
                "⚠️ Check 'Download Progress' tab to see Status Log with details."
            ))
        except Exception as e:
            self._add_log(f"Unexpected error: {str(e)}", 'error')
            raise UserError(_(f"❌ Error checking server: {str(e)}"))

        # Check if already installed
        self._add_log("Step 2: Checking if model is already installed...", 'info')
        installed = self._get_ollama_installed_models()
        self._add_log(f"Currently installed models: {len(installed)}", 'info')

        if self.selected_model in installed:
            self._add_log(f"⚠️ Model {self.selected_model} is already installed!", 'warning')
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Already Installed'),
                    'message': f'Model "{self.selected_model}" is already installed!',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        self._add_log(f"✅ Model not installed yet, proceeding with download", 'success')
        self._add_log("Step 3: Starting background download thread...", 'info')

        # Commit all pending changes BEFORE starting thread to avoid conflicts
        self.env.cr.commit()

        # Start background thread - pass only IDs, not self (to avoid cursor issues)
        thread = threading.Thread(
            target=self._download_ollama_model_static,
            args=(self.id, self.selected_model, self.ollama_url, self.env.cr.dbname)
        )
        thread.daemon = True
        thread.start()

        # Don't log anything else from main thread - would cause concurrent update conflicts
        # The background thread will add its own logs

        # Reopen wizard to show updated status
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'voice.llm.model.downloader',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {
                'default_selected_model': self.selected_model,
                'active_tab': 'download_progress',
            },
        }

    @staticmethod
    def _download_ollama_model_static(wizard_id, model_name, ollama_url, dbname):
        """Static method to download model (runs in background thread)"""
        import time
        import odoo

        # Create completely new registry and cursor - no reference to original self
        registry = odoo.registry(dbname)

        with registry.cursor() as cr:
            # Create new environment from scratch
            env = api.Environment(cr, SUPERUSER_ID, {})

            # Helper function to add logs with new cursor
            def add_log(message, level='info'):
                color_map = {'info': '#17a2b8', 'success': '#28a745', 'warning': '#ffc107', 'error': '#dc3545'}
                icon_map = {'info': 'ℹ️', 'success': '✅', 'warning': '⚠️', 'error': '❌'}

                import datetime
                timestamp = datetime.datetime.now().strftime('%H:%M:%S')
                color = color_map.get(level, '#6c757d')
                icon = icon_map.get(level, '•')

                new_entry = f'<div style="margin: 5px 0; padding: 5px; border-left: 3px solid {color};">' \
                           f'<strong style="color: {color};">[{timestamp}] {icon} {message}</strong></div>'

                try:
                    cr.execute("SELECT status_log FROM voice_llm_model_downloader WHERE id = %s", (wizard_id,))
                    result = cr.fetchone()
                    current_log = result[0] if result and result[0] else ''

                    cr.execute("""
                        UPDATE voice_llm_model_downloader
                        SET status_log = %s
                        WHERE id = %s
                    """, (new_entry + current_log, wizard_id))
                    cr.commit()
                except Exception as e:
                    _logger.error(f"Error logging: {e}")

            try:
                # Initialize download status
                cr.execute("""
                    UPDATE voice_llm_model_downloader
                    SET download_status = 'downloading',
                        progress_percentage = 0.0,
                        downloaded_bytes = 0.0,
                        total_bytes = 0.0,
                        download_speed = 'Starting...',
                        download_message = %s
                    WHERE id = %s
                """, (f'🚀 Initializing download of {model_name}...', wizard_id))
                cr.commit()

                add_log("✅ Download thread started successfully!", 'success')
                add_log("Step 4: Connecting to Ollama...", 'info')
                add_log(f"Sending pull request to Ollama API...", 'info')
                add_log(f"POST {ollama_url}/api/pull", 'info')

                response = requests.post(
                    f"{ollama_url}/api/pull",
                    json={"name": model_name},
                    stream=True,
                    timeout=None
                )

                if response.status_code != 200:
                    error_msg = f"Download failed! HTTP {response.status_code}: {response.text}"
                    add_log(error_msg, 'error')

                    cr.execute("""
                        UPDATE voice_llm_model_downloader
                        SET download_status = 'error',
                            download_message = %s
                        WHERE id = %s
                    """, (error_msg, wizard_id))
                    cr.commit()
                    return

                add_log("✅ Download request accepted! Starting stream...", 'success')

                total_size = 0
                downloaded_size = 0
                start_time = time.time()
                last_update_time = start_time
                last_downloaded = 0

                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            status = data.get('status', '')

                            # Update progress
                            if 'total' in data and 'completed' in data:
                                total_size = data['total']
                                downloaded_size = data['completed']

                                if total_size > 0:
                                    progress = (downloaded_size / total_size) * 100

                                    # Calculate download speed
                                    current_time = time.time()
                                    time_diff = current_time - last_update_time

                                    if time_diff >= 1.0:  # Update every second
                                        bytes_diff = downloaded_size - last_downloaded
                                        speed_mbps = (bytes_diff / (1024 * 1024)) / time_diff

                                        if speed_mbps >= 1:
                                            speed_str = f"{speed_mbps:.2f} MB/s"
                                        else:
                                            speed_kbps = speed_mbps * 1024
                                            speed_str = f"{speed_kbps:.2f} KB/s"

                                        # Update database directly (avoid ORM in thread)
                                        cr.execute("""
                                            UPDATE voice_llm_model_downloader
                                            SET progress_percentage = %s,
                                                downloaded_bytes = %s,
                                                total_bytes = %s,
                                                download_speed = %s,
                                                download_message = %s
                                            WHERE id = %s
                                        """, (
                                            progress,
                                            downloaded_size / (1024 * 1024),  # MB
                                            total_size / (1024 * 1024),  # MB
                                            speed_str,
                                            f"⬇️ Downloading {model_name}...\n{status}",
                                            wizard_id
                                        ))
                                        cr.commit()

                                        last_update_time = current_time
                                        last_downloaded = downloaded_size

                            # Check if completed
                            if status == 'success':
                                cr.execute("""
                                    UPDATE voice_llm_model_downloader
                                    SET download_status = 'completed',
                                        progress_percentage = 100.0,
                                        download_message = %s
                                    WHERE id = %s
                                """, (f"✅ Successfully downloaded {model_name}!", wizard_id))
                                cr.commit()

                                # Update config parameter
                                cr.execute("""
                                    INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
                                    VALUES ('voice_command_hub.ollama_model', %s, 1, NOW(), 1, NOW())
                                    ON CONFLICT (key) DO UPDATE SET value = %s, write_date = NOW()
                                """, (model_name, model_name))
                                cr.commit()
                                add_log(f"✅ Download completed: {model_name}", 'success')
                                return

                        except json.JSONDecodeError:
                            continue

            except Exception as e:
                _logger.error(f"Error downloading model: {e}")
                add_log(f"❌ Error: {str(e)}", 'error')
                cr.execute("""
                    UPDATE voice_llm_model_downloader
                    SET download_status = 'error',
                        download_message = %s
                    WHERE id = %s
                """, (f"❌ Error: {str(e)}", wizard_id))
                cr.commit()

    def action_delete_model(self):
        """Delete an installed model"""
        self.ensure_one()

        if not self.selected_model:
            raise UserError(_("Please select a model to delete"))

        try:
            response = requests.delete(
                f"{self.ollama_url}/api/delete",
                json={"name": self.selected_model},
                timeout=10
            )

            if response.status_code == 200:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': f'Model "{self.selected_model}" deleted successfully!',
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_(f"Failed to delete model: {response.text}"))

        except Exception as e:
            raise UserError(_(f"Error deleting model: {str(e)}"))

    def action_refresh_status(self):
        """Manually refresh the download status"""
        self.ensure_one()

        # Invalidate all cached data for this record to force fresh read
        self.invalidate_recordset()

        # Re-browse the record to get completely fresh data from database
        # Note: We don't commit here to avoid concurrent update conflicts
        # The background download thread commits its own changes independently
        wizard = self.env['voice.llm.model.downloader'].browse(self.id)

        # Return action to reopen the wizard with fresh data
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'voice.llm.model.downloader',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
            'context': {'default_selected_model': wizard.selected_model},
        }
