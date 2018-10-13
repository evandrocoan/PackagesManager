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
dummy_record_setting   = "not_your_business"

g_package_control_name = "Package Control"
g_packagesmanager_name = "PackagesManager"
g_packages_loader_name = "0_package_control_loader"
g_sublime_setting_name = "Preferences"

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
    from package_control.settings import add_package_control_on_change, disable_package_control_uninstaller
    from package_control.bootstrap import bootstrap_dependency, mark_bootstrapped
    from package_control.package_manager import PackageManager
    from package_control import loader, text, sys_path

else:
    from .package_control.settings import add_package_control_on_change, disable_package_control_uninstaller
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
    disable_package_control_uninstaller()


def plugin_loaded():
    global g_main_directory
    g_main_directory = get_main_directory( PACKAGE_ROOT_DIRECTORY )

    global g_sublime_setting_file
    global g_package_control_directory

    global g_package_control_package
    global g_package_control_loader_file
    global g_package_control_setting_file
    global g_packagesmanager_setting_file

    manager  = PackageManager()
    settings = manager.settings.copy()

    g_package_control_directory = os.path.join( g_main_directory,
            "Packages", g_package_control_name )

    g_sublime_setting_file = os.path.join( g_main_directory,
            "Packages", "User", "%s.sublime-settings" % g_sublime_setting_name )

    g_package_control_setting_file = os.path.join( g_main_directory,
            "Packages", "User", "%s.sublime-settings" % g_package_control_name )

    g_packagesmanager_setting_file = os.path.join( g_main_directory,
            "Packages", "User", "%s.sublime-settings" % g_packagesmanager_name )

    g_package_control_package = os.path.join( g_main_directory,
            "Installed Packages", "%s.sublime-package" % g_package_control_name )

    g_package_control_loader_file = os.path.join( g_main_directory,
            "Installed Packages", "%s.sublime-package" % g_packages_loader_name )

    global g_settings_names
    global g_settings_files

    g_settings_names = [g_package_control_name, g_packagesmanager_name, g_sublime_setting_name]
    g_settings_files = [g_package_control_setting_file, g_packagesmanager_setting_file, g_sublime_setting_file]

    threading.Thread(target=_background_bootstrap, args=(settings,)).start()
    threading.Thread(target=configure_package_control_uninstaller).start()


def configure_package_control_uninstaller():
    clean_package_control_settings()
    add_package_control_on_change( uninstall_package_control )

    # print( " is_package_control_installed()  " + str( is_package_control_installed() ) )
    # print( " g_package_control_package:      " + str( g_package_control_package ) )
    # print( " g_package_control_directory:    " + str( g_package_control_directory ) )
    # print( " g_package_control_loader_file:  " + str( g_package_control_loader_file ) )
    # print( " g_package_control_setting_file: " + str( g_package_control_setting_file ) )

    if is_package_control_installed():
        uninstall_package_control()

    clean_up_sublime_settings()


def clean_up_sublime_settings():
    """
        Removes the dummy setting added by setup_sublime_settings().
    """

    for setting_file in g_settings_files:

        for index in range( 0, 3 ):
            sublime_setting = load_data_file( setting_file )

            if dummy_record_setting in sublime_setting:
                del sublime_setting[dummy_record_setting]

                sublime_setting = sort_dictionary( sublime_setting )
                write_data_file( setting_file, sublime_setting )

                time.sleep( 0.1 )


def _remove_package_control_from_installed_packages_setting(setting_file_name):
    setting_file = os.path.join( g_main_directory,
            "Packages", "User", "%s.sublime-settings" % setting_file_name )

    settings = load_data_file( setting_file )

    if 'installed_packages' in settings \
            and g_package_control_name in settings['installed_packages']:

        settings['installed_packages'].remove(g_package_control_name)
        settings = sort_dictionary( settings )

        write_data_file( setting_file, settings )


