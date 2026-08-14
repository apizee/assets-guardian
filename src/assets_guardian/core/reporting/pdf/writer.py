import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from assets_guardian.core.domain.models.finding import Finding, SeverityType
from assets_guardian.core.domain.models.report import Report
from assets_guardian.core.domain.ports.pdf_builders import IPDFBuilder

from .rules_loader import load_rules

logger = logging.getLogger(__name__)


class AGPDF(FPDF):
    """Custom PDF class for Assets Guardian (Header, Footer, TOC)."""

    def __init__(self, document_title: str, rules: dict[str, Any] | None = None):
        super().__init__()
        self._document_title = document_title
        self._toc: list[Any] = []
        self.rules = rules or {}
        self.settings = self.rules.get("settings", {})
        self.set_auto_page_break(auto=True, margin=15)

    def draw_checkbox(self) -> None:
        """Draws a checkbox according to dynamic settings."""
        if not self.settings.get("show_checkboxes", True):
            return

        size = self.settings.get("checkbox_size", 3.5)
        x, y = self.get_x(), self.get_y()
        self.rect(x, y + 1, size, size)
        self.set_x(x + size + 2)

    def apply_font(self, font_name: str) -> None:
        """Applies a font defined in the rules (title, subtitle, etc.)."""
        font_data = self.rules.get("fonts", {}).get(font_name)
        if font_data:
            self.set_font(**font_data)

    def get_current_date(self) -> datetime:
        """Returns the current date/time according to the configured timezone."""
        tz_name = self.settings.get("timezone", "UTC")
        try:
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            # Fallback to UTC if the timezone is invalid
            return datetime.now(UTC)

    def header(self) -> None:
        """Document header."""
        if self.page_no() == 1:
            return
        self.set_font("helvetica", style="B", size=10)
        self.cell(110, 10, self._document_title, align="L")
        date_str = self.get_current_date().strftime("%d/%m/%Y %H:%M")
        self.cell(0, 10, date_str, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)

    def footer(self) -> None:
        """Document footer."""
        self.set_y(-15)
        self.set_font("helvetica", style="", size=8)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def add_toc_entry(self, title: str) -> int:
        """Adds an entry to the TOC and returns a link."""
        link = self.add_link()
        self._toc.append({"title": title, "page": self.page_no(), "link": link})
        return link

    def insert_toc(self) -> None:
        """Populates the table of contents on the current page."""
        self.set_y(40)  # Make sure we start below the header
        self.set_font("helvetica", "B", 16)
        self.cell(0, 10, "Table of Contents", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)
        self.set_font("helvetica", "", 12)

        for entry in self._toc:
            title = entry["title"]
            page = str(entry["page"])
            link = entry["link"]

            w_title = self.get_string_width(title)
            w_page = self.get_string_width(page)
            w_dots = self.w - self.l_margin - self.r_margin - w_title - w_page - 10

            dots = "." * int(w_dots / self.get_string_width("."))

            # Make the entire line clickable
            self.cell(w_title, 10, title, border=0, align="L", link=link)
            self.cell(w_dots, 10, dots, border=0, align="C", link=link)
            self.cell(
                w_page,
                10,
                page,
                border=0,
                align="R",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
                link=link,
            )

    def render_findings(self, findings: Iterable[Finding]) -> None:
        """Grouped rendering of findings by severity with indentation."""
        by_severity = defaultdict(list)
        for f in findings:
            by_severity[f.severity].append(f)

        for severity in [
            SeverityType.CRITICAL,
            SeverityType.DANGER,
            SeverityType.WARNING,
            SeverityType.INFO,
        ]:
            severity_findings = by_severity[severity]
            if not severity_findings:
                continue

            # Severity title (the block)
            color = self.rules["colors"].get(severity, self.rules["colors"]["text"])
            self.set_text_color(color["r"], color["g"], color["b"])
            self.apply_font("severity")
            self.cell(0, 10, severity, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)
            self.set_text_color(0, 0, 0)

            # Indent the findings block
            original_margin = self.l_margin
            self.set_left_margin(original_margin + 10)

            for finding in severity_findings:
                self.apply_font("body")

                if self.will_page_break(15):
                    self.add_page()
                self.draw_checkbox()

                # ID and Title
                self.set_font(style="B")
                self.write(5, f"[{finding.rule_id}] ")
                self.set_font(style="")
                self.write(5, f"{finding.title}")

                # Impacted entities (placed BEFORE description on the same line)
                if finding.entities_impacted:
                    self.set_font(style="I", size=9)
                    impacted = ", ".join(finding.entities_impacted)
                    self.write(5, f" ({impacted})")
                    self.set_font(style="", size=10)

                self.ln(5)

                # Description
                if finding.description:
                    # Clean line breaks and multiple spaces for compact rendering
                    desc = " ".join(finding.description.split())
                    self.apply_font("body")
                    self.multi_cell(0, 5, desc, align="L")
                    self.ln(1)

                self.ln(2)

            # Restore the margin
            self.set_left_margin(original_margin)


