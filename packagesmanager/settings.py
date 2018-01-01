import sublime

try:
    str_cls = unicode
except (NameError):
    str_cls = str

# Globally used to count how many dependencies are found installed
g_dependencies_installed = 0


def increment_dependencies_installed():
    global g_dependencies_installed
    g_dependencies_installed += 1


def get_dependencies_installed():
    return g_dependencies_installed


# The `PackagesManager.sublime-settings` loaded by `sublime.load_settings`
g_packagesmanger_settings = None
g_packagesmanger_name = ""


def set_sublime_settings(settings):
    global g_packagesmanger_settings
    g_packagesmanger_settings = settings


def add_packagesmanager_on_change(key_name, callback):
    global g_packagesmanger_name
    g_packagesmanger_name = key_name

    g_packagesmanger_settings.add_on_change( key_name, callback )


def disable_package_control_uninstaller():
    """
        This is required to be called when uninstalling PackagesManager, otherwise we could never
        install Package Control just before uninstalling PackagesManager.
    """
    g_packagesmanger_settings.clear_on_change( g_packagesmanger_name )


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