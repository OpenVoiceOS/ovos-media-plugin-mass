"""Backwards-compatible re-export.

The Music Assistant HTTP client now lives in the standalone ``py-music-assistant``
package and is shared across the OVOS Music Assistant integrations. This module
re-exports it so existing imports of
``ovos_media_plugin_mass.music_assistant_client`` keep working.
"""
from py_music_assistant import SimpleHTTPMusicAssistantClient, debug_method

__all__ = ["SimpleHTTPMusicAssistantClient", "debug_method"]
