import os
import re

import sublime

from ..package_manager import PackageManager


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
            package_entry = [package]
            metadata = self.manager.get_metadata(package)
            package_dir = os.path.join(sublime.packages_path(), package)

            description = metadata.get('description')
            if not description:
                description = 'No description provided'
            package_entry.append(description)

            version = metadata.get('version')
            if not version and os.path.exists(os.path.join(package_dir, '.git')):
                installed_version = 'git repository'
            elif not version and os.path.exists(os.path.join(package_dir, '.hg')):
                installed_version = 'hg repository'
            else:
                installed_version = 'v' + version if version else 'unknown version'

            url = metadata.get('url')
            if url:
                url = '; ' + re.sub('^https?://', '', url)
            else:
                url = ''

            package_entry.append(action + installed_version + url)

            if package in default_packages:
                default_count += 1
                package_entry.append( "Default" )
                package_entry.append( default_count )

            elif package in dependencies:
                dependencies_count += 1
                package_entry.append( "Dependency" )
                package_entry.append( dependencies_count )

            else:
                package_count += 1
                package_entry.append( "Third Part" )
                package_entry.append( package_count )

            package_list.append(package_entry)

        self.package_count = package_count
        self.default_count = default_count
        self.dependencies_count = dependencies_count
        return package_list
