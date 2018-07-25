import sublime
import sublime_plugin

from .list_packages_command import ListPackagesThread


class ListUnmanagedPackagesCommand(sublime_plugin.WindowCommand):

    """
    A command that shows a list of all packages that are not managed by
    PackagesManager, i.e. that are installed, but not mentioned in
    `installed_packages`.
    """

    def run(self):
        settings = sublime.load_settings('PackagesManager.sublime-settings')

        ignored_packages = settings.get('unmanaged_packages_ignore', [])
        ignored_packages.extend(settings.get('installed_packages', []))

        def filter_packages(package):
            return package[0] not in ignored_packages

        ListPackagesThread(self.window, filter_packages).start()