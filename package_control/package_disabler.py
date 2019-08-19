import sublime

import os
import json
import time
import random
import threading

from . import text
from . import settings as g_settings
from .console_write import console_write
from .package_io import package_file_exists, read_package_file
from .settings import preferences_filename, pc_settings_filename, load_list_setting, save_list_setting

# This has to be imported this way for consistency with the public API,
# otherwise this code and packages will each load a different instance of the
# module, and the event tracking won't work. However, upon initial install,
# when running ST3, the module will not yet be imported, and the cwd will not
# be Packages/PackagesManager/ so we need to patch it into sys.modules.
try:
    from package_control import events
except (ImportError):
    events = None


class PackageDisabler():
    old_color_scheme_package = None
    old_color_scheme = None

    old_theme_package = None
    old_theme = None

    old_syntaxes = {}
    old_color_schemes = {}

    def __init__(self):
        self.pc_settings = sublime.load_settings(pc_settings_filename())
        self.debug = self.pc_settings.get('debug')
        # self.debug = True

    def get_version(self, package):
        """
        Gets the current version of a package

        :param package:
            The name of the package

        :return:
            The string version
        """

        if package_file_exists(package, 'package-metadata.json'):
            metadata_json = read_package_file(package, 'package-metadata.json')
            if metadata_json:
                try:
                    return json.loads(metadata_json).get('version', 'unknown version')
                except (ValueError):
                    pass

        return 'unknown version'

    def disable_packages(self, packages, operation_type='upgrade'):
        """
        Disables one or more packages before installing or upgrading to prevent
        errors where Sublime Text tries to read files that no longer exist, or
        read a half-written file.

        :param packages:
            The string package name, or an array of strings

        :param operation_type:
            The type of operation that caused the package to be disabled:
             - "upgrade"
             - "remove"
             - "install"
             - "disable"
             - "loader"

        :return:
            A list of package names that were disabled
        """
        if self.debug: console_write(u'Calling disable_packages() with: %s, type: %s', (packages, operation_type))
        _operation_type = ( lambda package_name: operation_type ) if not hasattr( operation_type, "__call__" ) else operation_type

        if not packages:
            console_write( u'No packages to process by reenable_package!' )
            return []

        global events
        try:
            from PackagesManager.package_control import events

        except (ImportError):
            events = None
            console_write( u'Warning: Could not run packages events, if any event was scheduled!' )

        if not isinstance(packages, list):
            packages = [packages]

        in_process = []
        settings = sublime.load_settings(preferences_filename())

        PackageDisabler.old_color_scheme_package = None
        PackageDisabler.old_color_scheme = None

        PackageDisabler.old_theme_package = None
        PackageDisabler.old_theme = None

        for package in packages:
            operation = _operation_type(package)

            if events and operation in ['upgrade', 'remove']:
                version = self.get_version(package)
                tracker_type = 'pre_upgrade' if operation == 'upgrade' else operation
                events.add(tracker_type, package, version)

            global_color_scheme = settings.get('color_scheme')
            if global_color_scheme is not None and global_color_scheme.find('Packages/' + package + '/') != -1:
                PackageDisabler.old_color_scheme_package = package
                PackageDisabler.old_color_scheme = global_color_scheme
                settings.set('color_scheme', 'Packages/Color Scheme - Default/Monokai.tmTheme')

            for window in sublime.windows():
                for view in window.views():
                    view_settings = view.settings()
                    syntax = view_settings.get('syntax')
                    if syntax is not None and syntax.find('Packages/' + package + '/') != -1:
                        if package not in PackageDisabler.old_syntaxes:
                            PackageDisabler.old_syntaxes[package] = []
                        PackageDisabler.old_syntaxes[package].append([view, syntax])
                        view_settings.set('syntax', 'Packages/Text/Plain text.tmLanguage')
                    # Handle view-specific color_scheme settings not already taken care
                    # of by resetting the global color_scheme above
                    scheme = view_settings.get('color_scheme')
                    if scheme is not None and scheme != global_color_scheme and scheme.find('Packages/' + package + '/') != -1:
                        if package not in PackageDisabler.old_color_schemes:
                            PackageDisabler.old_color_schemes[package] = []
                        PackageDisabler.old_color_schemes[package].append([view, scheme])
                        view_settings.set('color_scheme', 'Packages/Color Scheme - Default/Monokai.tmTheme')

            # Change the theme before disabling the package containing it
            if package_file_exists(package, settings.get('theme')):
                PackageDisabler.old_theme_package = package
                PackageDisabler.old_theme = settings.get('theme')
                settings.set('theme', 'Default.sublime-theme')

            # We don't mark a package as in-process when disabling it, otherwise
            # it automatically gets re-enabled the next time Sublime Text starts
            if operation != 'disable':
                in_process.append( package )

        # Force Sublime Text to understand the package is to be ignored
        self._force_setting( self._force_add, 'in_process_packages', in_process, g_settings.packagesmanager_setting_path() )

        disabled_packages = []
        to_disable = list( packages )

        while len( to_disable ) > 0:
            MAXIMUM_TO_REENABLE = 10
            effectively_added = self._force_setting( self._force_add, 'ignored_packages', to_disable[:MAXIMUM_TO_REENABLE] )
            disabled_packages.extend( effectively_added )
            to_disable = to_disable[MAXIMUM_TO_REENABLE:]

        return disabled_packages

    def reenable_package(self, packages, operation_type='upgrade'):
        """
        Re-enables a package(s) after it has been installed or upgraded

        :param packages:
            The string packages name or a list of packages name

        :param operation_type:
            The type of operation that caused the packages to be re-enabled:
             - "upgrade"
             - "remove"
             - "install"
             - "enable"
             - "loader"
        """
        if self.debug: console_write(u'Calling reenable_package() with: %s, type: %s', (packages, operation_type))
        if isinstance( packages, str ): packages = [packages]
        _operation_type = ( lambda package_name: operation_type ) if not hasattr( operation_type, "__call__" ) else operation_type

        if not packages:
            console_write( u'No packages to process by reenable_package!' )
            return

        global events
        try:
            from PackagesManager.package_control import events

        except (ImportError):
            events = None
            console_write( u'Warning: Could not run packages events, if any event was scheduled!' )

        settings = sublime.load_settings(preferences_filename())
        ignored = load_list_setting(settings, 'ignored_packages')

        if events:
            for package in packages:
                operation = _operation_type( package )

                if package in ignored:

                    if operation in ['install', 'upgrade']:
                        version = self.get_version(package)
                        tracker_type = 'post_upgrade' if operation == 'upgrade' else operation
                        events.add(tracker_type, package, version)
                        events.clear(tracker_type, package, future=True)
                        if operation == 'upgrade':
                            events.clear('pre_upgrade', package)

                    elif operation == 'remove':
                        events.clear('remove', package)

        # Force Sublime Text to understand the package is to be unignored
        to_enable = list( packages )

        while len( to_enable ) > 0:
            MAXIMUM_TO_REENABLE = 10
            self._force_setting( self._force_remove, 'ignored_packages', to_enable[:MAXIMUM_TO_REENABLE] )
            to_enable = to_enable[MAXIMUM_TO_REENABLE:]

        for package in packages:
            operation = _operation_type( package )
            if self.debug: console_write( u'operation: %s, _operation_type: %s', (operation, _operation_type) )

            if package in ignored:
                corruption_notice = u' You may see some graphical corruption until you restart Sublime Text.'

                if operation == 'remove' and PackageDisabler.old_theme_package == package:
                    message = text.format(u'''
                        PackagesManager

                        The package containing your active theme was just removed
                        and the Default theme was enabled in its place.
                    ''')
                    if int(sublime.version()) < 3106:
                        message += corruption_notice
                    sublime.message_dialog(message)

                # By delaying the restore, we give Sublime Text some time to
                # re-enable the package, making errors less likely
                def delayed_settings_restore():
                    syntax_errors = set()
                    color_scheme_errors = set()

                    if PackageDisabler.old_syntaxes is None:
                        PackageDisabler.old_syntaxes = {}
                    if PackageDisabler.old_color_schemes is None:
                        PackageDisabler.old_color_schemes = {}

                    if operation == 'upgrade' and package in PackageDisabler.old_syntaxes:
                        for view_syntax in PackageDisabler.old_syntaxes[package]:
                            view, syntax = view_syntax
                            if resource_exists(syntax):
                                view.settings().set('syntax', syntax)
                            elif syntax not in syntax_errors:
                                console_write(u'The syntax "%s" no longer exists' % syntax)
                                syntax_errors.add(syntax)

                    if self.debug: console_write( "PackageDisabler.old_color_scheme_package: %s, \n"
                            "PackageDisabler.old_theme_package: %s, \n"
                            "PackageDisabler.old_color_schemes: %s, \n"
                            "package: %s",
                            (PackageDisabler.old_color_scheme_package,
                             PackageDisabler.old_theme_package,
                             PackageDisabler.old_color_schemes,
                             package) )

                    if operation == 'upgrade' and PackageDisabler.old_color_scheme_package == package:
                        if resource_exists(PackageDisabler.old_color_scheme):
                            settings.set('color_scheme', PackageDisabler.old_color_scheme)
                        else:
                            color_scheme_errors.add(PackageDisabler.old_color_scheme)
                            sublime.error_message(text.format(
                                u'''
                                PackagesManager

                                The package containing your active color scheme was
                                just upgraded, however the .tmTheme file no longer
                                exists. Sublime Text has been configured use the
                                default color scheme instead.
                                '''
                            ))

                    if operation == 'upgrade' and package in PackageDisabler.old_color_schemes:
                        for view_scheme in PackageDisabler.old_color_schemes[package]:
                            view, scheme = view_scheme
                            if resource_exists(scheme):
                                view.settings().set('color_scheme', scheme)
                            elif scheme not in color_scheme_errors:
                                console_write(u'The color scheme "%s" no longer exists' % scheme)
                                color_scheme_errors.add(scheme)

                    if operation == 'upgrade' and PackageDisabler.old_theme_package == package:
                        if package_file_exists(package, PackageDisabler.old_theme):
                            settings.set('theme', PackageDisabler.old_theme)
                            message = text.format(u'''
                                PackagesManager

                                The package containing your active theme was just
                                upgraded.
                            ''')
                            if int(sublime.version()) < 3106:
                                message += corruption_notice
                            sublime.message_dialog(message)
                        else:
                            sublime.error_message(text.format(
                                u'''
                                PackagesManager

                                The package containing your active theme was just
                                upgraded, however the .sublime-theme file no longer
                                exists. Sublime Text has been configured use the
                                default theme instead.
                                '''
                            ))

                    sublime.save_settings(preferences_filename())

                sublime.set_timeout(delayed_settings_restore, 1000)

        threading.Thread(target=self._delayed_in_progress_removal, args=(packages,)).start()

    def _delayed_in_progress_removal(self, packages):
        sleep_delay = 5 + random.randint( 0, 10 )
        packages = list( packages )
        to_remove = []

        console_write( "After %s seconds sleep, it will finish the packages changes: %s", ( sleep_delay, packages ) )
        time.sleep( sleep_delay )

        settings = sublime.load_settings( preferences_filename() )
        ignored = load_list_setting( settings, 'ignored_packages' )

        for package in packages:

            if package in ignored:
                console_write( "The package %s should not be in your User ignored_packages "
                        "package settings, after %d seconds.", ( package, sleep_delay ) )

            else:
                to_remove.append( package )

        console_write( "After randomly %s seconds delay, finishing the packages changes: %s", ( sleep_delay, to_remove ) )
        self._force_setting( self._force_remove, 'in_process_packages', to_remove, g_settings.packagesmanager_setting_path() )

    def _force_setting(self, callback, *args, **kwargs):
        return callback(*args, **kwargs)

    def _force_add(self, setting_name, packages_to_add, full_setting_path=None):
        """
            Keeps it running continually because something is setting it back. Flush just a few
            items each time. Let the packages be unloaded by Sublime Text while ensuring anyone is
            putting them back in.

            Randomly reverting back the `ignored_packages` setting on batch operations
            https://github.com/SublimeTextIssues/Core/issues/2132
        """
        if not full_setting_path: full_setting_path = g_settings.sublime_setting_path()
        packages_to_add.sort()

        currently_ignored = g_settings.get_list_setting(setting_name, full_setting_path)
        effectively_added = [package_name for package_name in packages_to_add if package_name not in currently_ignored]

        if self.debug: console_write( "_force_rem, full_setting_path:                %s", ( full_setting_path ) )
        if self.debug: console_write( "_force_add, currently add packages:           %s", ( currently_ignored ) )
        if self.debug: console_write( "_force_add, adding the packages:              %s", ( packages_to_add ) )
        if self.debug: console_write( "_force_add, effectively added:                %s", ( effectively_added ) )

        g_settings.unique_list_append( currently_ignored, packages_to_add )
        currently_ignored.sort()

        console_write( "Processing %s add for the packages: %s", ( setting_name, effectively_added ) )
        g_settings.set_list_setting( setting_name, currently_ignored, full_setting_path )

        return effectively_added

    def _force_remove(self, setting_name, packages_to_remove, full_setting_path=None):
        """
            Keeps it running continually because something is setting it back. Flush just a few
            items each time. Let the packages be unloaded by Sublime Text while ensuring anyone is
            putting them back in.

            Randomly reverting back the `ignored_packages` setting on batch operations
            https://github.com/SublimeTextIssues/Core/issues/2132
        """
        if not full_setting_path: full_setting_path = g_settings.sublime_setting_path()
        packages_to_remove.sort()

        currently_ignored = g_settings.get_list_setting(setting_name, full_setting_path)
        effectively_added = [package_name for package_name in packages_to_remove if package_name in currently_ignored]

        if self.debug: console_write( "_force_rem, full_setting_path:                %s", ( full_setting_path ) )
        if self.debug: console_write( "_force_rem, currently add packages:           %s", ( currently_ignored ) )
        if self.debug: console_write( "_force_rem, removing the packages:            %s", ( packages_to_remove ) )
        if self.debug: console_write( "_force_rem, effectively added:                %s", ( effectively_added ) )

        currently_ignored.sort()
        currently_ignored = [package_name for package_name in currently_ignored if package_name not in packages_to_remove]

        console_write( "Processing remove %s for the packages: %s", ( setting_name, effectively_added ) )
        g_settings.set_list_setting( setting_name, currently_ignored, full_setting_path )

        return effectively_added

def resource_exists(path):
    """
    Checks to see if a file exists

    :param path:
        A unicode string of a resource path, e.g. Packages/Package Name/resource_name.ext

    :return:
        A bool if it exists
    """

    if not path.startswith('Packages/'):
        return False

    parts = path[9:].split('/', 1)
    if len(parts) != 2:
        return False

    package_name, relative_path = parts
    return package_file_exists(package_name, relative_path)
