import sys
import json

from ..console_write import console_write
from ..package_io import package_file_exists, read_package_file


class ProviderException(Exception):

    """If a provider could not return information"""

    def __unicode__(self):
        return self.args[0]

    def __str__(self):
        if sys.version_info < (3,):
            return self.__bytes__()
        return self.__unicode__()

    def __bytes__(self):
        return self.__unicode__().encode('utf-8')


def get_package_metadata(package):
    """
    Returns the package metadata for an installed package

    :param package:
        The name of the package

    :return:
        A dict with the keys:
            version
            url
            description
        or an empty dict on error
    """
    metadata = {}
    metadata_filenames = ['package-metadata.json', 'dependency-metadata.json']

    for metadata_filename in metadata_filenames:

        if package_file_exists(package, metadata_filename):
            metadata_json = read_package_file(package, metadata_filename)

            if metadata_json:

                try:
                    metadata = json.loads(metadata_json)
                    break

                except (ValueError):
                    console_write(
                        u'''
                        An error occurred while trying to parse the package
                        metadata for %s.
                        ''',
                        (package)
                    )

    return metadata


def do_old_new_names_mapping(package, output):
    previous_names = package.get('previous_names', [])

    if not isinstance(previous_names, list):
        previous_names = [previous_names]

    for previous_name in previous_names:
        output[previous_name] = package['name']
