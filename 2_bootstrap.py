import sys
import threading
import os
from textwrap import dedent
from collections import OrderedDict

import json
import time
import stat

import sublime
import sublime_plugin

PACKAGE_ROOT_DIRECTORY = os.path.dirname( os.path.realpath( __file__ ) )
CURRENT_PACKAGE_NAME   = os.path.basename( PACKAGE_ROOT_DIRECTORY ).rsplit('.', 1)[0]

PACKAGE_CONTROL_NAME = "Package Control"
PACKAGESMANAGER_NAME = "PackagesManager"
PACKAGE_CONTROL_LOADER_NAME = "0_package_control_loader"
PACKAGESMANAGER_LOADER_NAME = "0_packagesmanager_loader"

g_is_running = False
IGNORE_PACKAGE_MINIMUM_WAIT_TIME = 1.7


# Clean up the installed and pristine packages for PackagesManager 2 to
# prevent a downgrade from happening via Sublime Text
if sys.version_info < (3,):
    sublime_dir = os.path.dirname(sublime.packages_path())
    pristine_dir = os.path.join(sublime_dir, 'Pristine Packages')
    installed_dir = os.path.join(sublime_dir, 'Installed Packages')
    pristine_file = os.path.join(pristine_dir, '%s.sublime-package' % PACKAGESMANAGER_NAME)
    installed_file = os.path.join(installed_dir, '%s.sublime-package' % PACKAGESMANAGER_NAME)
    if os.path.exists(pristine_file):
        os.remove(pristine_file)
    if os.path.exists(installed_file):
        os.remove(installed_file)

if sys.version_info < (3,):
    from package_control import settings as g_settings
    from package_control.bootstrap import bootstrap_dependency, mark_bootstrapped
    from package_control.package_manager import PackageManager
    from package_control import loader, text, sys_path

else:
    from .package_control import settings as g_settings
    from .package_control.bootstrap import bootstrap_dependency, mark_bootstrapped
    from .package_control.package_manager import PackageManager
    from .package_control import loader, text, sys_path


def compare_text_with_file(input_text, file):
    """
        Return `True` when the provided text and the `file` contents are equal.
    """

    if os.path.exists( file ):

        with open( file, "r", encoding='utf-8' ) as file:
            text = file.read()
            return input_text == text


