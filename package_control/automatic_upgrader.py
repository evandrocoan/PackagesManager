import threading
import os
import datetime
# To prevent import errors in thread with datetime
import locale  # noqa
import time
import functools

import sublime

from .show_error import show_error
from .console_write import console_write
from .package_disabler_iterator import IgnoredPackagesBugFixer
from .package_installer import PackageInstaller
from .package_renamer import PackageRenamer
from .file_not_found_error import FileNotFoundError
from .open_compat import open_compat, read_compat, write_compat
from .settings import pc_settings_filename, load_list_setting, increment_dependencies_installed, get_dependencies_installed, force_lower


class AutomaticUpgrader(threading.Thread):

    """
    Automatically checks for updated packages and installs them. controlled
    by the `auto_upgrade`, `auto_upgrade_ignore`, and `auto_upgrade_frequency`
    settings.
    """

    def __init__(self, found_packages, found_dependencies):
        """
        :param found_packages:
            A list of package names for the packages that were found to be
            installed on the machine.

        :param found_dependencies:
            A list of installed dependencies found on the machine
        """

        self.installer = PackageInstaller()
        self.manager = self.installer.manager

        self.load_settings()

        self.package_renamer = PackageRenamer()
        self.package_renamer.load_settings()

        self.auto_upgrade = self.settings.get('auto_upgrade')
        self.auto_upgrade_ignore = self.settings.get('auto_upgrade_ignore')

        self.load_last_run()
        self.determine_next_run()

        clean_found_packages = force_lower( found_packages )
        clean_installed_packages = force_lower( self.installed_packages )

        # Detect if a package is missing that should be installed
        self.missing_packages = list(clean_installed_packages - clean_found_packages)
        required_dependencies = self.manager.find_required_dependencies()

        clean_found_dependencies = force_lower( found_dependencies )
        clean_required_dependencies = force_lower( required_dependencies )

        self.missing_dependencies = list(clean_required_dependencies - clean_found_dependencies)

        # print( "automatic_upgrader.py, missing_dependencies:  %s\n%s" % (
        #         len(self.missing_dependencies), list(sorted(self.missing_dependencies, key=lambda s: s.lower())) ) )
        # print( "automatic_upgrader.py, found_dependencies:    %s\n%s" % (
        #         len(found_dependencies), list(sorted(found_dependencies, key=lambda s: s.lower())) ) )
        # print( "automatic_upgrader.py, required_dependencies: %s\n%s" % (
        #         len(required_dependencies), list(sorted(required_dependencies, key=lambda s: s.lower())) ) )

        if self.auto_upgrade and self.next_run <= time.time():
            self.save_last_run(time.time())

        threading.Thread.__init__(self)

    def load_last_run(self):
        """
        Loads the last run time from disk into memory
        """

        self.last_run = None

        self.last_run_file = os.path.join(sublime.packages_path(), 'User', 'PackagesManager.last-run')

        try:
            with open_compat(self.last_run_file) as fobj:
                self.last_run = int(read_compat(fobj))
        except (FileNotFoundError, ValueError):
            pass

    def determine_next_run(self):
        """
        Figure out when the next run should happen
        """

        self.next_run = int(time.time())

        frequency = self.settings.get('auto_upgrade_frequency')
        if frequency:
            if self.last_run:
                self.next_run = int(self.last_run) + (frequency * 60 * 60)
            else:
                self.next_run = time.time()

    def save_last_run(self, last_run):
        """
        Saves a record of when the last run was

        :param last_run:
            The unix timestamp of when to record the last run as
        """

        with open_compat(self.last_run_file, 'w') as fobj:
            write_compat(fobj, int(last_run))

    def load_settings(self):
        """
        Loads the list of installed packages
        """

        self.settings = sublime.load_settings(pc_settings_filename())
        self.installed_packages = load_list_setting(self.settings, 'installed_packages')
        self.should_install_missing = self.settings.get('install_missing')

    def run(self):
        self.install_missing()

        if self.next_run > time.time():
            self.print_skip()
            return

        self.upgrade_packages()

    def install_missing(self):
        """
        Installs all packages that were listed in the list of
        `installed_packages` from PackagesManager.sublime-settings but were not
        found on the filesystem and passed as `found_packages`. Also installs
        any missing dependencies.
        """

        # We always install missing dependencies - this operation does not
        # obey the "install_missing" setting since not installing dependencies
        # would result in broken packages.
        if self.missing_dependencies:
            total_missing_dependencies = len(self.missing_dependencies)
            dependency_s = 'ies' if total_missing_dependencies != 1 else 'y'
            console_write(
                u'''
                Installing %s missing dependenc%s:
                %s
                ''',
                (total_missing_dependencies, dependency_s, self.missing_dependencies)
            )

            for dependency in self.missing_dependencies:
                if self.manager.install_package(dependency, is_dependency=True):
                    console_write(u'Installed missing dependency %s', dependency)
                    increment_dependencies_installed()

        dependencies_installed = get_dependencies_installed()

        if dependencies_installed:
            def notify_restart():
                dependency_was = 'ies were' if dependencies_installed != 1 else 'y was'
                show_error(
                    u'''
                    %s missing dependenc%s just installed. Sublime Text
                    should be restarted, otherwise one or more of the
                    installed packages may not function properly.
                    ''',
                    (dependencies_installed, dependency_was)
                )
            sublime.set_timeout(notify_restart, 1000)

        # Missing package installs are controlled by a setting
        if not self.missing_packages or not self.should_install_missing:
            return

        total_missing_packages = len(self.missing_packages)

        if total_missing_packages > 0:
            package_s = 's' if total_missing_packages != 1 else ''
            console_write(
                u'''
                Installing %s missing package%s:
                %s
                ''',
                (total_missing_packages, package_s, self.missing_packages)
            )

        # Fetching the list of packages also grabs the renamed packages
        self.manager.list_available_packages()
        renamed_packages = self.manager.settings.get('renamed_packages', {})

        for package in IgnoredPackagesBugFixer(self.missing_packages, "install"):

            # If the package has been renamed, detect the rename and update
            # the settings file with the new name as we install it
            if package in renamed_packages:
                old_name = package
                new_name = renamed_packages[old_name]

                def update_installed_packages():
                    self.installed_packages.remove(old_name)
                    self.installed_packages.append(new_name)
                    self.settings.set('installed_packages', self.installed_packages)
                    sublime.save_settings(pc_settings_filename())

                sublime.set_timeout(update_installed_packages, 10)
                package = new_name

            if self.manager.install_package(package):
                console_write(
                    u'''
                    Installed missing package %s
                    ''',
                    package
                )

    def print_skip(self):
        """
        Prints a notice in the console if the automatic upgrade is skipped
        due to already having been run in the last `auto_upgrade_frequency`
        hours.
        """

        last_run = datetime.datetime.fromtimestamp(self.last_run)
        next_run = datetime.datetime.fromtimestamp(self.next_run)
        date_format = '%Y-%m-%d %H:%M:%S'
        console_write(
            u'''
            Skipping automatic upgrade, last run at %s, next run at %s or after
            ''',
            (last_run.strftime(date_format), next_run.strftime(date_format))
        )

    def upgrade_packages(self):
        """
        Upgrades all packages that are not currently upgraded to the lastest
        version. Also renames any installed packages to their new names.
        """

        if not self.auto_upgrade:
            return

        self.package_renamer.rename_packages(self.manager)

        package_list = self.installer.make_package_list(
            [
                'install',
                'reinstall',
                'downgrade',
                'overwrite',
                'none'
            ],
            ignore_packages=self.auto_upgrade_ignore
        )

        # If PackagesManager is being upgraded, just do that and restart
        for package in package_list:
            if package[0] != 'PackagesManager':
                continue

            if self.last_run:
                def reset_last_run():
                    # Re-save the last run time so it runs again after PC has
                    # been updated
                    self.save_last_run(self.last_run)
                sublime.set_timeout(reset_last_run, 1)
            package_list = [package]
            break

        if not package_list:
            console_write(
                u'''
                No updated packages
                '''
            )
            return

        console_write(
            u'''
            Installing %s upgrades:
            %s
            ''',
            (len(package_list), package_list)
        )

        for package_name in IgnoredPackagesBugFixer([info[0] for info in package_list], "upgrade"):

            if self.manager.install_package(package_name):
                version = self.manager.get_version(package_name)
                console_write(
                    u'''
                    Upgraded %s to %s
                    ''',
                    (package_name, version)
                )
