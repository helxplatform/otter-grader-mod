"""Runtime based on OpenShift that uses `oc`-style API
"""

import yaml
from kubernetes import client, config
from openshift.dynamic import DynamicClient
from ._base import BaseRuntime


class OpenshiftRuntime(BaseRuntime):
    """Class for executing grader in Openshift containers
    """

    def __init__(self, *args, **kwargs):
        """Instantiate runtime object
        """

        super().__init__(*args, **kwargs)
        self.k8s_client = config.new_client_from_config()
        self.dyn_client = DynamicClient(self.k8s_client)

        self.deployment_config = {
            "apiVersion": "apps.openshift.io/v1",
            "kind": "DeploymentConfig",
            "metadata": {
                "name": "otter-grade",
                "namespace": namespace
            },
            "spec": {
                "replicas": 1,
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "otter-grade"
                        }
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "otter-grade",
                                "image": self.image,
                                "ports": [
                                    {
                                        "containerPort": 3000
                                    }
                                ]
                            }
                        ]
                    }
                },
                "triggers": [
                    {
                        "type": "ConfigChange"
                    },
                ]
            }
        }

    def create(self, **kwargs):
        """Create the container"""

    def start(self):
        """Starts the container"""

    def wait(self):
        """Wait the container completion"""

    def kill(self):
        """Kill the container"""

    def get_container_id(self):
        """Returns the container identifier"""

    def get_logs(self):
        """Returns the logs for the container"""

    def finalize(self):
        """Final cleanup and writeout

        Should copy files back to the local paths and remove container if
        no_kill not set
        """

runtime_class = OpenshiftRuntime
