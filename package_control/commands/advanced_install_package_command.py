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


class AdvancedInstallPackageCommand(sublime_plugin.WindowCommand):

    """
    A command that accepts a comma-separated list of packages to install, or
    prompts the user to paste a comma-separated list.
    """

    def run(self, packages=None):
        is_str = isinstance(packages, str_cls)
        is_bytes = isinstance(packages, bytes_cls)

        if packages and (is_str or is_bytes):
            packages = self.split(packages)

        if packages and isinstance(packages, list):
            return self.start(packages)

        self.window.show_input_panel(
            'Packages to Install (Comma-separated)',
            '',
            self.on_done,
            None,
            None
        )

    def split(self, packages):
        if isinstance(packages, bytes_cls):
            packages = packages.decode('utf-8')
        return re.split(r'\s*,\s*', packages)

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
        thread = AdvancedInstallPackageThread(packages)
        thread.start()
        message = 'Installing package'
        if len(packages) > 1:
            message += 's'
        ThreadProgress(thread, message, '')


class AdvancedInstallPackageThread(threading.Thread):

    """
    A thread to run the installation of one or more packages.
    """

    def __init__(self, packages):
        """
        :param window:
            An instance of :class:`sublime.Window` that represents the Sublime
            Text window to show the available package list.
        """
        self.manager = PackageManager()
        self.packages = [packages] if isinstance( packages, str ) else packages

        self.installed = self.manager.list_packages()
        threading.Thread.__init__(self)

    def run(self):
        installed = list(self.installed)

        def closure(package_name):
            return 'install' if package_name not in installed else 'upgrade'

        iterable = IgnoredPackagesBugFixer(self.packages, closure)

        for package in iterable:

            # Do not reenable if installation deferred until next restart
            if self.manager.install_package(package) is None:
                iterable.skip_reenable(package)
