"""Management command to index Vision articles into FAISS."""

import asyncio
import logging

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand

from hipeac_mcp.models.vision import VisionArticle
from hipeac_mcp.services.rags import VisionRagService


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Django management command to index Vision articles.

    This command fetches all published Vision articles from the database and
    indexes them into the FAISS vector store for semantic search.
    """

    help = "Index Vision articles into FAISS vector store"

    def add_arguments(self, parser):
        """Add command arguments.

        :param parser: ArgumentParser instance
        """
        parser.add_argument(
            "--year",
            type=int,
            default=2025,
            help="Vision year to index (default: 2025)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of articles to index (for testing)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force reindex all articles (clears existing index)",
        )

    def handle(self, *args, **options):
        """Execute the command.

        :param args: Positional arguments
        :param options: Command options
        """
        asyncio.run(self.async_handle(**options))

    async def async_handle(self, **options):
        """Async implementation of the indexing logic.

        :param options: Command options
        """
        year = options.get("year", 2025)
        limit = options.get("limit")
        force = options.get("force", False)

        self.stdout.write(self.style.SUCCESS(f"Starting Vision {year} indexing process..."))

        service = VisionRagService(year=year)

        if force:
            self.stdout.write(self.style.WARNING("Force reindex enabled - clearing existing index"))

        queryset = VisionArticle.objects.filter(section__vision__year=year).select_related("section__vision")
        if limit:
            queryset = queryset[:limit]

        total = await sync_to_async(queryset.count)()
        self.stdout.write(f"Found {total} articles for Vision {year}")

        indexed = 0
        failed = 0

        async for article in queryset:
            try:
                self.stdout.write(f"Indexing: {article.slug} ({article.title[:50]}...)")
                await service.index_article(article)
                indexed += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Indexed ({indexed}/{total})"))
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  ✗ Failed: {e}"))
                logger.error(f"Failed to index article {article.slug}: {e}")

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS(f"Vision {year} indexing complete!"))
        self.stdout.write(f"  Total articles: {total}")
        self.stdout.write(f"  Successfully indexed: {indexed}")
        if failed > 0:
            self.stdout.write(self.style.ERROR(f"  Failed: {failed}"))
        self.stdout.write("=" * 60)