def _background_bootstrap(settings):
    """
    Runs the bootstrap process in a thread since it may need to block to update
    the PackagesManager loader

    :param settings:
        A dict of settings
    """

    reenable_package_code = r"""
        #!/usr/bin/env python3
        # -*- coding: UTF-8 -*-

        ####################### Licensing #######################################################
        #
        # PackagesManager, Re-enabler Utility
        # Copyright (C) 2018 Evandro Coan <https://github.com/evandrocoan>
        #
        #  Redistributions of source code must retain the above
        #  copyright notice, this list of conditions and the
        #  following disclaimer.
        #
        #  Redistributions in binary form must reproduce the above
        #  copyright notice, this list of conditions and the following
        #  disclaimer in the documentation and/or other materials
        #  provided with the distribution.
        #
        #  Neither the name Evandro Coan nor the names of any
        #  contributors may be used to endorse or promote products
        #  derived from this software without specific prior written
        #  permission.
        #
        #  This program is free software; you can redistribute it and/or modify it
        #  under the terms of the GNU General Public License as published by the
        #  Free Software Foundation; either version 3 of the License, or ( at
        #  your option ) any later version.
        #
        #  This program is distributed in the hope that it will be useful, but
        #  WITHOUT ANY WARRANTY; without even the implied warranty of
        #  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
        #  General Public License for more details.
        #
        #  You should have received a copy of the GNU General Public License
        #  along with this program.  If not, see <http://www.gnu.org/licenses/>.
        #
        #########################################################################################
        #

        '''
        Reenable PackagesManager, if it was disabled during its own update and get lost.

        This has no effect if the user disabled PackagesManager by himself because this program only takes
        effect when PackagesManager is disabled and is inserted on the PackagesManager `in_process_packages`
        setting. And the setting `in_process_packages` is only set by PackagesManager, when its starts
        updating some package.

        See the issue:
        1. https://github.com/wbond/package_control/issues/1164
           Create a dummy package that can re-enable Package Control if ST was restarted during a Package Control update
        '''

        import sublime

        import os
        import random
        import time
        import threading

        SUBLIME_SETTING_NAME = "Preferences"
        PACKAGESMANAGER_NAME = "{manager}"

        PACKAGE_ROOT_DIRECTORY = os.path.dirname( os.path.realpath( __file__ ) )


        def main_directory():
            return get_main_directory( PACKAGE_ROOT_DIRECTORY )


        def get_main_directory(current_directory):
            possible_main_directory = os.path.normpath( os.path.dirname( os.path.dirname( current_directory ) ) )

            if sublime:
                sublime_text_packages = os.path.normpath( os.path.dirname( sublime.packages_path() ) )

                if possible_main_directory == sublime_text_packages:
                    return possible_main_directory

                else:
                    return sublime_text_packages

            return possible_main_directory


        def sublime_setting_path():
            return os.path.join( main_directory(), "Packages", "User", "%s.sublime-settings" % SUBLIME_SETTING_NAME )


        def packagesmanager_setting_path():
            return os.path.join( main_directory(), "Packages", "User", "%s.sublime-settings" % PACKAGESMANAGER_NAME )


        def sublime_setting_file():
            return '%s.sublime-settings' % SUBLIME_SETTING_NAME


        def packagesmanager_setting_file():
            return '%s.sublime-settings' % PACKAGESMANAGER_NAME


        def plugin_loaded():
            threading.Thread( target=_delayed_in_progress_removal, args=(PACKAGESMANAGER_NAME,) ).start()


        def _delayed_in_progress_removal(package_name):
            sleep_delay = 60 + random.randint( 0, 60 )
            time.sleep( sleep_delay )

            packages_setting = sublime.load_settings( packagesmanager_setting_file() )
            in_process_count = packages_setting.get( 'in_process_packages_count', 0 )
            in_process_packages = packages_setting.get( 'in_process_packages', [] )

            # print("in_process_count:", in_process_count, ", in_process_packages:", in_process_packages)
            if package_name in in_process_packages:
                sublime_settings = sublime.load_settings( sublime_setting_file() )
                ignored_packages = sublime_settings.get( 'ignored_packages', [] )

                if package_name in ignored_packages:
                    print( "{manager}: The package `%s` should not be in your User `ignored_packages` "
                          "package settings, after %d seconds." % ( package_name, sleep_delay ) )

                    if in_process_count > 3:
                        ignored_packages.remove( package_name )

                        sublime_settings.set( 'ignored_packages', ignored_packages )
                        packages_setting.erase( 'in_process_packages_count' )

                        sublime.save_settings( sublime_setting_file() )
                        sublime.save_settings( packagesmanager_setting_file() )

                    else:
                        packages_setting.set( 'in_process_packages_count', in_process_count + 1 )
                        sublime.save_settings( packagesmanager_setting_file() )

                else:
                    print("{manager}: Finishing the package `%s` changes after randomly %s seconds delay." % ( package_name, sleep_delay ) )
                    in_process_packages.remove( package_name )

                    packages_setting.erase( 'in_process_packages_count' )
                    packages_setting.set( 'in_process_packages', in_process_packages )
                    sublime.save_settings( packagesmanager_setting_file() )
    """.format( manager=PACKAGESMANAGER_NAME )

    packages_directory = os.path.dirname( PACKAGE_ROOT_DIRECTORY )
    reenable_package_code = dedent(reenable_package_code).lstrip()
    reenable_package_file = os.path.join( packages_directory, "zz_packagesmanager_reenabler.py" )

    if not compare_text_with_file(reenable_package_code, reenable_package_file):

        with open( reenable_package_file, 'w', newline='\n', encoding='utf-8' ) as output_file:
            output_file.write( reenable_package_code )

    base_loader_code = r"""
        import sys
        import time
        import stat

        import sublime
        import sublime_plugin

        import os
        from os.path import dirname

        # This file adds the package_control subdirectory of {manager}
        # to first in the sys.path so that all other packages may rely on
        # PC for utility functions, such as event helpers, adding things to
        # sys.path, downloading files from the internet, etc


        if sys.version_info >= (3,):
            def decode(path):
                return path

            def encode(path):
                return path

            loader_dir = dirname(__file__)

        else:
            def decode(path):
                if not isinstance(path, unicode):
                    path = path.decode(sys.getfilesystemencoding())
                return path

            def encode(path):
                if isinstance(path, unicode):
                    path = path.encode(sys.getfilesystemencoding())
                return path

            loader_dir = decode(os.getcwd())


        st_dir = dirname(dirname(loader_dir))

        found = False
        if sys.version_info >= (3,):
            installed_packages_dir = os.path.join(st_dir, u'Installed Packages')
            pc_package_path = os.path.join(installed_packages_dir, u'{manager}.sublime-package')
            if os.path.exists(encode(pc_package_path)):
                found = True

        if not found:
            packages_dir = os.path.join(st_dir, u'Packages')
            pc_package_path = os.path.join(packages_dir, u'{manager}')
            if os.path.exists(encode(pc_package_path)):
                found = True

        # Handle the development environment
        if not found and sys.version_info >= (3,):
            import Default.sort
            if os.path.basename(Default.sort.__file__) == 'sort.py':
                packages_dir = dirname(dirname(Default.sort.__file__))
                pc_package_path = os.path.join(packages_dir, u'{manager}')
                if os.path.exists(encode(pc_package_path)):
                    found = True

        if found:
            if os.name == 'nt':
                from ctypes import windll, create_unicode_buffer
                buf = create_unicode_buffer(512)
                if windll.kernel32.GetShortPathNameW(pc_package_path, buf, len(buf)):
                    pc_package_path = buf.value

            sys.path.insert(0, encode(pc_package_path))
            import package_control
            # We remove the import path right away so as not to screw up
            # Sublime Text and its import machinery
            sys.path.remove(encode(pc_package_path))

        else:
            print( u'{manager}: Error finding main directory from loader' )
    """.format( manager=PACKAGESMANAGER_NAME )

    base_loader_code = dedent(base_loader_code).lstrip()
    loader.add_or_update('00', 'package_control', base_loader_code)

    # SSL support fo Linux
    if sublime.platform() == 'linux' and int(sublime.version()) < 3109:
        linux_ssl_url = u'http://packagecontrol.io/ssl/1.0.2/ssl-linux.sublime-package'
        linux_ssl_hash = u'23f35f64458a0a14c99b1bb1bbc3cb04794c7361c4940e0a638d40f038acd377'
        linux_ssl_priority = u'01'
        linux_ssl_version = '1.0.2'

        def linux_ssl_show_restart():
            sublime.message_dialog(text.format(
                u'''
                {PACKAGESMANAGER_NAME}

                {PACKAGESMANAGER_NAME} just installed or upgraded the missing Python
                _ssl module for Linux since Sublime Text does not include it.

                Please restart Sublime Text to make SSL available to all
                packages.
                '''.format(PACKAGESMANAGER_NAME=PACKAGESMANAGER_NAME)
            ))

        threading.Thread(
            target=bootstrap_dependency,
            args=(
                settings,
                linux_ssl_url,
                linux_ssl_hash,
                linux_ssl_priority,
                linux_ssl_version,
                linux_ssl_show_restart,
            )
        ).start()

    # SSL support for SHA-2 certificates with ST2 on Windows
    elif sublime.platform() == 'windows' and sys.version_info < (3,):
        win_ssl_url = u'http://packagecontrol.io/ssl/1.0.0/ssl-windows.sublime-package'
        win_ssl_hash = u'3c28982eb400039cfffe53d38510556adead39ba7321f2d15a6770d3ebc75030'
        win_ssl_priority = u'01'
        win_ssl_version = u'1.0.0'

        def win_ssl_show_restart():
            sublime.message_dialog(text.format(
                u'''
                {PACKAGESMANAGER_NAME}

                {PACKAGESMANAGER_NAME} just upgraded the Python _ssl module for ST2 on
                Windows because the bundled one does not include support for
                modern SSL certificates.

                Please restart Sublime Text to complete the upgrade.
                '''.format( PACKAGESMANAGER_NAME=PACKAGESMANAGER_NAME )
            ))

        threading.Thread(
            target=bootstrap_dependency,
            args=(
                settings,
                win_ssl_url,
                win_ssl_hash,
                win_ssl_priority,
                win_ssl_version,
                win_ssl_show_restart,
            )
        ).start()

    else:
        sublime.set_timeout(mark_bootstrapped, 10)

