import threading
import re
import time
import functools

import sublime
import sublime_plugin

from ..show_error import show_error
from ..package_manager import PackageManager
from ..thread_progress import ThreadProgress
from ..package_disabler_iterator import IgnoredPackagesBugFixer

try:
    str_cls = unicode
    bytes_cls = str
except (NameError):
    str_cls = str
    bytes_cls = bytes


class AdvancedUninstallPackageCommand(sublime_plugin.WindowCommand):

    """
    A command that accepts a comma-separated list of packages to uninstall, or
    prompts the user to paste a comma-separated list
    """

    def run(self, packages=None):
        is_str = isinstance(packages, str_cls)
        is_bytes = isinstance(packages, bytes_cls)

        if packages and (is_str or is_bytes):
            packages = self.split(packages)

        if packages and isinstance(packages, list):
            return self.start(packages)

        self.window.show_input_panel(
            'Packages to Uninstall (Comma-separated)',
            '',
            self.on_done,
            None,
            None
        )

    def split(self, packages):
        if isinstance(packages, bytes_cls):
            packages = packages.decode('utf-8')
        return re.split(u'\s*,\s*', packages)

    def on_done(self, input):
        """
        Input panel handler - adds the provided URL as a repository

        :param input:
            A string of the URL to the new repository
        """

        input = input.strip()

        if not input:
            show_error(
                u'''
                No package names were entered
                '''
            )
            return

        self.start(self.split(input))

    def start(self, packages):
        thread = AdvancedUninstallPackageThread(packages)
        thread.start()
        message = 'Uninstalling package'
        if len(packages) > 1:
            message += 's'
        ThreadProgress(thread, message, '')


class AdvancedUninstallPackageThread(threading.Thread):

    """
    A thread to run the uninstallation of one or more packages.
    """

    def __init__(self, packages):
        """
        :param window:
            An instance of :class:`sublime.Window` that represents the Sublime
            Text window to show the available package list in.
        """
        threading.Thread.__init__(self)

        self.manager = PackageManager()
        self.packages = packages

    def run(self):
        iterable = IgnoredPackagesBugFixer(self.packages, "remove")

        for package in iterable:

            # Do not reenable if installation deferred until next restart
            if self.manager.remove_package(package) is None:
                iterable.skip_reenable(package)
