"""Abstract base classes for runtime classes"""

class BaseRuntime():
    """Abstract base runtime class"""

    def __init__(self, image, command, volumes, no_kill=False, no_create=False,
                 **kwargs):
        """Instantiate the runtime object
        """
        self.image = image
        self.command = command
        self.volumes = volumes
        self.no_kill = no_kill
        if not no_create:
            self.container = self.create(**kwargs)
            assert self.container is not None

    def create(self, **kwargs):
        """Create the container
        """
        raise NotImplementedError(
            "Runtime baseclass create() invoked, must be overridden!")

    def wait(self):
        """Wait the container completion
        """
        raise NotImplementedError(
            "Runtime baseclass wait() invoked, must be overridden!")

    def kill(self):
        """Kill the container
        """
        raise NotImplementedError(
            "Runtime baseclass kill() invoked, must be overridden!")

    def get_container_id(self):
        """Returns the container identifier
        """
        raise NotImplementedError(
            "Runtime baseclass get_container_id() invoked, "
            "must be overridden!")

    def get_logs(self):
        """Returns logs for the container
        """
        raise NotImplementedError(
            "Runtime baseclass get_logs() invoked, "
            "must be overridden!")

    def finalize(self):
        """Final cleanup and writeout

        Should copy files back to their local paths and remove container if
        no_kill not set
        """
        raise NotImplementedError(
            "Runtime baseclass finalize() invoked, "
            "must be overridden!")

# In an implemented module, this should be set to the defined class.
runtime_class = None
