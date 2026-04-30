"""Shared configuration classes for VISM components."""

import logging
from dataclasses import field
from pydantic import field_validator
from pydantic.dataclasses import dataclass
from yaml_dataclass import YamlConfigCached

from lib.logs import LoggingConfig

shared_logger = logging.getLogger("vism_shared")

@dataclass
class DatabaseConfig:
    """Database connection configuration."""

    data_validation_key: str
    host: str
    port: int
    database: str
    username: str
    password: str
    driver: str = "postgresql+psycopg2"

    @field_validator("host")
    @classmethod
    def host_must_be_valid(cls, v):
        if not v:
            raise ValueError("database host can not be empty.")

        return v

    @field_validator("port")
    @classmethod
    def port_must_be_valid(cls, v):
        """Validate that port is in valid range."""
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

@dataclass
class DataExchange:
    """Configuration for data exchange module."""

    module: str
    validation_key: str = None

@dataclass
class Security:
    """Security configuration including validation and encryption."""

    data_exchange: DataExchange = None
    chroot_base_dir: str = None

@dataclass
class S3Config:
    """Configuration for s3."""

    bucket: str
    endpoint: str
    access_key: str
    secret_key: str
    region: str = ""

@dataclass
class VismConfig(YamlConfigCached):
    """Base configuration class for VISM components."""

    security: Security = field(default_factory=Security)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    database: DatabaseConfig = None
    s3: S3Config = None
