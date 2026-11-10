#!/usr/bin/env python3
"""KzL Agent — native GTK4/libadwaita Linux client (no webview)."""
import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import html
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import subprocess
import sys
import urllib.parse

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

from backend import Gateway, DemoGateway, Store, PocketError, ReadRetry, activity_rows, search_loaded_messages, tool_state_label, tool_progress, conversation_export, attachment, prompt_payload, field_visible, form_answers, experimental_session_path, artifacts, save_download, schedule_payload
from richtext import render_native, safe_url
from terminal_policy import directory_path
from account_client import AccountClient

ROOT = Path(__file__).resolve().parent
STYLE = '''
window { background: @window_bg_color; }
.brand { font-size: 21px; font-weight: 750; letter-spacing: -.5px; }
.muted { color: alpha(@window_fg_color, .68); }
.sidebar { background: alpha(@window_fg_color, .025); }
.sidebar-brand { padding: 8px 4px 12px; }
.sidebar-subtitle, .session-directory { font-size: 12px; }
.sidebar-actions button { min-height: 42px; border-radius: 12px; }
.sidebar-actions .new-conversation { background: #a71e36; color: white; border: 1px solid #dd4057; }
.sidebar-actions .new-conversation:hover { background: #be2942; }
.sidebar-search { min-height: 38px; border-radius: 12px; }
.sidebar-section { font-size: 12px; font-weight: 600; }
.sidebar-row { padding: 10px 12px; border-radius: 10px; margin: 1px 8px; }
.sidebar-row:selected { background: alpha(@window_fg_color, .075); color: @window_fg_color; }
.session-title { font-size: 13px; font-weight: 550; }
.session-time, .message-time { font-size: 11px; color: alpha(@window_fg_color, .6); }
.sidebar-footer { padding: 12px 10px 0; border-top: 1px solid alpha(@window_fg_color, .1); }
.sidebar-footer button { min-width: 36px; min-height: 38px; border-radius: 10px; }
.sidebar-more { min-height: 34px; border-radius: 10px; margin: 8px 16px 16px; }
.chat-panel { border: 1px solid alpha(@window_fg_color, .1); border-radius: 20px; }
.chat-title { font-size: 18px; font-weight: 650; }
.chat-subtitle { font-size: 12px; color: alpha(@window_fg_color, .68); }
.toolbar-flat { padding: 18px 20px; border-bottom: 1px solid alpha(@window_fg_color, .08); }
.toolbar-flat button, .toolbar-flat menubutton > button { min-width: 32px; min-height: 34px; border-radius: 10px; }
.chat-actions { padding: 6px; }
.chat-actions button { min-height: 36px; border-radius: 9px; }
.agent-identity { padding: 5px; border: 1px solid alpha(@window_fg_color, .12); border-radius: 12px; background: alpha(@window_fg_color, .035); }
.message-avatar { min-width: 28px; min-height: 28px; }
.user-avatar { border-radius: 50%; padding: 6px; background: alpha(@window_fg_color, .06); }
.user-bubble { background: alpha(@window_fg_color, .055); border: 1px solid alpha(@window_fg_color, .1); padding: 12px 16px; border-radius: 16px; }
.message-text { font-size: 16px; line-height: 1.5; }
.code-block { font-family: monospace; font-size: 13px; padding: 12px; border-radius: 10px; background: alpha(@window_fg_color, .045); }
.tool-disclosure { padding: 10px 12px; border-radius: 10px; background: alpha(@window_fg_color, .045); }
.tool-disclosure > title { font-size: 12px; }
.composer { border-radius: 18px; background: alpha(@window_fg_color, .035); border: 1px solid alpha(@window_fg_color, .2); padding: 8px; box-shadow: 0 4px 18px alpha(black, .05); }
.composer:focus-within { border-color: #e54860; }
.composer textview, .composer textview text { background: transparent; font-size: 15px; }
.composer button { border-radius: 12px; min-height: 44px; min-width: 44px; background: transparent; box-shadow: none; border: 0; padding: 0; }
.composer .voice-action { background: alpha(@window_fg_color, .06); }
.composer .send { background: #c62743; color: white; }
.composer .send:hover { background: #df3653; }
.composer .send:disabled { background: alpha(@window_fg_color, .08); color: alpha(@window_fg_color, .4); opacity: 1; }
.composer-footer { margin: 0 28px 16px; }
.conversation-options button { min-height: 32px; border-radius: 18px; padding: 3px 12px; }
.conversation-options .model-picker { font-size: 12px; font-weight: 500; }
.conversation-status { font-size: 11px; color: alpha(@window_fg_color, .66); }
.error-banner { background: alpha(#c41a29, .09); padding: 10px 16px; border-radius: 12px; }
.permission { background: alpha(#c58a17, .12); padding: 10px; border-radius: 12px; }
.kzl-name { color: #c41a29; font-weight: 650; }
.empty-title { font-size: 28px; font-weight: 600; letter-spacing: -.8px; }
.pill { border-radius: 15px; padding: 3px 10px; }
button:focus-visible, entry:focus-visible, textview:focus-visible { outline: 2px solid #cc304a; outline-offset: 2px; }
.call-start { background: @window_fg_color; color: @window_bg_color; min-height: 38px; border-radius: 16px; }
.kzl-call-start { background: #c41a29; color: white; }
.md-h1 { font-size: 26px; font-weight: 700; letter-spacing: -.6px; }
.md-h2 { font-size: 22px; font-weight: 650; letter-spacing: -.3px; }
.md-h3 { font-size: 19px; font-weight: 600; }
.md-h4, .md-h5, .md-h6 { font-size: 16px; font-weight: 600; }
.md-quote { border-left: 3px solid alpha(@window_fg_color, .22); padding: 4px 0 4px 14px; color: alpha(@window_fg_color, .8); }
.md-table-cell { padding: 8px 12px; border-bottom: 1px solid alpha(@window_fg_color, .1); font-size: 14px; }
.md-table-head { background: alpha(@window_fg_color, .07); font-weight: 600; }
.md-table-alt { background: alpha(@window_fg_color, .025); }
.md-table-scroll { border: 1px solid alpha(@window_fg_color, .12); border-radius: 12px; }
.md-code-view, .md-code-view text { background: transparent; font-family: monospace; font-size: 13px; }
/* Native graphite/red redesign. Light/system choices and focus stay available. */
window.darktech { background: #0e0f11; color: #f2f2f5; }
.darktech headerbar { background: #101114; color: #f2f2f5; box-shadow: none; border-bottom: 1px solid #24252b; }
.darktech .sidebar { background: #101113; }
.darktech .sidebar-actions button, .darktech .sidebar-more { background: #1c1d21; border: 1px solid #34353d; }
.darktech .sidebar-actions .new-conversation { background: linear-gradient(110deg, #64152a, #30151e); border-color: #cb334f; }
.darktech .sidebar-actions .new-conversation:hover { background: #732039; }
.darktech .sidebar-search { background: #1b1c20; border: 1px solid #34353b; }
.darktech .sidebar-row:selected { background: linear-gradient(110deg, #431924, #2b1a21); color: white; box-shadow: inset 2px 0 #e53c5b; }
.darktech .sidebar-row:selected image { color: #f34b69; }
.darktech .chat-panel { background: #0f1012; border-color: #26272d; }
.darktech .toolbar-flat { border-bottom-color: #26272d; background: linear-gradient(140deg, #101113 60%, #241319); border-radius: 20px 20px 0 0; }
.darktech .toolbar-flat button, .darktech .toolbar-flat menubutton > button { background: #17181b; border: 1px solid #2d2e34; }
.darktech .agent-identity { background: #21171e; border-color: #3d2833; }
.darktech .kzl-name { color: #ff637b; }
.darktech .muted, .darktech .dim-label, .darktech .chat-subtitle { color: #b5b5c0; opacity: 1; }
.darktech .user-bubble { background: #242027; border-color: #3c303d; }
.darktech .tool-disclosure { background: #1a1b1f; }
.darktech .composer { background: linear-gradient(115deg, #242027, #191a1e); border-color: #a22c45; box-shadow: 0 6px 20px alpha(black, .2); }
.darktech .composer:focus-within { border-color: #ef4664; }
.darktech .composer .send { background: linear-gradient(135deg, #e43d5a, #ac1d37); }
.darktech .composer .send:hover { background: #e84360; }
.darktech .composer .send:disabled { background: #343039; color: #aaa4b0; }
.darktech .conversation-options .model-picker { background: #1a1b1f; border: 1px solid #34353c; color: #e4e4e9; }
.darktech .code-block { background: #15161b; border: 1px solid #2a2b33; }
.darktech .error-banner { background: #321820; color: #ffb8be; border: 1px solid #71313d; }
.darktech .permission { background: #302515; color: #f6d499; border: 1px solid #64502e; }
.darktech .md-table-head { background: #23232e; }
.darktech .md-table-alt { background: #121219; }
.darktech .md-table-scroll { border-color: #363643; }
.darktech button:focus-visible, .darktech entry:focus-visible, .darktech textview:focus-visible { outline-color: #ff637b; }
.compact .toolbar-flat { padding: 12px; }
.compact .chat-panel { border-radius: 0; border-width: 0; }
.compact .composer-footer { margin: 0 16px 12px; }
'''


def box(vertical=False, spacing=0):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)


def label(text='', cls=None, wrap=False):
    widget = Gtk.Label(label=str(text), xalign=0)
    if cls:
        widget.add_css_class(cls)
    if wrap:
        widget.set_wrap(True); widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    return widget


def margins(widget, value):
    for side in ('top', 'bottom', 'start', 'end'):
        getattr(widget, 'set_margin_' + side)(value)
    return widget


def button(icon=None, text=None, callback=None, tooltip=None):
    widget = Gtk.Button(icon_name=icon) if icon else Gtk.Button(label=text)
    if icon:
        widget.add_css_class('flat')
    if callback:
        widget.connect('clicked', lambda *_: callback())
    if tooltip:
        widget.set_tooltip_text(tooltip)
        widget.update_property([Gtk.AccessibleProperty.LABEL], [tooltip])
    return widget


def children(widget):
    child = widget.get_first_child()
    while child:
        following = child.get_next_sibling(); yield child; child = following


def clear(widget):
    for child in children(widget):
        widget.remove(child)


def inline(text):
    """Small safe Markdown subset. Never execute markup supplied by a tool."""
    escaped = html.escape(text)
    escaped = re.sub(r'`([^`\n]+)`', r'<tt>\1</tt>', escaped)
    return re.sub(r'\*\*([^*\n]+)\*\*', r'<b>\1</b>', escaped)


def display_time(value, relative=False):
    """Format gateway epoch milliseconds (or legacy seconds); missing stays blank."""
    try:
        stamp = float(value)
        if stamp <= 0:
            return ''
        moment = datetime.fromtimestamp(stamp / 1000 if stamp > 100_000_000_000 else stamp)
        if relative and moment.date() != datetime.now().date():
            return 'Ontem' if moment.date() == (datetime.now() - timedelta(days=1)).date() else moment.strftime('%d/%m')
        return moment.strftime('%H:%M')
    except (ValueError, TypeError, OverflowError, OSError):
        return ''


