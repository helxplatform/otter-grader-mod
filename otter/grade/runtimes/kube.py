"""Runtime based on Kubernetes that k8s client
"""

import os
from time import sleep
import subprocess

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

from ._base import BaseRuntime
from ..utils import OTTER_DOCKER_IMAGE_NAME
from ...utils import loggers

LOGGER = loggers.get_logger(__name__)

class KubeRuntime(BaseRuntime):
    """Class for executing grader in Openshift containers
    """

    def __init__(self, *args, **kwargs):
        """Instantiate runtime object
        """

        super().__init__(*args, no_create=True, **kwargs)
        self.config = config.load_incluster_config()
        self.api_instance = client.CoreV1Api()
        self.batch_v1 = client.BatchV1Api()
        self.core_v1 = client.CoreV1Api()
        self.secret_name = kwargs.get('secret_name',
                                      'harbor')
        self.namespace = self._get_current_namespace
        self.repo = os.environ.get(
            'OTTERGRADER_REPO_NAME',
            'containers.renci.org/helxplatform/ottergrader')
        self.image_spec = self.repo + "/" + self.image
        self.pod_name = None
        if not kwargs.get('no_create', False):
            self.create()

    # Issues with this
    def _get_current_namespace(self):
        """Get the name of the current namespace or project"""
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r") as secrets:
                for line in secrets:
                    namespace = line
        LOGGER.info(f"checking downwardapi for namespace: {line}")
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
        # command=["sh", "-c", 'until [ -f /tmp/.ottergrader_ready ]; do echo "waiting ready file"; sleep 2; done;'],
        # Define init containers
        init_containers = [
            client.V1Container(
                name="init-filewait",
                image="busybox:latest",
                command = ["sh", "-c", 'echo "Init container started - waiting on build"; sleep 20'], 
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
        # image=self.image_spec,
        containers = [
            client.V1Container(
                name=OTTER_DOCKER_IMAGE_NAME,
                image="containers.renci.org/helxplatform/ottergrader/otter-grade:d42c6de",
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
        config.load_incluster_config()
        core_v1 = client.CoreV1Api()
        batch_v1 = client.BatchV1Api()
        job = self._create_jobspec()
        created_job = batch_v1.create_namespaced_job(
            body=job,
            namespace=self.namespace
        )
        # Wait for Pod to be created
        while not self.pod_name:
            try:
                # Get Pod associated with the Job
                pods = core_v1.list_namespaced_pod(namespace=self.namespace, label_selector=f"job-name={created_job.metadata.name}")
                if pods.items:
                    self.pod_name = pods.items[0].metadata.name
            except Exception as e:
                LOGGER.error(f"Error occurred while fetching Pod: {e}")

            if not self.pod_name:
                sleep(1)
        LOGGER.info(f"Pod has been created {self.pod_name}")
        # call wait in order to ensure job/pods are launched
        

    @property
    def pod(self):
        return self.pod_name

    @property
    def job(self):
        """Return the job APIObject"""
        config.load_incluster_config()
        batch_v1 = client.BatchV1Api()
        if not self.pod_name:
            return None  # Handle case where pod_name is not set yet

        try:
            # Retrieve the Job object by name
            job_obj = batch_v1.read_namespaced_job(namespace=self.namespace, name=self.pod_name)
            return job_obj
        except Exception as e:
            LOGGER.error(f"Error occurred while fetching Job: {e}")
            return None


    def wait(self): 
        """Wait for the container to complete"""
        config.load_incluster_config()
        batch_v1 = client.BatchV1Api()
        while True:
            try:
                # Fetch the Job object associated with self.pod_name
                job_obj = batch_v1.read_namespaced_job(namespace=self.namespace, name=self.pod_name)
                conditions = job_obj.status.conditions
                
                if not conditions:
                    sleep(10)  # Wait a bit before checking again
                    continue
                
                statuses = [c.type for c in conditions]
                
                if 'Failed' in statuses:
                    LOGGER.error(f"Job {self.pod_name} has failed.")
                    break
                elif 'Complete' in statuses:
                    LOGGER.info(f"Job {self.pod_name} has completed successfully.")
                    break
                else:
                    LOGGER.info(f"Job {self.pod_name} is still running. Status: {statuses}")
                
                sleep(10)
            except Exception as e:
                LOGGER.error(f"Error occurred while waiting for Job {self.pod_name}: {e}")
                break

    def kill(self):
        """Kill the container by deleting the Job"""
        config.load_incluster_config()
        batch_v1 = client.BatchV1Api()
        try:
            # Delete the Job associated with self.pod_name
            batch_v1.delete_namespaced_job(
                namespace=self.namespace,
                name=self.pod_name,
                body=client.V1DeleteOptions()
            )
            LOGGER.info(f"Job {self.pod_name} has been deleted.")
        except Exception as e:
            LOGGER.error(f"Error occurred while deleting Job {self.pod_name}: {e}")

    def get_container_id(self):
        """Returns the Pod UID"""
        config.load_incluster_config()
        core_v1 = client.CoreV1Api()
        if not self.pod_name:
            return None  # Handle case where pod_name is not set yet
        try:
            pod_obj = core_v1.read_namespaced_pod(namespace=self.namespace, name=self.pod_name)
            return pod_obj.metadata.uid
        except Exception as e:
            LOGGER.error(f"Error occurred while fetching Pod: {e}")
            return None

    def get_logs(self):
        """Retrieve logs from all containers in the Pod"""
        config.load_incluster_config()
        core_v1 = client.CoreV1Api()
        try:
            # Fetch logs from all containers in the Pod
            logs = core_v1.read_namespaced_pod_log(
                namespace=self.namespace,
                name=self.pod_name,
                container=self.pod_name,
                tail_lines=100 
            )
            return logs
        except Exception as e:
            LOGGER.error(f"Error occurred while fetching logs for Pod {self.pod_name}: {e}")
            return None

    # use if kubectl doesn't work directly
    def copy_files_between_pods(self, source_pod_name, source_container_name, source_path, destination_pod_name, destination_container_name, destination_path):
        config.load_incluster_config()
        api_instance = client.CoreV1Api()
        try:
            # Copy files from source pod
            resp = api_instance.connect_get_namespaced_pod_exec(
                name=source_pod_name,
                namespace=self.namespace,
                command=['/bin/sh', '-c', f'kubectl cp {source_pod_name}:{source_path} {destination_pod_name}:{destination_path}'],
                container=source_container_name,
                stderr=True, stdin=True,
                stdout=True, tty=False
            )
            LOGGER.info("File copied successfully")
            LOGGER.info(resp)
        except ApiException as e:
            LOGGER.error("Exception when calling CoreV1Api->connect_get_namespaced_pod_exec: %s\n" % e)

    def finalize(self):
        """Final cleanup and writeout

        Should copy files back to the local paths and remove container if
        no_kill not set
        """
        config.load_incluster_config()
        batch_v1 = client.BatchV1Api()
        if not self.pod_name:
            LOGGER.info("Pod name is not set. Finalize operation cannot proceed.")
            return

        try:
            for local_path, container_path in self.volumes:
                command = ["oc", "cp", f"{self.pod_name}:{container_path}", local_path]
                subprocess.run(command, check=True)

            # Delete Job if no_kill is not set
            if not self.no_kill:
                batch_v1.delete_namespaced_job(namespace=self.namespace, name=self.pod_name, body=client.V1DeleteOptions())

        except Exception as e:
            LOGGER.error(f"Error occurred during finalize operation: {e}")

runtime_class = KubeRuntime
