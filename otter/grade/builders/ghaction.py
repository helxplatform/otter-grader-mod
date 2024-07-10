"""
github-actions builder
"""
import os
import tempfile
import zipfile
import pathlib
import json
import shutil
from glob import glob
from git import Repo 

from ..utils import OTTER_DOCKER_IMAGE_NAME
from ...utils import loggers, OTTER_CONFIG_FILENAME
from ...run.run_autograder.autograder_config import AutograderConfig

OTTER_IMAGE_NAME = 'containers.renci.org/helxplatform/ottergrader/gradebuild'

repo_url = 'https://github.com/joshua-seals/builder.git'
local_repo_path = '/tmp/builder'
files_to_move = ['run_autograder', 'setup.sh', 'environment.yml', 'otter_config.json', 'run_otter.py', 'requirements.*', 'files*']

LOGGER = loggers.get_logger(__name__)

# currently don't care about the base_image
def build_image(dockerfile: str, ag_zip_path: str, base_image: str, tag: str,
                config: AutograderConfig):
    """
    Creates a grading image based on zip file and attaches a tag.

    Args:
    dockerfile (``str``): path to the dockerfile
    ag_zip_path (``str``): path to the autograder zip file
    base_image (``str``): base Docker image to build from
    tag (``str``): tag to be added when creating the image
    config (``otter.run.run_autograder.autograder_config.AutograderConfig``):
        config overrides for the autograder

    Returns:
    ``str``: the tag of the newly-build Docker image
    """

    LOGGER.info(f"Offloading build job to github-actions")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(ag_zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        # Clone the gh-build repo and remove the /wants dir
        if not os.path.exists(local_repo_path):
            repo = Repo.clone_from(repo_url, local_repo_path)
        repo = Repo(local_repo_path)
        build_wants_dir = 'build-wants'
        if os.path.isdir(os.path.join(local_repo_path, build_wants_dir)):
            shutil.rmtree(os.path.join(local_repo_path, build_wants_dir))
        # Remake the path
        os.makedirs(os.path.join(local_repo_path, build_wants_dir))
        for root,_,files in os.walk(temp_dir):
            for file_name in files:
              file_path = os.path.join(root, file_name)
              if os.path.isfile(file_path):
                if root.endswith('tests') or file_name.startswith('files') or file_name in files_to_move:
                  shutil.copy(file_path, os.path.join(local_repo_path, build_wants_dir, file_name))
    
        # Commit changes
        commit_message = "Added generated files to build-wants directory"
        repo.index.commit(commit_message)

        # Push changes to remote repository
        origin = repo.remote(name='origin')
        origin.push()

        # Get the latest commit (HEAD commit) after push
        head_commit = repo.head.commit

        # Get the short SHA of the latest commit
        short_sha = head_commit.hexsha[:7]
        return OTTER_DOCKER_IMAGE_NAME + ":" + short_sha