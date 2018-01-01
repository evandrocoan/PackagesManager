import sublime
import sublime_plugin

from ..tests import runner
from ..tests.clients import GitHubClientTests, BitBucketClientTests
from ..tests.providers import (
    BitBucketRepositoryProviderTests,
    ChannelProviderTests,
    GitHubRepositoryProviderTests,
    GitHubUserProviderTests,
    RepositoryProviderTests,
)


class PackagesManagerTestsCommand(sublime_plugin.WindowCommand):

    """
    A command to run the tests for PackagesManager
    """

    def run(self):
        runner(
            self.window,
            [
                GitHubClientTests,
                BitBucketClientTests,
                GitHubRepositoryProviderTests,
                BitBucketRepositoryProviderTests,
                GitHubUserProviderTests,
                RepositoryProviderTests,
                ChannelProviderTests
            ]
        )

    def is_visible(self):
        settings = sublime.load_settings('PackagesManager.sublime-settings')
        return settings.get('enable_tests', False)