def uninstall_package_control():

    if not is_package_control_installed():
        print( "[2_bootstrap.py] uninstall_package_control, is_package_control_installed: False" )
        return

    try:
        from PackagesManager.package_control.show_error import silence_error_message_box
        from PackagesManager.package_control.package_manager import PackageManager
        from PackagesManager.package_control.package_disabler import PackageDisabler

    except ImportError as error:
        print( "[2_bootstrap.py] uninstall_package_control, ImportError: %s" % error )
        return

    if not is_allowed_to_run():
        print( "[2_bootstrap.py] uninstall_package_control, is_allowed_to_run: False" )
        return

    print( "[2_bootstrap.py] uninstall_package_control, Running uninstall_package_control..." )

    package_disabler   = PackageDisabler()
    packages_to_ignore = [g_package_control_name, g_packages_loader_name]

    def _uninstall_package_control():
        silence_error_message_box( 63.0 )
        disable_package_control_uninstaller()

        # Keeps it running continually because something is setting it back, enabling Package Control again
        setup_packages_ignored_list( package_disabler, packages_to_ignore )

        # Wait some time until `Package Control` finally get ignored
        for interval in range( 0, 10 ):
            safe_remove( g_package_control_package )
            safe_remove( g_package_control_loader_file )
            safe_remove( g_package_control_loader_file + "-new" )
            time.sleep( 0.1 )

        time.sleep( IGNORE_PACKAGE_MINIMUM_WAIT_TIME )
        package_manager = PackageManager()

        package_manager.remove_package( g_package_control_name, False )
        package_manager.remove_package( g_packages_loader_name, False )

        safe_remove( g_package_control_package )
        safe_remove( g_package_control_loader_file )
        safe_remove( g_package_control_loader_file + "-new" )

        _remove_package_control_from_installed_packages_setting(g_packagesmanager_name)
        _remove_package_control_from_installed_packages_setting(g_package_control_name)

    try:
        _uninstall_package_control()

    except:
        setup_all_settings()
        _uninstall_package_control()

    finally:
        setup_packages_ignored_list( package_disabler, packages_to_remove=packages_to_ignore )

        add_package_control_on_change( uninstall_package_control )
        clean_package_control_settings()

        global g_is_running
        g_is_running = False


def clean_package_control_settings(is_already_called=False):
    """
        Clean it a few times because Package Control is kinda running and still flushing stuff down
        to its settings file.
    """

    def _clean_package_control_settings():
        flush_settings = False
        package_control_settings = load_data_file( g_package_control_setting_file )

        if 'bootstrapped' not in package_control_settings:
            flush_settings = ensure_not_removed_bootstrapped( package_control_settings )

        elif package_control_settings['bootstrapped']:
            flush_settings = ensure_not_removed_bootstrapped( package_control_settings )

        if 'remove_orphaned' not in package_control_settings:
            flush_settings = ensure_not_removed_orphaned( package_control_settings )

        elif package_control_settings['remove_orphaned']:
            flush_settings = ensure_not_removed_orphaned( package_control_settings )

        # Avoid infinity loop of writing to the settings file
        if flush_settings:
            package_control_settings = sort_dictionary( package_control_settings )
            write_data_file( g_package_control_setting_file, package_control_settings )

    try:
        _clean_package_control_settings()

    except:
        setup_all_settings()
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


def setup_packages_ignored_list(package_disabler, packages_to_add=[], packages_to_remove=[]):
    """
        Flush just a few items each time. Let the packages be unloaded by Sublime Text while
        ensuring anyone is putting them back in.

        Randomly reverting back the `ignored_packages` setting on batch operations
        https://github.com/SublimeTextIssues/Core/issues/2132
    """
    currently_ignored = get_ignored_packages()

    packages_to_add.sort()
    packages_to_remove.sort()

    print( "[2_bootstrap.py] setup_packages_ignored_list, currently ignored packages: " + str( currently_ignored ) )
    print( "[2_bootstrap.py] setup_packages_ignored_list, ignoring the packages:      " + str( packages_to_add ) )
    print( "[2_bootstrap.py] setup_packages_ignored_list, unignoring the packages:    " + str( packages_to_remove ) )

    currently_ignored = [package_name for package_name in currently_ignored if package_name not in packages_to_remove]
    unique_list_append( currently_ignored, packages_to_add )

    currently_ignored.sort()
    ignoring_type = "remove"

    # This adds them to the `in_process` list on the Package Control.sublime-settings file
    if len( packages_to_add ):
        package_disabler.disable_packages( packages_to_add, ignoring_type )
        time.sleep( 0.1 )

    # This should remove them from the `in_process` list on the Package Control.sublime-settings file
    if len( packages_to_remove ):
        package_disabler.reenable_package( packages_to_remove, ignoring_type )
        time.sleep( 0.1 )

    # Something, somewhere is setting the ignored_packages list back to `["Vintage"]`. Then
    # ensure we override this.
    for interval in range( 0, 30 ):
        set_ignored_packages( currently_ignored )
        time.sleep( 0.1 )

        if len( packages_to_add ):

            if not is_package_control_installed():
                break

        if len( packages_to_remove ):
            new_ignored_list = get_ignored_packages()
            print( "[2_bootstrap.py] packages_to_remove, currently ignored packages: " + str( new_ignored_list ) )

            if new_ignored_list:

                if len( new_ignored_list ) == len( currently_ignored ) \
                        and new_ignored_list == currently_ignored:

                    break


