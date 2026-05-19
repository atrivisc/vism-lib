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
    HEARTBEAT_INTERVAL: int = 30
    RETRY_INTERVAL: int = 30

    def __init__(self, leader_queue: str, host: str, port: int, user: str, password: str, vhost: str = "/"):
        self.leader_queue = leader_queue

        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.vhost = vhost

        self.is_leader = False

        self._channel: AbstractRobustChannel | None = None
        self._connection: AbstractRobustConnection | None = None
        self._stop_event = asyncio.Event()

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

    @staticmethod
    async def leader_heartbeat() -> None:
        now = datetime.now().strftime("%H:%M:%S")
        shared_logger.info(f"I am the leader — heartbeat at {now}")

    @staticmethod
    async def follower_heartbeat() -> None:
        shared_logger.info("Nothing to do — I am secondary")

    async def try_become_leader(self) -> bool:
        try:
            if not self._connection or self._connection.is_closed:
                self._connection = await self.get_connection()
            if not self._channel or self._channel.is_closed:
                self._channel = await self._connection.channel(on_return_raises=True)

            queue = await self._channel.declare_queue(
                self.leader_queue,
                exclusive=True,
                auto_delete=True,
                durable=False,
            )

            await queue.consume(self._on_leader_message, no_ack=True)
            self.is_leader = True
            shared_logger.info("Won the election — I am now the leader")
            return True
        except aio_pika.exceptions.ChannelPreconditionFailed:
            return False
        except Exception as e:
            shared_logger.debug(f"Lost election round: {e}")
            if self._channel and not self._channel.is_closed:
                await self._channel.close()
            return False

    async def _on_leader_message(self, _) -> None:
        pass # we don't care about messages here

    async def resign(self) -> None:
        if self.is_leader and self._channel and not self._channel.is_closed:
            shared_logger.info("Resigning as leader.")
            if not self._channel.is_closed:
                await self._channel.close()
            self.is_leader = False

    async def run_leadership(self) -> None:
        try:
            while not self._stop_event.is_set():
                if not self.is_leader:
                    won = await self.try_become_leader()
                    if not won:
                        await self.follower_heartbeat()
                        await asyncio.sleep(self.RETRY_INTERVAL)
                else:
                    if self._channel and self._channel.is_closed:
                        shared_logger.warning("Lost leader channel — re-entering election")
                        self.is_leader = False
                        continue

                    await self.leader_heartbeat()
                    await asyncio.sleep(self.HEARTBEAT_INTERVAL)
        except Exception as e:
            shared_logger.error(f"Stopping rabbitmq leadership loop: {e}")
            await self.resign()
            self._stop_event.set()

    def stop(self) -> None:
        self._stop_event.set()
