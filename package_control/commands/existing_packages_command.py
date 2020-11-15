import os
import re

import sublime

from ..package_manager import PackageManager

USE_QUICK_PANEL_ITEM = hasattr(sublime, 'QuickPanelItem')


class ExistingPackagesCommand():

    """
    Allows listing installed packages and their current version
    """

    def __init__(self):
        self.manager = PackageManager()

    def make_package_list(self, action=''):
        """
        Returns a list of installed packages suitable for displaying in the
        quick panel.

        :param action:
            An action to display at the beginning of the third element of the
            list returned for each package

        :return:
            A list of lists, each containing three strings:
              0 - package name
              1 - package description
              2 - [action] installed version; package url
        """

        packages = self.manager.list_packages(list_everything=True)
        default_packages = self.manager.list_default_packages()
        dependencies = self.manager.list_dependencies()

        if action:
            action += ' '

        package_count = 0
        default_count = 0
        dependencies_count = 0

        package_list = []
        for package in sorted(packages, key=lambda s: s.lower()):
            metadata = self.manager.get_metadata(package)
            package_dir = os.path.join(sublime.packages_path(), package)

            description = metadata.get('description')
            if not description:
                description = 'No description provided'

            version = metadata.get('version')
            if not version and os.path.exists(os.path.join(package_dir, '.git')):
                installed_version = 'git repository'
            elif not version and os.path.exists(os.path.join(package_dir, '.hg')):
                installed_version = 'hg repository'
            else:
                installed_version = 'v' + version if version else 'unknown version'

            url = metadata.get('url', '')
            url_display = re.sub('^https?://', '', url)

            if package in default_packages:
                default_count += 1
                extra_info = " (Default #%d)" % default_count
            elif package in dependencies:
                dependencies_count += 1
                extra_info = " (Dependency #%d)" % dependencies_count
            else:
                package_count += 1
                extra_info = " (Third Part #%d)" % package_count

            if USE_QUICK_PANEL_ITEM:
                description = '<em>%s</em>' % sublime.html_format_command(description)
                final_line = '<em>' + action + installed_version + extra_info + '</em>'
                if url_display:
                    final_line += '; <a href="%s">%s</a>' % (url, url_display)
                package_entry = sublime.QuickPanelItem(package, [description, final_line])
            else:
                final_line = action + installed_version + extra_info
                if url_display:
                    final_line += '; ' + url_display
                package_entry = [package, description, final_line]

            package_list.append(package_entry)

        self.package_count = package_count
        self.default_count = default_count
        self.dependencies_count = dependencies_count
        return package_list
