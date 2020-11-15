import sublime
import sublime_plugin


class PackageControlDisableDebugModeCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings('PackagesManager.sublime-settings')
        settings.set('debug', False)
        sublime.save_settings('PackagesManager.sublime-settings')

        sublime.message_dialog(
            'PackagesManager\n\n'
            'Debug mode has been disabled'
        )

    def is_visible(self):
        return sublime.load_settings('PackagesManager.sublime-settings').get('debug')

    def is_enabled(self):
        return self.is_visible()
