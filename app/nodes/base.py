from typing import Any, Literal


class BaseNode:
    """Base Node abstraction with minimal lifecycle and output handling."""

    def __init__(self, id: str, name: str, type: Literal["trigger", "action"]) -> None:
        self.id = id
        self.name = name
        self.type = type
        self.isActive = False
        self.outputData: Any = None
        self.inputData: Any = None

    def execute(self) -> Any:
        """Executes the node's main function."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stops the node."""
        self.isActive = False

    def getOutput(self) -> Any:
        """Returns the data produced by this node."""
        return self.outputData

    def setOutput(self, data: Any) -> None:
        """Sets the data to pass to the next node."""
        self.outputData = data