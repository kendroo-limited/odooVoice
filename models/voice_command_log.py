# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class VoiceCommandLog(models.Model):
    _name = 'voice.command.log'
    _description = 'Voice Command Log'
    _order = 'timestamp desc'

    session_id = fields.Many2one(
        'voice.command.session',
        string='Session',
        required=True,
        ondelete='cascade',
        index=True
    )
    timestamp = fields.Datetime(
        string='Timestamp',
        required=True,
        default=fields.Datetime.now,
        index=True
    )
    level = fields.Selection([
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ], string='Level', required=True, default='info', index=True)

    message = fields.Text(
        string='Message',
        required=True
    )
    payload_json = fields.Json(
        string='Payload',
        help='Additional structured data as JSON'
    )

    # For easy filtering
    user_id = fields.Many2one(
        'res.users',
        string='User',
        related='session_id.user_id',
        store=True,
        index=True
    )

    def name_get(self):
        result = []
        for record in self:
            name = f"[{record.level.upper()}] {record.message[:50]}"
            result.append((record.id, name))
        return result
