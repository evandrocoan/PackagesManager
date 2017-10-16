import sys
import threading
import os
from textwrap import dedent

import json
import time
import stat
import sublime

CURRENT_DIRECTORY = os.path.dirname( os.path.realpath( __file__ ) )
CURRENT_FILE      = os.path.basename( CURRENT_DIRECTORY ).rsplit('.', 1)[0]

g_package_control_name = "Package Control"
g_package_control_settings_file = ""

# Clean up the installed and pristine packages for PackagesManager 2 to
# prevent a downgrade from happening via Sublime Text
if sys.version_info < (3,):
    sublime_dir = os.path.dirname(sublime.packages_path())
    pristine_dir = os.path.join(sublime_dir, 'Pristine Packages')
    installed_dir = os.path.join(sublime_dir, 'Installed Packages')
    pristine_file = os.path.join(pristine_dir, 'PackagesManager.sublime-package')
    installed_file = os.path.join(installed_dir, 'PackagesManager.sublime-package')
    if os.path.exists(pristine_file):
        os.remove(pristine_file)
    if os.path.exists(installed_file):
        os.remove(installed_file)

if sys.version_info < (3,):
    from packagesmanager.bootstrap import bootstrap_dependency, mark_bootstrapped
    from packagesmanager.package_manager import PackageManager
    from packagesmanager import loader, text, sys_path
else:
    from .packagesmanager.bootstrap import bootstrap_dependency, mark_bootstrapped
    from .packagesmanager.package_manager import PackageManager
    from .packagesmanager import loader, text, sys_path


def plugin_loaded():
    manager = PackageManager()
    settings = manager.settings.copy()

    threading.Thread(target=_background_bootstrap, args=(settings,)).start()
    configure_package_control_uninstaller()

def configure_package_control_uninstaller():
    global g_package_control_settings_file

    g_package_control_settings_file = os.path.join( get_main_directory( CURRENT_DIRECTORY ),
            "Packages", "User", "%s.sublime-settings" % g_package_control_name )

    clean_package_control_settings()

    settings = sublime.load_settings( "%s.sublime-settings" % g_package_control_name )
    settings.add_on_change( g_package_control_name, uninstall_package_control )


def uninstall_package_control():

    try:
        from PackagesManager.packagesmanager.show_error import silence_error_message_box
        from PackagesManager.packagesmanager.package_manager import PackageManager
        from PackagesManager.packagesmanager.package_disabler import PackageDisabler

    except ImportError:
        return

    print( "[00-packagesmanager.py] Uninstalling %s..." % g_package_control_name )
    silence_error_message_box()

    package_disabler = PackageDisabler()
    package_disabler.disable_packages( [ g_package_control_name ], "remove" )

    time.sleep( 0.7 )

    package_manager = PackageManager()
    package_manager.remove_package( g_package_control_name, False )

    clean_package_control_settings()


def clean_package_control_settings():
    """
        Clean it a few times because Package Control is kinda running and still flushing stuff down
        to its settings file.
    """
    package_control_settings = load_data_file( g_package_control_settings_file )

    if 'remove_orphaned' not in package_control_settings:
        ensure_not_removed_orphaned( package_control_settings )

    elif package_control_settings['remove_orphaned']:
        ensure_not_removed_orphaned( package_control_settings )


def ensure_not_removed_orphaned(package_control_settings):
    print( "[00-packagesmanager.py] Finishing Package Control Uninstallation..." )

    package_control_settings['remove_orphaned'] = False
    write_data_file( g_package_control_settings_file, package_control_settings )


def get_main_directory(current_directory):
    possible_main_directory = os.path.normpath( os.path.dirname( os.path.dirname( current_directory ) ) )

    if sublime:
        sublime_text_packages = os.path.normpath( os.path.dirname( sublime.packages_path() ) )

        if possible_main_directory == sublime_text_packages:
            return possible_main_directory

        else:
            return sublime_text_packages

    return possible_main_directory


def write_data_file(file_path, channel_dictionary):
    print( "[00-packagesmanager.py] Writing to the data file: " + file_path )

    with open(file_path, 'w', encoding='utf-8') as output_file:
        json.dump( channel_dictionary, output_file, indent=4 )