# ST2 compat
if sys.version_info < (3,):
    plugin_loaded()


def plugin_unloaded():
    g_settings.disable_package_control_uninstaller()


def plugin_loaded():
    global g_main_directory
    g_main_directory = g_settings.main_directory()

    global g_package_control_directory
    g_package_control_directory = os.path.join( g_main_directory,
            "Packages", PACKAGE_CONTROL_NAME )

    global g_package_control_package
    g_package_control_package = os.path.join( g_main_directory,
            "Installed Packages", "%s.sublime-package" % PACKAGE_CONTROL_NAME )

    global g_package_control_loader_file
    g_package_control_loader_file = os.path.join( g_main_directory,
            "Installed Packages", "%s.sublime-package" % PACKAGE_CONTROL_LOADER_NAME )

    manager  = PackageManager()
    settings = manager.settings.copy()

    threading.Thread(target=_background_bootstrap, args=(settings,)).start()
    threading.Thread(target=configure_package_control_uninstaller).start()


def configure_package_control_uninstaller():
    clean_package_control_settings()
    g_settings.add_package_control_on_change( uninstall_package_control )

    # print( " is_package_control_installed()  " + str( is_package_control_installed() ) )
    # print( " g_package_control_package:      " + str( g_package_control_package ) )
    # print( " g_package_control_directory:    " + str( g_package_control_directory ) )
    # print( " g_package_control_loader_file:  " + str( g_package_control_loader_file ) )
    # print( " package_control_setting_path(): " + str( g_settings.package_control_setting_path() ) )

    if is_package_control_installed():
        thread = uninstall_package_control()
        if thread: thread.join()

    g_settings.clean_up_sublime_settings()


