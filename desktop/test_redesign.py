"""Display-free checks for the redesign's formatting and navigation logic."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest

from main import Gdk, Gtk, Pocket, STYLE, display_time


class Widget:
    def __init__(self, visible=True):
        self.visible = visible
        self.focused = False

    def get_visible(self):
        return self.visible

    def set_visible(self, value):
        self.visible = value

    def grab_focus(self):
        self.focused = True


class RedesignTests(unittest.TestCase):
    def test_css_parses_with_native_gtk(self):
        provider = Gtk.CssProvider()
        errors = []
        provider.connect('parsing-error', lambda _, section, error: errors.append(str(error)))
        provider.load_from_string(STYLE)
        self.assertEqual(errors, [])

    def test_time_accepts_gateway_milliseconds_and_legacy_seconds(self):
        moment = datetime(2026, 11, 5, 18, 33)
        self.assertEqual(display_time(moment.timestamp()), '18:33')
        self.assertEqual(display_time(moment.timestamp() * 1000), '18:33')

    def test_absent_or_invalid_time_is_not_invented(self):
        for value in (None, '', 'bad', 0, -1, float('nan'), float('inf'), {}):
            with self.subTest(value=value):
                self.assertEqual(display_time(value), '')

    def test_relative_time_uses_local_calendar_day(self):
        now = datetime.now()
        self.assertEqual(display_time(now.timestamp(), True), now.strftime('%H:%M'))
        self.assertEqual(display_time((now - timedelta(days=1)).timestamp(), True), 'Ontem')
        old = now - timedelta(days=7)
        self.assertEqual(display_time(old.timestamp(), True), old.strftime('%d/%m'))

    def app(self, portrait):
        return SimpleNamespace(sidebar=Widget(False), content=Widget(), search=Widget(),
                               portrait=SimpleNamespace(get_active=lambda: portrait),
                               dialogs=[], save_choosers=[], upload_choosers=[], closing=False)

    def test_portrait_sidebar_replaces_chat_and_returns_without_navigation(self):
        app = self.app(True)
        Pocket.toggle_sidebar(app)
        self.assertTrue(app.sidebar.visible)
        self.assertFalse(app.content.visible)
        Pocket.toggle_sidebar(app)
        self.assertFalse(app.sidebar.visible)
        self.assertTrue(app.content.visible)

    def test_desktop_sidebar_keeps_chat_visible(self):
        app = self.app(False)
        Pocket.toggle_sidebar(app)
        self.assertTrue(app.sidebar.visible)
        self.assertTrue(app.content.visible)

    def test_conversation_search_shortcut_focuses_sidebar_without_sending(self):
        app = self.app(True)
        self.assertTrue(Pocket.window_shortcuts(app, None, Gdk.KEY_k, 0, Gdk.ModifierType.CONTROL_MASK))
        self.assertTrue(app.search.focused)
        self.assertTrue(app.sidebar.visible)
        self.assertFalse(app.content.visible)

    def test_message_search_restores_chat_before_opening_results(self):
        app = self.app(True)
        app.sidebar.set_visible(True); app.content.set_visible(False)
        observed = []
        app.search_conversation = lambda: observed.append(app.content.get_visible())
        self.assertTrue(Pocket.window_shortcuts(app, None, Gdk.KEY_f, 0, Gdk.ModifierType.CONTROL_MASK))
        self.assertEqual(observed, [True])
        self.assertFalse(app.sidebar.visible)

    def test_search_shortcut_does_not_operate_behind_a_dialog(self):
        for guard in ('dialogs', 'save_choosers', 'upload_choosers'):
            app = self.app(True)
            setattr(app, guard, [object()])
            self.assertFalse(Pocket.window_shortcuts(app, None, Gdk.KEY_k, 0, Gdk.ModifierType.CONTROL_MASK))
            self.assertFalse(app.search.focused)
            self.assertFalse(app.sidebar.visible)


if __name__ == '__main__':
    unittest.main()
