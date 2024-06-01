"""Default docker image builder
"""

import logging
import tempfile
import zipfile
import pathlib
import json

from python_on_whales import docker

from ..utils import OTTER_DOCKER_IMAGE_NAME
from ...utils import loggers, OTTER_CONFIG_FILENAME
from ...run.run_autograder.autograder_config import AutograderConfig

LOGGER = loggers.get_logger(__name__)

def build_image(dockerfile: str, ag_zip_path: str, base_image: str, tag: str,
                config: AutograderConfig):
    """
    Creates a grading image based on zip file and attaches a tag.

    Args:
    dockerfile (``str``): path to the dockerfile
    ag_zip_path (``str``): path to the autograder zip file
    base_image (``str``): base Docker image to build from
    tag (``str``): tag to be added when creating the image
    config (``otter.run.run_autograder.autograder_config.AutograderConfig``): config overrides
    for the autograder

    Returns:
    ``str``: the tag of the newly-build Docker image
    """
    image = OTTER_DOCKER_IMAGE_NAME + ":" + tag
    LOGGER.info(f"Building image using {base_image} as base image")

    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(ag_zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        # Update the otter_config.json file from the autograder zip with the
        # provided config overrides.
        config_path = pathlib.Path(temp_dir) / OTTER_CONFIG_FILENAME
        old_config = AutograderConfig()
        if config_path.exists():
            old_config = AutograderConfig(
                json.loads(config_path.read_text("utf-8")))

        old_config.update(config.get_user_config())
        config_path.write_text(json.dumps(old_config.get_user_config()))

        try:
            docker.build(
                temp_dir,
                build_args={"BASE_IMAGE": base_image},
                tags=[image],
                file=dockerfile,
                load=True,
            )
        except TypeError as e:
            raise TypeError(
                f"Docker build failed; if this is your first time "
                f"seeing this error, ensure that "
                f"Docker is running on your machine.\n\n"
                f"Original error: {e}")
    return image