def _remove_package_control_from_installed_packages_setting(setting_file):
    settings = g_settings.load_data_file( setting_file )

    if 'installed_packages' in settings \
            and PACKAGE_CONTROL_NAME in settings['installed_packages']:

        settings['installed_packages'].remove(PACKAGE_CONTROL_NAME)
        settings = g_settings.sort_dictionary( settings )

        g_settings.write_data_file( setting_file, settings )


def uninstall_package_control():

    if not is_package_control_installed():
        print( "[2_bootstrap.py] uninstall_package_control, is_package_control_installed: False" )
        return

    if not is_allowed_to_run():
        print( "[2_bootstrap.py] uninstall_package_control, is_allowed_to_run: False" )
        return

    thread = threading.Thread(target=_uninstall_package_control).start()
    return thread


def _uninstall_package_control():

    try:
        from PackagesManager.package_control.show_error import silence_error_message_box
        from PackagesManager.package_control.package_manager import PackageManager
        from PackagesManager.package_control.package_disabler import PackageDisabler

    except ImportError as error:
        print( "[2_bootstrap.py] uninstall_package_control, ImportError: %s" % error )
        return

    print( "" )
    print( "[2_bootstrap.py] uninstall_package_control, Running uninstall_package_control..." )

    package_disabler   = PackageDisabler()
    packages_to_ignore = [PACKAGE_CONTROL_NAME, PACKAGE_CONTROL_LOADER_NAME]

    def _try_uninstall_package_control():
        silence_error_message_box( 63.0 )
        g_settings.disable_package_control_uninstaller()

        # Keeps it running continually because something is setting it back, enabling Package Control again
        g_settings.setup_packages_ignored_list( package_disabler, packages_to_add=packages_to_ignore )

        # Wait some time until `Package Control` finally get ignored
        for interval in range( 0, 10 ):
            safe_remove( g_package_control_package )
            safe_remove( g_package_control_loader_file )
            safe_remove( g_package_control_loader_file + "-new" )
            time.sleep( 0.1 )

        time.sleep( IGNORE_PACKAGE_MINIMUM_WAIT_TIME )
        package_manager = PackageManager()

        package_manager.remove_package( PACKAGE_CONTROL_NAME, False )
        package_manager.remove_package( PACKAGE_CONTROL_LOADER_NAME, False )

        safe_remove( g_package_control_package )
        safe_remove( g_package_control_loader_file )
        safe_remove( g_package_control_loader_file + "-new" )

        _remove_package_control_from_installed_packages_setting(g_settings.packagesmanager_setting_path())
        _remove_package_control_from_installed_packages_setting(g_settings.package_control_setting_path())

    try:
        _try_uninstall_package_control()

    except:
        g_settings.setup_all_settings()

        _try_uninstall_package_control()
        g_settings.clean_up_sublime_settings()

    finally:
        g_settings.setup_packages_ignored_list( package_disabler, packages_to_remove=packages_to_ignore )
        g_settings.add_package_control_on_change( uninstall_package_control )

        clean_package_control_settings()
        copy_package_control_settings()

        global g_is_running
        g_is_running = False


