import sublime


class ThreadProgress():

    """
    Animates an indicator, [=   ], in the status area while a thread runs

    :param thread:
        The thread to track for activity

    :param message:
        The message to display next to the activity indicator

    :param success_message:
        The message to display once the thread is complete
    """
    running = False

    def __init__(self, thread, message, success_message):
        ThreadProgress.setup(thread, message, success_message)

    @classmethod
    def setup(cls, thread, message, success_message):
        cls.thread = thread
        cls.message = message
        cls.success_message = success_message
        cls.addend = 1
        cls.size = 8
        cls.last_view = None
        cls.window = None
        cls.index = 0
        if not cls.running:
            cls.running = True
            sublime.set_timeout(lambda: cls.run(), 100)

    @classmethod
    def run(cls):
        if cls.window is None:
            cls.window = sublime.active_window()
        active_view = cls.window.active_view()

        if cls.last_view is not None and active_view != cls.last_view:
            cls.last_view.erase_status('_packages_manager')
            cls.last_view = None

        if not cls.thread.is_alive():
            def cleanup():
                active_view.erase_status('_packages_manager')
            if hasattr(cls.thread, 'result') and not cls.thread.result:
                cleanup()
                return
            active_view.set_status('_packages_manager', cls.success_message)
            sublime.set_timeout(cleanup, 5000)
            ThreadProgress.running = False
            return

        before = cls.index % cls.size
        after = (cls.size - 1) - before

        active_view.set_status('_packages_manager', '%s [%s=%s]' % (cls.message, ' ' * before, ' ' * after))
        if cls.last_view is None:
            cls.last_view = active_view

        if not after:
            cls.addend = -1
        if not before:
            cls.addend = 1
        cls.index += cls.addend

        sublime.set_timeout(lambda: cls.run(), 100)
