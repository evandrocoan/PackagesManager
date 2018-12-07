import sublime

import os
import time
import json

import traceback
import functools

from collections import OrderedDict

try:
    str_cls = unicode
except (NameError):
    str_cls = str

PACKAGE_ROOT_DIRECTORY = os.path.dirname( os.path.dirname( os.path.realpath( __file__ ) ) )
CURRENT_PACKAGE_NAME   = os.path.basename( PACKAGE_ROOT_DIRECTORY ).rsplit('.', 1)[0]

# The minimum time between multiple calls setting the `ignored_packages` setting, without triggering
# the Sublime Text error `It appears a package is trying to ignore itself, causing a loop`
IGNORE_PACKAGE_MINIMUM_WAIT_TIME = 1.7

# Globally used to count how many dependencies are found installed
g_dependencies_installed = 0

PACKAGESMANAGER_NAME = "PackagesManager"
PACKAGE_CONTROL_NAME = "Package Control"

SUBLIME_SETTING_NAME = "Preferences"
DUMMY_RECORD_SETTING = "not_your_business"


def main_directory():
    return get_main_directory( PACKAGE_ROOT_DIRECTORY )


def sublime_setting_path():
    return os.path.join( main_directory(), "Packages", "User", "%s.sublime-settings" % SUBLIME_SETTING_NAME )


def package_control_setting_path():
    return os.path.join( main_directory(), "Packages", "User", "%s.sublime-settings" % PACKAGE_CONTROL_NAME )


def packagesmanager_setting_path():
    return os.path.join( main_directory(), "Packages", "User", "%s.sublime-settings" % PACKAGESMANAGER_NAME )


def settings_names():
    return [PACKAGE_CONTROL_NAME, PACKAGESMANAGER_NAME, SUBLIME_SETTING_NAME]


def settings_paths():
    return [package_control_setting_path(), packagesmanager_setting_path(), sublime_setting_path()]


def increment_dependencies_installed():
    global g_dependencies_installed
    g_dependencies_installed += 1


def get_dependencies_installed():
    return g_dependencies_installed


def get_package_control_sublime_settings():
    return sublime.load_settings( "%s.sublime-settings" % PACKAGE_CONTROL_NAME )


def add_package_control_on_change(callback):
    get_package_control_sublime_settings().add_on_change( PACKAGE_CONTROL_NAME, callback )


def disable_package_control_uninstaller():
    """
        This is required to be called when uninstalling PackagesManager, otherwise we could never
        install Package Control just before uninstalling PackagesManager.
    """
    get_package_control_sublime_settings().clear_on_change( PACKAGE_CONTROL_NAME )


def preferences_filename():
    """
    :return: The appropriate settings filename based on the version of Sublime Text
    """

    if int(sublime.version()) >= 2174:
        return 'Preferences.sublime-settings'
    return 'Global.sublime-settings'


def pc_settings_filename():
    """
    :return: The settings file for PackagesManager
    """

    return 'PackagesManager.sublime-settings'


def load_list_setting(settings, name):
    """
    Sometimes users accidentally change settings that should be lists to
    just individual strings. This helps fix that.

    :param settings:
        A sublime.Settings object

    :param name:
        The name of the setting

    :return:
        The current value of the setting, always a list
    """

    value = settings.get(name)
    if not value:
        return []
    if isinstance(value, str_cls):
        value = [value]
    if not isinstance(value, list):
        return []

    filtered_value = []
    for v in value:
        if not isinstance(v, str_cls):
            continue
        filtered_value.append(v)
    return sorted(filtered_value, key=lambda s: s.lower())


def save_list_setting(settings, filename, name, new_value, old_value=None):
    """
    Updates a list-valued setting

    :param settings:
        The sublime.Settings object

    :param filename:
        The settings filename to save in

    :param name:
        The setting name

    :param new_value:
        The new value for the setting

    :param old_value:
        If not None, then this and the new_value will be compared. If they
        are the same, the settings will not be flushed to disk.
    """

    # Clean up the list to only include unique values, sorted
    new_value = list(set(new_value))
    new_value = sorted(new_value, key=lambda s: s.lower())

    if old_value is not None:
        if old_value == new_value:
            return

    settings.set(name, new_value)
    sublime.save_settings(filename)


def write_data_file(file_path, dictionary_data):

    with open( file_path, 'w', newline='\n', encoding='utf-8' ) as output_file:
        json.dump( dictionary_data, output_file, indent='\t', separators=(',', ': ') )