def clean_package_control_settings():
    """
        Clean it a few times because Package Control is kinda running and still flushing stuff down
        to its settings file.
    """

    if not os.path.exists( g_settings.package_control_setting_path() ):
        return

    def _clean_package_control_settings():
        flush_settings = False
        package_control_settings = g_settings.load_data_file( g_settings.package_control_setting_path() )

        if 'bootstrapped' not in package_control_settings:
            flush_settings |= ensure_not_removed_bootstrapped( package_control_settings )

        elif package_control_settings['bootstrapped']:
            flush_settings |= ensure_not_removed_bootstrapped( package_control_settings )

        if 'remove_orphaned' not in package_control_settings:
            flush_settings |= ensure_not_removed_orphaned( package_control_settings )

        elif package_control_settings['remove_orphaned']:
            flush_settings |= ensure_not_removed_orphaned( package_control_settings )

        # Avoid infinity loop of writing to the settings file, because this is called every time they change
        if flush_settings:
            write_settings(g_settings.package_control_setting_path(), package_control_settings)

    try:
        _clean_package_control_settings()

    except:
        g_settings.setup_all_settings()
        _clean_package_control_settings()


def ensure_not_removed_bootstrapped(package_control_settings):
    """
        Forces the `Package Control.sublime-settings` to be reloaded, so we can uninstall it
        immediately.
    """
    print( "[2_bootstrap.py] ensure_not_removed_bootstrapped, finishing Package Control Uninstallation, setting bootstrapped..." )
    package_control_settings['bootstrapped']  = False
    return True


def ensure_not_removed_orphaned(package_control_settings):
    """
        Save the default user value for `remove_orphaned` on `_remove_orphaned`, so it can be
        restored later.
    """
    print( "[2_bootstrap.py] ensure_not_removed_orphaned, finishing Package Control Uninstallation, setting remove_orphaned..." )
    package_control_settings['remove_orphaned'] = False
    package_control_settings['remove_orphaned_backup'] = True
    return True