def setup_all_settings():

    for setting_name in g_settings_names:
        setup_sublime_settings( setting_name + ".sublime-settings" )


def setup_sublime_settings(setting_file_name):
    """
        Removes trailing commas and comments from the settings file, allowing it to be loaded by
        json parser.
    """

    for index in range( 0, 10 ):
        sublime_setting = sublime.load_settings( setting_file_name )
        sublime_setting.set( dummy_record_setting, index )

        sublime.save_settings( setting_file_name )
        time.sleep( 0.1 )


def is_package_control_installed():
    return os.path.exists( g_package_control_loader_file ) \
            or os.path.exists( g_package_control_package ) \
            or os.path.exists( g_package_control_directory )


def sort_dictionary(dictionary):
    return OrderedDict( sorted( dictionary.items() ) )


def get_ignored_packages():
    sublime_setting = load_data_file( g_sublime_setting_file )
    return sublime_setting.get( "ignored_packages", [] )


def set_ignored_packages(ignored_packages):

    if ignored_packages:
        ignored_packages.sort()

    sublime_setting = load_data_file( g_sublime_setting_file )
    sublime_setting["ignored_packages"] = ignored_packages

    sublime_setting = sort_dictionary( sublime_setting )
    write_data_file( g_sublime_setting_file, sublime_setting )


def is_allowed_to_run():
    global g_is_running

    if g_is_running:
        print( "[2_bootstrap.py] You are already running a command. Wait until it finishes or restart Sublime Text" )
        return False

    g_is_running = True
    return True


def unique_list_append(a_list, *lists):

    for _list in lists:

        for item in _list:

            if item not in a_list:
                a_list.append( item )


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


def get_main_directory(current_directory):
    possible_main_directory = os.path.normpath( os.path.dirname( os.path.dirname( current_directory ) ) )

    if sublime:
        sublime_text_packages = os.path.normpath( os.path.dirname( sublime.packages_path() ) )

        if possible_main_directory == sublime_text_packages:
            return possible_main_directory

        else:
            return sublime_text_packages

    return possible_main_directory


def write_data_file(file_path, dictionary_data):
    # print( "[2_bootstrap.py] Writing to the data file: " + file_path )

    with open( file_path, 'w', newline='\n', encoding='utf-8' ) as output_file:
        json.dump( dictionary_data, output_file, indent='\t', separators=(',', ': ') )


def load_data_file(file_path, wait_on_error=True):
    """
        Attempt to read the file some times when there is a value error. This could happen when the
        file is currently being written by Sublime Text.
    """
    dictionary_data = {}

    if os.path.exists( file_path ):
        error = None
        maximum_attempts = 3

        while maximum_attempts > 0:

            try:
                with open( file_path, 'r', encoding='utf-8' ) as studio_channel_data:
                    return json.load( studio_channel_data, object_pairs_hook=OrderedDict )

            except ValueError as error:
                print( "[2_bootstrap.py] Error, maximum_attempts %d, load_data_file: %s" % ( maximum_attempts, error ) )
                maximum_attempts -= 1

                if wait_on_error:
                    time.sleep( 0.1 )

        if maximum_attempts < 1:
            raise ValueError( "file_path: %s, error: %s" % ( file_path, error ) )

    else:
        print( "[2_bootstrap.py] Error on load_data_file(1), the file '%s' does not exists!" % file_path )

    return dictionary_data

