

from distutils.core import setup, Extension
from glob import glob
import time, sys


setup(
	name = 'foreground_app_info',
	version = time.strftime("1.%Y%m%d.%H%M%S", time.gmtime()),
	packages = ['foreground_app_info'],
	package_dir = {'foreground_app_info': ''},	
	description = 'Get details about the application and opened URL which is in foreground',
	author = 'Albert Zeyer',
	author_email = 'albzey@gmail.com',
	url = 'https://github.com/albertz/foreground_app_info',
	license = '2-clause BSD license',
	long_description = open('README.rst').read(),
	classifiers = [
		'Development Status :: 4 - Beta',
		'Environment :: MacOS X',
		'Environment :: Win32 (MS Windows)',
		'Environment :: X11 Applications',
		'Intended Audience :: Developers',
		'Intended Audience :: Education',
		'License :: OSI Approved :: BSD License',
		'Operating System :: MacOS :: MacOS X',
		'Operating System :: Microsoft :: Windows',
		'Operating System :: POSIX',
		'Operating System :: Unix',
		'Programming Language :: Python',
		'Topic :: Software Development :: Libraries :: Python Modules',
		]
)

