import asyncio
import logging
from datetime import datetime
import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel
from aiormq import AMQPConnectionError
from vism_lib.errors import VismException

shared_logger = logging.getLogger("vism_shared")

class RabbitMQError(VismException):
    """Raised when a RabbitMQ error occurs."""

class RabbitMQClient:

    def __init__(self, leader_queue: str, host: str, port: int, user: str, password: str, vhost: str = "/"):
        self.leader_queue = leader_queue

        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.vhost = vhost

    async def get_connection(self) -> AbstractRobustConnection:
        try:
            return await aio_pika.connect_robust(
                host=self.host,
                port=self.port,
                login=self.user,
                password=self.password,
                virtualhost=self.vhost,
                heartbeat=30,
            )
        except AMQPConnectionError as e:
            raise RabbitMQError(
                f"Failed to connect to RabbitMQ: {e}"
            ) from e