class Pocket(Gtk.Application):
    def __init__(self, demo=False, state=None):
        super().__init__(application_id='com.omokir.PocketDesktop', flags=Gio.ApplicationFlags.NON_UNIQUE if demo else Gio.ApplicationFlags.DEFAULT_FLAGS)
        root = Path(state or Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / ('opencode-pocket-desktop-demo' if demo else 'opencode-pocket-desktop'))
        self.store = Store(root)
        self.client = DemoGateway() if demo else Gateway(root, legacy=Path.home() / '.local/state/opencode-iphone/token.secret')
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='pocket')
        self.session = None; self.sessions = []; self.messages = []; self.catalog = []
        self.scope = 0; self.list_ticket = 0; self.refreshing = False; self.busy = False
        self.read_gates = {key: ReadRetry() for key in ('sessions', 'catalog', 'last', 'history')}
        self.list_queued = None; self.last_lookup = None; self.read_errors = {}; self.notice_owner = None
        self.closing = False; self.hydrating = False; self.save_timer = 0
        self.save_error = None
        self.pairing_in_flight = False
        self.cursor = None; self.older = None; self.loaded_older = False; self.render_key = None
        self.older_loading = False
        self.permission_snapshot = []; self.form_snapshot = []
        self.review_available = {'permission': True, 'form': True}
        self.review_epoch = {'permission': 0, 'form': 0}
        self.message_widgets = {}
        self.directory = ''; self.dialogs = []; self.sent = 0; self.errors = []
        self.voice_window = None; self.voice_session = None; self.voice_media = None; self.voice_generation = 0; self.tone = None
        self.voice_cancel = None
        self.save_chooser_factory = Gtk.FileChooserNative
        self.save_choosers = []
        self.uploads = None; self.transfer_window = None; self.upload_running_id = None; self.upload_job_cancel = None
        self.upload_chooser_factory = Gtk.FileChooserNative; self.upload_choosers = []
        self.terminal_processes = []

    def async_job(self, work, done=None, failed=None, scoped=True):
        scope = self.scope
        future = self.pool.submit(work)
        def finished(future):
            try:
                value = future.result(); error = None
            except Exception as exc:
                value = None; error = str(exc)
            def apply():
                if self.closing or (scoped and scope != self.scope):
                    return GLib.SOURCE_REMOVE
                if error:
                    (failed or self.error)(error)
                elif done:
                    done(value)
                return GLib.SOURCE_REMOVE
            GLib.idle_add(apply)
        future.add_done_callback(finished)

    def do_activate(self):
        if hasattr(self, 'window'):
            self.window.present(); return
        Adw.init()
        css = Gtk.CssProvider(); css.load_from_string(STYLE)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = Gtk.ApplicationWindow(application=self, title='KzL Agent')
        self.window.set_default_size(1280, 860)
        self.window.connect('close-request', self.close)
        shortcuts = Gtk.EventControllerKey(); shortcuts.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        shortcuts.connect('key-pressed', self.window_shortcuts); self.window.add_controller(shortcuts)
        self.root = box(True)
        self.header = Gtk.HeaderBar()
        self.header.set_title_widget(label('KzL Agent', 'sidebar-section'))
        self.history_button = button('sidebar-show-symbolic', callback=self.toggle_sidebar, tooltip='Histórico')
        self.header.pack_start(self.history_button)
        self.portrait = Gtk.ToggleButton(icon_name='phone-symbolic', tooltip_text='Modo retrato · 414 px')
        self.portrait.connect('toggled', self.portrait_changed)
        self.header.pack_end(self.portrait)
        self.header.pack_end(button('emblem-system-symbolic', callback=self.settings, tooltip='Ajustes'))
        self.window.set_titlebar(self.header)
        self.body = box()
        self.sidebar = box(True, 0); self.sidebar.set_size_request(300, -1); self.sidebar.set_hexpand(False); self.sidebar.add_css_class('sidebar')
        self.build_sidebar()
        self.body.append(self.sidebar)
        self.content = box(True); self.content.set_hexpand(True); self.content.add_css_class('chat-panel'); margins(self.content, 8)
        self.build_chat(); self.body.append(self.content)
        self.root.append(self.body); self.body.set_vexpand(True)
        self.window.set_child(self.root)
        manager = Adw.StyleManager.get_default()
        manager.connect('notify::dark', lambda *_: self.sync_theme_classes())
        # Explicit redesign request changes the initial look, not other state.
        theme = self.store.data.get('theme', 'dark') if self.store.data.get('darktech_v1') else 'dark'
        self.store.data['darktech_v1'] = True
        self.apply_theme(theme)
        self.portrait.set_active(bool(self.store.data.get('portrait')))
        self.window.present()
        self.load_sessions(initial=True); self.load_catalog()
        self.poll_timer = GLib.timeout_add(1200, self.poll)

    def brand_image(self, size=32):
        picture = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROOT / 'KzL.png'), size, size, True))
        picture.set_pixel_size(size); picture.set_size_request(size, size)
        return picture

    def action_button(self, icon, title, callback):
        item = button(callback=callback, tooltip=title)
        content = box(False, 12); content.append(Gtk.Image.new_from_icon_name(icon)); content.append(label(title))
        item.set_child(content)
        return item

    def build_sidebar(self):
        brand = margins(box(False, 12), 18); brand.add_css_class('sidebar-brand')
        brand.append(self.brand_image(40))
        text = box(True, 3); text.append(label('KzL Agent', 'brand'))
        subtitle = label('Seu agente no computador', 'sidebar-subtitle'); subtitle.add_css_class('muted'); subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        text.append(subtitle); brand.append(text); self.sidebar.append(brand)
        actions = box(True, 8); actions.add_css_class('sidebar-actions'); actions.set_margin_start(18); actions.set_margin_end(18)
        self.new_button = self.action_button('list-add-symbolic', 'Nova conversa', self.new_chat); self.new_button.add_css_class('new-conversation'); actions.append(self.new_button)
        actions.append(self.action_button('chat-symbolic', 'Conversar com KzL', self.open_kzl)); self.sidebar.append(actions)
        self.search = Gtk.SearchEntry(placeholder_text='Buscar conversas'); margins(self.search, 18); self.search.add_css_class('sidebar-search')
        self.search.set_tooltip_text('Buscar conversas · Ctrl+K')
        self.search.connect('search-changed', lambda *_: self.load_sessions()); self.sidebar.append(self.search)
        heading = box(False, 10); heading.set_margin_start(24); heading.set_margin_end(18); heading.set_margin_bottom(10)
        heading.append(Gtk.Image.new_from_icon_name('view-list-symbolic')); heading.append(label('Conversas recentes', 'sidebar-section')); self.sidebar.append(heading)
        scroll = Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); scroll.set_vexpand(True)
        self.session_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.session_list.add_css_class('navigation-sidebar'); self.session_list.connect('row-activated', self.row_activated)
        scroll.set_child(self.session_list); self.sidebar.append(scroll)
        self.more = button(text='Ver mais conversas', callback=lambda: self.load_sessions(more=True)); self.more.add_css_class('sidebar-more'); self.more.set_visible(False); self.sidebar.append(self.more)
        footer = box(False, 3); footer.add_css_class('sidebar-footer')
        for icon, title, callback in [('folder-symbolic', 'Arquivos', self.files), ('go-up-symbolic', 'Transferências retomáveis', self.transfers), ('view-list-symbolic', 'Atividade e alterações', self.activity), ('computer-symbolic', 'Computador', self.computer)]:
            item = button(icon, callback=callback, tooltip=title); item.set_hexpand(True); footer.append(item)
        self.sidebar.append(footer)
        detail = label('Demonstração · sem API' if self.client.demo else 'Computador local · KzL Agent', 'sidebar-subtitle'); detail.add_css_class('muted'); self.sidebar.append(margins(detail, 18))

    def build_chat(self):
        toolbar = box(False, 10); toolbar.add_css_class('toolbar-flat')
        identity = self.brand_image(32); identity.add_css_class('agent-identity'); toolbar.append(identity)
        heading = box(True, 4); heading.set_hexpand(True)
        self.title = label('Como posso ajudar?', 'chat-title'); self.title.set_ellipsize(Pango.EllipsizeMode.END); self.title.set_max_width_chars(30); heading.append(self.title)
        self.subtitle = label('Seu agente no computador', 'chat-subtitle'); self.subtitle.set_ellipsize(Pango.EllipsizeMode.END); self.subtitle.set_max_width_chars(30); heading.append(self.subtitle); toolbar.append(heading)
        self.pin_button = button('non-starred-symbolic', callback=self.toggle_pin, tooltip='Fixar conversa'); toolbar.append(self.pin_button)
        toolbar.append(button('document-edit-symbolic', callback=self.rename, tooltip='Renomear conversa'))
        self.chat_menu = Gtk.MenuButton(icon_name='view-more-symbolic', tooltip_text='Mais ações da conversa')
        self.chat_menu.update_property([Gtk.AccessibleProperty.LABEL], ['Mais ações da conversa'])
        self.chat_popover = Gtk.Popover(); menu = box(True, 4); menu.add_css_class('chat-actions')
        def action(icon, title, callback):
            item = self.action_button(icon, title, lambda: (self.chat_popover.popdown(), callback()))
            menu.append(item); return item
        action('document-new-symbolic', 'Nova conversa', self.new_chat)
        action('folder-new-symbolic', 'Novo chat em um projeto', self.choose_project)
        action('starred-symbolic', 'Projetos favoritos', self.projects)
        menu.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        action('system-run-symbolic', 'Comandos, skills e fila', self.resources)
        self.terminal_button = action('utilities-terminal-symbolic', 'Terminal local do projeto', self.open_terminal)
        self.stop_button = action('media-playback-stop-symbolic', 'Interromper execução', self.interrupt)
        self.chat_popover.set_child(menu); self.chat_menu.set_popover(self.chat_popover); toolbar.append(self.chat_menu); self.content.append(toolbar)
        self.notice = label('', 'error-banner', True); margins(self.notice, 12); self.notice.set_visible(False); self.notice.set_selectable(True); self.root.append(self.notice)  # Visible even when portrait history replaces the chat.
        self.scroll = Gtk.ScrolledWindow(); self.scroll.set_vexpand(True); self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.message_box = box(True, 28); margins(self.message_box, 24)
        clamp = Adw.Clamp(maximum_size=960, tightening_threshold=720); clamp.set_child(self.message_box)
        self.scroll.update_property([Gtk.AccessibleProperty.LABEL], ['Histórico da conversa'])
        self.scroll.set_child(clamp); self.content.append(self.scroll)
        self.permission_box = margins(box(True, 5), 10); self.permission_box.set_visible(False); self.content.append(self.permission_box)
        self.attach_box = margins(box(False, 5), 10); self.attach_box.set_visible(False); self.content.append(self.attach_box)
        self.compose = margins(box(False, 8), 24); self.compose.add_css_class('composer'); self.compose.set_valign(Gtk.Align.END)
        self.compose.set_margin_top(10); self.compose.set_margin_bottom(12)
        self.compose.append(button('mail-attachment-symbolic', callback=self.attach, tooltip='Anexar imagens, PDF ou texto'))
        self.draft = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR); self.draft.set_top_margin(12); self.draft.set_bottom_margin(10); self.draft.set_left_margin(4); self.draft.set_right_margin(4)
        self.draft.update_property([Gtk.AccessibleProperty.LABEL], ['Mensagem'])
        self.draft.get_buffer().connect('changed', self.draft_changed)
        keys = Gtk.EventControllerKey(); keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE); keys.connect('key-pressed', self.key_pressed); self.draft.add_controller(keys)
        draft_scroll = Gtk.ScrolledWindow(); draft_scroll.set_hexpand(True); draft_scroll.set_min_content_height(44); draft_scroll.set_max_content_height(150); draft_scroll.set_propagate_natural_height(True); draft_scroll.set_child(self.draft)
        overlay = Gtk.Overlay(); overlay.set_child(draft_scroll); overlay.set_hexpand(True)
        self.placeholder = label('Mensagem para o Agente KzL…', 'muted'); self.placeholder.set_ellipsize(Pango.EllipsizeMode.END); self.placeholder.set_margin_start(5); self.placeholder.set_valign(Gtk.Align.CENTER); self.placeholder.set_can_target(False); overlay.add_overlay(self.placeholder); self.compose.append(overlay)
        self.voice_button = button('audio-input-microphone-symbolic', callback=self.open_voice, tooltip='Live desta conversa · API paga'); self.voice_button.add_css_class('voice-action'); self.voice_button.set_valign(Gtk.Align.END); self.compose.append(self.voice_button)
        self.send_button = button('document-send-symbolic', callback=self.send, tooltip='Enviar mensagem · Enter'); self.send_button.add_css_class('send'); self.send_button.set_valign(Gtk.Align.END); self.compose.append(self.send_button)
        clamp = Adw.Clamp(maximum_size=960); clamp.set_child(self.compose); self.content.append(clamp)
        self.composer_footer = box(False, 12); self.composer_footer.add_css_class('composer-footer'); self.composer_footer.add_css_class('conversation-options')
        self.status = label('Demonstração sem API' if self.client.demo else 'Conectando ao computador…', 'conversation-status'); self.status.set_ellipsize(Pango.EllipsizeMode.END); self.status.set_hexpand(True); self.status.set_valign(Gtk.Align.CENTER); self.composer_footer.append(self.status)
        self.options_button = button(text='Modelo · Build', callback=self.options, tooltip='Modelo e modo da conversa'); self.options_button.add_css_class('model-picker'); self.options_button.set_halign(Gtk.Align.END)
        self.options_button.get_child().set_ellipsize(Pango.EllipsizeMode.END); self.options_button.get_child().set_max_width_chars(28); self.composer_footer.append(self.options_button)
        clamp = Adw.Clamp(maximum_size=960); clamp.set_child(self.composer_footer); self.content.append(clamp)

    def error(self, text):
        if not text and self.save_error:
            text = self.save_error; self.notice_owner = 'storage'
        else:
            self.notice_owner = None
        self.notice.set_text(str(text)); self.notice.set_visible(bool(text)); self.errors.append(str(text)) if text else None

    def read_result(self, channel, error=None):
        if error:
            self.read_errors[channel] = error; self.errors.append(error)
        else:
            self.read_errors.pop(channel, None)
        if self.save_error:
            self.error(''); return
        if self.session and self.store.pending_prompts(self.session['id']):
            self.restore_outgoing_notice(); return
        # Do not erase unrelated action errors when a background GET succeeds.
        if self.notice_owner and self.notice_owner.startswith('read:'):
            if not self.read_errors:
                self.notice.set_text(''); self.notice.set_visible(False); self.notice_owner = None
            else:
                key = next(reversed(self.read_errors)); self.notice_owner = 'read:' + key
                self.notice.set_text(self.read_errors[key]); self.notice.set_visible(True)
        elif not self.notice.get_visible() and self.read_errors:
            key = next(reversed(self.read_errors)); self.notice_owner = 'read:' + key
            self.notice.set_text(self.read_errors[key]); self.notice.set_visible(True)

    def dialog(self, title, width=600):
        window = Gtk.Window(title=title, transient_for=self.window, modal=True)
        if Adw.StyleManager.get_default().get_dark():
            window.add_css_class('darktech')
        header = Gtk.HeaderBar(); header.set_title_widget(label(title, 'chat-title')); window.set_titlebar(header)
        window.set_default_size(width, 420)
        content = margins(box(True, 12), 20)
        scroll = Gtk.ScrolledWindow(); scroll.set_child(content); scroll.set_vexpand(True)
        root = box(True); root.append(scroll); root.append(margins(button(text='Fechar', callback=window.close), 12)); window.set_child(root)
        self.dialogs.append(window); window.connect('close-request', lambda *_: self.dialogs.remove(window) if window in self.dialogs else None)
        window.present(); return window, content

    def confirm(self, title, detail, callback):
        window, content = self.dialog(title, 480)
        content.append(label(detail, wrap=True))
        accept = button(text='Confirmar', callback=lambda: (window.close(), callback())); accept.add_css_class('suggested-action'); content.append(accept)

    def request_path(self, suffix=''):
        if not self.session:
            raise PocketError('Abra uma conversa primeiro.')
        return '/api/session/' + urllib.parse.quote(self.session['id'], safe='') + suffix

    def load_sessions(self, more=False, initial=False, automatic=False):
        gate = self.read_gates['sessions']
        if not gate.begin(manual=not automatic):
            if not automatic and gate.in_flight:
                self.list_queued = (more, initial)  # Only the latest manual search survives.
            return
        self.list_ticket += 1; ticket = self.list_ticket; scope = self.scope
        self.last_lookup = None; self.more.set_sensitive(False)
        params = {'limit': '30', 'archived': 'false', 'parentID': 'null', 'search': self.search.get_text()}
        params['cursor' if more else 'order'] = self.cursor if more else 'desc'
        def queued():
            request = self.list_queued; self.list_queued = None
            if request is not None:
                self.load_sessions(*request); return True
            return False
        def done(page):
            gate.success(); self.more.set_sensitive(True)
            if queued():
                return
            if ticket != self.list_ticket:
                return
            self.sessions = list({s['id']: s for s in ((self.sessions if more else []) + page.get('data', []))}.values())
            self.cursor = (page.get('cursor') or {}).get('next'); self.more.set_visible(bool(self.cursor)); self.render_sessions()
            self.read_result('sessions')
            if initial and scope == self.scope and not params['search'] and not self.search.get_text():
                last = self.store.data.get('last')
                selected = next((s for s in self.sessions if s['id'] == last), None)
                if last and not selected and re.fullmatch(r'ses[A-Za-z0-9_-]+', last):
                    self.last_lookup = (last, scope, ticket); self.read_gates['last'].invalidate(); self.load_last_session()
                elif selected or self.sessions:
                    self.open_chat(selected or self.sessions[0])
                else:
                    self.render_messages([])
            if not self.session:
                self.status.set_text('Restaurando última conversa…' if self.last_lookup else 'Conectado · selecione uma conversa ou crie uma explicitamente')
            self.restore_outgoing_notice()
        def failed(text):
            gate.failure(); self.more.set_sensitive(True)
            if queued():
                return
            self.read_result('sessions', text)
            if not self.session:
                self.status.set_text('Gateway indisponível · reconexão somente de leitura')
        self.async_job(lambda: self.client.request('/api/session?' + urllib.parse.urlencode(params)), done, failed, scoped=False)

    def load_last_session(self):
        lookup = self.last_lookup; gate = self.read_gates['last']
        if not lookup or not gate.begin():
            return
        identifier, scope, ticket = lookup
        def work():
            try:
                return self.client.request('/api/session/' + identifier), None
            except Exception as error:
                return None, error
        def done(result):
            if lookup != self.last_lookup or scope != self.scope or ticket != self.list_ticket:
                gate.abandon(); return
            value, error = result
            if error:
                if getattr(error, 'status', None) in (None, 408, 429, 500, 502, 503, 504):
                    gate.failure()
                else:
                    gate.success()  # Missing/forbidden chat requires user review, not a substitute chat.
                self.read_result('last', 'Última conversa indisponível; histórico não foi substituído. ' + str(error))
                self.status.set_text('Última conversa indisponível · histórico preservado; nenhuma substituição criada'); return
            gate.success(); self.read_result('last'); self.open_chat(value['data'])
        self.async_job(work, done, scoped=False)

    def render_sessions(self):
        clear(self.session_list)
        pins = set(self.store.data.get('pins', []))
        ordered = sorted(self.sessions, key=lambda s: (s['id'] not in pins, -(s.get('time') or {}).get('updated', 0)))
        for session in ordered:
            if (session.get('metadata') or {}).get('kzlAgent'):
                continue
            row = Gtk.ListBoxRow(); row.add_css_class('sidebar-row'); row.session = session
            content = box(False, 12)
            icon = Gtk.Image.new_from_icon_name('starred-symbolic' if session['id'] in pins else 'chat-symbolic'); content.append(icon)
            details = box(True, 3); details.set_hexpand(True)
            title = label(session.get('title') or 'Sem título', 'session-title'); title.set_ellipsize(Pango.EllipsizeMode.END); title.set_max_width_chars(24); details.append(title)
            directory = Path(session.get('location', {}).get('directory', '')).name
            project = label(directory, 'session-directory'); project.add_css_class('muted'); project.set_ellipsize(Pango.EllipsizeMode.END); project.set_max_width_chars(24); details.append(project); content.append(details)
            when = label(display_time((session.get('time') or {}).get('updated'), relative=True), 'session-time'); when.set_valign(Gtk.Align.START); content.append(when)
            row.set_child(content); self.session_list.append(row)
            if self.session and session['id'] == self.session['id']:
                self.session_list.select_row(row)

    def row_activated(self, _, row):
        self.open_chat(row.session)

    def current_draft(self, sid=None):
        sid = sid or (self.session or {}).get('id')
        return self.store.data['drafts'].setdefault(sid, {'text': '', 'files': []}) if sid else {'text': '', 'files': []}

    def persist(self):
        try:
            self.store.save()
            self.save_error = None
            if self.notice_owner == 'storage':
                self.error(''); self.restore_outgoing_notice()
        except Exception as exc:
            self.save_error = 'Não foi possível salvar preferências/rascunho: ' + str(exc)
            self.error('')
        return GLib.SOURCE_REMOVE

    def draft_changed(self, *_):
        if self.hydrating:
            return
        buffer = self.draft.get_buffer(); text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        self.current_draft()['text'] = text
        self.update_composer()
        if self.save_timer:
            GLib.source_remove(self.save_timer)
        self.save_timer = GLib.timeout_add(500, self.save_draft)

    def save_draft(self):
        self.save_timer = 0; self.persist(); return GLib.SOURCE_REMOVE

    def update_composer(self):
        draft = self.current_draft(); self.send_button.set_sensitive(not self.busy and bool(draft['text'].strip() or draft.get('files')))
        self.draft.set_editable(not self.busy)
        self.placeholder.set_visible(not draft['text'])

    def open_chat(self, session):
        self.persist(); self.scope += 1; self.refreshing = False; self.session = session
        self.read_gates['history'] = ReadRetry(); self.last_lookup = None
        for channel in ('history', 'last', 'permission', 'form'):
            self.read_errors.pop(channel, None)
        self.messages = []; self.render_key = None; self.loaded_older = False; self.older = None
        self.older_loading = False
        self.permission_snapshot = []; self.form_snapshot = []
        self.review_available = {'permission': True, 'form': True}
        self.store.data['last'] = session['id']; self.persist()
        self.title.set_text(session.get('title') or 'Conversa'); self.update_options_label()
        self.pin_button.set_icon_name('starred-symbolic' if session['id'] in self.store.data['pins'] else 'non-starred-symbolic')
        self.hydrating = True; self.draft.get_buffer().set_text(self.current_draft()['text']); self.hydrating = False
        self.render_attachments(); self.update_composer(); self.render_sessions(); clear(self.permission_box)
        self.render_messages([]); self.error(''); self.restore_outgoing_notice(); self.refresh()
        if self.portrait.get_active():
            self.sidebar.set_visible(False); self.content.set_visible(True)

    def update_options_label(self):
        session = self.session or {}; model = session.get('model') or {}
        name = next((m.get('name') or m['id'] for m in self.catalog if m['id'] == model.get('id') and m['providerID'] == model.get('providerID')), model.get('id', 'Modelo padrão'))
        description = name + ' · ' + (session.get('agent') or 'build').capitalize()
        self.options_button.set_label(description)
        self.subtitle.set_text(description)
        self.options_button.set_tooltip_text('Modelo e modo da conversa: ' + description)

    def restore_outgoing_notice(self):
        if self.save_error:
            self.error(''); return
        if self.session and self.store.pending_prompts(self.session['id']):
            self.notice.set_text('Envio anterior sem confirmação. Confira o histórico antes de repetir; pedido e identificador foram preservados. Nada será reenviado automaticamente.')
            self.notice.set_visible(True)
            self.notice_owner = 'outgoing'

    def reconcile_outgoing(self):
        result = self.store.reconcile_prompts(self.session['id'], self.messages)
        if result['draft_cleared']:
            self.hydrating = True; self.draft.get_buffer().set_text(''); self.hydrating = False
            self.render_attachments(); self.update_composer()
        if result['admitted']:
            self.persist()
            if self.notice.get_text().startswith(('Envio anterior sem confirmação.', 'Envio não confirmado.')):
                self.notice.set_text(''); self.notice.set_visible(False)
                self.notice_owner = None
        if result['pending']:
            self.restore_outgoing_notice()

    def poll(self):
        if self.closing:
            return GLib.SOURCE_REMOVE
        if self.window.get_visible():
            if self.session and not self.refreshing:
                self.refresh(manual=False)
            elif not self.session:
                if not self.read_gates['sessions'].ready:
                    self.load_sessions(initial=True, automatic=True)
                elif self.last_lookup:
                    self.load_last_session()
            if not self.read_gates['catalog'].ready:
                self.load_catalog(automatic=True)
        return GLib.SOURCE_CONTINUE

    def refresh(self, manual=True):
        if not self.session or self.refreshing:
            return
        gate = self.read_gates['history']
        if not gate.begin(manual=manual, repeat=True):
            return
        self.refreshing = True; path = self.request_path()
        def work():
            page = self.client.request(path + '/message?limit=50&order=desc')
            reviews = {}; failures = {}
            for kind in ('permission', 'form'):
                try:
                    reviews[kind] = self.client.request(path + '/' + kind)
                except Exception as exc:
                    failures[kind] = str(exc)
            return page, reviews, failures
        def done(result):
            self.refreshing = False
            gate.success()
            page, reviews, failures = result
            merged = {m['id']: m for m in self.messages}
            merged.update({m['id']: m for m in page.get('data', [])})
            self.messages = sorted(merged.values(), key=lambda m: (m.get('time', {}).get('created', 0), m['id']))
            self.reconcile_outgoing()
            if not self.loaded_older:
                self.older = (page.get('cursor') or {}).get('next')
            for kind, attribute in (('permission', 'permission_snapshot'), ('form', 'form_snapshot')):
                if kind in failures:
                    self.review_epoch[kind] += 1
                self.review_available[kind] = kind not in failures
                if kind in reviews:
                    setattr(self, attribute, reviews[kind].get('data', []))
                self.read_result(kind, ('Revisão indisponível; controles antigos bloqueados. ' + failures[kind]) if kind in failures else None)
            self.render_messages(self.messages)
            self.render_permissions(self.permission_snapshot, self.form_snapshot, stale=failures)
            self.read_result('history')
            running = bool(self.messages and self.messages[-1].get('type') == 'assistant' and not self.messages[-1].get('time', {}).get('completed'))
            self.status.set_text(('Demonstração · ' if self.client.demo else 'Conectado · ') + ('revisões indisponíveis; mensagens atualizadas' if failures else ('trabalhando…' if running else 'Enter envia · Shift+Enter quebra linha')))
        def failed(text):
            self.refreshing = False; gate.failure()
            self.review_available = {'permission': False, 'form': False}
            for kind in self.review_epoch:
                self.review_epoch[kind] += 1
            self.render_permissions(self.permission_snapshot, self.form_snapshot, stale=self.review_available)
            self.status.set_text('Sem atualização · histórico atual preservado'); self.read_result('history', text)
        self.async_job(work, done, failed)

    def render_messages(self, messages):
        key = json.dumps([messages, self.older, self.older_loading], sort_keys=True)
        if key == self.render_key:
            return
        self.render_key = key
        adjustment = self.scroll.get_vadjustment(); at_bottom = adjustment.get_upper() - adjustment.get_value() - adjustment.get_page_size() < 100
        wanted = []; new_widgets = {}
        if self.older:
            previous = button(text='Carregando mensagens anteriores…' if self.older_loading else 'Carregar mensagens anteriores', callback=self.load_older)
            previous.set_sensitive(not self.older_loading); wanted.append(previous)
        if not messages:
            empty = margins(box(True, 12), 35); empty.set_valign(Gtk.Align.CENTER); empty.set_vexpand(True)
            empty.append(label('Como posso ajudar?', 'empty-title')); empty.append(label('Envie uma mensagem ou anexe um arquivo.', 'muted', True)); wanted.append(empty)
        for message in messages:
            if message.get('type') not in ('user', 'assistant'):
                continue
            fingerprint = hashlib.sha256(json.dumps(message, sort_keys=True).encode()).digest()
            cached = self.message_widgets.get(message['id'])
            if cached and cached[0] == fingerprint:
                wanted.append(cached[1]); new_widgets[message['id']] = cached; continue
            row = box(False, 14); row.add_css_class('message-row')
            content = box(True, 10); content.set_hexpand(True)
            is_user = message.get('type') == 'user'
            if is_user:
                content.add_css_class('user-bubble'); row.set_margin_start(32)
            else:
                avatar = self.brand_image(28); avatar.add_css_class('agent-identity'); avatar.add_css_class('message-avatar'); avatar.set_valign(Gtk.Align.START); row.append(avatar)
            row.append(content)
            text = message.get('text') or '\n'.join(p.get('text') or '' for p in message.get('content') or [] if p.get('type') == 'text')
            rendered = render_native(text, self.request_link, lambda value: self.window.get_clipboard().set(value)); content.append(rendered)
            for file in message.get('files') or []:
                content.append(label('▤ ' + (file.get('name') or file.get('mime') or 'Anexo'), 'dim-label', True))
            if message.get('type') == 'assistant':
                directory = (self.session or {}).get('location', {}).get('directory', '')
                for artifact in artifacts(message, directory, links=rendered.markdown_links):
                    card = box(False, 10); card.add_css_class('code-block')
                    name = label(artifact['name'], wrap=True); name.set_hexpand(True); card.append(name)
                    card.append(button('document-save-symbolic', callback=lambda item=artifact: self.download_artifact(item), tooltip='Salvar arquivo referenciado na resposta'))
                    content.append(card)
            tools = [p for p in message.get('content') or [] if p.get('type') == 'tool']
            if tools:
                expander = Gtk.Expander(label=tool_progress(tools)); expander.add_css_class('tool-disclosure')
                steps = box(True, 10)
                for tool in tools[:100]:
                    state = tool_state_label(tool)
                    heading = label(state + ' · ' + str(tool.get('name') or tool.get('id') or 'Ferramenta')[:200], 'chat-title', True)
                    heading.set_selectable(True); steps.append(heading)
                    if state == 'Falhou':
                        failure = json.dumps((tool.get('state') or {}).get('error', {}), ensure_ascii=False)
                        details = label(failure[:5000], 'error-banner', True); details.set_selectable(True); steps.append(details)
                    raw = json.dumps(tool, ensure_ascii=False, indent=2)
                    details = label(raw[:12000] + ('\n[Prévia limitada a 12.000 caracteres.]' if len(raw) > 12000 else ''), 'code-block', True)
                    details.set_selectable(True)
                    advanced = Gtk.Expander(label='Detalhes somente leitura'); advanced.set_child(details); steps.append(advanced)
                if len(tools) > 100:
                    steps.append(label('Mostrando as primeiras 100 ferramentas; contagem inclui todas.', 'muted', True))
                expander.set_child(steps); content.append(expander)
            if message.get('error'):
                content.append(label('Erro: ' + json.dumps(message['error'], ensure_ascii=False), 'error-banner', True))
            timestamp = display_time((message.get('time') or {}).get('created'))
            if timestamp:
                when = label(timestamp, 'message-time'); when.set_halign(Gtk.Align.END); content.append(when)
            if is_user:
                avatar = Gtk.Image.new_from_icon_name('avatar-default-symbolic'); avatar.set_pixel_size(20); avatar.add_css_class('user-avatar'); avatar.set_valign(Gtk.Align.START); row.append(avatar)
            wanted.append(row); new_widgets[message['id']] = (fingerprint, row)
        keep = set(wanted)
        for child in list(children(self.message_box)):
            if child not in keep:
                self.message_box.remove(child)
        previous = None
        for child in wanted:
            if child.get_parent() is None:
                self.message_box.append(child)
            self.message_box.reorder_child_after(child, previous); previous = child
        self.message_widgets = new_widgets
        if at_bottom and not self.older_loading:
            def bottom():
                adjustment.set_value(max(0, adjustment.get_upper() - adjustment.get_page_size())); return GLib.SOURCE_REMOVE
            GLib.timeout_add(40, bottom)

    def request_link(self, uri):
        target = safe_url(uri)
        if not target:
            self.error('Link bloqueado: apenas HTTP(S) e e-mail sem cabeçalhos são aceitos.'); return
        self.confirm('Abrir link externo?', target + '\n\nO destino acima será aberto pelo aplicativo padrão do Linux. Nenhum arquivo será executado pelo KzL Agent.', lambda: self.launch_external_uri(target))

    def launch_external_uri(self, uri):
        target = safe_url(uri)
        if not target or self.closing:
            return
        launcher = Gtk.UriLauncher.new(target)
        def done(launcher, result, *_):
            try:
                launcher.launch_finish(result)
            except GLib.Error:
                self.error('Não foi possível abrir o link no aplicativo padrão do Linux.')
        launcher.launch(self.window, None, done, None)

    def load_older(self):
        if not self.session or not self.older or self.older_loading:
            return
        cursor = self.older; scope = self.scope
        self.older_loading = True; self.render_messages(self.messages)
        path = self.request_path('/message?') + urllib.parse.urlencode({'limit': 50, 'cursor': cursor})
        def done(page):
            adjustment = self.scroll.get_vadjustment()
            old_height = adjustment.get_upper(); old_value = adjustment.get_value()
            merged = {m['id']: m for m in page.get('data', [])}; merged.update({m['id']: m for m in self.messages})
            self.messages = sorted(merged.values(), key=lambda m: (m.get('time', {}).get('created', 0), m['id']))
            self.loaded_older = True; next_cursor = (page.get('cursor') or {}).get('next')
            self.older = next_cursor if next_cursor != cursor else None
            self.render_messages(self.messages)  # Loading suppresses automatic scroll-to-bottom.
            self.older_loading = False
            def restore():
                if self.scope == scope and not self.closing:
                    # Preserve the reading offset after GTK measures prepended
                    # rows. Do not override an intervening manual scroll.
                    if abs(adjustment.get_value() - old_value) < 2:
                        adjustment.set_value(old_value + max(0, adjustment.get_upper() - old_height))
                    self.render_messages(self.messages)
                return GLib.SOURCE_REMOVE
            GLib.timeout_add(60, restore)
            if next_cursor == cursor:
                self.error('Paginação interrompida: o servidor repetiu o cursor. Histórico carregado preservado.')
        def failed(text):
            self.older_loading = False; self.render_messages(self.messages)
            self.error('Mensagens anteriores indisponíveis. Histórico e cursor preservados; tente carregar novamente. ' + text)
        self.async_job(lambda: self.client.request(path), done, failed)

    def render_permissions(self, permissions, forms, stale=()):
        clear(self.permission_box)
        self.permission_box.set_visible(bool(permissions or forms or stale))
        binding = self.action_binding()
        if stale:
            self.permission_box.append(label('Algumas revisões não puderam ser atualizadas. Controles antigos estão bloqueados até a próxima leitura confirmada.', 'error-banner', True))
        for permission in permissions:
            item = button(text='Permissão necessária · ' + (permission.get('message') or permission.get('action', 'Revisar')), callback=lambda p=permission: self.review_permission(p, binding))
            item.set_sensitive('permission' not in stale)
            item.add_css_class('permission'); self.permission_box.append(item)
        for form in forms:
            item = button(text='Responder: ' + form.get('title', 'Pergunta'), callback=lambda f=form: self.answer_form(f, binding))
            item.set_sensitive('form' not in stale); self.permission_box.append(item)

    def review_permission(self, permission, binding=None):
        binding = binding or self.action_binding()
        if not self.review_available['permission']:
            self.error('Permissões sem leitura recente confirmada. Atualize a conversa antes de responder.'); return
        if not self.action_matches(binding):
            self.error('Conversa mudou. Reabra a permissão.'); return
        path = self.request_path('/permission/' + urllib.parse.quote(permission['id'], safe='') + '/reply')
        window, content = self.dialog('Revisar permissão')
        epoch = self.review_epoch['permission']
        content.append(label(binding['title'] + '\n' + binding['directory'], wrap=True))
        source = permission.get('source') or {}
        message = next((m for m in self.messages if m['id'] == source.get('messageID')), None)
        content.append(label(permission.get('message') or permission.get('action', ''), wrap=True))
        tool = next((p for p in (message or {}).get('content') or [] if p.get('id') == source.get('id')), None)
        raw = json.dumps({'permission': permission, 'action': tool}, ensure_ascii=False, indent=2)
        details = label(raw[:100000], 'code-block', True); details.set_selectable(True); content.append(details)
        sent = False
        status = label('', 'error-banner', True); content.append(status)
        def reply(decision):
            nonlocal sent
            if sent:
                return
            if not self.review_available['permission'] or epoch != self.review_epoch['permission']:
                status.set_text('Permissões indisponíveis. Aguarde leitura confirmada e reabra a revisão.'); return
            if not self.action_matches(binding):
                window.close(); self.error('Conversa mudou. Revise a permissão novamente.'); return
            try:
                identifier = self.store.begin_action(binding, 'permission', {'id': permission['id'], 'decision': decision})
            except Exception as exc:
                status.set_text(str(exc)); return
            sent = True; deny.set_sensitive(False); approve.set_sensitive(False)
            def finish(state, detail=''):
                self.store.mark_action(identifier, state, detail); self.persist()
                if state == 'acknowledged':
                    window.close()
                    if self.action_matches(binding):
                        self.refresh()
                else:
                    status.set_text('Resposta de permissão sem confirmação; repetição bloqueada. Confira o registro em Recursos. ' + detail)
            self.async_job(lambda: self.client.request(path, 'POST', {'decision': decision}), lambda _: finish('acknowledged'), lambda text: finish('uncertain', text), scoped=False)
        deny = button(text='Negar', callback=lambda: reply('reject')); content.append(deny)
        approve = button(text='Permitir uma vez', callback=lambda: self.confirm('Permitir ação?', 'Confirme ação, argumentos e destino revisados acima.', lambda: reply('once')))
        approve.set_sensitive(not (self.session.get('metadata') or {}).get('phoneControl') and len(raw) <= 100000); content.append(approve)
        if not approve.get_sensitive():
            content.append(label('Ação física ou detalhes extensos: revise na interface original antes de permitir.', wrap=True))

    def answer_form(self, form, binding=None):
        binding = binding or self.action_binding()
        if not self.review_available['form']:
            self.error('Perguntas sem leitura recente confirmada. Atualize a conversa antes de responder.'); return
        if not self.action_matches(binding):
            self.error('Conversa mudou. Reabra a pergunta.'); return
        path = self.request_path('/form/' + urllib.parse.quote(form['id'], safe='') + '/reply')
        window, content = self.dialog(form.get('title', 'Pergunta'))
        epoch = self.review_epoch['form']
        content.append(label(binding['title'] + '\n' + binding['directory'], wrap=True))
        values = {f['key']: f.get('default', False if f['type'] == 'boolean' else None) for f in form['fields']}
        groups = []
        def visibility():
            for field, group in groups:
                group.set_visible(field_visible(field, values))
        def changed(key, value):
            values[key] = value; visibility()
        for field in form['fields']:
            key = field['key']; kind = field['type']; options = field.get('options') or []
            group = box(True, 7); groups.append((field, group)); content.append(group)
            group.append(label(field.get('title', key) + (' *' if field.get('required') else ''), 'chat-title', True))
            if field.get('description'):
                group.append(label(field['description'], 'dim-label', True))
            if kind == 'boolean':
                control = Gtk.CheckButton(label='Sim', active=bool(values[key])); group.append(control)
                control.connect('toggled', lambda control, k=key: changed(k, control.get_active()))
            elif kind in ('string', 'multiselect'):
                first = None; checks = []
                for option in options:
                    control = Gtk.CheckButton(label=option['label'])
                    if kind == 'string' and first:
                        control.set_group(first)
                    first = first or control
                    control.set_active(option['value'] in (values[key] or []) if kind == 'multiselect' else option['value'] == values[key])
                    group.append(control); checks.append((option['value'], control))
                    if kind == 'multiselect':
                        control.connect('toggled', lambda _, k=key, checks=checks: changed(k, [v for v, c in checks if c.get_active()]))
                    else:
                        control.connect('toggled', lambda c, k=key, v=option['value']: changed(k, v) if c.get_active() else None)
                if not options or field.get('custom'):
                    entry = Gtk.Entry(placeholder_text=field.get('placeholder') or ('Outras respostas, separadas por vírgula' if kind == 'multiselect' else 'Sua resposta'))
                    entry.update_property([Gtk.AccessibleProperty.LABEL], [field.get('title', key) + (' · obrigatório' if field.get('required') else '')])
                    if isinstance(values[key], str):
                        entry.set_text(values[key])
                    group.append(entry)
                    if kind == 'multiselect':
                        entry.connect('changed', lambda entry, k=key, checks=checks: changed(k, list(dict.fromkeys([v for v, c in checks if c.get_active()] + [v.strip() for v in entry.get_text().split(',') if v.strip()]))))
                    else:
                        entry.connect('changed', lambda entry, k=key: changed(k, entry.get_text()))
            elif kind in ('number', 'integer'):
                entry = Gtk.Entry(placeholder_text='Número', text=str(values[key]) if values[key] is not None else '')
                entry.update_property([Gtk.AccessibleProperty.LABEL], [field.get('title', key) + (' · obrigatório' if field.get('required') else '')])
                entry.connect('changed', lambda entry, k=key: changed(k, entry.get_text())); group.append(entry)
            else:
                group.append(label('Tipo não suportado nesta versão. Responda na interface original.', wrap=True))
        visibility()
        error = label('', 'error-banner', True); error.set_visible(False); content.append(error)
        sent = False
        def submit():
            nonlocal sent
            if sent:
                return
            try:
                if not self.action_matches(binding):
                    raise PocketError('Conversa mudou. Reabra a pergunta.')
                if not self.review_available['form'] or epoch != self.review_epoch['form']:
                    raise PocketError('Perguntas indisponíveis. Aguarde leitura confirmada e reabra a pergunta.')
                value = form_answers(form, values)
                identifier = self.store.begin_action(binding, 'form', {'id': form['id'], 'answer': value})
                sent = True; send.set_sensitive(False)
                def failed(text):
                    self.store.mark_action(identifier, 'uncertain', text); self.persist()
                    error.set_text('Resposta sem confirmação; repetição bloqueada. Confira o registro em Recursos. ' + text); error.set_visible(True)
                def done(_):
                    self.store.mark_action(identifier, 'acknowledged'); self.persist(); window.close()
                    if self.action_matches(binding):
                        self.refresh()
                self.async_job(lambda: self.client.request(path, 'POST', {'answer': value}), done, failed, scoped=False)
            except Exception as exc:
                error.set_text(str(exc)); error.set_visible(True)
        send = button(text='Enviar resposta', callback=submit); content.append(send)

    def window_shortcuts(self, _, key, code, modifiers):
        if not modifiers & Gdk.ModifierType.CONTROL_MASK or modifiers & (Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK):
            return False
        # Main-window shortcuts never operate behind a modal review/save dialog.
        if self.dialogs or self.save_choosers or self.upload_choosers or self.closing:
            return False
        if key in (Gdk.KEY_f, Gdk.KEY_F):
            if self.portrait.get_active():
                self.sidebar.set_visible(False); self.content.set_visible(True)
            self.search_conversation(); return True
        if key in (Gdk.KEY_k, Gdk.KEY_K):
            self.sidebar.set_visible(True)
            self.content.set_visible(not self.portrait.get_active())
            self.search.grab_focus(); return True
        if key in (Gdk.KEY_n, Gdk.KEY_N):
            self.new_chat(); return True
        return False

    def key_pressed(self, _, key, code, modifiers):
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not modifiers & Gdk.ModifierType.SHIFT_MASK:
            self.send(); return True
        return False

    def send(self):
        if self.busy:
            return
        if not self.session:
            self.error('Crie uma conversa antes de enviar.'); return
        draft = self.current_draft(); path = self.request_path('/prompt'); sid = self.session['id']
        try:
            payload = self.store.begin_prompt(sid, draft)
        except Exception as exc:
            self.error(str(exc)); return
        self.busy = True; self.update_composer()
        def done(_):
            self.busy = False; self.sent += 1
            self.store.mark_prompt(payload['id'], 'admitted')
            self.store.data['drafts'][sid] = {'text': '', 'files': []}; self.persist()
            if self.session and self.session['id'] == sid:
                self.hydrating = True; self.draft.get_buffer().set_text(''); self.hydrating = False
                self.render_attachments(); self.error(''); self.refresh()
            self.update_composer(); self.load_sessions()
        def failed(text):
            self.busy = False
            admitted = self.store.mark_prompt(payload['id'], 'uncertain'); self.persist(); self.update_composer()
            if not admitted:
                self.error('Envio não confirmado. Confira conversa antes de reenviar. Rascunho e identificador mantidos. ' + text)
                self.restore_outgoing_notice()
        self.async_job(lambda: self.client.request(path, 'POST', payload), done, failed, scoped=False)

    def new_chat(self, directory=None):
        if self.busy:
            return
        pending = self.store.pending_creations(directory)
        if pending:
            window, content = self.dialog('Criação anterior sem confirmação')
            content.append(label((directory or 'Projeto padrão') + '\nA conversa pode já existir. Confira o histórico antes de iniciar outra. Nada será reenviado automaticamente.', wrap=True))
            content.append(button(text='Atualizar histórico', callback=self.load_sessions))
            def reviewed():
                def accept():
                    for record in pending:
                        self.store.mark_creation(record['id'], 'reviewed')
                    self.persist(); window.close()
                self.confirm('Liberar nova criação?', 'Marcar como conferido não confirma nem cancela a criação anterior. Isso apenas libera uma nova tentativa manual, que pode criar outra conversa.', accept)
            content.append(button(text='Já conferi o histórico', callback=reviewed)); return
        try:
            identifier = self.store.begin_creation(directory)
        except Exception as exc:
            self.error(str(exc)); return
        payload = {'location': {'directory': directory}} if directory else {}
        scope = self.scope; self.busy = True; self.update_composer()
        def done(result):
            self.busy = False
            session = result.get('data', {})
            if not isinstance(session.get('id'), str) or not session['id'].startswith('ses'):
                failed('Resposta sem identificador de conversa válido.'); return
            self.store.mark_creation(identifier, 'acknowledged', session['id']); self.persist()
            if scope == self.scope:
                self.open_chat(session)
            self.load_sessions()
            self.update_composer()
        def failed(text):
            self.store.mark_creation(identifier, 'uncertain'); self.persist()
            self.busy = False; self.update_composer(); self.error('Criação não confirmada. Repetição bloqueada até conferência explícita do histórico. ' + text)
        self.async_job(lambda: self.client.request('/api/session', 'POST', payload), done, failed, scoped=False)

    def choose_project(self):
        chooser = Gtk.FileChooserNative(title='Pasta do projeto', transient_for=self.window, action=Gtk.FileChooserAction.SELECT_FOLDER, accept_label='Abrir projeto')
        def response(chooser, code):
            if code == Gtk.ResponseType.ACCEPT:
                file = chooser.get_file()
                if file and file.get_path():
                    self.new_chat(file.get_path())
            chooser.destroy()
        chooser.connect('response', response); chooser.show()

    def attach(self):
        if self.busy:
            return
        if not self.session:
            self.error('Abra uma conversa antes de anexar.'); return
        chooser = Gtk.FileChooserNative(title='Anexar arquivos', transient_for=self.window, action=Gtk.FileChooserAction.OPEN, accept_label='Anexar'); chooser.set_select_multiple(True)
        scope = self.scope
        def response(chooser, code):
            if code == Gtk.ResponseType.ACCEPT and scope == self.scope:
                files = chooser.get_files(); paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
                self.async_job(lambda: [attachment(path) for path in paths if path], self.add_attachments)
            chooser.destroy()
        chooser.connect('response', response); chooser.show()

    def add_attachments(self, files):
        draft = self.current_draft(); combined = draft.get('files', []) + files
        if len(combined) > 5 or sum(f['size'] for f in combined) > 8 * 1024 * 1024:
            self.error('Limite de cinco anexos e 8 MB no total.'); return
        draft['files'] = combined; self.persist(); self.render_attachments(); self.update_composer()

    def render_attachments(self):
        clear(self.attach_box)
        self.attach_box.set_visible(bool(self.current_draft().get('files')))
        for index, file in enumerate(self.current_draft().get('files', [])):
            item = button(text=file['name'][:25] + ' ×', callback=lambda i=index: self.remove_attachment(i)); item.add_css_class('pill'); self.attach_box.append(item)

    def remove_attachment(self, index):
        del self.current_draft()['files'][index]; self.persist(); self.render_attachments(); self.update_composer()

    def interrupt(self):
        if self.session:
            binding = self.action_binding(); path = self.request_path('/interrupt'); accepted = False
            def accept():
                nonlocal accepted
                if accepted:
                    return
                accepted = True
                if not self.action_matches(binding):
                    self.error('Conversa mudou. Confirme novamente a interrupção.'); return
                try:
                    identifier = self.store.begin_action(binding, 'interrupt', {})
                except Exception as exc:
                    self.error(str(exc)); return
                def finish(state, detail=''):
                    self.store.mark_action(identifier, state, detail); self.persist()
                    if self.action_matches(binding):
                        self.error('Pedido de interrupção recebido; encerramento ainda não confirmado.' if state == 'acknowledged' else 'Interrupção sem confirmação. Confira execução e registro antes de repetir. ' + detail)
                        self.refresh()
                self.async_job(lambda: self.client.request(path, 'POST', {}), lambda _: finish('acknowledged'), lambda text: finish('uncertain', text), scoped=False)
            self.confirm('Interromper execução?', binding['title'] + '\n' + binding['directory'], accept)

    def load_catalog(self, automatic=False):
        gate = self.read_gates['catalog']
        if not gate.begin(manual=not automatic):
            return
        def done(result):
            gate.success(); self.catalog = result.get('models', []); self.update_options_label(); self.read_result('catalog')
        def failed(text):
            gate.failure(); self.read_result('catalog', text)
        self.async_job(lambda: self.client.request('/phone/catalog'), done, failed, scoped=False)

    def options(self):
        if not self.session:
            return
        window, content = self.dialog('Modelo e modo')
        binding = self.action_binding()
        content.append(label(binding['title'] + '\n' + binding['directory'], wrap=True))
        mode = Gtk.DropDown.new_from_strings(['Build', 'Plan']); mode.set_selected(1 if self.session.get('agent') == 'plan' else 0)
        mode.update_property([Gtk.AccessibleProperty.DESCRIPTION], ['Modo de trabalho'])
        content.append(label('Modo')); content.append(mode)
        models = list(self.catalog); model = self.session.get('model') or {}
        if not model.get('id'):
            models.insert(0, {'id': '', 'providerID': '', 'name': 'Manter modelo padrão atual'})
        # Never silently replace an unavailable current model with catalog[0].
        if model.get('id') and not any(m['id'] == model['id'] and m['providerID'] == model.get('providerID') for m in models):
            models.insert(0, dict(model, name=model['id'] + ' · atual'))
        selected = next((i for i, item in enumerate(models) if item['id'] == model.get('id') and item['providerID'] == model.get('providerID')), 0)
        picker = Gtk.DropDown.new_from_strings([m.get('name') or m['id'] for m in models] or ['Modelo atual']); picker.set_selected(selected); content.append(label('Modelo')); content.append(picker)
        picker.update_property([Gtk.AccessibleProperty.DESCRIPTION], ['Modelo da conversa'])
        variant = Gtk.Entry(placeholder_text='Variante opcional, ex.: high', text=model.get('variant') or ''); content.append(label('Variante')); content.append(variant)
        variant.update_property([Gtk.AccessibleProperty.LABEL], ['Variante do modelo · opcional'])
        path = self.request_path(); busy = False
        status = label('', 'error-banner', True); status.set_selectable(True); content.append(status)
        def readback(error='', expected=None):
            def work():
                try:
                    return self.client.request(path), None
                except Exception as exc:
                    return None, str(exc)
            def done(result):
                nonlocal busy
                busy = False; check.set_sensitive(True)
                value, read_error = result
                if read_error:
                    status.set_text('Configuração sem confirmação. Nenhum reenvio automático. ' + error + '\nLeitura: ' + read_error); return
                actual = value.get('data', {})
                if actual.get('id') != binding['id']:
                    status.set_text('Resposta de outra conversa recusada. Configuração não confirmada.'); return
                if self.action_matches(binding):
                    self.session = actual; self.update_options_label()
                saved_model = actual.get('model') or {}
                matches = expected and actual.get('agent') == expected[0] and (expected[1] is None or (
                    all(saved_model.get(k) == v for k, v in expected[1].items())
                    and (saved_model.get('variant') or '') == (expected[1].get('variant') or '')))
                if not error and matches:
                    window.close(); return
                status.set_text('Estado consultado no projeto original: ' + str(actual.get('agent', 'padrão')) + ' · ' + str(saved_model.get('providerID', '')) + '/' + str(saved_model.get('id', 'padrão')) + ' · variante: ' + str(saved_model.get('variant') or 'padrão') + '\n' + (('Gravação parcial ou sem confirmação: ' + error) if error else 'Revise o estado antes de salvar novamente.'))
                mode.set_selected(1 if actual.get('agent') == 'plan' else 0)
                saved_model = actual.get('model') or {}
                index = next((i for i, item in enumerate(models) if item['id'] == saved_model.get('id') and item['providerID'] == saved_model.get('providerID')), None)
                if index is not None:
                    picker.set_selected(index)
                elif saved_model.get('id'):
                    models.append(dict(saved_model, name=saved_model['id'] + ' · salvo'))
                    picker.get_model().append(models[-1]['name']); picker.set_selected(len(models)-1)
                variant.set_text(saved_model.get('variant') or '')
            self.async_job(work, done, scoped=False)
        def save():
            nonlocal busy
            if busy:
                return
            if not self.action_matches(binding):
                status.set_text('Conversa mudou. Reabra as opções no projeto desejado.'); return
            agent = 'plan' if mode.get_selected() == 1 else 'build'
            chosen = models[picker.get_selected()] if models else None
            payload = {'providerID': chosen['providerID'], 'id': chosen['id']} if chosen and chosen.get('id') else None
            if payload and variant.get_text().strip():
                payload['variant'] = variant.get_text().strip()
            busy = True; submit.set_sensitive(False); check.set_sensitive(False)
            status.set_text('Salvando no projeto confirmado…')
            def work():
                try:
                    self.client.request(path + '/agent', 'POST', {'agent': agent})
                    if payload:
                        self.client.request(path + '/model', 'POST', {'model': payload})
                    return ''
                except Exception as exc:
                    return str(exc)
            self.async_job(work, lambda error: readback(error, (agent, payload)), scoped=False)
        submit = button(text='Salvar', callback=save); content.append(submit)
        def inspect():
            nonlocal busy
            if not busy:
                busy = True; check.set_sensitive(False); readback()
        check = button(text='Consultar estado salvo', callback=inspect); content.append(check)
        content.append(label('Após uma tentativa, use Consultar estado salvo ou reabra as opções para uma nova gravação. Não há repetição automática.', 'muted', True))

    def rename(self):
        if not self.session:
            return
        window, content = self.dialog('Renomear conversa', 450)
        binding = self.action_binding()
        content.append(label(binding['title'] + '\n' + binding['directory'], wrap=True))
        entry = Gtk.Entry(text=self.session.get('title', '')); content.append(entry); path = self.request_path()
        status = label('', 'error-banner', True); content.append(status)
        attempted = False
        def save():
            nonlocal attempted
            if attempted:
                return
            if not self.action_matches(binding):
                status.set_text('Conversa mudou. Reabra a renomeação.'); return
            title = entry.get_text().strip()
            if not 1 <= len(title) <= 200:
                self.error('Nome precisa ter de 1 a 200 caracteres.'); return
            try:
                identifier = self.store.begin_action(binding, 'rename', {'title': title})
            except Exception as exc:
                status.set_text(str(exc)); return
            attempted = True; submit.set_sensitive(False)
            status.set_text('Renomeando no projeto confirmado…')
            def work():
                error = ''
                try:
                    self.client.request(path, 'PATCH', {'title': title})
                except Exception as exc:
                    error = str(exc)
                try:
                    return self.client.request(path), error
                except Exception as exc:
                    return None, error + '\nLeitura: ' + str(exc)
            def done(result):
                value, error = result; actual = (value or {}).get('data', {})
                confirmed = actual.get('id') == binding['id'] and actual.get('title') == title
                self.store.mark_action(identifier, 'acknowledged' if confirmed else 'uncertain', error); self.persist()
                if actual.get('id') == binding['id'] and self.action_matches(binding):
                    self.session = actual; self.title.set_text(actual.get('title', 'Conversa'))
                if confirmed:
                    window.close(); self.load_sessions()
                else:
                    status.set_text('Nome sem confirmação. Nenhum reenvio automático. Confira histórico e registro em Recursos. ' + error)
            self.async_job(work, done, scoped=False)
        submit = button(text='Salvar nome', callback=save); content.append(submit)

    def toggle_pin(self):
        if not self.session:
            return
        pins = self.store.data['pins']; sid = self.session['id']
        pins.remove(sid) if sid in pins else pins.append(sid)
        self.persist(); self.pin_button.set_icon_name('starred-symbolic' if sid in pins else 'non-starred-symbolic'); self.render_sessions()

    def projects(self):
        window, content = self.dialog('Projetos favoritos')
        for path in self.store.data['projects']:
            content.append(button(text=path, callback=lambda p=path: (window.close(), self.new_chat(p))))
        if self.session:
            directory = self.session.get('location', {}).get('directory', '')
            def add():
                if directory and directory not in self.store.data['projects']:
                    self.store.data['projects'].append(directory); self.persist()
                window.close()
            content.append(button(text='Favoritar projeto atual', callback=add))
        content.append(button(text='Escolher outra pasta', callback=lambda: (window.close(), self.choose_project())))

    def open_kzl(self):
        self.async_job(lambda: self.client.request('/phone/kzl/ensure', 'POST', {}), lambda result: self.open_chat(result['data']))

    def json_view(self, title, work):
        window, content = self.dialog(title, 780)
        output = label('Carregando…', 'code-block', True); output.set_selectable(True); content.append(output)
        self.async_job(work, lambda data: output.set_text(json.dumps(data, ensure_ascii=False, indent=2)), lambda error: output.set_text(error))
        return window, content

    def activity(self):
        if not self.session:
            return
        binding = self.action_binding(); sid = binding['id']; path = self.request_path()
        window, content = self.dialog('Atividade · revisão da conversa', 840)
        content.append(label(binding['title'] + '\n' + binding['directory'], wrap=True))
        content.append(label('Somente leitura · não aplica patches, não executa saída do terminal e não cancela tarefas.', 'muted', True))
        self.activity_sections = {}
        sections = [('diff', 'Alterações', path + '/diff?context=3'),
                    ('terminal', 'Saída do terminal', experimental_session_path(sid, 'terminal/read') + '?lines=100'),
                    ('tasks', 'Tarefas desta conversa', '/phone/kzl/tasks')]
        pending = set()
        def load(kind, route, target):
            if kind in pending or window not in self.dialogs:
                return
            pending.add(kind)
            def done(value=None, error=None):
                pending.discard(kind)
                if window not in self.dialogs:
                    return
                clear(target)
                if error:
                    target.append(label('Leitura indisponível · ' + str(error), 'error-banner', True)); return
                rows = activity_rows(kind, value, sid)
                if not rows:
                    target.append(label('Nenhum item disponível nesta conversa.', 'muted', True))
                for row in rows:
                    group = box(True, 6)
                    heading = label(row['title'], 'chat-title', True); heading.set_selectable(True); group.append(heading)
                    group.append(label(row['detail'], 'muted', True))
                    if row['body']:
                        view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.NONE)
                        view.get_buffer().set_text(row['body'])
                        view.update_property([Gtk.AccessibleProperty.LABEL], [row['title'] + ' · conteúdo somente leitura'])
                        scroll = Gtk.ScrolledWindow(); scroll.set_min_content_height(100); scroll.set_max_content_height(300); scroll.set_propagate_natural_height(True); scroll.set_child(view)
                        group.append(scroll)
                        group.append(button(text='Copiar prévia', callback=lambda text=row['body']: self.window.get_clipboard().set(text)))
                    target.append(group)
            self.async_job(lambda: self.client.request(route), lambda value: done(value), lambda error: done(error=error), scoped=False)
        for kind, title, route in sections:
            content.append(label(title, 'md-h3'))
            target = box(True, 14); target.append(label('Carregando…', 'muted')); content.append(target)
            self.activity_sections[kind] = target
            content.append(button(text='Atualizar ' + title.lower(), callback=lambda k=kind, r=route, t=target: load(k, r, t)))
            load(kind, route, target)

    def computer(self):
        self.json_view('Computador', lambda: self.client.request('/phone/status'))

    def open_terminal(self):
        if self.client.demo:
            _, content = self.dialog('Terminal local · demonstração')
            content.append(label('A demonstração não inicia shell ou executa comandos. No modo conectado, o terminal abre em uma janela Linux nativa após confirmar o projeto.', wrap=True)); return
        if not self.session:
            self.error('Abra uma conversa/projeto antes de abrir o terminal.'); return
        source = self.session.get('location', {}).get('directory', ''); scope = self.scope
        def ready(path):
            def confirmed():
                if self.scope != scope or self.closing:
                    self.error('Conversa mudou. Confirme novamente a pasta do terminal.'); return
                self.spawn_terminal(path)
            self.confirm('Abrir terminal local do projeto?', path + '\n\nInicia seu shell neste Linux, com seus direitos e configurações de usuário. Não é terminal remoto nem endpoint do iPhone. Nenhum comando do chat será executado automaticamente. A janela é independente do chat.', confirmed)
        self.async_job(lambda: directory_path(source), ready)

    def spawn_terminal(self, directory):
        try:
            path = directory_path(directory)
            if path != directory:
                raise ValueError('A pasta mudou desde a confirmação. Revise o destino novamente.')
            process = subprocess.Popen([sys.executable, str(ROOT/'terminal.py'), '--directory', path],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       close_fds=True, start_new_session=True)
            self.terminal_processes.append(process)
            self.status.set_text('Inicialização do terminal local solicitada. Comandos serão digitados na janela separada.')
            def reap():
                result = process.wait()
                def done():
                    if process in self.terminal_processes:
                        self.terminal_processes.remove(process)
                    if result and not self.closing:
                        self.error('Terminal local não iniciou corretamente. Confira GTK3/VTE e a pasta selecionada.')
                    return GLib.SOURCE_REMOVE
                if not self.closing:
                    GLib.idle_add(done)
            threading.Thread(target=reap, name='kzl-terminal-wait', daemon=True).start()
        except (ValueError, OSError) as error:
            self.error('Não foi possível iniciar terminal local: ' + str(error))

    def resources(self):
        if not self.session:
            return
        binding = self.action_binding()
        path = self.request_path(); directory = binding['directory']
        query = '?' + urllib.parse.urlencode({'location[directory]': directory})
        window, content = self.dialog('Comandos e skills')
        content.append(button(text='Buscar nas mensagens carregadas', callback=lambda: self.search_conversation(binding)))
        content.append(button(text='Salvar conversa carregada (.txt)', callback=lambda: self.export_conversation(binding)))
        content.append(button(text='Agendamentos desta conversa', callback=self.schedules))
        content.append(label(binding['title'] + '\n' + directory, wrap=True))
        rows = box(True, 8); content.append(rows)
        def done(result):
            if not self.action_matches(binding):
                self.error('Conversa mudou. Reabra os recursos.'); return
            child = rows.get_first_child()
            while child:
                following = child.get_next_sibling(); rows.remove(child); child = following
            commands, skills, inbox = result
            proof = self.store.reconcile_inbox(binding['id'], inbox.get('data', []))
            if proof['admitted']:
                self.persist()
            if proof['draft_cleared']:
                self.hydrating = True; self.draft.get_buffer().set_text(''); self.hydrating = False
                self.render_attachments(); self.update_composer()
            for command in commands.get('data', []):
                rows.append(button(text='/' + command['name'], callback=lambda cmd=command: self.run_command(cmd, binding)))
            for skill in skills.get('data', []):
                rows.append(button(text='Skill · ' + skill.get('name', skill['id']), callback=lambda s=skill: self.run_skill(s, binding)))
            for item in inbox.get('data', []):
                rows.append(label('Fila · ' + str(item.get('id', '')) + ' · ' + str(item.get('delivery', '')), wrap=True))
            for record in self.store.action_records(binding['id']):
                rows.append(label(record['kind'] + ' · ' + record['target'] + ' · ' + record['state'], wrap=True))
                if record['state'] in ('attempted', 'uncertain'):
                    def review(identifier=record['id']):
                        self.confirm('Marcar registro como conferido?', 'Isso não confirma execução nem reenvia a ação. Confira histórico e efeitos antes de liberar uma nova execução.', lambda: (self.store.mark_action(identifier, 'reviewed'), self.persist(), reload()))
                    rows.append(button(text='Já conferi esta ação', callback=review))
            if not commands.get('data') and not skills.get('data'):
                content.append(label('Nenhum comando/skill disponível neste projeto.', wrap=True))
        def reload():
            self.async_job(lambda: (self.client.request('/api/command' + query), self.client.request('/api/skill' + query), self.client.request(path + '/inbox')), done)
        content.append(button(text='Atualizar recursos', callback=reload)); reload()

    def action_binding(self):
        return {'id': self.session['id'], 'title': self.session.get('title', 'Conversa'), 'directory': self.session.get('location', {}).get('directory', ''), 'scope': self.scope}

    def action_matches(self, binding):
        return bool(self.session and not self.closing and self.action_binding() == binding)

    def action_dialog(self, title, binding, kind, make_payload, route, entry=False):
        if not self.action_matches(binding):
            self.error('Conversa mudou. Reabra a ação.'); return
        window, content = self.dialog(title)
        content.append(label(binding['title'] + '\n' + binding['directory'], wrap=True))
        field = Gtk.Entry(placeholder_text='Argumentos')
        if entry:
            content.append(field)
        locked = False
        def run():
            nonlocal locked
            if locked or not self.action_matches(binding):
                self.error('Conversa mudou ou ação já confirmada. Reabra para revisar.'); return
            payload = make_payload(field.get_text())
            accepted = False
            def accept():
                nonlocal locked, accepted
                if accepted or locked:
                    return
                accepted = True
                if not self.action_matches(binding):
                    self.error('Conversa mudou. Reabra a ação.'); return
                try:
                    identifier = self.store.begin_action(binding, kind, payload)
                except Exception as error:
                    self.error(str(error)); return
                locked = True; execute.set_sensitive(False)
                def finish(state, detail=''):
                    self.store.mark_action(identifier, state, detail); self.persist()
                    if self.action_matches(binding):
                        if state == 'acknowledged':
                            window.close(); self.refresh()
                        else:
                            self.error('Ação sem confirmação; repetição bloqueada. Confira recursos/histórico. ' + detail)
                self.async_job(lambda: self.client.request(route, 'POST', payload), lambda _: finish('acknowledged'), lambda text: finish('uncertain', text), scoped=False)
            self.confirm(title + '?', binding['title'] + '\n' + binding['directory'] + '\n' + json.dumps(payload, ensure_ascii=False), accept)
        execute = button(text='Executar comando' if entry else 'Ativar skill', callback=run); content.append(execute)

    def run_skill(self, skill, binding):
        self.action_dialog('Ativar ' + skill.get('name', skill['id']), binding, 'skill', lambda _: {'id': skill['id'], 'resume': True}, experimental_session_path(binding['id'], 'skill'))

    def run_command(self, command, path):
        binding = path if isinstance(path, dict) else self.action_binding()
        if isinstance(path, str) and path != self.request_path():
            self.error('Conversa mudou. Reabra o comando.'); return
        self.action_dialog('/' + command['name'], binding, 'command', lambda text: {'name': command['name'], 'text': text}, '/api/session/' + binding['id'] + '/command', entry=True)

    def search_conversation(self, binding=None):
        if not self.session:
            return
        binding = binding or self.action_binding()
        if not self.action_matches(binding):
            self.error('Conversa mudou. Reabra a busca.'); return
        # Snapshot only plain message text; never search raw tool/config/file data.
        snapshot = [{'id': m['id'], 'type': m.get('type'), 'text': m.get('text') or '\n'.join(p.get('text') or '' for p in m.get('content', []) if p.get('type') == 'text')} for m in self.messages]
        window, content = self.dialog('Buscar nesta conversa', 650)
        content.append(label(binding['title'] + '\nBusca local: somente mensagens carregadas ao abrir. Até 100 resultados; não consulta o provedor.', 'muted', True))
        entry = Gtk.SearchEntry(placeholder_text='Trecho da mensagem'); entry.update_property([Gtk.AccessibleProperty.LABEL], ['Buscar trecho nas mensagens carregadas']); content.append(entry)
        count = label('Digite um trecho para buscar.', 'muted'); content.append(count)
        results = box(True, 8); content.append(results)
        def jump(identifier):
            if not self.action_matches(binding):
                count.set_text('Conversa mudou. Reabra a busca na conversa desejada.'); return
            cached = self.message_widgets.get(identifier)
            if not cached:
                count.set_text('Mensagem não está mais carregada. Reabra a busca.'); return
            ok, bounds = cached[1].compute_bounds(self.scroll)
            if ok:
                adjustment = self.scroll.get_vadjustment()
                adjustment.set_value(adjustment.get_value() + bounds.get_y())
                window.close()
        def changed(*_):
            clear(results)
            try:
                matches = search_loaded_messages(snapshot, entry.get_text())
            except PocketError as exc:
                count.set_text(str(exc)); return
            count.set_text((str(len(matches)) + ' resultado(s)' + (' · limite de exibição' if len(matches) == 100 else '')) if entry.get_text().strip() else 'Digite um trecho para buscar.')
            for match in matches:
                result = button(text=('Você' if match['role'] == 'user' else 'Assistente') + ' · ' + match['preview'], callback=lambda identifier=match['id']: jump(identifier))
                result.get_child().set_wrap(True); result.get_child().set_wrap_mode(Pango.WrapMode.WORD_CHAR); results.append(result)
        entry.connect('search-changed', changed); entry.grab_focus()

    def export_conversation(self, binding=None):
        if not self.session:
            self.error('Abra uma conversa antes de exportar.'); return
        binding = binding or self.action_binding()
        if not self.action_matches(binding):
            self.error('Conversa mudou. Reabra a exportação na conversa desejada.'); return
        try:
            snapshot = conversation_export(self.session, self.messages)
        except Exception as exc:
            self.error(str(exc)); return
        window, content = self.dialog('Salvar conversa como texto')
        content.append(label(binding['title'] + '\nSomente mensagens carregadas agora. Não inclui rascunho, conteúdo dos anexos ou detalhes de ferramentas. O arquivo pode conter informações privadas da conversa.', wrap=True))
        accepted = False
        def choose():
            nonlocal accepted
            if accepted:
                return
            accepted = True; window.close()
            chooser = self.save_chooser_factory(title='Salvar conversa carregada', transient_for=self.window, action=Gtk.FileChooserAction.SAVE, accept_label='Salvar texto')
            chooser.set_current_name('kzl-conversa.txt'); self.save_choosers.append(chooser)
            def response(chooser, code):
                if chooser not in self.save_choosers:
                    return
                self.save_choosers.remove(chooser)
                selected = chooser.get_file() if code == Gtk.ResponseType.ACCEPT else None
                destination = selected.get_path() if selected else None
                chooser.destroy()
                if not destination:
                    return
                overwrite = Path(destination).exists()
                written = False
                def perform():
                    nonlocal written
                    if written or self.closing:
                        return
                    written = True
                    self.async_job(lambda: save_download(destination, snapshot, overwrite), lambda _: self.status.set_text('Conversa exportada · ' + binding['title'] + ' · ' + str(len(snapshot)) + ' bytes'), scoped=False)
                if overwrite:
                    self.confirm('Substituir arquivo?', destination + '\n\nExportação da conversa: ' + binding['title'], perform)
                else:
                    perform()
            chooser.connect('response', response); chooser.show()
        content.append(button(text='Escolher destino', callback=choose))

    def files(self, root=None, path=''):
        window, content = self.dialog('Arquivos do computador', 650)
        content.append(button(text='Enviar arquivo grande · retomável', callback=lambda: (window.close(), self.transfers())))
        def work():
            roots = self.client.request('/phone/files/roots')['roots']
            selected = root or (roots[0]['id'] if roots else None)
            if not selected:
                raise PocketError('Nenhuma pasta liberada no gateway.')
            listing = self.client.request('/phone/files/list?' + urllib.parse.urlencode({'root': selected, 'path': path}))
            return roots, selected, listing
        def done(result):
            roots, selected, listing = result
            for item in roots:
                content.append(button(text=item['name'], callback=lambda r=item['id']: (window.close(), self.files(r))))
            content.append(label('/' + listing.get('path', ''), 'dim-label', True))
            if listing.get('parent') is not None:
                content.append(button(text='↑ Pasta acima', callback=lambda: (window.close(), self.files(selected, listing['parent']))))
            for item in listing.get('entries', []):
                if item['kind'] == 'directory':
                    content.append(button(text='▸ ' + item['name'], callback=lambda f=item: (window.close(), self.files(selected, f['path']))))
                else:
                    download = button(text='↓ ' + item['name'], callback=lambda f=item: self.download(selected, f)); download.set_sensitive(item.get('readable', False)); content.append(download)
        self.async_job(work, done)

    def transfers(self):
        if self.transfer_window:
            self.transfer_window.present(); return
        if self.client.demo:
            _, content = self.dialog('Transferências · demonstração')
            content.append(label('Uploads reais ficam bloqueados na demonstração. Use o modo conectado para enviar arquivos à caixa de entrada do KzL Agent, sem remover os originais.', wrap=True)); return
        try:
            if self.uploads is None:
                from uploads import UploadManager
                self.uploads = UploadManager(self.store.root, self.client)
        except Exception as error:
            self.error(str(error)); return
        window, content = self.dialog('Transferências retomáveis', 720); window.set_default_size(720, 650); window.set_modal(False); self.transfer_window = window
        content.append(label('Arquivos grandes, sem recomeçar do zero', 'brand', True))
        content.append(label('Destino: caixa de entrada do gateway, atualmente Downloads/Iphone 11 Omoki. Cada envio recebe nome único. Originais nunca são apagados; anexos de chat continuam separados. Retomadas são manuais. Fechar este painel mantém o envio; fechar o aplicativo solicita pausa.', 'dim-label', True))
        notice = label('', wrap=True); content.append(notice)
        rows = box(True, 12); content.append(rows); widgets = {}
        state_names = {'ready': 'Pronto', 'checking': 'Consultando notebook', 'uploading': 'Enviando', 'committing': 'Verificando conteúdo', 'completed': 'Confirmado por SHA-256', 'paused': 'Pausado', 'uncertain': 'Requer conferência / retomada'}
        def usable():
            return self.transfer_window is window and not self.closing
        def pause():
            if self.upload_job_cancel:
                self.upload_job_cancel.set()
            if self.upload_running_id:
                self.uploads.pause(self.upload_running_id)
            notice.set_text('Pausa solicitada. Bloco ou confirmação em andamento podem terminar; original permanece intacto.')
        def finished(_=None):
            self.upload_running_id = None; self.upload_job_cancel = None
            if usable():
                render()
        def failed(error):
            finished()
            if usable():
                notice.set_text(error)
        def run(identifier, cancelled=None):
            if self.upload_running_id and self.upload_running_id != 'preparing':
                notice.set_text('Aguarde ou pause o envio atual antes de iniciar outro.'); return
            event = cancelled if cancelled is not None else threading.Event()
            self.upload_job_cancel = event; self.upload_running_id = identifier
            self.async_job(lambda: self.uploads.run(identifier, cancelled=event), finished, failed, scoped=False)
            if usable():
                render()
        def add_path(path):
            if self.upload_running_id:
                notice.set_text('Aguarde ou pause o envio atual.'); return
            self.upload_running_id = 'preparing'; event = threading.Event(); self.upload_job_cancel = event
            notice.set_text('Calculando SHA-256 da origem… Você pode pausar. Nenhum original será removido.')
            def prepared(identifier):
                if event.is_set() or self.closing:
                    self.uploads.update(identifier, state='paused', message='Preparação pausada; envio não iniciado. Original preservado.'); finished(); return
                run(identifier, event)
            self.async_job(lambda: self.uploads.add(path, cancelled=event), prepared, failed, scoped=False)
            render()
        def choose():
            if self.upload_running_id:
                return
            chooser = self.upload_chooser_factory(title='Arquivo para envio retomável', transient_for=window, action=Gtk.FileChooserAction.OPEN, accept_label='Selecionar'); self.upload_choosers.append(chooser)
            def selected(control, response):
                file = control.get_file() if response == Gtk.ResponseType.ACCEPT else None
                path = file.get_path() if file else None; control.destroy()
                if control in self.upload_choosers:
                    self.upload_choosers.remove(control)
                if path and usable():
                    self.confirm('Enviar arquivo à caixa do KzL Agent?', path + '\n\nO original será preservado. O gateway recebe uma cópia em nome único; nada será enviado ao modelo.', lambda: add_path(path) if usable() else None)
            chooser.connect('response', selected); chooser.show()
        controls = box(False, 8)
        add = button(text='Selecionar e enviar arquivo', callback=choose); controls.append(add)
        pause_button = button(text='Pausar envio atual', callback=pause); controls.append(pause_button)
        content.prepend(controls)
        def forget(identifier):
            try:
                self.uploads.forget(identifier); render()
            except Exception as error:
                notice.set_text(str(error))
        def copy_path(identifier, insert=False):
            try:
                record = self.uploads.get(identifier)
                if record['state'] != 'completed':
                    raise PocketError('Confira recibo antes de usar o caminho.')
                path = '~/' + record['destination']
                if insert:
                    if not self.session or self.busy:
                        raise PocketError('Abra uma conversa e aguarde envio atual antes de inserir o caminho.')
                    self.draft.get_buffer().insert_at_cursor('\nArquivo confirmado na pasta pessoal do computador (não relativo ao projeto): ' + json.dumps(path, ensure_ascii=False) + '\n')
                    notice.set_text('Caminho inserido no rascunho. Nenhum prompt foi enviado.')
                else:
                    self.window.get_clipboard().set(path); notice.set_text('Caminho copiado. Nenhum arquivo foi aberto ou executado.')
            except Exception as error:
                notice.set_text(str(error))
        def render():
            if not usable():
                return GLib.SOURCE_REMOVE
            add.set_sensitive(not self.upload_running_id); pause_button.set_sensitive(bool(self.upload_running_id))
            records = self.uploads.list(); current = {record['id'] for record in records}
            for identifier in list(widgets):
                if identifier not in current:
                    rows.remove(widgets.pop(identifier)['row'])
            for record in records:
                identifier = record['id']
                if identifier not in widgets:
                    card = box(True, 7); card.add_css_class('code-block'); rows.append(card)
                    name = label(record['name'], 'chat-title', True); name.set_selectable(True); card.append(name)
                    status = label('', wrap=True); card.append(status)
                    destination = label('', 'dim-label', True); destination.set_selectable(True); card.append(destination)
                    progress = Gtk.ProgressBar(show_text=True); card.append(progress)
                    actions = box(False, 6); card.append(actions)
                    resume = button(text='Retomar / conferir', callback=lambda i=identifier: run(i)); actions.append(resume)
                    copy = button(text='Copiar caminho', callback=lambda i=identifier: copy_path(i)); actions.append(copy)
                    insert = button(text='Inserir no chat', callback=lambda i=identifier: copy_path(i, True)); actions.append(insert)
                    remove = button('edit-delete-symbolic', callback=lambda i=identifier: self.confirm('Remover registro concluído?', 'Somente esta entrada sai da lista. Arquivos locais e do notebook não serão apagados.', lambda: forget(i)), tooltip='Remover somente registro concluído'); actions.append(remove)
                    widgets[identifier] = dict(row=card, status=status, destination=destination, progress=progress, resume=resume, copy=copy, insert=insert, remove=remove)
                item = widgets[identifier]; complete = record.get('state') == 'completed'
                item['status'].set_text(state_names.get(record['state'], record['state']) + '\n' + record.get('message', ''))
                item['destination'].set_text(record.get('destination') or 'Destino será confirmado pelo gateway antes do primeiro bloco.')
                offset, total = record.get('offset', 0), record['size']
                item['progress'].set_fraction(1 if complete else (offset / total if total else 0))
                item['progress'].set_text(f'{offset:,} / {total:,} bytes')
                item['resume'].set_sensitive(not complete and not self.upload_running_id and not record.get('active'))
                for key in ('copy', 'insert', 'remove'):
                    item[key].set_sensitive(complete)
            return GLib.SOURCE_CONTINUE
        refresh = button(text='Atualizar registros', callback=lambda: self.async_job(self.uploads.journal, lambda _: render(), lambda error: notice.set_text(error) if usable() else None, scoped=False)); content.append(refresh)
        timer = GLib.timeout_add(400, render)
        def closed(*_):
            self.transfer_window = None; GLib.source_remove(timer)
            return False
        window.connect('close-request', closed); render()

    def download(self, root, file):
        chooser = self.save_chooser_factory(title='Salvar arquivo', transient_for=self.window, action=Gtk.FileChooserAction.SAVE, accept_label='Salvar'); chooser.set_current_name(Path(file['name']).name)
        self.save_choosers.append(chooser)
        path = '/phone/files/download?' + urllib.parse.urlencode({'root': root, 'path': file['path']})
        def response(chooser, code):
            if code == Gtk.ResponseType.ACCEPT:
                selected = chooser.get_file()
                destination = selected.get_path() if selected else None
                if not destination:
                    self.error('Escolha destino local para salvar.'); chooser.destroy()
                    if chooser in self.save_choosers:
                        self.save_choosers.remove(chooser)
                    return
                def perform():
                    def work():
                        data = self.client.request(path, binary=True, version=file.get('version'))
                        save_download(destination, data, overwrite)
                        return len(data)
                    self.async_job(work, lambda size: self.status.set_text(f'Arquivo salvo · {size} bytes'))
                overwrite = Path(destination).exists()
                if overwrite:
                    self.confirm('Substituir arquivo?', destination, perform)
                else:
                    perform()
            chooser.destroy()
            if chooser in self.save_choosers:
                self.save_choosers.remove(chooser)
        chooser.connect('response', response); chooser.show()

    def open_voice(self):
        if self.voice_window:
            self.voice_window.present(); return
        if not self.session:
            self.error('Abra uma conversa antes de iniciar Live.'); return
        try:
            from voice import WebRTCAudio, VoiceSession, LocalTone, context_text, configuration
        except (ImportError, ValueError) as error:
            self.error('Áudio nativo indisponível: ' + str(error)); return
        bound = json.loads(json.dumps(self.session)); history = list(self.messages)
        window, content = self.dialog('Live · ' + (bound.get('title') or 'Conversa'), 480)
        window.set_modal(False); window.set_default_size(480, 650); self.voice_window = window
        title = label('KzL' if (bound.get('metadata') or {}).get('kzlAgent') else 'Live da conversa', 'empty-title', True); title.set_halign(Gtk.Align.CENTER); content.append(title)
        if (bound.get('metadata') or {}).get('kzlAgent'):
            avatar = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROOT / 'KzL.png'), 96, 96, True))
            avatar.set_pixel_size(96); avatar.set_halign(Gtk.Align.CENTER); content.append(avatar)
        else:
            icon = Gtk.Image.new_from_icon_name('audio-input-microphone-symbolic'); icon.set_pixel_size(48); icon.set_halign(Gtk.Align.CENTER); content.append(icon)
        subtitle = label(bound.get('title') or 'Conversa atual', 'dim-label', True); subtitle.set_halign(Gtk.Align.CENTER); content.append(subtitle)
        status = label('Pronto para conversar', 'chat-title', True); status.set_halign(Gtk.Align.CENTER); content.append(status)
        caption = label('', wrap=True); caption.set_selectable(True); caption.set_visible(False); content.append(caption)
        proposals = box(True, 8); proposals.set_visible(False); content.append(proposals)
        content.append(label('OpenAI Realtime é API paga separada da assinatura Codex. Áudio, transcrição e contexto recente serão enviados à OpenAI. Limite de 3 minutos. Pedidos de trabalho exigem revisão; permissões normais continuam valendo.', 'dim-label', True))
        starting = {'value': False}
        def current(generation):
            return self.voice_window is window and self.voice_generation == generation and not self.closing
        def ended(error=None):
            if self.voice_cancel:
                self.voice_cancel.set()
            self.voice_generation += 1
            if self.voice_session:
                self.voice_session.stop()
            if self.voice_media:
                self.voice_media.stop()
            self.voice_button.remove_css_class('error'); starting['value'] = False
            start.set_sensitive(not self.client.demo); start.set_visible(True); mute.set_sensitive(False); end.set_sensitive(False)
            if error:
                status.set_text(error)
        def request_call():
            if self.client.demo or starting['value'] or (self.voice_session and not self.voice_session.closed):
                return
            self.confirm('Iniciar chamada paga?', 'O microfone e o contexto desta conversa serão enviados à OpenAI Realtime por até 3 minutos. Encerrar não desfaz uma criação já enviada ao provedor. Nenhuma tarefa será executada sem revisão.', begin)
        def begin():
            if self.voice_window is not window or starting['value'] or (self.voice_session and not self.voice_session.closed):
                return
            self.voice_generation += 1; generation = self.voice_generation
            cancelled = threading.Event(); self.voice_cancel = cancelled
            starting['value'] = True; start.set_sensitive(False); start.set_visible(False); end.set_sensitive(True); status.set_text('Conferindo disponibilidade…')
            def ready(catalog):
                if not current(generation):
                    return
                models = (catalog.get('data') or {}).get('models') or []
                if not any(m.get('model') == 'gpt-realtime-2.1' and m.get('available') and 'webrtc' in (m.get('transports') or []) for m in models):
                    ended('Realtime WebRTC não disponível no gateway. Configure a credencial OpenAI no OpenCode.'); return
                try:
                    media = WebRTCAudio(); self.voice_media = media
                    session = VoiceSession(media, context_text(bound, history)); self.voice_session = session
                    def voice_status(text):
                        status.set_text(text)
                        if session.closed and current(generation):
                            ended(text)
                    session.on_status = voice_status
                    session.on_caption = lambda text: (caption.set_text(text), caption.set_visible(bool(text)))
                    session.on_error = lambda text: ended(text) if current(generation) else None
                    session.on_proposal = lambda call_id, task: proposal(call_id, task, generation)
                    def offered(sdp, kind):
                        if not current(generation) or session.closed:
                            return
                        status.set_text('Criando sessão paga pelo notebook…')
                        def answer(text):
                            if current(generation) and not session.closed:
                                try:
                                    media.remote(text)
                                except Exception as error:
                                    ended(str(error))
                        self.async_job(lambda: self.client.voice_session(sdp, configuration(), approved=True, cancelled=cancelled), answer, lambda text: ended('Criação não confirmada; não será repetida. ' + text) if current(generation) else None, scoped=False)
                    media.on_description = offered
                    self.voice_button.add_css_class('error'); mute.set_active(False); mute.set_sensitive(True)
                    media.start(); status.set_text('Preparando áudio e WebRTC…')
                except Exception as error:
                    ended(str(error))
            self.async_job(self.client.voice_models, ready, lambda text: ended(text) if current(generation) else None, scoped=False)
        def proposal(call_id, task, generation):
            if not current(generation):
                return
            proposals.set_visible(True)
            card = box(True, 8); card.add_css_class('permission'); card.append(label('Pedido de voz · aguardando revisão', 'chat-title')); card.append(label(task, wrap=True)); proposals.append(card)
            state = {'sent': False}
            def send_task():
                if not current(generation) or not self.voice_session or self.voice_session.closed or state['sent']:
                    return
                state['sent'] = True; review.set_sensitive(False)
                payload = prompt_payload({'text': task, 'files': []})
                record = {'sessionID': bound['id'], 'requestID': payload['id'], 'state': 'attempted', 'text': task}
                records = self.store.data.setdefault('voice_requests', {})
                records[payload['id']] = record
                while len(records) > 50:
                    del records[next(iter(records))]
                try:
                    self.store.save()
                except Exception as error:
                    record['state'] = 'not_sent'; status.set_text('Pedido não enviado: ' + str(error)); return
                route = '/api/session/' + urllib.parse.quote(bound['id'], safe='') + '/prompt'
                def admitted(_):
                    record['state'] = 'admitted'; self.persist()
                    if current(generation):
                        card.append(label('Pedido recebido pelo OpenCode — ainda não significa concluído.', wrap=True))
                    if self.session and self.session['id'] == bound['id']:
                        self.refresh()
                def failed(text):
                    record['state'] = 'uncertain'; self.persist()
                    if current(generation):
                        card.append(label('Envio não confirmado. Confira histórico; não será reenviado automaticamente. ' + text, wrap=True))
                self.async_job(lambda: self.client.request(route, 'POST', payload), admitted, failed, scoped=False)
            review = button(text='Revisar e enviar ao OpenCode', callback=lambda: self.confirm('Enviar tarefa desta ligação?', task + '\n\nProjeto: ' + bound.get('location', {}).get('directory', ''), send_task)); card.append(review)
        start = button(text='Ligar · API paga', callback=request_call); start.add_css_class('call-start'); start.set_sensitive(not self.client.demo); content.append(start)
        if (bound.get('metadata') or {}).get('kzlAgent'):
            start.add_css_class('kzl-call-start')
        mute = Gtk.ToggleButton(label='Silenciar microfone'); mute.set_sensitive(False)
        mute.connect('toggled', lambda control: self.voice_session.set_muted(control.get_active()) if self.voice_session else None); content.append(mute)
        end = button(text='Encerrar áudio', callback=lambda: ended('Áudio encerrado. Trabalho já enviado ao notebook não foi interrompido.')); end.add_css_class('destructive-action'); end.set_sensitive(False); content.append(end)
        def test_output():
            if starting['value'] or (self.voice_session and not self.voice_session.closed):
                status.set_text('Encerre a chamada antes de testar a saída local.'); return
            if self.tone:
                self.tone.stop()
            self.tone = LocalTone(); self.tone.on_done = status.set_text
            try:
                self.tone.start(); status.set_text('Teste curto de saída local — sem microfone ou API.')
            except Exception as error:
                self.tone.stop(); status.set_text(str(error))
        content.append(button(text='Testar saída local · sem API', callback=test_output))
        def copy_transcript():
            text = self.voice_session.transcript if self.voice_session else ''
            if text:
                self.window.get_clipboard().set(text); status.set_text('Última transcrição copiada. Nada foi enviado ao chat.')
        content.append(button(text='Copiar última transcrição', callback=copy_transcript))
        if self.client.demo:
            content.append(label('Demonstração: chamadas pagas estão bloqueadas. Teste local apenas reproduz som sintético.', wrap=True))
        def close_voice(*_):
            self.voice_generation += 1; ended()
            if self.tone:
                self.tone.stop()
            self.voice_window = None
            return False
        window.connect('close-request', close_voice)

    def download_artifact(self, artifact):
        parent = str(Path(artifact['path']).parent)
        def work():
            context = self.client.request('/phone/files/context?' + urllib.parse.urlencode({'directory': parent}))
            listing = self.client.request('/phone/files/list?' + urllib.parse.urlencode(context))
            item = next((f for f in listing.get('entries', []) if f['name'] == artifact['name'] and f['kind'] == 'file'), None)
            if not item or not item.get('readable'):
                raise PocketError('Arquivo referenciado não existe ou não está liberado pelo gateway.')
            return context['root'], item
        self.async_job(work, lambda result: self.download(*result))

    def schedules(self):
        if not self.session:
            return
        sid = self.session['id']; scope = self.scope
        window, content = self.dialog('Agendamentos', 600)
        status = label('Carregando…', wrap=True); content.append(status)
        rows = box(True, 10); content.append(rows)
        writes = {'locked': False}
        def write(path, method, payload, reason):
            if scope != self.scope or writes['locked']:
                return
            def confirmed():
                if scope != self.scope or writes['locked']:
                    return
                writes['locked'] = True; rows.set_sensitive(False); create.set_sensitive(False)
                def done(_):
                    writes['locked'] = False; rows.set_sensitive(True); create.set_sensitive(True); load()
                def failed(error):
                    status.set_text('Alteração não confirmada. Escritas bloqueadas nesta janela; confira estado antes de reabrir. ' + error)
                self.async_job(lambda: self.client.request(path, method, payload), done, failed)
            self.confirm(reason, 'Notebook precisa estar disponível. Execução agendada pode consumir cota do modelo desta conversa.', confirmed)
        def loaded(result):
            clear(rows); items = result.get('data', [])
            status.set_text('Nenhum agendamento.' if not items else 'Agendamentos carregados do notebook.')
            for item in items:
                card = box(True, 6); card.add_css_class('code-block')
                card.append(label(item.get('name') or 'Tarefa agendada', 'chat-title', True))
                card.append(label(f'{item["status"]} · {item.get("runCount", 0)} execuções', 'dim-label'))
                if item.get('nextDueAt'):
                    card.append(label(datetime.fromtimestamp(item['nextDueAt'] / 1000).astimezone().strftime('%d/%m/%Y %H:%M %Z')))
                path = '/api/experimental/schedule/' + urllib.parse.quote(item['id'], safe='')
                if item['status'] != 'done':
                    paused = item['status'] == 'paused'
                    card.append(button(text='Retomar' if paused else 'Pausar', callback=lambda p=path, paused=paused: write(p + ('/resume' if paused else '/pause'), 'POST', {}, 'Retomar agendamento?' if paused else 'Pausar agendamento?')))
                card.append(button(text='Excluir', callback=lambda p=path: write(p, 'DELETE', None, 'Excluir agendamento?')))
                rows.append(card)
        def load():
            self.async_job(lambda: self.client.request('/api/experimental/schedule?' + urllib.parse.urlencode({'sessionID': sid})), loaded, lambda error: (status.set_text(error), create.set_sensitive(False)))
        content.append(label('Nova execução', 'chat-title'))
        prompt = Gtk.Entry(placeholder_text='Tarefa para executar depois'); content.append(prompt)
        calendar = Gtk.Calendar(); calendar.select_day(GLib.DateTime.new_now_local().add_hours(1)); content.append(calendar)
        clock = Gtk.Entry(text=(datetime.now() + timedelta(hours=1)).strftime('%H:%M'), placeholder_text='HH:MM · horário local'); content.append(clock)
        content.append(label('Horário local do Linux. Não será executado pelo processo da prévia; agendamento pertence ao notebook.', 'dim-label', True))
        def create_schedule():
            try:
                selected = calendar.get_date(); hour, minute = map(int, clock.get_text().split(':'))
                when = datetime(selected.get_year(), selected.get_month(), selected.get_day_of_month(), hour, minute).astimezone()
                payload = schedule_payload(sid, prompt.get_text(), when.isoformat())
                write('/api/experimental/schedule', 'POST', payload, 'Agendar para ' + when.strftime('%d/%m/%Y %H:%M %Z') + '?')
            except (ValueError, PocketError) as error:
                status.set_text(str(error))
        create = button(text='Agendar uma execução', callback=create_schedule); content.append(create)
        content.append(button(text='Atualizar estado', callback=load)); load()

    def connections(self):
        if not self.session:
            self.error('Abra uma conversa para consultar as conexões desse projeto.'); return
        directory = self.session['location']['directory']
        window, content = self.dialog('Conexões · KzL Center', 620)
        content.append(label('Projeto: ' + directory, 'muted', True))
        content.append(label('Consulta somente leitura. Não instala MCPs, não autentica contas e não concede permissões.', wrap=True))
        content.append(label('API OpenAI é cobrada por uso, separadamente da assinatura ChatGPT. Métodos listados não comprovam saldo nem acesso a um modelo.', 'muted', True))
        content.append(button(text='Gerenciar cadastro MCP e acesso deste projeto', callback=lambda: self.manage_connections(directory)))
        content.append(button(text='OpenAI · API e conta ChatGPT', callback=lambda: self.openai_accounts(directory)))
        rows = box(True, 10); content.append(rows)
        status = label('', 'muted', True); content.append(status)
        busy = False
        def load():
            nonlocal busy
            if busy:
                return
            busy = True; refresh.set_sensitive(False); clear(rows)
            status.set_text('Consultando conexões…')
            def done(value):
                nonlocal busy
                busy = False
                if window not in self.dialogs:
                    return
                refresh.set_sensitive(True)
                if value.get('directory') != directory:
                    status.set_text('Resposta de outro projeto recusada.'); return
                unavailable = value.get('unavailable', [])
                names = {'connected': 'Conectado', 'pending': 'Conectando', 'disabled': 'Desativado', 'failed': 'Falhou', 'needs_auth': 'Precisa autenticar', 'unknown': 'Não confirmado'}
                rows.append(label('Servidores MCP', 'chat-title'))
                for item in value.get('mcp', []):
                    rows.append(label(item['name'] + ' · ' + names.get(item['status'], 'Não confirmado'), wrap=True))
                if not value.get('mcp'):
                    rows.append(label('Consulta indisponível.' if 'mcp' in unavailable else 'Nenhum servidor neste projeto.', wrap=True))
                rows.append(label('Contas e integrações', 'chat-title'))
                for item in value.get('integrations', []):
                    rows.append(label(item['name'] + ' · métodos: ' + ', '.join(item['methods']) + ' · conexões registradas: ' + str(item['connectionCount']), wrap=True))
                if not value.get('integrations'):
                    rows.append(label('Consulta indisponível.' if 'integration' in unavailable else 'Nenhuma integração neste projeto.', wrap=True))
                status.set_text('Consulta parcial; algumas categorias estão indisponíveis.' if unavailable else 'Estado consultado. Conectado não significa autorização para executar ações.')
            def failed(_):
                nonlocal busy
                busy = False
                if window in self.dialogs:
                    refresh.set_sensitive(True); status.set_text('Conexões indisponíveis. Verifique pareamento, gateway e versão instalada.')
            path = '/phone/connections?' + urllib.parse.urlencode({'directory': directory})
            self.async_job(lambda: self.client.request(path), done, failed, scoped=False)
        refresh = button(text='Atualizar conexões', callback=load); content.append(refresh); load()

    def manage_connections(self, directory):
        window, content = self.dialog('Cadastro MCP · ' + directory, 680)
        content.append(label('Cadastro global, acesso por projeto. Habilitar MCP local executa seu comando no computador. Confira origem e argumentos. Não coloque segredos no comando; ambiente aceita apenas referências {env:NOME}.', 'error-banner', True))
        content.append(label('Persistência não confirma ativação. Adaptador KzL deve estar instalado no OpenCode. Após alterar, consulte Conexões; revogar não interrompe operações já admitidas.', 'muted', True))
        rows = box(True, 10); content.append(rows)
        name = Gtk.Entry(placeholder_text='Nome: letras minúsculas, números, _ ou -'); content.append(name)
        name.update_property([Gtk.AccessibleProperty.LABEL], ['Nome do servidor MCP'])
        config = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR); config.set_size_request(-1, 100)
        config.update_property([Gtk.AccessibleProperty.LABEL], ['Configuração MCP em JSON, sem segredos'])
        config.get_buffer().set_text('{"type":"remote","url":"https://example.com/mcp"}')
        content.append(config)
        status = label('', 'muted', True); content.append(status)
        revision = None; busy = False; uncertain = False
        def controls():
            add.set_sensitive(revision is not None and not busy and not uncertain)
            refresh.set_sensitive(not busy)
        def display(value):
            nonlocal revision, uncertain
            revision = value['registry']['revision']; uncertain = False; clear(rows)
            for server, record in value['registry']['servers'].items():
                granted = directory in record['projects']
                row = box(True, 5)
                row.append(label(server + (' · acesso declarado neste projeto' if granted else ' · sem acesso neste projeto'), wrap=True))
                description = json.dumps(record['config'], ensure_ascii=False)
                row.append(label(description, 'muted', True))
                row.append(button(text='Revogar neste projeto' if granted else 'Habilitar neste projeto',
                    callback=lambda n=server, g=granted, d=description: prepare('revoke' if g else 'grant', n, detail=d)))
                row.append(button(text='Remover cadastro global', callback=lambda n=server: prepare('remove', n)))
                rows.append(row)
            status.set_text('Registro lido · revisão ' + str(revision) + '. Estado em execução deve ser consultado separadamente.'); controls()
        def load():
            nonlocal busy
            if busy:
                return
            busy = True; clear(rows); controls()
            def done(value):
                nonlocal busy
                busy = False
                if window in self.dialogs: display(value)
            def failed(_):
                nonlocal busy, revision
                busy = False; revision = None
                if window in self.dialogs: status.set_text('Registro indisponível. Nada alterado.'); controls()
            self.async_job(lambda: self.client.request('/phone/connections/registry'), done, failed, scoped=False)
        def prepare(operation, server, declaration=None, detail=''):
            if busy or uncertain or revision is None:
                return
            payload = {'revision': revision, 'operation': operation, 'name': server}
            if operation == 'add': payload['config'] = declaration
            if operation in ('grant', 'revoke'): payload['directory'] = directory
            warning = {'add': 'Salvar cadastro sem ativar', 'grant': 'Autorizar conexão MCP neste projeto',
                       'revoke': 'Revogar conexão neste projeto', 'remove': 'Remover cadastro e acessos de todos os projetos'}[operation]
            self.confirm(warning, server + '\nProjeto: ' + directory + '\n' + detail + '\nNão concede aprovação irrestrita para ferramentas. Alterações em execução precisam de confirmação posterior.', lambda: write(payload))
        def write(payload):
            nonlocal busy
            if busy or uncertain or window not in self.dialogs or revision != payload['revision']:
                return
            busy = True; clear(rows); controls(); status.set_text('Salvando registro…')
            def done(value):
                nonlocal busy
                busy = False
                if window in self.dialogs: display(value)
            def failed(_):
                nonlocal busy, uncertain
                busy = False; uncertain = True
                if window in self.dialogs:
                    status.set_text('Alteração não confirmada. Nenhuma repetição automática. Atualize registro e confira estado antes de outra ação.'); controls()
            self.async_job(lambda: self.client.request('/phone/connections/registry', 'POST', payload), done, failed, scoped=False)
        def add_server():
            buffer = config.get_buffer()
            try: value = json.loads(buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False))
            except ValueError: status.set_text('JSON inválido.'); return
            prepare('add', name.get_text().strip(), value, json.dumps(value, ensure_ascii=False))
        add = button(text='Revisar novo cadastro', callback=add_server); content.append(add)
        refresh = button(text='Consultar registro atual', callback=load); content.append(refresh); load()

    def openai_accounts(self, directory):
        client = AccountClient(self.client, self.store, directory)
        window, content = self.dialog('OpenAI · KzL Center', 620)
        content.append(label('API usa cobrança por uso; ChatGPT usa limites da assinatura compatível. Conectar não inicia chamada paga nem muda modelo da conversa.', wrap=True))
        content.append(label('Chave será enviada somente ao OpenCode deste computador. Cadastro preserva a credencial ativa existente. Se não houver uma, o OpenCode pode ativar esta chave. Seleção de credencial fica no OpenCode.', 'muted', True))
        key = Gtk.Entry(visibility=False, placeholder_text='Chave OpenAI API · nunca incluída no histórico'); content.append(key)
        key.update_property([Gtk.AccessibleProperty.LABEL], ['Chave OpenAI API protegida'])
        methods = box(True, 8); content.append(methods)
        status = label('', 'muted', True); content.append(status)
        busy = False
        def controls():
            save.set_sensitive(not busy and not client.pending)
            refresh.set_sensitive(not busy); receipt.set_sensitive(not busy and bool(client.pending))
        def finish(text):
            nonlocal busy
            busy = False
            if window in self.dialogs: status.set_text(text); controls()
        def failed(_): finish('Autenticação indisponível ou não confirmada. Consulte resultado; nada será repetido automaticamente.')
        def submit_key():
            if busy or client.pending: return
            self.confirm('Cadastrar chave OpenAI?', 'Salvar no OpenCode sem substituir login ativo existente. Não valida saldo nem acesso aos modelos. Nenhum teste pago será iniciado.', send_key)
        def send_key():
            nonlocal busy
            if busy or client.pending or window not in self.dialogs: return
            value = key.get_text().strip(); key.set_text('')
            busy = True; controls()
            def done(result):
                finish('Credencial salva no OpenCode. ' + ('Tornou-se ativa por não existir outra credencial.' if result.get('active') else 'Login ativo existente preservado; esta chave não foi ativada.'))
            self.async_job(lambda: client.add_key(value), done, failed, scoped=False)
        def oauth(method):
            if busy or client.pending: return
            self.confirm('Entrar com ChatGPT?', 'Usar autorização oficial no navegador. Concluir login pode selecionar a nova conta no OpenCode; registros anteriores não são apagados. Assinatura não fornece créditos de API.', lambda: start(method))
        def start(method):
            nonlocal busy
            if busy or client.pending or window not in self.dialogs: return
            busy = True; controls()
            def done(result):
                finish('Abra autorização oficial e depois consulte resultado. ' + result.get('instructions', ''))
                if window not in self.dialogs: return
                # Link opening remains an explicit user gesture, never automatic.
                link = Gtk.LinkButton(uri=result['url'], label='Abrir autorização oficial OpenAI')
                methods.append(link)
                if result.get('mode') == 'code' or result.get('paste'):
                    status.set_text('Após autorização, cole código ou URL de retorno neste campo protegido, não no chat.')
            self.async_job(lambda: client.start_oauth(method), done, failed, scoped=False)
        def load():
            nonlocal busy
            if busy: return
            busy = True; clear(methods); controls()
            def done(value):
                if window not in self.dialogs: return
                for method in value.get('methods', []):
                    if method.get('type') == 'oauth' and not method.get('requiresFields'):
                        item = button(text=method['label'], callback=lambda m=method['id']: oauth(m)); item.set_sensitive(not client.pending); methods.append(item)
                finish('Métodos oficiais consultados · conexões registradas: ' + str(len(value.get('connections', []))) + '. Conexão registrada não comprova saldo ou acesso ao modelo.')
            self.async_job(client.inventory, done, failed, scoped=False)
        def poll():
            nonlocal busy
            if busy or not client.pending: return
            busy = True; controls()
            self.async_job(client.status, lambda result: finish('Estado da tentativa: ' + result['status'] + '. Nenhuma operação reenviada.'), failed, scoped=False)
        code = Gtk.Entry(visibility=False, placeholder_text='Código OAuth ou URL de retorno, quando solicitado'); content.append(code)
        code.update_property([Gtk.AccessibleProperty.LABEL], ['Código OAuth protegido'])
        def complete():
            if busy or not client.pending: return
            self.confirm('Concluir autorização OpenAI?', 'Enviar código ou URL somente ao OpenCode. Nenhum código será salvo no histórico. A conta autorizada pode se tornar a selecionada no OpenCode.', send_code)
        def send_code():
            nonlocal busy
            if busy or not client.pending or window not in self.dialogs: return
            value = code.get_text().strip(); code.set_text(''); busy = True; controls()
            self.async_job(lambda: client.complete_oauth(value), lambda result: finish('Estado OAuth: ' + result['status']), failed, scoped=False)
        content.append(button(text='Revisar conclusão OAuth', callback=complete))
        save = button(text='Revisar cadastro de chave API', callback=submit_key); content.append(save)
        receipt = button(text='Consultar resultado da tentativa anterior', callback=poll); content.append(receipt)
        refresh = button(text='Consultar métodos e contas', callback=load); content.append(refresh); load()

    def settings(self):
        window, content = self.dialog('Ajustes', 520)
        content.append(label('KzL Agent 0.8.0 · Center · Darktech nativo', 'brand'))
        content.append(button(text='Conexões · MCPs e contas', callback=self.connections))
        content.append(label('Demonstração isolada, sem API.' if self.client.demo else 'Gateway local: http://127.0.0.1:49375', wrap=True))
        content.append(label('Atalhos: Ctrl+K busca conversas · Ctrl+F busca nas mensagens carregadas · Ctrl+N cria conversa · Enter envia · Shift+Enter quebra linha. Os atalhos da janela não atuam por trás de diálogos.', 'muted', True))
        themes = Gtk.DropDown.new_from_strings(['Sistema', 'Claro', 'Escuro']); themes.set_selected(['system', 'light', 'dark'].index(self.store.data.get('theme', 'system')))
        themes.connect('notify::selected', lambda *_: self.apply_theme(['system', 'light', 'dark'][themes.get_selected()])); content.append(label('Aparência')); content.append(themes)
        if not self.client.demo:
            content.append(label('Parear computador · código de seis dígitos. Gere pelo atalho existente “Conectar OpenCode no iPhone”; o código também serve para desktop.', wrap=True))
            code = Gtk.Entry(placeholder_text='Código de pareamento', input_purpose=Gtk.InputPurpose.DIGITS); content.append(code)
            code.update_property([Gtk.AccessibleProperty.LABEL], ['Código de pareamento · seis dígitos'])
            result = label('', 'error-banner', True); content.append(result)
            attempted = None
            def pair():
                nonlocal attempted
                value = code.get_text().strip()
                if self.pairing_in_flight or value == attempted:
                    return
                if not re.fullmatch(r'[0-9]{6}', value):
                    result.set_text('Informe um código de seis dígitos.'); return
                attempted = value; self.pairing_in_flight = True; submit.set_sensitive(False)
                result.set_text('Aguardando confirmação de pareamento…')
                def done(_):
                    self.pairing_in_flight = False; window.close()
                    self.load_sessions(initial=self.session is None); self.load_catalog()
                    if self.session:
                        self.refresh()
                def failed(text):
                    self.pairing_in_flight = False
                    result.set_text('Pareamento não confirmado. Gere outro código antes de uma nova tentativa. Nada foi reenviado automaticamente. ' + text)
                self.async_job(lambda: self.client.pair(value), done, failed, scoped=False)
            submit = button(text='Parear computador', callback=pair); content.append(submit)
            code.connect('changed', lambda *_: submit.set_sensitive(not self.pairing_in_flight and code.get_text().strip() != attempted))
        content.append(label('Live usa áudio/WebRTC nativo, com confirmação antes de cada chamada paga. CallKit e controle físico do iPhone não pertencem ao Linux. Terminal local interativo abre em janela separada após confirmar o projeto; saída do terminal do gateway continua somente leitura. Agendamentos ficam em Recursos da conversa.', wrap=True))

    def sync_theme_classes(self):
        for window in [self.window, *self.dialogs]:
            if Adw.StyleManager.get_default().get_dark():
                window.add_css_class('darktech')
            else:
                window.remove_css_class('darktech')

    def apply_theme(self, theme):
        schemes = {'system': Adw.ColorScheme.DEFAULT, 'light': Adw.ColorScheme.FORCE_LIGHT, 'dark': Adw.ColorScheme.FORCE_DARK}
        Adw.StyleManager.get_default().set_color_scheme(schemes.get(theme, Adw.ColorScheme.DEFAULT))
        self.sync_theme_classes()
        self.store.data['theme'] = theme; self.persist()

    def toggle_sidebar(self):
        visible = not self.sidebar.get_visible()
        self.sidebar.set_visible(visible)
        if self.portrait.get_active():
            self.content.set_visible(not visible)

    def portrait_changed(self, *_):
        active = self.portrait.get_active(); self.store.data['portrait'] = active; self.persist()
        self.sidebar.set_visible(not active); self.content.set_visible(True)
        self.sidebar.set_hexpand(active)
        (self.window.add_css_class if active else self.window.remove_css_class)('compact')
        margins(self.content, 0 if active else 8)
        for widget, spacing in ((self.message_box, 14 if active else 24), (self.compose, 12 if active else 24)):
            widget.set_margin_start(spacing); widget.set_margin_end(spacing)
        self.composer_footer.set_orientation(Gtk.Orientation.VERTICAL if active else Gtk.Orientation.HORIZONTAL)
        self.composer_footer.set_spacing(6 if active else 12)
        self.options_button.set_halign(Gtk.Align.START if active else Gtk.Align.END)
        self.window.set_resizable(not active)
        # GTK client-side decoration reserves 5px per side in this theme.
        self.window.set_default_size(424 if active else 1280, 906 if active else 860)

    def close(self, *_):
        if self.closing:
            return False
        try:
            # Do not tear down media/workers or hide the only editable copy
            # until the final draft/preferences snapshot is actually durable.
            self.store.save()
        except Exception as exc:
            self.error('Fechamento bloqueado: não foi possível salvar o rascunho. ' + str(exc))
            if not any(w.get_title() == 'Rascunho não salvo' for w in self.dialogs):
                window, content = self.dialog('Rascunho não salvo', 520)
                content.append(label('O armazenamento recusou a gravação. A janela e os rascunhos continuam abertos. Copie textos importantes ou libere espaço/permissão e tente novamente. Forçar o encerramento pode perder alterações ainda não salvas.', wrap=True))
                content.append(button(text='Continuar editando', callback=window.close))
                content.append(button(text='Tentar salvar e fechar', callback=lambda: (window.close(), self.window.close())))
            return True
        self.closing = True
        self.voice_generation += 1
        if self.voice_cancel:
            self.voice_cancel.set()
        if self.voice_session:
            self.voice_session.stop()
        if self.voice_media:
            self.voice_media.stop()
        if self.tone:
            self.tone.stop()
        if self.upload_job_cancel:
            self.upload_job_cancel.set()
        if self.uploads:
            self.uploads.close()
        for chooser in list(self.upload_choosers):
            chooser.destroy()
        self.upload_choosers.clear()
        for chooser in list(self.save_choosers):
            chooser.destroy()
        self.save_choosers.clear()
        if self.save_timer:
            GLib.source_remove(self.save_timer); self.save_timer = 0
        for dialog in list(self.dialogs):
            dialog.close()
        self.pool.shutdown(wait=False, cancel_futures=True)
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='Offline synthetic data; never uses credentials or APIs')
    parser.add_argument('--portrait', action='store_true', help='Open with a 414px native portrait viewport')
    parser.add_argument('--state-dir', help='Override private preferences directory')
    args = parser.parse_args()
    os.umask(0o077)
    app = Pocket(args.demo, args.state_dir)
    if args.portrait:
        app.store.data['portrait'] = True
    app.run([])
