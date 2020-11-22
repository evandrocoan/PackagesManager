import sublime
import sublime_plugin
import threading

from .. import text
from ..show_quick_panel import show_quick_panel
from ..package_manager import PackageManager
from ..settings import preferences_filename
from ..package_disabler import PackageDisabler
from .existing_packages_command import ExistingPackagesCommand

USE_QUICK_PANEL_ITEM = hasattr(sublime, 'QuickPanelItem')


class DisablePackageCommand(sublime_plugin.WindowCommand, PackageDisabler):

    """
    A command that adds a package to Sublime Text's ignored packages list
    """

    def __init__(self, window):
        PackageDisabler.__init__(self)
        self.window = window

        self.exclusion_flag   = " (excluded)"
        self.inclusion_flag   = " (selected)"
        self.last_picked_item = 0
        self.last_excluded_items = 0

    def run(self):
        self.settings = sublime.load_settings(preferences_filename())
        ignored = self.settings.get('ignored_packages')
        if not ignored:
            ignored = []
        self.ignored = ignored
        threading.Thread(target=self.threaded).start()

    def threaded(self):
        manager = PackageManager()
        packages = manager.list_all_packages()

        package_list = list(set(packages) - set(self.ignored))
        package_list = sorted(package_list, key=lambda s: s.lower())

        existing_packages = ExistingPackagesCommand()
        all_package_set = { item[0] : item for item in existing_packages.make_package_list('Disable') }

        self.package_list = [ ["", "", ""] ]
        self.package_list.extend(
            all_package_set[package] if package in all_package_set else [package, "", ""]
                for package in package_list )

        self.update_start_item_name()
        self.package_list[0][2] = "(from {length} packages available)".format( length=len( self.package_list ) - 1 )

        if len( self.package_list ) < 2:
            sublime.message_dialog(text.format(
                u'''
                PackagesManager

                There are no enabled packages to disable
                '''
            ))
            return
        show_quick_panel(self.window, self.package_list, self.on_done)

    def on_done(self, picked_index):
        """
        Quick panel user selection handler - disables the selected package

        :param picked:
            An integer of the 0-based package name index from the presented
            list. -1 means the user cancelled.
        """

        if picked_index < 0:
            return

        if picked_index == 0:

            # No repositories selected, reshow the menu
            if self.get_total_items_selected() < 1:
                show_quick_panel( self.window, self.package_list, self.on_done )

            else:
                packages = []

                for index in range( 1, self.last_picked_item + 1 ):
                    if USE_QUICK_PANEL_ITEM:
                        package_name = self.package_list[index].trigger
                    else:
                        package_name = self.package_list[index][0]

                    if package_name.endswith( self.exclusion_flag ):
                        continue

                    if package_name.endswith( self.inclusion_flag ):
                        package_name = package_name[:-len( self.inclusion_flag )]

                    packages.append( package_name )

                self.disable_packages(packages, 'disable')

                sublime.status_message(text.format(
                    '''
                    Package %s successfully added to list of disabled packages -
                    restarting Sublime Text may be required
                    ''',
                    packages
                ))
        else:

            if picked_index <= self.last_picked_item:
                picked_package = self.package_list[picked_index]

                if picked_package[0].endswith( self.inclusion_flag ):
                    picked_package[0] = picked_package[0][:-len( self.inclusion_flag )]

                if picked_package[0].endswith( self.exclusion_flag ):

                    if picked_package[0].endswith( self.exclusion_flag ):
                        picked_package[0] = picked_package[0][:-len( self.exclusion_flag )]

                    self.last_excluded_items -= 1
                    self.package_list[picked_index][0] = picked_package[0] + self.inclusion_flag

                else:
                    self.last_excluded_items += 1
                    self.package_list[picked_index][0] = picked_package[0] + self.exclusion_flag

            else:
                self.last_picked_item += 1
                self.package_list[picked_index][0] = self.package_list[picked_index][0] + self.inclusion_flag

            self.update_start_item_name()
            self.package_list.insert( 1, self.package_list.pop( picked_index ) )

            show_quick_panel( self.window, self.package_list, self.on_done )

    def update_start_item_name(self):
        items = self.get_total_items_selected()

        if items:
            self.package_list[0][0] = "Select this first item to ignore the selected packages..."

        else:
            self.package_list[0][0] = "Select all the packages you would like to ignore"

        self.package_list[0][1] = "(%d items selected)" % ( items )

    def get_total_items_selected(self):
        return self.last_picked_item - self.last_excluded_items
