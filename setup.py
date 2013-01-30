import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = """por.models
=============

for more details visit: http://getpenelope.github.com/"""
CHANGES = open(os.path.join(here, 'CHANGES.txt')).read()

requires = [
    'por.dashboard',
    ]

setup(name='por.trac',
      version='1.1.8',
      description='Penelope: Trac integration',
      long_description=README + '\n\n' +  CHANGES,
      classifiers=[
        "Programming Language :: Python",
        "Framework :: Pylons",
        ],
      author='Penelope Team',
      author_email='penelopedev@redturtle.it',
      url='https://getpenelope.github.com',
      keywords='web wsgi bfg pylons pyramid',
      namespace_packages=['por'],
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      test_suite='por.trac',
      install_requires = requires,
      entry_points = """\
      [console_scripts]
      authz = por.trac.authz:main
      auth_wsgi = por.trac.auth_wsgi:main
      """,
      )

