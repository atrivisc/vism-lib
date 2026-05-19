"""Base controller class for VISM components."""

import asyncio
from datetime import datetime
from typing import Coroutine

import aio_pika
from aio_pika.abc import AbstractRobustChannel, AbstractRobustConnection

from vism_lib.config import shared_logger, DataExchange, VismConfig
from vism_lib.database import VismDatabase
from vism_lib.logs import setup_logger, SensitiveDataFilter
from vism_lib.rabbitmq import RabbitMQClient
from vism_lib.s3 import AsyncS3Client


class Controller:
    """Base controller class for managing modules and configuration."""
    HEARTBEAT_INTERVAL: int = 30
    RETRY_INTERVAL: int = 30

    configClass = VismConfig
    databaseClass = VismDatabase

    def __init__(self):
        self.config: VismConfig = self.configClass.read_config()
        self.setup_logging()
        self.database = self.databaseClass(self.config.database)
        self.s3 = AsyncS3Client(self.config.s3)
        self.data_exchange_module = None

        self.rabbitmq_client = RabbitMQClient(
            self.config.rabbitmq.leader_queue,
            host=self.config.rabbitmq.host,
            port=self.config.rabbitmq.port,
            user=self.config.rabbitmq.user,
            password=self.config.rabbitmq.password,
            vhost=self.config.rabbitmq.vhost,
        )

        self._rabbitmq_channel: AbstractRobustChannel | None = None
        self._rabbitmq_connection: AbstractRobustConnection | None = None

        self.is_leader = False
        self._shutdown_event = asyncio.Event()

    def __post_init__(self):
        self.setup_logging()

    def setup_logging(self):
        """Set up logging configuration."""
        shared_logger.info("Setting up logging")
        setup_logger(self.config.logging)

    def shutdown(self):
        """Initiates shutdown of the CA."""
        shared_logger.info("Received shutdown signal, shutting down")
        self._shutdown_event.set()

    async def setup_data_exchange_module(self) -> DataExchange:
        """Set up the data exchange module from configuration."""
        data_exchange_module_imports = __import__(
            f'modules.{self.config.security.data_exchange.module}',
            fromlist=['Module', 'ModuleConfig']
        )

        SensitiveDataFilter.SENSITIVE_PATTERNS.update(
            data_exchange_module_imports.LOGGING_SENSITIVE_PATTERNS
        )

        self.data_exchange_module = data_exchange_module_imports.Module(self)
        return self.data_exchange_module

    @staticmethod
    async def leader_heartbeat() -> None:
        now = datetime.now().strftime("%H:%M:%S")
        shared_logger.info(f"I am the leader — heartbeat at {now}")

    @staticmethod
    async def follower_heartbeat() -> None:
        shared_logger.info("Nothing to do — I am secondary")

    async def try_become_leader(self) -> bool:
        try:
            if not self._rabbitmq_connection or self._rabbitmq_connection.is_closed:
                self._rabbitmq_connection = await self.rabbitmq_client.get_connection()
            if not self._rabbitmq_channel or self._rabbitmq_channel.is_closed:
                self._rabbitmq_channel = await self._rabbitmq_connection.channel(on_return_raises=True)

            queue = await self._rabbitmq_channel.declare_queue(
                self.config.rabbitmq.leader_queue,
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
            if self._rabbitmq_channel and not self._rabbitmq_channel.is_closed:
                await self._rabbitmq_channel.close()
            return False

    async def _on_leader_message(self, _) -> None:
        pass # we don't care about messages here

    async def resign(self, resign_callback: Coroutine = None) -> None:
        if self.is_leader:
            shared_logger.info("Resigning as leader.")
            self.is_leader = False

        if not self._rabbitmq_channel.is_closed:
            await self._rabbitmq_channel.close()
        if not self._rabbitmq_connection.is_closed:
            await self._rabbitmq_connection.close()

        await resign_callback

    async def elect_leader_loop(self, resign_callback: Coroutine = None, leader_callback: Coroutine = None, follower_callback: Coroutine = None) -> None:
        try:
            while not self._shutdown_event.is_set():
                if not self.is_leader:
                    won = await self.try_become_leader()
                    if not won:
                        await self.follower_heartbeat()
                        await leader_callback
                        await asyncio.sleep(self.RETRY_INTERVAL)
                else:
                    if self._rabbitmq_channel and self._rabbitmq_channel.is_closed:
                        shared_logger.warning("Lost leader channel — re-entering election")
                        self.is_leader = False
                        continue

                    await self.leader_heartbeat()
                    await follower_callback
                    await asyncio.sleep(self.HEARTBEAT_INTERVAL)
        except Exception as e:
            shared_logger.error(f"Stopping rabbitmq leadership loop: {e}")
        finally:
            await self.resign(resign_callback)
