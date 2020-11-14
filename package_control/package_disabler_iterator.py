
import sublime

import time
import functools

# from .settings import run_on_main_thread
from .package_disabler import PackageDisabler

# How many packages to ignore and unignore in batch to fix the ignored packages bug error
PACKAGES_COUNT_TO_IGNORE_AHEAD = 8

# The minimum time between multiple calls setting the `ignored_packages` setting, without triggering
# the Sublime Text error `It appears a package is trying to ignore itself, causing a loop`
IGNORE_PACKAGE_MINIMUM_WAIT_TIME = 1.7

g_next_packages_to_ignore = []
g_default_ignored_packages = []


def sublime_settings():
    settings_name = "Preferences.sublime-settings"
    return sublime.load_settings( settings_name )


def save_sublime_settings():
    settings_name = "Preferences.sublime-settings"
    sublime.save_settings( settings_name )


def packagesmanager_settings():
    settings_name = "PackagesManager.sublime-settings"
    return sublime.load_settings( settings_name )


def save_packagesmanager_settings():
    settings_name = "PackagesManager.sublime-settings"
    sublime.save_settings( settings_name )


def unique_list_append(a_list, *lists):
    for _list in lists:
        for item in _list:
            if item not in a_list:
                a_list.append( item )


def save_ignored_packages_callback():
    packagesmanager_settings().set( 'next_packages_to_ignore', g_next_packages_to_ignore )
    save_packagesmanager_settings()


def clean_ignored_packages_callback():
    packagesmanager_settings().erase( 'next_packages_to_ignore' )
    save_packagesmanager_settings()


# Disabling a package means changing settings, which can only be done
# in the main thread. We just sleep in this thread for a bit to ensure
# that the packages have been disabled and are ready to be installed.
def run_on_main_thread(callback):
    is_finished = [False]

    def main_thread_call():
        callback()
        is_finished[0] = True

    sublime.set_timeout( main_thread_call, 1 )

    while not is_finished[0]:
        time.sleep( 0.1 )


