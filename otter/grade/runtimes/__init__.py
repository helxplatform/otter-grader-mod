"""Submodule for configuring runtime environments for container execution
"""

import importlib

def get_runtime(runtime_name='docker'):
    "return a runtime class based on runtime_name"
    module = importlib.import_module(__package__ + '.' + runtime_name)
    return module.runtime_class
