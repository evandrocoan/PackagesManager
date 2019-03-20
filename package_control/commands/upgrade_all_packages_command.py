import time
import threading
import functools

import sublime
import sublime_plugin

from .. import text
from ..console_write import console_write
from ..show_quick_panel import show_quick_panel
from ..thread_progress import ThreadProgress
from ..package_installer import PackageInstaller, PackageInstallerThread
from ..package_renamer import PackageRenamer
from ..package_disabler_iterator import IgnoredPackagesBugFixer


class UpgradeAllPackagesCommand(sublime_plugin.WindowCommand):

    """
    A command to automatically upgrade all installed packages that are
    upgradable.
    """

    def run(self):
        package_renamer = PackageRenamer()
        package_renamer.load_settings()

        thread = UpgradeAllPackagesThread(self.window, package_renamer)
        thread.start()
        ThreadProgress(thread, 'Loading repositories', '')


class UpgradeAllPackagesThread(threading.Thread, PackageInstaller):

    """
    A thread to run the action of retrieving upgradable packages in.
    """

    def __init__(self, window, package_renamer):
        self.window = window
        self.package_renamer = package_renamer
        self.completion_type = 'upgraded'
        threading.Thread.__init__(self)
        PackageInstaller.__init__(self)

    def run(self):
        package_names = []
        package_list = self.make_package_list(['install', 'reinstall', 'none'])
        self.package_renamer.rename_packages(self.manager)

        if not package_list:
            sublime.message_dialog(text.format(
                u'''
                PackagesManager

                There are no packages ready for upgrade
                '''
            ))
            return

        console_write( 'Upgrading packages %s' % package_list )

        for info in package_list:
            package_names.append(info[0])

        iterable = IgnoredPackagesBugFixer(package_names, 'upgrade')

        for package in iterable:
            console_write( 'Upgrading package %s' % package )

            # Do not reenable if installation deferred until next restart
            if self.manager.install_package(package) is None:
                iterable.skip_reenable(package)

            console_write( 'Package %s successfully %s' % (package, self.completion_type) )