def copy_package_control_settings():
    print( "[2_bootstrap.py] Coping Package Control settings to PackagesManager..." )

    def _copy_package_control_settings():
        flush_settings = False
        package_control_settings = g_settings.load_data_file( g_settings.package_control_setting_path() )
        packagesmanager_settings = g_settings.load_data_file( g_settings.packagesmanager_setting_path() )
        sublime_settings = g_settings.load_data_file( g_settings.sublime_setting_path() )

        def remove_name(name_to, setting_name, settings):
            while setting_name in settings and \
                    name_to in settings[setting_name]:
                settings[setting_name].remove( name_to )

        # Assure any lost package on `in_process_packages` is added
        flush_settings |= copy_list_setting( 'in_process_packages', package_control_settings, packagesmanager_settings, 'installed_packages')
        flush_settings |= copy_list_setting( 'installed_packages', package_control_settings, packagesmanager_settings)

        # Assure Package Control name is not copied
        remove_name(PACKAGE_CONTROL_NAME, 'installed_packages', packagesmanager_settings)
        remove_name(PACKAGE_CONTROL_LOADER_NAME, 'installed_packages', packagesmanager_settings)

        remove_name(PACKAGESMANAGER_NAME, 'ignored_packages', sublime_settings)
        remove_name(PACKAGESMANAGER_LOADER_NAME, 'ignored_packages', sublime_settings)

        # Assure Package Control `installed_packages` setting is cleaned out in case the user
        # accidentally install Package Control, then, Package Control will not attempt to install
        # packages which where removed later by PackagesManager. Packages Control will not attempt
        # to uninstall all the packages because its setting `remove_orphaned` packages is set to
        # `false` by clean_package_control_settings().
        flush_settings |= copy_value_setting( 'installed_packages', { 'installed_packages': [] }, package_control_settings)

        flush_settings |= copy_list_setting( 'channels', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_list_setting( 'repositories', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_list_setting( 'install_prereleases', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_list_setting( 'auto_upgrade_ignore', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_list_setting( 'git_binary', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_list_setting( 'hg_binary', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_list_setting( 'dirs_to_ignore', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_list_setting( 'files_to_ignore', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_list_setting( 'files_to_include', package_control_settings, packagesmanager_settings)

        flush_settings |= copy_value_setting( 'debug', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'submit_usage', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'submit_url', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'auto_upgrade', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'install_missing', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'auto_upgrade_frequency', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'timeout', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'cache_length', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'http_proxy', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'https_proxy', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'proxy_username', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'proxy_password', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'http_cache', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'http_cache_length', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'user_agent', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'ignore_vcs_packages', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'git_update_command', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'hg_update_command', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'downloader_precedence', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'package_destination', package_control_settings, packagesmanager_settings)
        flush_settings |= copy_value_setting( 'package_profiles', package_control_settings, packagesmanager_settings)

        # Avoid infinity loop of writing to the settings file, because this is called every time they change
        if flush_settings:
            write_settings(g_settings.package_control_setting_path(), package_control_settings)
            write_settings(g_settings.packagesmanager_setting_path(), packagesmanager_settings)
            write_settings(g_settings.sublime_setting_path(), sublime_settings)

    try:
        _copy_package_control_settings()

    except:
        g_settings.setup_all_settings()
        _copy_package_control_settings()


def write_settings(setting_file, settings):
    settings = g_settings.sort_dictionary( settings )
    g_settings.write_data_file( setting_file, settings )


def copy_list_setting(setting_name, package_control_settings, packagesmanager_settings, alternative=None):
    """
        Makes sure that Package Control and PackagesManager have the same `setting_name`, as
        `installed_packages` to avoid PackagesManager uninstalling all packages after removing
        Package Control.

        @return True, if the settings files need to be flushed/written to the file system.
    """
    flush_settings = False
    alternative = alternative if alternative else setting_name

    if setting_name in package_control_settings:

        if alternative in packagesmanager_settings:
            setting_data = packagesmanager_settings[alternative]
            packagesmanager_set = set(setting_data)

        else:
            packagesmanager_set = set()
            packagesmanager_settings[alternative] = []

        for element in package_control_settings[setting_name]:

            if element not in packagesmanager_set:
                flush_settings = True
                packagesmanager_set.add(element)
                packagesmanager_settings[alternative].append(element)

    return flush_settings


def copy_value_setting(setting_name, source_settings, destine_settings):
    flush_settings = False

    if setting_name in source_settings:

        if setting_name in destine_settings:
            flush_settings = destine_settings[setting_name] != source_settings[setting_name]

        destine_settings[setting_name] = source_settings[setting_name]

    return flush_settings


def is_package_control_installed():
    return os.path.exists( g_package_control_loader_file ) \
            or os.path.exists( g_package_control_package ) \
            or os.path.exists( g_package_control_directory )


def is_allowed_to_run():
    global g_is_running

    if g_is_running:
        print( "[2_bootstrap.py] You are already running a command. Wait until it finishes or restart Sublime Text" )
        return False

    g_is_running = True
    return True


def safe_remove(absolute_path):

    if os.path.exists( absolute_path ):

        try:
            delete_read_only_file( absolute_path )

        except Exception:
            pass


def delete_read_only_file(absolute_path):
    _delete_read_only_file( None, absolute_path, None )


def _delete_read_only_file(action, name, exc):
    os.chmod( name, stat.S_IWRITE )
    os.remove( name )