def load_data_file(file_path, wait_on_error=True):
    """
        Attempt to read the file some times when there is a value error. This could happen when the
        file is currently being written by Sublime Text.
    """
    dictionary_data = {}

    if os.path.exists( file_path ):
        maximum_attempts = 3

        while maximum_attempts > 0:

            try:
                with open( file_path, 'r', encoding='utf-8' ) as studio_channel_data:
                    return json.load( studio_channel_data, object_pairs_hook=OrderedDict )

            except ValueError as error:
                print( "[package_io] Error, maximum_attempts %d, load_data_file: %s, %s" % ( maximum_attempts, file_path, error ) )
                maximum_attempts -= 1

                if wait_on_error:
                    time.sleep( 0.1 )

        if maximum_attempts < 1:
            raise ValueError( "maximum_attempts < 1 on file_path: %s" % file_path )

    else:
        print( "[package_io] Error on load_data_file(1), the file '%s' does not exists! \n%s\n" % (
               file_path, "".join( traceback.format_stack() ) ) )

    return dictionary_data


def setup_packages_ignored_list(package_disabler, packages_to_add=[], packages_to_remove=[]):
    """
        Flush just a few items each time. Let the packages be unloaded by Sublime Text while
        ensuring anyone is putting them back in.

        Randomly reverting back the `ignored_packages` setting on batch operations
        https://github.com/SublimeTextIssues/Core/issues/2132
    """
    ignoring_type = "remove"

    # This adds them to the `in_process` list on the Package Control.sublime-settings file
    if len( packages_to_add ):
        package_disabler.disable_packages( packages_to_add, ignoring_type )
        time.sleep( IGNORE_PACKAGE_MINIMUM_WAIT_TIME )

    # This should remove them from the `in_process` list on the Package Control.sublime-settings file
    if len( packages_to_remove ):

        for package in packages_to_remove:
            package_disabler.reenable_package( package, ignoring_type )
            time.sleep( IGNORE_PACKAGE_MINIMUM_WAIT_TIME )


def get_main_directory(current_directory):
    possible_main_directory = os.path.normpath( os.path.dirname( os.path.dirname( current_directory ) ) )

    if sublime:
        sublime_text_packages = os.path.normpath( os.path.dirname( sublime.packages_path() ) )

        if possible_main_directory == sublime_text_packages:
            return possible_main_directory

        else:
            return sublime_text_packages

    return possible_main_directory


def setup_all_settings(_settings_names=None):
    """
        Converts from Sublime Text settings to valid JSON objects.
    """
    if not _settings_names: _settings_names = settings_names()

    for setting_name in _settings_names:
        setup_sublime_settings( setting_name + ".sublime-settings" )


def setup_sublime_settings(setting_file_name):
    """
        Removes trailing commas and comments from the settings file, allowing it to be loaded by
        json parser.
    """

    for index in range( 0, 3 ):
        sublime_settings = sublime.load_settings( setting_file_name )
        sublime_settings.set( DUMMY_RECORD_SETTING, index )

        sublime.save_settings( setting_file_name )
        time.sleep( IGNORE_PACKAGE_MINIMUM_WAIT_TIME )


def clean_up_sublime_settings(_settings_paths=None, _settings_names=None):
    """
        Removes the dummy setting added by setup_all_settings().
    """

    try:
        _clean_up_sublime_settings(_settings_paths)

    except Exception:
        setup_all_settings( _settings_names )
        _clean_up_sublime_settings( _settings_paths )


def _clean_up_sublime_settings(_settings_paths=None):
    """
        Removes the dummy setting added by setup_all_settings().
    """
    if not _settings_paths: _settings_paths = settings_paths()

    for setting_path in _settings_paths:

        for index in range( 0, 3 ):
            sublime_settings = load_data_file( setting_path )

            if DUMMY_RECORD_SETTING in sublime_settings:
                del sublime_settings[DUMMY_RECORD_SETTING]

                sublime_settings = sort_dictionary( sublime_settings )
                write_data_file( setting_path, sublime_settings )

                time.sleep( IGNORE_PACKAGE_MINIMUM_WAIT_TIME )


def sort_dictionary(dictionary):
    return OrderedDict( sorted( dictionary.items() ) )


def get_list_setting(setting_name, full_setting_path=None):
    if not full_setting_path: full_setting_path = sublime_setting_path()

    setting_base_name = os.path.basename( full_setting_path )
    sublime_settings = sublime.load_settings( setting_base_name )
    sublime_setting_value = sublime_settings.get( setting_name, [] )

    sublime_settings = load_data_file( full_setting_path )
    json_setting_value = sublime_settings.get( setting_name, [] )

    unique_list_append( json_setting_value, sublime_setting_value )
    return json_setting_value


def set_list_setting(setting_name, new_value, full_setting_path=None):
    if not full_setting_path: full_setting_path = sublime_setting_path()
    setting_base_name = os.path.basename( full_setting_path )

    if new_value:
        new_value.sort()

    sublime_settings = sublime.load_settings( setting_base_name )
    sublime_settings.set( setting_name, new_value )
    sublime.save_settings( setting_base_name )


def unique_list_append(a_list, *lists):

    for _list in lists:

        for item in _list:

            if item not in a_list:
                a_list.append( item )

