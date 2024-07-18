"""
github-actions builder
"""
import os
import tempfile
import zipfile
import shutil
from git import Repo 

from ..utils import OTTER_DOCKER_IMAGE_NAME
from ...utils import loggers
from ...run.run_autograder.autograder_config import AutograderConfig

github_token = os.getenv('GITHUB_TOKEN')
repo_url = 'github.com/helxplatform/otter-builder.git'
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
            rurl = f'https://{github_token}@{repo_url}'
            repo = Repo.clone_from(rurl, local_repo_path)
        repo = Repo(local_repo_path)
        build_wants_dir = 'build-wants'
        if os.path.isdir(os.path.join(local_repo_path, build_wants_dir)):
            shutil.rmtree(os.path.join(local_repo_path, build_wants_dir))
        # Remake the path
        os.makedirs(os.path.join(local_repo_path, build_wants_dir))

        # Iterate through the files in the temporary directory
        for root, _, files in os.walk(temp_dir):
            for file_name in files:
                file_path = os.path.join(root, file_name)

                # Check if the root directory ends with 'tests'
                if root.endswith('tests'):
                    # Copy the entire 'tests' directory to build-wants
                    tests_dest = os.path.join(local_repo_path, build_wants_dir, 'tests')
                    shutil.copytree(root, tests_dest, dirs_exist_ok=True)

                # Check if it's a regular file and matches criteria to move
                elif os.path.isfile(file_path):
                    if file_name.startswith('files') or file_name in files_to_move:
                        dest_file = os.path.join(local_repo_path, build_wants_dir, file_name)
                        shutil.copy(file_path, dest_file)
                        LOGGER.info(f"Copied {file_path} to {dest_file}")

        repo.git.add('-A')
        # Commit changes
        commit_message = "Added generated files to build-wants directory"
        repo.index.commit(commit_message)

        # Push changes to remote repository
        remote = repo.remote(name='origin')
        remote_url_with_token = f'https://{github_token}@{repo_url}'
        remote.set_url(remote_url_with_token)
        remote.push()

        # Get the latest commit (HEAD commit) after push
        head_commit = repo.head.commit

        # Get the short SHA of the latest commit
        short_sha = head_commit.hexsha[:7]
        LOGGER.info(f"Passing {OTTER_DOCKER_IMAGE_NAME}:{short_sha} image to runtime")
    return OTTER_DOCKER_IMAGE_NAME + ":" + short_sha