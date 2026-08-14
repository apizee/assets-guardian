import logging
from typing import Any

from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.registry.pdf_builder_registry import PDFBuilderRegistry
from assets_guardian.core.reporting.pdf.writer import PDFWriter
from assets_guardian.utils.dates import add_date_to_filename

logger = logging.getLogger(__name__)


class PdfEngine:
    """Engine responsible for generating the audit PDF report."""

    def generate(self, data: Any, ctx: Context, output_path: str | None = None) -> None:
        """Generates the audit PDF report from the audit findings.

        Args:
            data: Audit results (dictionary or iterable of Report).
            ctx: The application context.
            output_path: Destination path for the PDF. If not provided, it is
                computed from the configured path with today's date inserted.
        """
        builders = PDFBuilderRegistry.get_builders()

        pdf_writer = PDFWriter(
            pdf_builders=builders,
            rules_file_path=ctx.app_config.paths.pdf_config.clean_path,
            author_fullname=ctx.app_config.author.fullname,
            author_email=ctx.app_config.author.email,
        )

        if output_path is None:
            output_path = add_date_to_filename(ctx.app_config.paths.pdf.clean_path)

        reports = data.values() if isinstance(data, dict) else data

        logger.info("Launching PDF report generation...")
        pdf_writer.write(reports, output_path)
        logger.info("PDF report generation completed successfully.")
