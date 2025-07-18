# coding=utf-8
from setuptools import setup, find_packages
from octoprint_setuptools import create_plugin_setup_parameters
########################################################################################################################
# Do not forget to adjust the following variables to your own plugin.

# The plugin's identifier, has to be unique
plugin_identifier = "palette2"

# The plugin's python package, should be "octoprint_<plugin identifier>", has to be unique
plugin_package = "octoprint_%s" % plugin_identifier

# The plugin's human readable name. Can be overwritten within OctoPrint's internal data via __plugin_name__ in the
# plugin module
plugin_name = "Palette 2"

# The plugin's version. Can be overwritten within OctoPrint's internal data via __plugin_version__ in the plugin module
plugin_version = "3.0.2"

# The plugin's description. Can be overwritten within OctoPrint's internal data via __plugin_description__ in the plugin
# module
plugin_description = "TODO"

# The plugin's author. Can be overwritten within OctoPrint's internal data via __plugin_author__ in the plugin module
plugin_author = "Mosaic Manufacturing Ltd. & Ryan Turner"

# The plugin's author's mail address.
plugin_author_email = "info@mosaicmfg.com & rturnercardiff@gmail.com"

# The plugin's homepage URL. Can be overwritten within OctoPrint's internal data via __plugin_url__ in the plugin module
plugin_url = "https://gitlab.com/mosaic-mfg/palette-2-plugin & https://github.com/MrTCardiffUK/Mosaic-Palette"

# The plugin's license. Can be overwritten within OctoPrint's internal data via __plugin_license__ in the plugin module
plugin_license = "AGPLv3"

# Any additional requirements besides OctoPrint should be listed here
plugin_requires = ["pyyaml", "python-dotenv"]

# Additional package data to install for this plugin. The subfolders "templates", "static" and "translations" will
# already be installed automatically if they exist.
plugin_additional_packages = []
plugin_ignored_packages =[]
plugin_additional_data = []

additional_setup_parameters = {"python_requires": ">=3,<4"}

########################################################################################################################



setup_params = create_plugin_setup_parameters(
    identifier=plugin_identifier,
    package=plugin_package,
    name=plugin_name,
    version=plugin_version,
    description=plugin_description,
    author=plugin_author,
    mail=plugin_author_email,
    url=plugin_url,
    license=plugin_license,
    requires=plugin_requires,
    additional_packages=plugin_additional_packages,
    ignored_packages=plugin_ignored_packages,
    additional_data=plugin_additional_data
)

# Merge manually instead of using octoprint.util.dict_merge
setup_params.update(additional_setup_parameters)

setup(**setup_params)