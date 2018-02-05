
try:
    # Allow using this file on the website where the sublime
    # module is unavailable
    import sublime
except (ImportError):
    sublime = None

from . import text
from .console_write import console_write

import time
from threading import Timer

# When there is a batch performance for some chain of execution, and there are error on them,
# we cannot show a error message dialog for each one of them immediately, otherwise we would
# flood the user with messages. See: https://github.com/SublimeTextIssues/Core/issues/1510
is_error_recentely_displayed = False

last_time = time.time()
accumulated_time = 0.0

def show_error(string, params=None, strip=True, indent=None):
    """
    Displays an error message with a standard "PackagesManager" header after
    running the string through text.format()

    :param string:
        The error to display

    :param params:
        Params to interpolate into the string

    :param strip:
        If the last newline in the string should be removed

    :param indent:
        If all lines should be indented by a set indent after being dedented
    """
    string = text.format(string, params, strip=strip, indent=indent)

    if sublime:

        if is_error_recentely_displayed:
            console_write( string )

        else:
            sublime.error_message(u'PackagesManager\n\n%s\n%s' % (
                string,
                u'''
                If there will be new messages on the next seconds,
                they will be show on the Sublime Text console
                '''
                ) )

            silence_error_message_box(60.1)

    else:
        console_write( string )

def _restart_error_messages():
    global accumulated_time
    console_write( "Unsilencing Error Messages Boxes... Accumulated time: " + str( accumulated_time ) )

    if accumulated_time > 0:
        thread = Timer(accumulated_time, _restart_error_messages)

        accumulated_time = 0.0
        thread.start()

    else:
        global is_error_recentely_displayed
        is_error_recentely_displayed = False

def silence_error_message_box(how_many_seconds=60.0):
    global last_time
    global accumulated_time

    global is_error_recentely_displayed
    console_write( "Silencing Error Messages Boxes for %s seconds... Accumulated time: %s" % ( str( how_many_seconds ), str( accumulated_time ) ) )

    # Enable the message dialog after x.x seconds
    if is_error_recentely_displayed:
        accumulated_time += ( time.time() - last_time )

    else:
        is_error_recentely_displayed = True

        thread = Timer(how_many_seconds, _restart_error_messages)
        thread.start()

    last_time = time.time()

