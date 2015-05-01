===================
foreground_app_info
===================

Ever wanted to get some details about the foreground app,
such as which is it, which URL is currently opened, etc?
This project is for you.

Demo via ``sleep 3; ./demo.py``.

Examples::

    $ ./demo.py
    {'appName': 'Terminal',
     'idleTime': 0.274327906,
     'url': 'file:///Users/az/Programmierung/foreground_app_info',
     'windowTitle': './demo.py  /Users/az/Programmierung/foreground_app_info \xe2\x80\x94 osascript \xe2\x80\x94 80\xc3\x9724'}
    
    $ sleep 3; ./demo.py
    {'appName': 'Chrome',
     'idleTime': 1.440957492,
     'url': 'https://news.ycombinator.com/',
     'windowTitle': 'Hacker News'}
    
    $ sleep 3; ./demo.py
    {'appName': 'Finder',
     'idleTime': 2.213467371,
     'url': 'file:///Users/az/Documents/',
     'windowTitle': 'Documents'}
    
    $ sleep 3; ./demo.py
    {'appName': 'TextEdit',
     'idleTime': 1.435908488,
     'url': 'file:///Users/az/Documents/todo-musicplayer.txt',
     'windowTitle': 'todo-musicplayer.txt'}
    

This project is registered on `Pypi <https://pypi.python.org/pypi/foreground_app_info>`_.
You can install it via::

    $ pip install foreground_app_info

Simple demo code:

.. code-block:: python

    from foreground_app_info import get_app_info
    from pprint import pprint
    
    pprint(get_app_info())
    

This is currently used by `TimeCapture <https://github.com/albertz/timecapture>`_.
