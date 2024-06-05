"""Openshift image builder
"""

import temptfile
import zipfile

from kubernetes import client, config
from openshift.dynamic import DynamicClient

from ..utils import OTTER_DOCKER_IMAGE_NAME
from ...utils import loggers, OTTER_CONFIG_FILENAME
from ...run.run_autograder.autograder_config import AutograderConfig

LOGGER = loggers.get_logger(__name__)

def build_image(dockerfile: str, ag_zip_path: str, base_image: str, tag: str,
                config: AutograderConfig, namespace="eduhelx"):
    """Creates a grading image using the openshift image builder
    """
    image = OTTER_DOCKER_IMAGE_NAME + ":" + tag
    LOGGER.info(f"Building image using {base_image} as base image")

    config.load_incluster_config()

    k8s_client = client.ApiClient()
    dyn_client = DynamicClient(k8s_client)
    build_config = {
        "apiVersion": "build.openshift.io/v1",
        "kind": "BuildConfig",
        "metadata": {
            "name": OTTER_DOCKER_IMAGE_NAME,
            "namespace": namespace
        },
        "spec": {
            "source": {
                "type": "Binary"
            },
            "strategy": {
                "type": "Docker"
            },
            "output": {
                "to": {
                    "kind": "ImageStreamTag",
                    "name": image
                }
            }
        }
    }

    v1_bc = dyn_client.resources.get(api_version='build.openshift.io/v1', kind='BuildConfig')
    v1_bc.create(body=build_config)

    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(ag_zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
