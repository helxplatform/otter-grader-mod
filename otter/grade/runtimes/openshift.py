"""Runtime based on OpenShift that uses `oc`-style API
"""

import os
import tempfile
from time import sleep

import openshift_client as oc

from ._base import BaseRuntime
from ..utils import OTTER_DOCKER_IMAGE_NAME
from ...utils import loggers

LOGGER = loggers.get_logger(__name__)

class OpenshiftRuntime(BaseRuntime):
    """Class for executing grader in Openshift containers
    """

    def __init__(self, *args, **kwargs):
        """Instantiate runtime object
        """

        super().__init__(*args, no_create=True, **kwargs)
        self.secret_name = kwargs.get('secret_name',
                                      'ottergrader-harbor-secret')
        self.namespace = kwargs.get('namespace', None)
        if not self.namespace:
            self.namespace = self._get_current_namespace

        self.repo = os.environ.get(
            'OTTERGRADER_REPO_NAME',
            'containers.renci.org/helxplatform/ottergrader')
        self.image_spec = self.repo + "/" + self.image
        if not kwargs.get('no_create', False):
            self.create()

    def _get_current_namespace(self):
        """Get the name of the current namespace or project"""
        return oc.invoke('project', ['-q']).out().strip()

    def _get_env(self):
        """Put any needed environment variables into the env
        """
        env = []

        http_proxy = os.environ.get('OTTERGRADER_HTTP_PROXY', None)
        if http_proxy:
            env.append({
                'name': 'http_proxy',
                'value': http_proxy})
            env.append({
                'name': 'HTTP_PROXY',
                'value': http_proxy})

        https_proxy = os.environ.get('OTTERGRADER_HTTPS_PROXY', None)
        if https_proxy:
            env.append({
                'name': 'https_proxy',
                'value': https_proxy})
            env.append({
                'name': 'HTTPS_PROXY',
                'value': https_proxy})
        return env

    def _create_jobspec(self):
        """Create a specifier for the main pod
        """
        env = self._get_env()

        jobspec = {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {
                'generateName': 'otter-grade-submission-'
            },
            'spec': {
                'activeDeadlineSeconds': 3600,
                'backoffLimit': 1,
                'template': {
                    'spec': {
                        'containers': [
                            {
                                'name': OTTER_DOCKER_IMAGE_NAME,
                                'image': self.image_spec,
                                'env': env,
                                'volumeMounts': [
                                    {
                                        'mountPath': '/autograder/submission',
                                        'name': 'submission-volume'
                                    }
                                ],
                                "resources": {
                                    "limits": {
                                        "cpu": "1",
                                        "ephemeral-storage": "1G",
                                        "memory": "1G",
                                    },
                                },
                                "requests": {
                                    "cpu": "1",
                                    "ephemeral-storage": "1G",
                                    "memory": "1G"
                                }
                            }
                        ],
                        'initContainers': [
                            {
                                'name': 'init-filewait',
                                'image': 'busybox:latest',
                                'command': [
                                    'sh', '-c',
                                    'until [ -f /tmp/.ottergrader_ready ]; '
                                    'do echo "waiting ready file"; '
                                    'sleep 2; done;'
                                ],
                                'env': env,
                                'volumeMounts': [
                                    {
                                        'mountPath': '/autograder/submission',
                                        'name': 'submission-volume'
                                    }
                                ],
                                "resources": {
                                    "limits": {
                                        "cpu": "1",
                                        "ephemeral-storage": "1G",
                                        "memory": "1G",
                                    },
                                },
                                "requests": {
                                    "cpu": "1",
                                    "ephemeral-storage": "1G",
                                    "memory": "1G"
                                }
                            }
                        ],
                        'volumes': [
                            {
                                'name': 'submission-volume',
                                'emptyDir': {
                                    'sizeLimit': '100Mi'
                                }
                            }
                        ],
                        'restartPolicy': 'Never',
                    }
                }
            }
        }
        return jobspec

    def create(self, **kwargs):
        """Create the container"""
        LOGGER.info(f"Creating job spec")
        job_def = self._create_jobspec()
        self._job_selector = oc.create(job_def)
        podname = None
        while not podname:
            try:
                podname = self.pod.name()
            except IndexError:
                sleep(1)
        LOGGER.info("Pod %s created by job %s", podname, self.job.name())
        LOGGER.debug("Pod %s contains containers (%s)", podname,
                     str([c['name'] for c in
                          self.pod.model['spec']['containers']]))
        LOGGER.debug("Pod %s contains init containers (%s)", podname,
                     str([c['name'] for c in
                          self.pod.model['spec']['initContainers']]))
        for local_path, container_path in self.volumes:
            oc.invoke('cp',
                      [
                          local_path,
                          podname + ':' + container_path,
                          '-c', 'init-filewait'
                      ])
        with tempfile.NamedTemporaryFile() as tf:
            # Create an empty file then copy it in
            oc.invoke('cp', [tf.name, podname + ':/tmp/.ottergrader_ready',
                             '-c', 'init-filewait'])

    @property
    def pod(self):
        """Return the pod APIObject"""
        return self._job_selector.object().get_owned('pod')[0]

    @property
    def job(self):
        """Return the job APIObject"""
        return self._job_selector.object()

    def wait(self):
        """Wait the container completion"""
        while True:
            conditions = self.job.model['status']['conditions']
            statuses = [c['type'] for c in conditions]
            if 'Failed' in statuses:
                # Maybe we should log something? Dunno...
                break
            if 'Complete' in statuses:
                break
            sleep(4)


    def _get_active_container(self):
        """Return the name of a running container
        """
        for cs in self.pod.model['status']['containerStatuses']:
            if 'running' in cs['state']:
                return cs['name']
        for ics in self.pod.model['status']['initContainerStatuses']:
            if 'running' in ics['state']:
                return ics['name']
        return None

    def kill(self):
        """Kill the container"""
        active = self._get_active_container()
        if active:
            self.pod.execute(['kill', '-9', '1'], container_name=active)

    def get_container_id(self):
        """Returns the pod uid"""
        return self.pod.model['metadata']['uid']

    def get_logs(self):
        """Returns the logs for the container"""
        logdict = self.pod.logs()
        return list(logdict.values())[0]

    def finalize(self):
        """Final cleanup and writeout

        Should copy files back to the local paths and remove container if
        no_kill not set
        """
        podname = self.pod.name()
        for local_path, container_path in self.volumes:
            oc.invoke('cp', [podname + ':' + container_path,
                             local_path])

        if not self.no_kill:
            self._job_selector.delete()

runtime_class = OpenshiftRuntime
