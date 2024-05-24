"""Default local docker executor for grade containers"""

from python_on_whales import docker

class DockerRuntime():
    """Class for executing grader in the default Docker container runtime

    Ideally, can be subclassed with specific methods overridden to allow
    alternate runtimes to be used.
    """

    def __init__(self, image, command, volumes, no_kill=False, **kwargs):
        """Instantiate the runtime object
        """
        self.image = image
        self.command = command
        self.volumes = volumes
        self.no_kill = no_kill
        self.container = self.create(**kwargs)
        assert self.container is not None

    def create(self, **kwargs):
        """Use the defined runtime environment to create the container
        """
        container = docker.container.create(self.image, self.command,
                                            **kwargs)
        for local_path, container_path in self.volumes:
            docker.container.copy(local_path, (container, container_path))
        return container

    def start(self):
        """Starts the container
        """
        docker.container.start(self.container)

    def wait(self):
        """Wait for completion of the container process, returns rval
        """
        return docker.container.wait(self.container)

    def kill(self):
        """Kills a running container
        """
        docker.container.kill(self.container)

    def get_container_id(self):
        "Returns the container identifier"
        return self.container.id[:12]

    def get_logs(self):
        "Returns logfile output"
        return docker.container.logs(self.container)

    def finalize(self):
        "Copies files back to local paths"
        for local_path, container_path in self.volumes:
            docker.container.copy((self.container, container_path), local_path)

        if not self.no_kill:
            self.container.remove()

runtime_class = DockerRuntime
