"""Openshift image builder
"""

import os
import tempfile
import zipfile
import pathlib
import json
from glob import glob

import openshift_client as oc

from ..utils import OTTER_DOCKER_IMAGE_NAME
from ...utils import loggers, OTTER_CONFIG_FILENAME
from ...run.run_autograder.autograder_config import AutograderConfig

LOGGER = loggers.get_logger(__name__)

def _make_bc_spec(image, tag, repo, base_image, dockerfile, namespace,
                  secret_name, http_proxy=None, https_proxy=None):
    """return an object suitable for passing as a buildconfig payload"""
    if not repo.endswith('/'):
        repo = repo + '/'

    push_target = repo + image + ':' + tag
    LOGGER.info("Setting buildconfig push location to %s", push_target)

    with open(dockerfile, 'rt') as df:
        df_string = df.read()

    env = []
    if http_proxy:
        env.append({
            'name': 'http_proxy',
            'value': http_proxy})
        env.append({
            'name': 'HTTP_PROXY',
            'value': http_proxy})
    if https_proxy:
        env.append({
            'name': 'https_proxy',
            'value': https_proxy})
        env.append({
            'name': 'HTTPS_PROXY',
            'value': https_proxy})

    bc = {
        "apiVersion": "v1",
        "items": [
            {
                "apiVersion": "build.openshift.io/v1",
                "kind": "BuildConfig",
                "metadata": {
                    "generateName": image + '-',
                    "namespace": namespace
                },
                "spec": {
                    "output": {
                        "pushSecret": {
                            "name": secret_name
                        },
                        "to": {
                            "kind": "DockerImage",
                            "name": push_target
                        }
                    },
                    "runPolicy": "Serial",
                    "source": {
                        "binary": {},
                        "dockerfile": df_string,
                        "type": "Binary"
                    },
                    "strategy": {
                        "dockerStrategy": {
                            "from": {
                                "kind": "DockerImage",
                                "name": base_image
                            },
                            "env": env,
                            "imageOptimizationPolicy": "SkipLayers",
                        },
                        "type": "Docker"
                    },
                    "successfulBuildsHistoryLimit": 5,
                    "triggers": [
                        {
                            "type": "ConfigChange"
                        }
                    ],
                    "resources": {
                        "limits": {
                            "cpu": "1",
                            "ephemeral-storage": "4G",
                            "memory": "1G",
                        },
                    },
                    "requests": {
                        "cpu": "1",
                        "ephemeral-storage": "4G",
                        "memory": "1G"
                    }
                },
            }
        ],
        "kind": "List"
    }

    return bc

def build_image(dockerfile: str, ag_zip_path: str, base_image: str, tag: str,
                config: AutograderConfig, namespace=None):
    """Creates a grading image using the openshift image builder
    """
    LOGGER.info(f"Building image using {base_image} as base image")

    secret_name = os.environ.get('OTTERGRADER_SECRET_NAME',
                                 'ottergrader_secret')
    repo_name = os.environ.get('OTTERGRADER_REPO_NAME',
                               'containers.renci.org/helxplatform/ottergrader')
    http_proxy = os.environ.get('OTTERGRADER_HTTP_PROXY', None)
    https_proxy = os.environ.get('OTTERGRADER_HTTPS_PROXY', None)
    if not namespace:
        namespace = oc.invoke('project', ['-q']).out().strip()

    bc_spec = _make_bc_spec(
        image=OTTER_DOCKER_IMAGE_NAME,
        tag=tag,
        repo=repo_name,
        base_image=base_image,
        dockerfile=dockerfile,
        namespace=namespace,
        secret_name=secret_name,
        http_proxy=http_proxy,
        https_proxy=https_proxy
    )

    bc_selector = oc.create(bc_spec)

    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(ag_zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        LOGGER.debug("Using %s as temporary context dir", temp_dir)
        LOGGER.debug("Context dir base contents: %s", str(glob(temp_dir)))
        # Update the otter_config.json file from the autograder zip with the
        # provided config overrides.
        config_path = pathlib.Path(temp_dir) / OTTER_CONFIG_FILENAME
        old_config = AutograderConfig()
        if config_path.exists():
            old_config = AutograderConfig(
                json.loads(config_path.read_text("utf-8")))

        old_config.update(config.get_user_config())
        config_path.write_text(json.dumps(old_config.get_user_config()))

        build = bc_selector.start_build(
            '--from-dir=' + temp_dir)

    # bc_selector.delete()
    return OTTER_DOCKER_IMAGE_NAME + ":" + tag
