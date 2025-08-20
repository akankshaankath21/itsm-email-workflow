from typing import Any, Literal


class BaseNode:

    def __init__(self, id: str, name: str, type: Literal["trigger", "action"]) -> None:
        self.id = id
        self.name = name
        self.type = type
        self.isActive = False
        self.outputData: Any = None
        self.inputData: Any = None

    def execute(self) -> Any:
        raise NotImplementedError

    def stop(self) -> None:
        self.isActive = False

    def getOutput(self) -> Any:
        return self.outputData

    def setOutput(self, data: Any) -> None:
        self.outputData = data