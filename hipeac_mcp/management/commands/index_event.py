"""Management command to index event activities into FAISS."""

import asyncio
import logging

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand

from hipeac_mcp.models.events import Event
from hipeac_mcp.services.rags.events import EventRagService


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Django management command to index event data.

    Generates synthetic documents from event activities and indexes
    them into the FAISS vector store for semantic search.
    """

    help = "Index event activities into FAISS vector store"

    def add_arguments(self, parser):
        """Add command arguments.

        :param parser: ArgumentParser instance.
        """
        parser.add_argument(
            "--event-id",
            type=int,
            required=True,
            help="Event ID to index (e.g., 6816 for HiPEAC 2026)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force reindex (clears existing index for this event)",
        )

    def handle(self, *args, **options):
        """Execute the command.

        :param args: Positional arguments.
        :param options: Command options.
        """
        asyncio.run(self.async_handle(**options))

    async def async_handle(self, **options):
        """Async implementation of the indexing logic.

        :param options: Command options.
        """
        event_id = options["event_id"]
        force = options.get("force", False)

        try:
            event = await sync_to_async(Event.objects.get)(id=event_id)
        except Event.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Event not found: {event_id}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Indexing event: {event.name} (ID: {event.id})"))
        self.stdout.write(f"Type: {event.type}")
        self.stdout.write(f"Dates: {event.start_date} to {event.end_date}")
        self.stdout.write(f"Location: {event.city}, {event.country}")

        service = EventRagService(event_id=event.id)

        if force:
            self.stdout.write(self.style.WARNING("Force reindex enabled — clearing existing index"))
            service.reset_index()

        success = await service.index_event(event)

        if success:
            self.stdout.write(self.style.SUCCESS(f"Successfully indexed event {event.name}"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed to index event {event.name}"))
