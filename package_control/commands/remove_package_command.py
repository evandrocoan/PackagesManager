import threading
import time

import sublime
import sublime_plugin

from .existing_packages_command import ExistingPackagesCommand
from .advanced_uninstall_package_command import AdvancedUninstallPackageThread

from .. import text
from ..show_quick_panel import show_quick_panel
from ..thread_progress import ThreadProgress

USE_QUICK_PANEL_ITEM = hasattr(sublime, 'QuickPanelItem')


class RemovePackageCommand(sublime_plugin.WindowCommand):

    """
    A command that presents a list of installed packages, allowing the user to
    select one to remove
    """

    def run(self):
        thread = InstallPackageThread(self.window)
        thread.start()
        ThreadProgress(thread, 'Loading repositories', '')


class InstallPackageThread(threading.Thread, ExistingPackagesCommand):

    """
    A thread to run the action of retrieving available packages in. Uses the
    default ExistingPackagesCommand.on_done quick panel handler.
    """

    def __init__(self, window):
        """
        :param window:
            An instance of :class:`sublime.Window` that represents the Sublime
            Text window to show the available package list in.
        """
        threading.Thread.__init__(self)
        ExistingPackagesCommand.__init__(self)

        self.window = window
        self.completion_type = 'uninstalled'

        self.exclusion_flag   = " (excluded)"
        self.inclusion_flag   = " (selected)"
        self.last_picked_item = 0
        self.last_excluded_items = 0

    def run(self):
        self.package_list = [ ["", "", ""] ]
        self.package_list.extend( self.make_package_list( 'remove' ) )

        self.update_start_item_name()
        self.package_list[0][2] = "(from {length} packages available)".format( length=len( self.package_list ) - 1 )

        if len( self.package_list ) < 2:
            sublime.message_dialog(text.format(
                u'''
                PackagesManager

                There are no packages that can be removed
                '''
            ))
            return

        show_quick_panel( self.window, self.package_list, self.on_done )

    def on_done(self, picked_index):

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

                thread = AdvancedUninstallPackageThread( packages )
                thread.start()

                ThreadProgress(
                    thread,
                    'Uninstalling %s packages' % len(packages),
                    'Successfully %s %s packages' % (self.completion_type, len(packages))
                )

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
            self.package_list[0][0] = "Select this first item to start the uninstallation..."

        else:
            self.package_list[0][0] = "Select all the packages you would like to uninstall"

        self.package_list[0][1] = "(%d items selected)" % ( items )

    def get_total_items_selected(self):
        return self.last_picked_item - self.last_excluded_items
