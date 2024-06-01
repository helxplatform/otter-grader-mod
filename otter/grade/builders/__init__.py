"""Submodule for configuring image builders
"""

import importlib

def get_builder(builder_name='docker'):
    "return a builder class based on builder_name"
    module = importlib.import_module(__package__ + '.' + builder_name)
    return module.build_image
