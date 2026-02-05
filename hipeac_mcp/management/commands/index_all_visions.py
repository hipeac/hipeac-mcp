"""Management command to index all Vision years."""

import asyncio
import logging
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand

from hipeac_mcp.models.vision import Vision, VisionArticle
from hipeac_mcp.services.rags import VisionRagService


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Django management command to index all available Vision years.

    Discovers all Vision years from the database and indexes each one
    that isn't already indexed. Skips years that have already been indexed.
    """

    help = "Index all available Vision years into FAISS vector store"

    def add_arguments(self, parser):
        """Add command arguments.

        :param parser: ArgumentParser instance
        """
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force reindex all years (clears existing indexes)",
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
        force = options.get("force", False)

        self.stdout.write(self.style.SUCCESS("Discovering available Vision years..."))

        vision_years = [vision.year async for vision in Vision.objects.all().order_by("-year")]

        if not vision_years:
            self.stdout.write(self.style.WARNING("No Vision years found in database"))
            return

        self.stdout.write(f"Found {len(vision_years)} Vision year(s): {', '.join(map(str, vision_years))}")

        total_indexed = 0
        total_skipped = 0
        total_failed = 0

        for year in vision_years:
            index_path = Path(settings.FAISS_INDEX_PATH) / f"vision_articles_{year}.index"

            if index_path.exists() and not force:
                self.stdout.write(f"Vision {year}: Already indexed (skipping)")
                total_skipped += 1
                continue

            self.stdout.write(f"\nVision {year}: Starting indexing...")

            service = VisionRagService(year=year)
            queryset = VisionArticle.objects.filter(section__vision__year=year).select_related("section__vision")

            total_articles = await sync_to_async(queryset.count)()

            if total_articles == 0:
                self.stdout.write(self.style.WARNING(f"  No articles found for Vision {year}"))
                total_skipped += 1
                continue

            self.stdout.write(f"  Found {total_articles} articles")

            indexed = 0
            failed = 0

            async for article in queryset:
                try:
                    await service.index_article(article)
                    indexed += 1

                    if indexed % 10 == 0 or indexed == total_articles:
                        self.stdout.write(f"  Progress: {indexed}/{total_articles} articles")
                except Exception as e:
                    failed += 1
                    logger.error(f"Failed to index article {article.slug}: {e}")

            if failed > 0:
                self.stdout.write(self.style.WARNING(f"  Completed with errors: {indexed} indexed, {failed} failed"))
                total_failed += 1
            else:
                self.stdout.write(self.style.SUCCESS(f"  ✓ Successfully indexed all {indexed} articles"))
                total_indexed += 1

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("All Vision years processed"))
        self.stdout.write(f"  Indexed: {total_indexed}")
        self.stdout.write(f"  Skipped: {total_skipped}")
        if total_failed > 0:
            self.stdout.write(self.style.ERROR(f"  Failed: {total_failed}"))
        self.stdout.write("=" * 60)
