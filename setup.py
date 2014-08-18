# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, 'README.rst')) as f:
    README = f.read()


requires = ['tornado', 'pyzmq']


setup(name='loads-base',
      version='0.1',
      packages=find_packages(),
      include_package_data=True,
      description='The Loads agent',
      long_description=README,
      zip_safe=False,
      license='APLv2.0',
      classifiers=[
        "Programming Language :: Python",
      ],
      install_requires=requires,
      author='Mozilla Services',
      author_email='services-dev@mozilla.org',
      url='https://github.com/mozilla-services/loads-agent',
      tests_require=['nose', 'mock', 'unittest2'],
      test_suite='nose.collector'
      )
