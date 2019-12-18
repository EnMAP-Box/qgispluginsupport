from setuptools import setup, find_packages
from qps import __version__
setup(name='qps',
    version=__version__,
    description='QPS - QGIS Plugin Support. Tools and helpers to develop QGIS Plugins for remote sensing applications',
    author='Benjamin Jakimow    ',
    author_email='benjamin.jakimow@geo.hu-berlin.de',
    packages=find_packages(),
    url='https://bitbucket.org/jakimowb/qgispluginsupport',
    long_description=open('README.md').read(),
    include_package_data=True,
    dependency_links=['git+https://bitbucket.org/jakimowb/qgispluginsupport.git@develop#egg=qps']
    )

# python3 -m pip install --user https://bitbucket.org/jakimowb/bit-flag-renderer/get/master.zip#egg=qps
# python3 -m pip install --user git+https://bitbucket.org/jakimowb/qgispluginsupport.git@develop#egg=qps