def load_data_file(file_path):
    channel_dictionary = {}

    if os.path.exists( file_path ):

        try:
            with open( file_path, 'r', encoding='utf-8' ) as studio_channel_data:
                channel_dictionary = json.load( studio_channel_data )

        except ValueError as error:
            print( "[00-packagesmanager.py] Error on load_data_file(1), the file '%s', %s" % ( file_path, error ) )

    else:
        print( "[00-packagesmanager.py] Error on load_data_file(1), the file '%s' does not exists!" % file_path )

    return channel_dictionary


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

        import os
        from os.path import dirname


        # This file adds the packagesmanager subdirectory of PackagesManager
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
            pc_package_path = os.path.join(installed_packages_dir, u'PackagesManager.sublime-package')
            if os.path.exists(encode(pc_package_path)):
                found = True

        if not found:
            packages_dir = os.path.join(st_dir, u'Packages')
            pc_package_path = os.path.join(packages_dir, u'PackagesManager')
            if os.path.exists(encode(pc_package_path)):
                found = True

        # Handle the development environment
        if not found and sys.version_info >= (3,):
            import Default.sort
            if os.path.basename(Default.sort.__file__) == 'sort.py':
                packages_dir = dirname(dirname(Default.sort.__file__))
                pc_package_path = os.path.join(packages_dir, u'PackagesManager')
                if os.path.exists(encode(pc_package_path)):
                    found = True

        if found:
            if os.name == 'nt':
                from ctypes import windll, create_unicode_buffer
                buf = create_unicode_buffer(512)
                if windll.kernel32.GetShortPathNameW(pc_package_path, buf, len(buf)):
                    pc_package_path = buf.value

            sys.path.insert(0, encode(pc_package_path))
            import packagesmanager
            # We remove the import path right away so as not to screw up
            # Sublime Text and its import machinery
            sys.path.remove(encode(pc_package_path))

        else:
            print( u'PackagesManager: Error finding main directory from loader' )


        def plugin_loaded():
            CURRENT_DIRECTORY = os.path.dirname( os.path.realpath( __file__ ) )
            CURRENT_FILE      = os.path.basename( CURRENT_DIRECTORY ).rsplit('.', 1)[0]

            if found:
                remove_the_evel( CURRENT_DIRECTORY, "0_package_control_loader" )

            else:
                remove_the_evel( CURRENT_DIRECTORY, CURRENT_FILE )

            uninstall_package_control()


        def remove_the_evel(CURRENT_DIRECTORY, CURRENT_FILE):
            _packagesmanager_loader_path = os.path.join( os.path.dirname( CURRENT_DIRECTORY ), CURRENT_FILE + ".sublime-package" )

            if os.path.exists( _packagesmanager_loader_path ):
                print( "[00-packagesmanager.py] CURRENT_FILE:       " + CURRENT_FILE )
                print( "[00-packagesmanager.py] CURRENT_DIRECTORY:  " + CURRENT_DIRECTORY )
                print( "[00-packagesmanager.py] get_main_directory: " + get_main_directory( CURRENT_DIRECTORY ) )
                print( "[00-packagesmanager.py] Removing loader:    " + _packagesmanager_loader_path )

                try:
                    from package_control.package_disabler import PackageDisabler

                except ImportError:
                    from PackagesManager.packagesmanager.package_disabler import PackageDisabler

                package_disabler = PackageDisabler()

                package_disabler.disable_packages( [CURRENT_FILE], "remove" )
                time.sleep( 0.7 )

                safe_remove( _packagesmanager_loader_path )


        def uninstall_package_control():
            package_control_name = "Package Control"

            try:
                from PackagesManager.packagesmanager.show_error import silence_error_message_box
                from PackagesManager.packagesmanager.package_manager import PackageManager
                from PackagesManager.packagesmanager.package_disabler import PackageDisabler

            except ImportError:
                return

            package_manager    = PackageManager()
            installed_packages = package_manager.list_packages()

            if package_control_name in installed_packages:
                print( "[00-packagesmanager.py] Uninstalling %s..." % package_control_name )
                silence_error_message_box()

                package_disabler = PackageDisabler()
                package_disabler.disable_packages( [ package_control_name ], "remove" )

                time.sleep( 0.7 )
                package_manager.remove_package( package_control_name, False )


        def safe_remove(path):

            try:
                _delete_read_only_file(path)

            except Exception as error:
                print( "[00-packagesmanager.py] Failed to remove `%s`. Error is: %s" % ( path, error) )


        def _delete_read_only_file(path):
            delete_read_only_file( None, path, None )


        def delete_read_only_file(action, name, exc):
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
    """
    base_loader_code = dedent(base_loader_code).lstrip()
    loader.add_or_update('00', 'packagesmanager', base_loader_code)

    # SSL support fo Linux
    if sublime.platform() == 'linux' and int(sublime.version()) < 3109:
        linux_ssl_url = u'http://packagecontrol.io/ssl/1.0.2/ssl-linux.sublime-package'
        linux_ssl_hash = u'23f35f64458a0a14c99b1bb1bbc3cb04794c7361c4940e0a638d40f038acd377'
        linux_ssl_priority = u'01'
        linux_ssl_version = '1.0.2'

        def linux_ssl_show_restart():
            sublime.message_dialog(text.format(
                u'''
                PackagesManager

                PackagesManager just installed or upgraded the missing Python
                _ssl module for Linux since Sublime Text does not include it.

                Please restart Sublime Text to make SSL available to all
                packages.
                '''
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
                PackagesManager

                PackagesManager just upgraded the Python _ssl module for ST2 on
                Windows because the bundled one does not include support for
                modern SSL certificates.

                Please restart Sublime Text to complete the upgrade.
                '''
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
