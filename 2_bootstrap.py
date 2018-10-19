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

g_package_control_name = "Package Control"
g_packagesmanager_name = "PackagesManager"
g_package_control_loader_name = "0_package_control_loader"
g_packagesmanager_loader_name = "0_packagesmanager_loader"

g_is_running = False
IGNORE_PACKAGE_MINIMUM_WAIT_TIME = 1.7


# Clean up the installed and pristine packages for PackagesManager 2 to
# prevent a downgrade from happening via Sublime Text
if sys.version_info < (3,):
    sublime_dir = os.path.dirname(sublime.packages_path())
    pristine_dir = os.path.join(sublime_dir, 'Pristine Packages')
    installed_dir = os.path.join(sublime_dir, 'Installed Packages')
    pristine_file = os.path.join(pristine_dir, '%s.sublime-package' % g_packagesmanager_name)
    installed_file = os.path.join(installed_dir, '%s.sublime-package' % g_packagesmanager_name)
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


def _background_bootstrap(settings):
    """
    Runs the bootstrap process in a thread since it may need to block to update
    the PackagesManager loader

    :param settings:
        A dict of settings
    """

    base_loader_code = """
        import sys
        import time
        import stat

        import sublime
        import sublime_plugin

        import os
        from os.path import dirname

        # This file adds the package_control subdirectory of {g_packagesmanager_name}
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
            pc_package_path = os.path.join(installed_packages_dir, u'{g_packagesmanager_name}.sublime-package')
            if os.path.exists(encode(pc_package_path)):
                found = True

        if not found:
            packages_dir = os.path.join(st_dir, u'Packages')
            pc_package_path = os.path.join(packages_dir, u'{g_packagesmanager_name}')
            if os.path.exists(encode(pc_package_path)):
                found = True

        # Handle the development environment
        if not found and sys.version_info >= (3,):
            import Default.sort
            if os.path.basename(Default.sort.__file__) == 'sort.py':
                packages_dir = dirname(dirname(Default.sort.__file__))
                pc_package_path = os.path.join(packages_dir, u'{g_packagesmanager_name}')
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
            print( u'{g_packagesmanager_name}: Error finding main directory from loader' )
    """.format( g_packagesmanager_name=g_packagesmanager_name )

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
                {g_packagesmanager_name}

                {g_packagesmanager_name} just installed or upgraded the missing Python
                _ssl module for Linux since Sublime Text does not include it.

                Please restart Sublime Text to make SSL available to all
                packages.
                '''.format(g_packagesmanager_name=g_packagesmanager_name)
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
                {g_packagesmanager_name}

                {g_packagesmanager_name} just upgraded the Python _ssl module for ST2 on
                Windows because the bundled one does not include support for
                modern SSL certificates.

                Please restart Sublime Text to complete the upgrade.
                '''.format( g_packagesmanager_name=g_packagesmanager_name )
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
    g_main_directory = g_settings.load_constants( PACKAGE_ROOT_DIRECTORY )

    global g_package_control_directory
    g_package_control_directory = os.path.join( g_main_directory,
            "Packages", g_package_control_name )

    global g_package_control_package
    g_package_control_package = os.path.join( g_main_directory,
            "Installed Packages", "%s.sublime-package" % g_package_control_name )

    global g_package_control_loader_file
    g_package_control_loader_file = os.path.join( g_main_directory,
            "Installed Packages", "%s.sublime-package" % g_package_control_loader_name )

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
    # print( " g_package_control_setting_file: " + str( g_settings.g_package_control_setting_file ) )

    if is_package_control_installed():
        thread = uninstall_package_control()
        if thread: thread.join()

    g_settings.clean_up_sublime_settings()


def _remove_package_control_from_installed_packages_setting(setting_file):
    settings = g_settings.load_data_file( setting_file )

    if 'installed_packages' in settings \
            and g_package_control_name in settings['installed_packages']:

        settings['installed_packages'].remove(g_package_control_name)
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
    packages_to_ignore = [g_package_control_name, g_package_control_loader_name]

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

        package_manager.remove_package( g_package_control_name, False )
        package_manager.remove_package( g_package_control_loader_name, False )

        safe_remove( g_package_control_package )
        safe_remove( g_package_control_loader_file )
        safe_remove( g_package_control_loader_file + "-new" )

        _remove_package_control_from_installed_packages_setting(g_settings.g_packagesmanager_setting_file)
        _remove_package_control_from_installed_packages_setting(g_settings.g_package_control_setting_file)

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

    def _clean_package_control_settings():
        flush_settings = False
        package_control_settings = g_settings.load_data_file( g_settings.g_package_control_setting_file )

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
            write_settings(g_settings.g_package_control_setting_file, package_control_settings)

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
        package_control_settings = g_settings.load_data_file( g_settings.g_package_control_setting_file )
        packagesmanager_settings = g_settings.load_data_file( g_settings.g_packagesmanager_setting_file )
        sublime_settings = g_settings.load_data_file( g_settings.g_sublime_setting_file )

        def remove_name(name_to, setting_name, settings):
            # Assure Package Control name is not copied
            while setting_name in settings and \
                    name_to in settings[setting_name]:
                settings[setting_name].remove( name_to )

        # Assure any lost package on `in_process_packages` is added
        flush_settings |= copy_list_setting( 'in_process_packages', package_control_settings, packagesmanager_settings, 'installed_packages')
        flush_settings |= copy_list_setting( 'in_process_packages', packagesmanager_settings, packagesmanager_settings, 'installed_packages')
        flush_settings |= copy_list_setting( 'installed_packages', package_control_settings, packagesmanager_settings)

        remove_name(g_packagesmanager_name, 'ignored_packages', sublime_settings)
        remove_name(g_package_control_loader_name, 'ignored_packages', sublime_settings)

        remove_name(g_package_control_name, 'installed_packages', packagesmanager_settings)
        remove_name(g_package_control_loader_name, 'installed_packages', packagesmanager_settings)

        remove_name(g_package_control_name, 'in_process_packages', packagesmanager_settings)
        remove_name(g_packagesmanager_name, 'in_process_packages', packagesmanager_settings)
        remove_name(g_package_control_loader_name, 'in_process_packages', packagesmanager_settings)
        remove_name(g_packagesmanager_loader_name, 'in_process_packages', packagesmanager_settings)

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
            write_settings(g_settings.g_package_control_setting_file, package_control_settings)
            write_settings(g_settings.g_packagesmanager_setting_file, packagesmanager_settings)
            write_settings(g_settings.g_sublime_setting_file, sublime_settings)

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


