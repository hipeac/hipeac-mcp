"""Management command to test event document generation."""

import asyncio
import logging

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand

from hipeac_mcp.models.events import Event
from hipeac_mcp.services.rags.events import EventDocumentGenerator


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Django management command to test event document generation.

    This command generates a synthetic document for an event to preview
    what will be indexed in the vector store.
    """

    help = "Generate a synthetic document from an event for preview"

    def add_arguments(self, parser):
        """Add command arguments.

        :param parser: ArgumentParser instance.
        """
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--event-id",
            type=int,
            help="Event ID (e.g., 6816)",
        )
        group.add_argument(
            "--slug",
            type=str,
            help="Event slug (e.g., acaces-2025)",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Event year (optional, for disambiguation)",
        )
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Output file path (default: prints to stdout)",
        )

    def handle(self, *args, **options):
        """Execute the command.

        :param args: Positional arguments
        :param options: Command options
        """
        asyncio.run(self.async_handle(**options))

    async def async_handle(self, **options):
        """Async implementation of document generation.

        :param options: Command options.
        """
        event_id = options.get("event_id")
        slug = options.get("slug")
        year = options.get("year")
        output_path = options.get("output")

        identifier = str(event_id) if event_id else slug
        self.stdout.write(self.style.SUCCESS(f"Generating document for event: {identifier}"))

        try:
            if event_id:
                event = await sync_to_async(Event.objects.get)(id=event_id)
            elif year:
                event = await sync_to_async(Event.objects.get)(slug=slug, start_date__year=year)
            else:
                event = await sync_to_async(Event.objects.get)(slug=slug)
        except Event.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Event not found: {slug}"))
            return
        except Event.MultipleObjectsReturned:
            self.stdout.write(self.style.ERROR(f"Multiple events found for slug '{slug}'. Please specify --year."))
            return

        self.stdout.write(f"Event: {event.name}")
        self.stdout.write(f"Type: {event.type}")
        self.stdout.write(f"Dates: {event.start_date} to {event.end_date}")
        self.stdout.write(f"Location: {event.city}, {event.country}")
        self.stdout.write("")

        generator = EventDocumentGenerator()
        chunks = await generator.generate_chunks(event)

        self.stdout.write(f"Generated {len(chunks)} chunks")
        self.stdout.write("")

        if output_path:
            with open(output_path, "w") as f:
                for i, chunk in enumerate(chunks):
                    f.write(f"\n{'=' * 80}\n")
                    f.write(f"CHUNK {i + 1}/{len(chunks)}\n")
                    f.write(f"Type: {chunk['metadata'].get('document_type', 'unknown')}\n")
                    if chunk["metadata"].get("activity_type"):
                        f.write(f"Activity: {chunk['metadata']['activity_type']}\n")
                    f.write(f"Size: {len(chunk['content'])} characters\n")
                    f.write(f"{'=' * 80}\n\n")
                    f.write(chunk["content"])
            self.stdout.write(self.style.SUCCESS(f"Chunks saved to: {output_path}"))
        else:
            for i, chunk in enumerate(chunks):
                self.stdout.write(f"\n{'=' * 80}")
                self.stdout.write(f"CHUNK {i + 1}/{len(chunks)}")
                self.stdout.write(f"Type: {chunk['metadata'].get('document_type', 'unknown')}")
                if chunk["metadata"].get("activity_type"):
                    self.stdout.write(f"Activity: {chunk['metadata']['activity_type']}")
                self.stdout.write(f"Size: {len(chunk['content'])} characters")
                self.stdout.write(f"{'=' * 80}\n")
                self.stdout.write(chunk["content"])

        total_size = sum(len(chunk["content"]) for chunk in chunks)
        self.stdout.write(f"\nTotal size: {total_size} characters across {len(chunks)} chunks")
