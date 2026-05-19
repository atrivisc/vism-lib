"""Data vault storage module."""
from abc import abstractmethod, ABCMeta
from pydantic.dataclasses import dataclass
from yaml_dataclass import YamlConfigCached


@dataclass
class VaultConfig(YamlConfigCached):
    """Base class for vault module configuration."""


class Vault(metaclass=ABCMeta):
    """Base class for vault storage modules."""
    configClass = VaultConfig

    def __init__(self):
        self.config = self.configClass.read_config()

    @abstractmethod
    def get_secret(self, secret_path: str) -> str:
        """Get secret from a vault."""

    @abstractmethod
    def put_secret(self, secret_path: str, secret_value: bytes) -> None:
        """Put a secret into a vault."""
