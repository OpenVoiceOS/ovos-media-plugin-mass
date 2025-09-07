#!/usr/bin/env python3
import os

from setuptools import setup

BASEDIR = os.path.abspath(os.path.dirname(__file__))


def get_version():
    """ Find the version of the package"""
    version = None
    version_file = os.path.join(BASEDIR, 'ovos_media_plugin_mass', 'version.py')
    major, minor, build, alpha = (None, None, None, None)
    with open(version_file) as f:
        for line in f:
            if 'VERSION_MAJOR' in line:
                major = line.split('=')[1].strip()
            elif 'VERSION_MINOR' in line:
                minor = line.split('=')[1].strip()
            elif 'VERSION_BUILD' in line:
                build = line.split('=')[1].strip()
            elif 'VERSION_ALPHA' in line:
                alpha = line.split('=')[1].strip()

            if ((major and minor and build and alpha) or
                    '# END_VERSION_BLOCK' in line):
                break
    version = f"{major}.{minor}.{build}"
    if alpha and int(alpha) > 0:
        version += f"a{alpha}"
    return version


def package_files(directory):
    paths = []
    for (path, directories, filenames) in os.walk(directory):
        for filename in filenames:
            paths.append(os.path.join('..', path, filename))
    return paths


def required(requirements_file):
    """ Read requirements file and remove comments and empty lines. """
    with open(os.path.join(BASEDIR, requirements_file), 'r') as f:
        requirements = f.read().splitlines()
        if 'MYCROFT_LOOSE_REQUIREMENTS' in os.environ:
            print('USING LOOSE REQUIREMENTS!')
            requirements = [r.replace('==', '>=').replace('~=', '>=') for r in requirements]
        return [pkg for pkg in requirements
                if pkg.strip() and not pkg.startswith("#")]


PLUGIN_ENTRY_POINT = 'ovos-media-audio-plugin-mass=ovos_media_plugin_mass.media:MAssOCPAudioService'
OLD_PLUGIN_ENTRY_POINT = 'ovos_mass=ovos_media_plugin_mass.audio:MAssAudioService'

with open(os.path.join(BASEDIR, "README.md"), "r") as f:
    long_description = f.read()

setup(
    name='ovos-media-plugin-mass',
    version=get_version(),
    description='mass plugin for ovos',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/OpenVoiceOS/ovos-media-plugin-mass',
    author='JarbasAi',
    author_email='jarbasai@mailfence.com',
    license='Apache-2.0',
    packages=['ovos_media_plugin_mass'],
    install_requires=required("requirements/requirements.txt"),
    package_data={'': package_files('ovos_media_plugin_mass')},
    keywords='ovos audio video OCP plugin',
    entry_points={
        'mycroft.plugin.audioservice': OLD_PLUGIN_ENTRY_POINT,
        'opm.media.audio': PLUGIN_ENTRY_POINT,
        'console_scripts': [
            'ovos-mass-autoconfigure=ovos_media_plugin_mass.autoconfigure:main'
        ]}
)