class IgnoredPackagesBugFixer(object):
    _is_running = False

    def __init__(self, package_list_to_process, ignoring_type="install"):
        assert not IgnoredPackagesBugFixer._is_running, "IgnoredPackagesBugFixer is a Singleton and it is already running! Did you forget to stop it?"
        IgnoredPackagesBugFixer._is_running = True
        self.package_list_to_process = package_list_to_process

        self.package_disabler = PackageDisabler()
        self.uningored_packages_to_flush = 0

        # Value to pass to Package Control PackageDisabler:
        # - "upgrade"
        # - "remove"
        # - "install"
        # - "disable"
        # - "loader"
        self.ignoring_type = ignoring_type

        global g_default_ignored_packages
        global g_next_packages_to_ignore

        g_next_packages_to_ignore = packagesmanager_settings().get( 'next_packages_to_ignore', [] )
        g_default_ignored_packages = self.setup_packages_ignored_list( packages_to_remove=g_next_packages_to_ignore )

    def __iter__(self):
        package_list_to_process = self.package_list_to_process

        for package_name in package_list_to_process:
            self.ignore_next_packages( package_name, package_list_to_process )

            # To here, you can do anything with your package on `package_name` variable, because
            # the functions ignore_next_packages() and accumulative_unignore_user_packages()
            # will take care of everything to ensure they are disabled and reenabled.
            yield package_name
            self.accumulative_unignore_user_packages( package_name )

        # Ensure the list is clean when process finishes
        self.stop()

    def stop(self):
        """
            If the iteration is stopped by a break statement, this must to be called before break.
        """
        self.accumulative_unignore_user_packages( flush_everything=True )

        run_on_main_thread( clean_ignored_packages_callback )
        IgnoredPackagesBugFixer._is_running = False

    def skip_reenable(self, package_name):

        if package_name in g_next_packages_to_ignore:
            g_next_packages_to_ignore.remove( package_name )

        else:
            print( "PackagesManager: The package `%s` is not marked to be unignored." % package_name )

    def ignore_next_packages(self, package_name, packages_list):

        if self.uningored_packages_to_flush < 1:
            global g_next_packages_to_ignore

            last_ignored_packages = packages_list.index( package_name )
            g_next_packages_to_ignore.extend( packages_list[last_ignored_packages : last_ignored_packages+PACKAGES_COUNT_TO_IGNORE_AHEAD+1] )

            # If the package is already on the users' `ignored_packages` settings, it means either that
            # the package was disabled by the user, therefore we must not unignore it later when unignoring them.
            for package_name in list( g_next_packages_to_ignore ):

                if package_name in g_default_ignored_packages:
                    print( "PackagesManager: Warning, the package `%s` could not be ignored because it already ignored." % package_name )
                    g_next_packages_to_ignore.remove( package_name )

            g_next_packages_to_ignore.sort()

            # Let the packages be unloaded by Sublime Text while ensuring anyone is putting them back in
            self.setup_packages_ignored_list( packages_to_add=g_next_packages_to_ignore )

    def accumulative_unignore_user_packages(self, package_name="", flush_everything=False):
        """
            @param flush_everything     set all remaining packages as unignored
        """

        if flush_everything:
            self.setup_packages_ignored_list( packages_to_remove=g_next_packages_to_ignore )
            self.clear_next_ignored_packages()

        else:
            print( "PackagesManager: Adding package to unignore list: %s" % str( package_name ) )
            self.uningored_packages_to_flush += 1

            if self.uningored_packages_to_flush >= len( g_next_packages_to_ignore ):
                self.setup_packages_ignored_list( packages_to_remove=g_next_packages_to_ignore )
                self.clear_next_ignored_packages()

    def clear_next_ignored_packages(self):
        del g_next_packages_to_ignore[:]
        self.uningored_packages_to_flush = 0

    def setup_packages_ignored_list(self, packages_to_add=[], packages_to_remove=[]):
        """
            Flush just a few items each time. Let the packages be unloaded by Sublime Text while
            ensuring anyone is putting them back in.

            Randomly reverting back the `ignored_packages` setting on batch operations
            https://github.com/SublimeTextIssues/Core/issues/2132
        """
        currently_ignored = sublime_settings().get( "ignored_packages", [] )

        packages_to_add.sort()
        packages_to_remove.sort()

        print( "PackagesManager: Currently ignored packages: " + str( currently_ignored ) )
        print( "PackagesManager: Ignoring the packages:      " + str( packages_to_add ) )
        print( "PackagesManager: Unignoring the packages:    " + str( packages_to_remove ) )

        currently_ignored = [package_name for package_name in currently_ignored if package_name not in packages_to_remove]
        unique_list_append( currently_ignored, packages_to_add )
        currently_ignored.sort()

        # This adds them to the `in_process` list on the Package Control.sublime-settings file
        if len( packages_to_add ):
            # We use a functools.partial to generate the on-complete callback in
            # order to bind the current value of the parameters, unlike lambdas.
            closure = functools.partial( self.package_disabler.disable_packages, list(packages_to_add), self.ignoring_type )

            run_on_main_thread( closure )
            time.sleep( IGNORE_PACKAGE_MINIMUM_WAIT_TIME )

        # This should remove them from the `in_process` list on the Package Control.sublime-settings file
        if len( packages_to_remove ):
            # We use a functools.partial to generate the on-complete callback in
            # order to bind the current value of the parameters, unlike lambdas.
            closure = functools.partial( self.package_disabler.reenable_package, list(packages_to_remove), self.ignoring_type )

            run_on_main_thread( closure )
            time.sleep( IGNORE_PACKAGE_MINIMUM_WAIT_TIME )

        def main_callback():
            sublime_settings().set( "ignored_packages", currently_ignored )
            save_sublime_settings()

        # Something, somewhere is setting the ignored_packages list back to `["Vintage"]`. Then
        # ensure we override this.
        for interval in range( 0, 27 ):
            run_on_main_thread( main_callback )
            time.sleep( IGNORE_PACKAGE_MINIMUM_WAIT_TIME )

            new_ignored_list = sublime_settings().get( "ignored_packages", [] )
            print( "PackagesManager: Currently ignored packages: " + str( new_ignored_list ) )

            if new_ignored_list:

                if len( new_ignored_list ) == len( currently_ignored ) \
                        and new_ignored_list == currently_ignored:

                    break

        run_on_main_thread( save_ignored_packages_callback )
        return currently_ignored

