import threading
import os
import shlex
import functools

import sublime

from .show_error import show_error
from .console_write import console_write
from .unicode import unicode_from_os
from .clear_directory import clear_directory, unlink_or_delete_directory, clean_old_files
from .automatic_upgrader import AutomaticUpgrader
from .package_disabler import PackageDisabler
from .package_manager import PackageManager
from .open_compat import open_compat
from .package_io import package_file_exists
from .settings import preferences_filename, pc_settings_filename, load_list_setting, save_list_setting, increment_dependencies_installed
from . import cmd
from . import loader, text, __version__
from .providers.release_selector import is_compatible_version
from .commands.advanced_uninstall_package_command import AdvancedUninstallPackageThread


class PackageCleanup(threading.Thread):

    """
    Cleans up folders for packages that were removed, but that still have files
    in use.
    """

    def __init__(self):
        self.manager = PackageManager()
        self.disabler = PackageDisabler()
        self.ignore_in_process_packages = False

        settings = sublime.load_settings(pc_settings_filename())
        self.debug = settings.get('debug')

        # We no longer use the installed_dependencies setting because it is not
        # necessary and created issues with settings shared across operating systems
        if settings.get('installed_dependencies'):
            settings.erase('installed_dependencies')
            sublime.save_settings(pc_settings_filename())

        self.original_installed_packages = load_list_setting(settings, 'installed_packages')
        self.remove_orphaned = settings.get('remove_orphaned', True)

        threading.Thread.__init__(self)

    def run(self):
        if self.debug: console_write(u'Calling PackageCleanup.run()')

        # This song and dance is necessary so PackagesManager doesn't try to clean
        # itself up, but also get properly marked as installed in the settings
        installed_packages_at_start = list(self.original_installed_packages)

        # Ensure we record the installation of PackagesManager itself
        if 'PackagesManager' not in installed_packages_at_start:
            params = {
                'package': 'PackagesManager',
                'operation': 'install',
                'version': __version__
            }
            self.manager.record_usage(params)
            installed_packages_at_start.append('PackagesManager')

        found_packages = []
        not_found_packages = []
        installed_packages = list(installed_packages_at_start)

        found_dependencies = []
        installed_dependencies = self.manager.list_dependencies()

        # We scan the Installed Packages folder in ST3 before we check for
        # dependencies since some dependencies might be specified by a
        # .sublime-package-new that has not yet finished being installed.
        if int(sublime.version()) >= 3000:
            installed_path = sublime.installed_packages_path()

            for file in os.listdir(installed_path):
                # If there is a package file ending in .sublime-package-new, it
                # means that the .sublime-package file was locked when we tried
                # to upgrade, so the package was left in ignored_packages and
                # the user was prompted to restart Sublime Text. Now that the
                # package is not loaded, we can replace the old version with the
                # new one.
                if file[-20:] == '.sublime-package-new' and file != loader.loader_package_name + '.sublime-package-new':
                    package_name = file.replace('.sublime-package-new', '')
                    package_file = os.path.join(installed_path, package_name + '.sublime-package')
                    try:
                        if os.path.exists(package_file):
                            os.remove(package_file)
                    except Exception as error:
                        console_write(
                            u'''
                            Error: %s
                            ''',
                            error
                        )
                        self.disabler.disable_packages(package_name)
                        self.ignore_in_process_packages = True
                        continue

                    os.rename(os.path.join(installed_path, file), package_file)
                    console_write(
                        u'''
                        Finished replacing %s.sublime-package
                        ''',
                        package_name
                    )
                    continue

                if file[-16:] != '.sublime-package':
                    continue

                package_name = file.replace('.sublime-package', '')

                if package_name == loader.loader_package_name:
                    # This got `0_packagesmanager_loader`, it seems to be scanning the `Installed Packages` folder
                    # print( "package_cleanup.py, package_name: " + str( package_name ) )
                    found_dependencies.append(package_name)
                    continue

                # Cleanup packages that were installed via PackagesManager, but
                # we removed from the "installed_packages" list - usually by
                # removing them from another computer and the settings file
                # being synced.
                if self.remove_orphaned and package_name not in installed_packages_at_start \
                        and package_file_exists(package_name, 'package-metadata.json'):
                    not_found_packages.append(package_name)
                else:
                    found_packages.append(package_name)

        if not_found_packages:
            uninstaller = AdvancedUninstallPackageThread(not_found_packages)
            uninstaller.run()

        required_dependencies = set(self.manager.find_required_dependencies())
        extra_dependencies = list(set(installed_dependencies) - required_dependencies)

        # print( "package_cleanup.py, extra_dependencies:     %s\n%s" % (
        #         len(extra_dependencies), list(sorted(extra_dependencies, key=lambda s: s.lower())) ) )
        # print( "package_cleanup.py, installed_dependencies: %s\n%s" % (
        #         len(installed_dependencies), list(sorted(installed_dependencies, key=lambda s: s.lower())) ) )
        # print( "package_cleanup.py, required_dependencies:  %s\n%s" % (
        #         len(required_dependencies), list(sorted(required_dependencies, key=lambda s: s.lower())) ) )

        # Clean up unneeded dependencies so that found_dependencies will only
        # end up having required dependencies added to it
        for dependency in extra_dependencies:
            dependency_dir = os.path.join(sublime.packages_path(), dependency)
            if unlink_or_delete_directory(dependency_dir):
                console_write(
                    u'''
                    Removed directory for unneeded dependency %s
                    ''',
                    dependency
                )
            else:
                cleanup_file = os.path.join(dependency_dir, 'package-control.cleanup')
                if not os.path.exists(cleanup_file):
                    open_compat(cleanup_file, 'w').close()
                console_write(
                    u'''
                    Unable to remove directory for unneeded dependency %s -
                    deferring until next start
                    ''',
                    dependency
                )
            # Make sure when cleaning up the dependency files that we remove the loader for it also
            loader.remove(dependency)

        # command_line_interface = cmd.Cli( None, True )
        # command_line_interface.execute( shlex.split( "ls %s" % sublime.packages_path().replace('\\', '/') ),
        #         sublime.packages_path(), live_output=True, short_errors=True )

        for package_name in os.listdir(sublime.packages_path()):
            # print( "package_cleanup.py, Processing package: " + str( package_name ) )
            found = True

            package_dir = os.path.join(sublime.packages_path(), package_name)
            if not os.path.isdir(package_dir):
                continue

            clean_old_files(package_dir)

            if int(sublime.version()) > 3000 and os.path.exists(package_dir + '/.sublime-package-override'):
                if not os.path.exists(package_dir + '/.no-sublime-package'):
                    found = False

            # Cleanup packages/dependencies that could not be removed due to in-use files
            cleanup_file = os.path.join(package_dir, 'package-control.cleanup')
            if os.path.exists(cleanup_file):
                if unlink_or_delete_directory(package_dir):
                    console_write(
                        u'''
                        Removed old directory %s
                        ''',
                        package_name
                    )
                    found = False
                else:
                    if not os.path.exists(cleanup_file):
                        open_compat(cleanup_file, 'w').close()
                    console_write(
                        u'''
                        Unable to remove old directory %s - deferring until next
                        start
                        ''',
                        package_name
                    )

            # Finish reinstalling packages that could not be upgraded due to
            # in-use files
            reinstall = os.path.join(package_dir, 'package-control.reinstall')
            if os.path.exists(reinstall):
                metadata_path = os.path.join(package_dir, 'package-metadata.json')
                # No need to handle symlinks here as that was already handled in earlier step
                # that has attempted to re-install the package initially.
                if not clear_directory(package_dir, [metadata_path]):
                    if not os.path.exists(reinstall):
                        open_compat(reinstall, 'w').close()

                    def show_still_locked(package_name):
                        show_error(
                            u'''
                            An error occurred while trying to finish the upgrade of
                            %s. You will most likely need to restart your computer
                            to complete the upgrade.
                            ''',
                            package_name
                        )
                    # We use a functools.partial to generate the on-complete callback in
                    # order to bind the current value of the parameters, unlike lambdas.
                    sublime.set_timeout(functools.partial(show_still_locked, package_name), 10)
                else:
                    self.manager.install_package(package_name)

            if package_file_exists(package_name, 'package-metadata.json'):
                # This adds previously installed packages from old versions of
                # PC. As of PC 3.0, this should basically never actually be used
                # since installed_packages was added in late 2011.
                if not installed_packages_at_start:
                    installed_packages.append(package_name)
                    params = {
                        'package': package_name,
                        'operation': 'install',
                        'version':
                            self.manager.get_metadata(package_name).get('version')
                    }
                    self.manager.record_usage(params)

                # Cleanup packages that were installed via PackagesManager, but
                # we removed from the "installed_packages" list - usually by
                # removing them from another computer and the settings file
                # being synced.
                elif self.remove_orphaned and package_name not in installed_packages_at_start:
                    self.manager.backup_package_dir(package_name)
                    if unlink_or_delete_directory(package_dir):
                        console_write(
                            u'''
                            Removed directory for orphaned package %s
                            ''',
                            package_name
                        )
                        found = False
                    else:
                        if not os.path.exists(cleanup_file):
                            open_compat(cleanup_file, 'w').close()
                        console_write(
                            u'''
                            Unable to remove directory for orphaned package %s -
                            deferring until next start
                            ''',
                            package_name
                        )

            if package_name[-20:] == '.package-control-old':
                console_write(
                    u'''
                    Removed old directory %s
                    ''',
                    package_name
                )
                unlink_or_delete_directory(package_dir)

            # Skip over dependencies since we handle them separately
            if (package_file_exists(package_name, 'dependency-metadata.json')
                    or package_file_exists(package_name, '.sublime-dependency')):

                if package_name == loader.loader_package_name:
                    continue

                # If the file exists on the system, but it is not on the loader? Just add them. This
                # happens when you develop the dependency on you computer and the dependency is
                # installed by git.
                if not loader.exists(package_name):
                    console_write(
                        u'''
                        Adding missing dependency loader for the package: %s
                        ''',
                        package_name
                    )
                    load_order, loader_code = self.manager.get_dependency_priority_code(package_name)
                    loader.add_or_update(load_order, package_name, loader_code)
                    increment_dependencies_installed()

                # print( "package_cleanup.py, Adding dependency: " + str( package_name ) )
                found_dependencies.append(package_name)
                continue

            if found:
                found_packages.append(package_name)

        invalid_packages = []
        invalid_dependencies = []

        # Check metadata to verify packages were not improperly installed
        for package in found_packages:
            if package == 'User' or package == 'Default':
                continue

            metadata = self.manager.get_metadata(package)
            if metadata and not self.is_compatible(metadata):
                invalid_packages.append(package)

        # print( "package_cleanup.py, found_dependencies:     %d\n" % len( found_dependencies ) + str( found_dependencies ) )

        # Make sure installed dependencies are not improperly installed
        for dependency in found_dependencies:
            metadata = self.manager.get_metadata(dependency, is_dependency=True)
            if metadata and not self.is_compatible(metadata):
                invalid_dependencies.append(dependency)

        if invalid_packages or invalid_dependencies:
            def show_sync_error():
                message = u''
                if invalid_packages:
                    package_s = 's were' if len(invalid_packages) != 1 else ' was'
                    message += text.format(
                        u'''
                        The following incompatible package%s found installed:

                        %s

                        ''',
                        (package_s, '\n'.join(invalid_packages))
                    )
                if invalid_dependencies:
                    dependency_s = 'ies were' if len(invalid_dependencies) != 1 else 'y was'
                    message += text.format(
                        u'''
                        The following incompatible dependenc%s found installed:

                        %s

                        ''',
                        (dependency_s, '\n'.join(invalid_dependencies))
                    )
                message += text.format(
                    u'''
                    This is usually due to syncing packages across different
                    machines in a way that does not check package metadata for
                    compatibility.

                    Please visit https://packagecontrol.io/docs/syncing for
                    information about how to properly sync configuration and
                    packages across machines.

                    To restore package functionality, please remove each listed
                    package and reinstall it.
                    '''
                )
                show_error(message)
            sublime.set_timeout(show_sync_error, 100)

        sublime.set_timeout(lambda: self.finish(installed_packages, found_packages, found_dependencies), 10)

    def is_compatible(self, metadata):
        """
        Detects if a package is compatible with the current Sublime Text install

        :param metadata:
            A dict from a metadata file

        :return:
            If the package is compatible
        """

        sublime_text = metadata.get('sublime_text')
        platforms = metadata.get('platforms', [])

        # This indicates the metadata is old, so we assume a match
        if not sublime_text and not platforms:
            return True

        if not is_compatible_version(sublime_text):
            return False

        if not isinstance(platforms, list):
            platforms = [platforms]

        platform_selectors = [
            sublime.platform() + '-' + sublime.arch(),
            sublime.platform(),
            '*'
        ]

        for selector in platform_selectors:
            if selector in platforms:
                return True

        return False

    def finish(self, installed_packages, found_packages, found_dependencies):
        """
        A callback that can be run the main UI thread to perform saving of the
        PackagesManager.sublime-settings file. Also fires off the
        :class:`AutomaticUpgrader`.

        :param installed_packages:
            A list of the string package names of all "installed" packages,
            even ones that do not appear to be in the filesystem.

        :param found_packages:
            A list of the string package names of all packages that are
            currently installed on the filesystem.

        :param found_dependencies:
            A list of the string package names of all dependencies that are
            currently installed on the filesystem.
        """
        if self.debug: console_write(u'Calling PackageCleanup.finish()')

        # Make sure we didn't accidentally ignore packages because something
        # was interrupted before it completed.
        pc_filename = pc_settings_filename()
        pc_settings = sublime.load_settings(pc_filename)

        in_process = load_list_setting(pc_settings, 'in_process_packages')
        if not self.ignore_in_process_packages:
            to_reenable = []

            for package in in_process:
                # This prevents removing unused dependencies from being messed up by
                # the functionality to re-enable packages that were left disabled
                # by an error.
                if loader.loader_package_name == package and loader.is_swapping():
                    continue
                console_write(
                    u'''
                    The package %s is being re-enabled after a PackagesManager
                    operation was interrupted
                    ''',
                    package
                )
                to_reenable.append( package )

            if to_reenable: self.disabler.reenable_package(to_reenable, 'enable')

        save_list_setting(
            pc_settings,
            pc_filename,
            'installed_packages',
            installed_packages,
            self.original_installed_packages
        )
        AutomaticUpgrader(found_packages, found_dependencies).start()
