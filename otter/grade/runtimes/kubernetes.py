"""Runtime based on Kubernetes that k8s client
"""

import os
from time import sleep
import subprocess

from kubernetes import client, config

from ._base import BaseRuntime
from ..utils import OTTER_DOCKER_IMAGE_NAME
from ...utils import loggers

LOGGER = loggers.get_logger(__name__)

class KubernetesRuntime(BaseRuntime):
    """Class for executing grader in Openshift containers
    """

    def __init__(self, *args, **kwargs):
        """Instantiate runtime object
        """

        super().__init__(*args, no_create=True, **kwargs)
        self.secret_name = kwargs.get('secret_name',
                                      'harbor')
        # self.namespace = kwargs.get('namespace', None)
        # if not self.namespace:
        self.namespace = self._get_current_namespace
        self.volumes = []
        self.repo = os.environ.get(
            'OTTERGRADER_REPO_NAME',
            'containers.renci.org/helxplatform/ottergrader')
        self.image_spec = self.repo + "/" + self.image
        if not kwargs.get('no_create', False):
            self.create()
        # Need k8s config
        config.load_incluster_config()
        self.batch_v1 = client.BatchV1Api()
        self.core_v1 = client.CoreV1Api()
        self.pod_name = None

    def _get_current_namespace(self):
        """Get the name of the current namespace or project"""
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r") as secrets:
                for line in secrets:
                    namespace = line
        return namespace

    def _get_env(self):
        """Put any needed environment variables into the env
        """
        env = []

        http_proxy = os.environ.get('HTTP_PROXY', None)
        if http_proxy:
            env.append({
                'name': 'http_proxy',
                'value': http_proxy})
            env.append({
                'name': 'HTTP_PROXY',
                'value': http_proxy})

        https_proxy = os.environ.get('HTTPS_PROXY', None)
        if https_proxy:
            env.append({
                'name': 'https_proxy',
                'value': https_proxy})
            env.append({
                'name': 'HTTPS_PROXY',
                'value': https_proxy})
        return env

    def _create_jobspec(self):
        """Configure Pod template container
        """
        env = self._get_env()

        # Define init containers
        init_containers = [
            client.V1Container(
                name="init-filewait",
                image="busybox:latest",
                command = ["sh", "-c", 'echo "Init container started - waiting on build"; sleep 300'],
                # command=["sh", "-c", 'until [ -f /tmp/.ottergrader_ready ]; do echo "waiting ready file"; sleep 2; done;'],
                env=env,
                volume_mounts=[
                    client.V1VolumeMount(mount_path="/autograder/submission", name="submission-volume")
                ],
                resources=client.V1ResourceRequirements(
                    limits={"cpu": "1", "ephemeral-storage": "1G", "memory": "1G"},
                    requests={"cpu": "1", "ephemeral-storage": "1G", "memory": "1G"}
                )
            )
        ]

        # Define containers
        containers = [
            client.V1Container(
                name=OTTER_DOCKER_IMAGE_NAME,
                image=self.image_spec,
                env=env,
                volume_mounts=[
                    client.V1VolumeMount(mount_path="/autograder/submission", name="submission-volume")
                ],
                resources=client.V1ResourceRequirements(
                    limits={"cpu": "1", "ephemeral-storage": "1G", "memory": "1G"},
                    requests={"cpu": "1", "ephemeral-storage": "1G", "memory": "1G"}
                )
            )
        ]

        volumes = [
            client.V1Volume(
                name="submission-volume",
                empty_dir=client.V1EmptyDirVolumeSource(size_limit="100Mi")
            )
        ]

        # Define Pod template spec
        pod_template_spec = client.V1PodTemplateSpec(
            spec=client.V1PodSpec(
                containers=containers,
                init_containers=init_containers,
                volumes=volumes,
                restart_policy="Never"
            )
        )

        # Define Job spec
        job_spec = client.V1JobSpec(
            active_deadline_seconds=3600,
            backoff_limit=1,
            template=pod_template_spec
        )

        # Define Job object
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(generate_name="otter-grade-submission-"),
            spec=job_spec
        )

        return job

    def create(self, **kwargs):
        """Create the container"""
        LOGGER.info(f"Creating job")

        job = self._create_jobspec()
        # batch_v1 = client.BatchV1Api()
        created_job = self.batch_v1.create_namespaced_job(
            body=job,
            namespace=self.namespace
        )
        LOGGER.info(f"Job created. status='{str(created_job.status)}'")

        # Wait for Pod to be created
        while not self.pod_name:
            try:
                # Get Pod associated with the Job
                pods = self.core_v1.list_namespaced_pod(namespace=self.namespace, label_selector=f"job-name={created_job.metadata.name}")
                if pods.items:
                    self.pod_name = pods.items[0].metadata.name
            except Exception as e:
                LOGGER.error(f"Error occurred while fetching Pod: {e}")

            if not self.pod_name:
                sleep(1)  # Wait for 1 second before retrying
        LOGGER.info(f"Pod has been created {self.pod_name}")
        

    @property
    def pod(self):
        """Return the pod APIObject"""
        return self._job_selector.object().get_owned('pod')[0]


    @property
    def job(self):
        """Return the job APIObject"""
        if not self.pod_name:
            return None  # Handle case where pod_name is not set yet

        try:
            # Retrieve the Job object by name
            job_obj = self.batch_v1.read_namespaced_job(namespace=self.namespace, name=self.pod_name)
            return job_obj
        except Exception as e:
            print(f"Error occurred while fetching Job: {e}")
            return None


    # def wait(self): 
    #     """Wait the container completion"""
    #     while True:
    #         conditions = self.job.model['status']['conditions']
    #         statuses = [c['type'] for c in conditions]
    #         if 'Failed' in statuses:
    #             # Maybe we should log something? Dunno...
    #             break
    #         if 'Complete' in statuses:
    #             break
    #         sleep(4)


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
        """Returns the Pod UID"""
        if not self.pod_name:
            return None  # Handle case where pod_name is not set yet

        try:
            # Retrieve the Pod object by name
            pod_obj = self.core_v1.read_namespaced_pod(namespace=self.namespace, name=self.pod_name)
            return pod_obj.metadata.uid
        except Exception as e:
            print(f"Error occurred while fetching Pod: {e}")
            return None

    # def get_logs(self):
    #     """Returns the logs for the container"""
    #     logdict = self.pod.logs()
    #     return list(logdict.values())[0]

def finalize(self):
        """Final cleanup and writeout

        Should copy files back to the local paths and remove container if
        no_kill not set
        """
        if not self.pod_name:
            print("Pod name is not set. Finalize operation cannot proceed.")
            return

        try:
            # Copy files from Pod to local paths
            for local_path, container_path in self.volumes:
                command = ["kubectl", "cp", f"{self.pod_name}:{container_path}", local_path]
                subprocess.run(command, check=True)

            # Delete Job if no_kill is not set
            if not self.no_kill:
                self.batch_v1.delete_namespaced_job(namespace=self.namespace, name=self.pod_name, body=client.V1DeleteOptions())

        except Exception as e:
            print(f"Error occurred during finalize operation: {e}")

runtime_class = KubernetesRuntime