class PDFWriter:
    """Concrete PDF audit report generation service."""

    def __init__(
        self,
        pdf_builders: list[IPDFBuilder] | None = None,
        rules_file_path: str | Path | None = None,
        author_fullname: str | None = None,
        author_email: str | None = None,
    ):
        self.builders = {h.source_name: h for h in (pdf_builders or [])}
        self.rules = load_rules(rules_file_path)
        self.author_fullname = author_fullname
        self.author_email = author_email

    def write(self, reports: Iterable[Report], output_path: str | Path) -> None:
        logger.info("Starting PDF report generation: %s", output_path)

        pdf = AGPDF("Assets Guardian - Audit Report", rules=self.rules)
        self.__write_cover(pdf)

        # Reserve page 2 for the table of contents
        pdf.add_page()
        toc_page = pdf.page_no()

        # Statistical summary (uses existing report counters)
        self.__write_summary(pdf, reports)

        # Process each report source-by-source
        for report in reports:
            # Retrieve the first finding to identify the source (loads only one object in RAM)
            first_finding = next(iter(report), None)
            if not first_finding:
                continue

            source_name = first_finding.source
            instance_id = first_finding.instance_id
            pdf.add_page()

            builder = self.builders.get(source_name)
            section_title = builder.section_title if builder else source_name.capitalize()

            # Append the instance if it is not already in the title and is not "unknown"
            if instance_id and instance_id != "unknown" and instance_id not in section_title:
                section_title = f"{section_title} ({instance_id})"

            # Add entry to the TOC
            link = pdf.add_toc_entry(section_title)
            pdf.set_link(link)

            # Render section (streaming read of the report)
            if builder:
                builder.render(pdf, report)
            else:
                self.__default_render(pdf, report, section_title)

        # Return to the reserved page to populate the TOC
        last_page = pdf.page_no()
        pdf.page = toc_page
        pdf.insert_toc()
        pdf.page = last_page

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))
        logger.info("PDF report generated successfully.")

    def __write_cover(self, pdf: AGPDF) -> None:
        pdf.add_page()
        pdf.ln(60)
        pdf.apply_font("title")
        pdf.cell(0, 20, "Assets Guardian", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.apply_font("subtitle")
        pdf.cell(
            0,
            10,
            "IAM Compliance Audit Report",
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.cell(
            0,
            5,
            f"Generated on {pdf.get_current_date().strftime('%d/%m/%Y at %H:%M')}",
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

        if self.author_fullname or self.author_email:
            pdf.ln(2)
            pdf.apply_font("body")
            author_line = " - ".join(filter(None, [self.author_fullname, self.author_email]))
            pdf.cell(0, 5, f"By {author_line}", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def __write_summary(self, pdf: AGPDF, reports: Iterable[Report]) -> None:
        pdf.add_page()
        pdf.apply_font("heading")
        pdf.cell(0, 10, "Statistical Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(5)

        stats: dict[str, int] = defaultdict(int)
        for report in reports:
            for severity in SeverityType:
                stats[severity] += report.get_count_by_severity(severity)

        pdf.apply_font("body")
        for severity in [
            SeverityType.CRITICAL,
            SeverityType.DANGER,
            SeverityType.WARNING,
            SeverityType.INFO,
        ]:
            count = stats[severity]
            color = self.rules["colors"].get(severity, self.rules["colors"]["text"])
            pdf.set_text_color(color["r"], color["g"], color["b"])
            pdf.cell(40, 10, f"{severity} :")
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 10, f"{count} finding(s)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(10)

    def __default_render(self, pdf: AGPDF, findings: Iterable[Finding], section_title: str) -> None:
        pdf.apply_font("heading")
        pdf.cell(0, 10, section_title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        pdf.render_findings(findings)
