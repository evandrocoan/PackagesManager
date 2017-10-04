import sublime_plugin


class PackagesManagerInsertCommand(sublime_plugin.TextCommand):

    """
    A command used by the test runner to display output in the output panel
    """

    def run(self, edit, string=''):
        self.view.insert(edit, self.view.size(), string)
        self.view.show(self.view.size(), True)
