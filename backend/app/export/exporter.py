"""
Report exporters (PDF + Excel) for every report in the app.

Two layers:

* ``build_report_excel(spec)`` / ``build_report_pdf(spec)`` - the rich
  engine. A report is described by a plain-dict *spec*:

      {
        "title": "Trial Balance",
        "company_name": "ABC Traders",
        "period": "1-Apr-2025 to 31-Mar-2026",     # optional
        "meta": [("Ledger", "Cash"), ...],          # optional key/value strip
        "sections": [{
            "heading": "Ledger Vouchers",           # optional
            "sheet": "Vouchers",                    # optional Excel sheet name
            "columns": [{"key": "date", "label": "Date", "type": "date"}, ...],
            "rows":   [{"date": "2025-04-01", ..., "_style": "bold"}, ...],
            "totals": [{"name": "Total", "debit": 10.0}],   # optional
            "filterable": True,                     # Excel filter buttons
            "note": "free text under the table",
        }],
        "notes": ["free text at the end"],
      }

  Column ``type`` is one of text | amount | qty | int | date | balance |
  percent. Row keys starting with ``_`` are layout hints: ``_style``
  (bold | italic | muted | heading | total), ``_cell_styles`` (key -> style)
  and ``_indent`` (0-3, also becomes an Excel outline level so child rows
  can be collapsed).

* ``build_excel`` / ``build_pdf`` - the original flat-table signature, kept
  so every existing caller keeps working. They are translated into a spec.

Numbers are written to Excel as real numbers (sortable, filterable, usable
in formulas) and printed in the Indian grouping the app itself uses.
"""

import io
import os
import re
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ----------------------------------------------------------------------
# Palette
# ----------------------------------------------------------------------

NAVY = "1F3A5F"
ACCENT = "2F5D8C"
LIGHT = "EEF2F7"
ZEBRA = "F7F9FC"
GRID = "D5DCE6"
TOTAL_FILL = "E3E9F2"
MUTED = "6B7785"
TEXT = "1B2430"

NUMERIC_TYPES = {"amount", "qty", "int", "balance", "percent"}


# ----------------------------------------------------------------------
# Value formatting (mirrors the app's en-IN formatting)
# ----------------------------------------------------------------------

def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _to_number(value):
    """Return a float for numbers / numeric strings, else None."""
    if _is_number(value):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _group_indian(digits: str) -> str:
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def fmt_amount(value, blank_zero: bool = False) -> str:
    number = _to_number(value)
    if number is None:
        return "" if value is None else str(value)
    if round(number, 2) == 0:
        return "" if blank_zero else "0.00"
    whole, _, decimals = f"{abs(number):.2f}".partition(".")
    text = f"{_group_indian(whole)}.{decimals}"
    return f"(-){text}" if number < 0 else text


def fmt_qty(value, blank_zero: bool = False) -> str:
    number = _to_number(value)
    if number is None:
        return "" if value is None else str(value)
    if round(number, 3) == 0:
        return "" if blank_zero else "0"
    whole, _, decimals = f"{abs(number):.3f}".partition(".")
    decimals = decimals.rstrip("0")
    text = _group_indian(whole) + (f".{decimals}" if decimals else "")
    return f"(-){text}" if number < 0 else text


def fmt_balance(value) -> str:
    number = _to_number(value)
    if number is None:
        return "" if value is None else str(value)
    if round(number, 2) == 0:
        return "0.00"
    return f"{fmt_amount(abs(number))} {'Cr' if number < 0 else 'Dr'}"


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def to_date(value):
    """ISO / DD-MM-YYYY / DD/MM/YYYY / YYYYMMDD / date -> date, else None."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    for pattern, order in (
        (r"^(\d{4})-(\d{2})-(\d{2})", "ymd"),
        (r"^(\d{2})-(\d{2})-(\d{4})$", "dmy"),
        (r"^(\d{2})/(\d{2})/(\d{4})$", "dmy"),
        (r"^(\d{4})(\d{2})(\d{2})$", "ymd"),
    ):
        match = re.match(pattern, text)
        if match:
            a, b, c = (int(g) for g in match.groups())
            year, month, day = (a, b, c) if order == "ymd" else (c, b, a)
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def fmt_date(value) -> str:
    parsed = to_date(value)
    if parsed:
        return f"{parsed.day}-{_MONTHS[parsed.month - 1]}-{parsed.year}"
    return "" if value is None else str(value)


def format_cell(column: dict, value) -> str:
    """Text form of a cell, as printed in the PDF."""
    kind = column.get("type", "text")
    blank_zero = column.get("blank_zero", False)

    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if kind == "amount":
        return fmt_amount(value, blank_zero)
    if kind == "qty":
        return fmt_qty(value, blank_zero)
    if kind == "balance":
        return fmt_balance(value)
    if kind == "int":
        number = _to_number(value)
        if number is None:
            return str(value)
        if number == 0 and blank_zero:
            return ""
        return _group_indian(str(int(abs(number)))) if number >= 0 else f"-{int(abs(number))}"
    if kind == "percent":
        number = _to_number(value)
        return f"{number:g}%" if number is not None else str(value)
    if kind == "date":
        return fmt_date(value)
    return str(value)


# ----------------------------------------------------------------------
# Spec helpers
# ----------------------------------------------------------------------

_INVALID_SHEET_CHARS = r"\/?*[]:"


def _sheet_name(raw: str, used: set) -> str:
    base = "".join(c for c in (raw or "") if c not in _INVALID_SHEET_CHARS).strip()
    base = (base or "Report")[:31]
    name, n = base, 2
    while name.lower() in used:
        suffix = f" ({n})"
        name = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(name.lower())
    return name


def _is_numeric_col(column: dict) -> bool:
    return column.get("type", "text") in NUMERIC_TYPES


def _all_rows(section: dict) -> list:
    return list(section.get("rows") or []) + list(section.get("totals") or [])


def _style_of(row: dict, key: str | None = None) -> str:
    if key is not None:
        cell_style = (row.get("_cell_styles") or {}).get(key)
        if cell_style:
            return cell_style
    return row.get("_style") or ""


# ----------------------------------------------------------------------
# Excel
# ----------------------------------------------------------------------

_THIN = Side(style="thin", color=GRID)
_HAIR_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_FONT = "Arial"

_NUMBER_FORMATS = {
    "amount": '#,##0.00;"(-)"#,##0.00;0.00',
    "amount_blank": '#,##0.00;"(-)"#,##0.00;',
    "qty": '#,##0.00#;"(-)"#,##0.00#;0',
    "qty_blank": '#,##0.00#;"(-)"#,##0.00#;',
    "int": "#,##0",
    "int_blank": "#,##0;-#,##0;",
    "balance": '#,##0.00" Dr";#,##0.00" Cr";0.00',
    "percent": '0.00"%"',
    "date": "d-mmm-yyyy",
}


def _number_format(column: dict) -> str:
    kind = column.get("type", "text")
    if kind == "date":
        return _NUMBER_FORMATS["date"]
    if kind in ("amount", "qty", "int") and column.get("blank_zero"):
        return _NUMBER_FORMATS[f"{kind}_blank"]
    return _NUMBER_FORMATS.get(kind, "General")


def _excel_value(column: dict, value):
    """Python value to store in the cell (real numbers / dates)."""
    kind = column.get("type", "text")

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if kind in NUMERIC_TYPES:
        number = _to_number(value)
        return number if number is not None else str(value)
    if kind == "date":
        parsed = to_date(value)
        return parsed if parsed else str(value)
    return value if isinstance(value, (int, float)) else str(value)


def _font(style: str, base_color: str = TEXT, size: int = 10) -> Font:
    bold = style in ("bold", "total", "heading")
    italic = style in ("italic",)
    color = MUTED if style == "muted" else (NAVY if style == "heading" else base_color)
    return Font(name=_FONT, size=size, bold=bold, italic=italic, color=color)


def _estimate_width(column: dict, rows: list) -> float:
    longest = len(str(column.get("label", "")))
    for row in rows:
        text = format_cell(column, row.get(column["key"]))
        if text:
            longest = max(longest, max(len(part) for part in text.split("\n")))
    minimum = 14 if _is_numeric_col(column) else 10
    return float(min(max(minimum, longest + 3), 52))


def build_report_excel(spec: dict) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.title = spec.get("title") or "Report"
    workbook.properties.creator = "Tally Finance"

    sheets: dict[str, dict] = {}
    used_names: set[str] = set()

    default_sheet = spec.get("title") or "Report"
    for section in spec.get("sections", []):
        raw = section.get("sheet") or default_sheet
        key = raw.strip().lower()
        if key not in sheets:
            sheets[key] = {
                "name": _sheet_name(raw, used_names),
                "sections": [],
            }
        sheets[key]["sections"].append(section)

    if not sheets:
        sheets["report"] = {"name": _sheet_name(default_sheet, used_names), "sections": []}

    for index, info in enumerate(sheets.values()):
        _write_sheet(workbook, info, spec, first=index == 0)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _write_sheet(workbook, info: dict, spec: dict, first: bool) -> None:
    sheet = workbook.create_sheet(info["name"])
    sections = info["sections"]
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.tabColor = ACCENT
    sheet.sheet_properties.outlinePr.summaryBelow = False

    num_cols = max([len(s.get("columns", [])) for s in sections] + [2])
    # Make sure the title band spans at least a readable width.
    span = max(num_cols, 4)

    company = spec.get("company_name") or spec.get("title") or "Report"
    title = spec.get("title") or "Report"
    if not first:
        title = f"{title} - {info['name']}"

    row = 1
    band = PatternFill("solid", start_color=NAVY, end_color=NAVY)
    sub_band = PatternFill("solid", start_color=LIGHT, end_color=LIGHT)

    def banner(text, font, fill, height):
        nonlocal row
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
        cell = sheet.cell(row=row, column=1, value=text)
        cell.font = font
        cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        for col in range(1, span + 1):
            sheet.cell(row=row, column=col).fill = fill
        sheet.row_dimensions[row].height = height
        row += 1

    banner(company, Font(name=_FONT, size=16, bold=True, color="FFFFFF"), band, 28)
    banner(title, Font(name=_FONT, size=12, bold=True, color=NAVY), sub_band, 22)
    if spec.get("period"):
        banner(spec["period"], Font(name=_FONT, size=10, color=MUTED), sub_band, 18)
    banner(
        f"Generated on {datetime.now().strftime('%d-%b-%Y %H:%M')}  |  Amounts in INR",
        Font(name=_FONT, size=9, italic=True, color=MUTED),
        sub_band,
        16,
    )

    meta = spec.get("meta") if first else None
    if meta:
        row += 1
        for label, value in meta:
            if value is None or value == "":
                continue
            # One cell per line: the text spills across the empty cells to
            # its right, so a long label is never cut off by a narrow column.
            line = sheet.cell(row=row, column=1, value=f"{label}:  {value}")
            line.font = Font(name=_FONT, size=10, bold=True, color=TEXT)
            line.alignment = Alignment(horizontal="left")
            row += 1

    widths = [10.0] * num_cols
    first_header_row = None
    filter_ref = None

    for section in sections:
        columns = section.get("columns", [])
        rows = section.get("rows") or []
        totals = section.get("totals") or []
        row += 1

        if section.get("heading"):
            cell = sheet.cell(row=row, column=1, value=section["heading"])
            cell.font = Font(name=_FONT, size=12, bold=True, color=NAVY)
            for col in range(1, max(len(columns), 1) + 1):
                sheet.cell(row=row, column=col).border = Border(
                    bottom=Side(style="medium", color=ACCENT)
                )
            row += 1

        if not columns:
            continue

        # Header
        header_row = row
        if first_header_row is None:
            first_header_row = header_row
        for index, column in enumerate(columns, start=1):
            cell = sheet.cell(row=row, column=index, value=column["label"])
            cell.font = Font(name=_FONT, size=10, bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", start_color=NAVY, end_color=NAVY)
            cell.alignment = Alignment(
                horizontal="right" if _is_numeric_col(column) else "left",
                vertical="center",
                wrap_text=True,
            )
            cell.border = _HAIR_BORDER
        sheet.row_dimensions[row].height = 22
        row += 1

        # Body
        data_start = row
        if not rows and not totals:
            cell = sheet.cell(row=row, column=1, value="No records found.")
            cell.font = Font(name=_FONT, size=10, italic=True, color=MUTED)
            row += 1

        zebra_index = 0
        for data in rows:
            style = _style_of(data)
            indent = int(data.get("_indent") or 0)
            if style in ("heading", "total", "bold"):
                zebra_index = 0
            for index, column in enumerate(columns, start=1):
                value = _excel_value(column, data.get(column["key"]))
                cell = sheet.cell(row=row, column=index, value=value)
                cell_style = _style_of(data, column["key"])
                cell.font = _font(cell_style)
                cell.border = _HAIR_BORDER
                numeric = _is_numeric_col(column)
                cell.alignment = Alignment(
                    horizontal="right" if numeric else "left",
                    vertical="top",
                    wrap_text=not numeric,
                    indent=(indent if index == 1 else 0),
                )
                if numeric or column.get("type") == "date":
                    if not isinstance(value, str):
                        cell.number_format = _number_format(column)
                if style == "heading":
                    cell.fill = PatternFill("solid", start_color=LIGHT, end_color=LIGHT)
                elif style == "bold":
                    cell.fill = PatternFill("solid", start_color="F1F4F9", end_color="F1F4F9")
                elif zebra_index % 2 == 1:
                    cell.fill = PatternFill("solid", start_color=ZEBRA, end_color=ZEBRA)
            if indent:
                sheet.row_dimensions[row].outlineLevel = min(indent, 3)
            zebra_index += 1
            row += 1

        data_end = row - 1

        # Totals (outside the filter range, so filters never hide them)
        for total in totals:
            for index, column in enumerate(columns, start=1):
                value = _excel_value(column, total.get(column["key"]))
                cell = sheet.cell(row=row, column=index, value=value)
                cell.font = Font(name=_FONT, size=10, bold=True, color=NAVY)
                cell.fill = PatternFill("solid", start_color=TOTAL_FILL, end_color=TOTAL_FILL)
                cell.border = Border(
                    left=_THIN, right=_THIN,
                    top=Side(style="medium", color=NAVY),
                    bottom=Side(style="double", color=NAVY),
                )
                numeric = _is_numeric_col(column)
                cell.alignment = Alignment(
                    horizontal="right" if numeric else "left", vertical="center"
                )
                if numeric and not isinstance(value, str):
                    cell.number_format = _number_format({**column, "blank_zero": False})
            row += 1

        if section.get("note"):
            cell = sheet.cell(row=row, column=1, value=section["note"])
            cell.font = Font(name=_FONT, size=9, italic=True, color=MUTED)
            row += 1

        if section.get("filterable") and filter_ref is None and rows:
            filter_ref = (
                f"A{header_row}:{get_column_letter(len(columns))}{data_end}"
            )

        for index, column in enumerate(columns):
            widths[index] = max(
                widths[index], _estimate_width(column, _all_rows(section))
            )

    for notes in spec.get("notes") or []:
        row += 1
        cell = sheet.cell(row=row, column=1, value=notes)
        cell.font = Font(name=_FONT, size=9, italic=True, color=MUTED)

    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    if filter_ref:
        sheet.auto_filter.ref = filter_ref

    # Keep the column headers visible while scrolling (only when the
    # banner above them is short enough not to eat the screen).
    if first_header_row and first_header_row <= 12:
        sheet.freeze_panes = sheet.cell(row=first_header_row + 1, column=1)

    # Print setup: fit to page width, repeat the header, page numbers.
    sheet.page_setup.orientation = "landscape" if num_cols > 5 else "portrait"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_margins.left = sheet.page_margins.right = 0.4
    sheet.page_margins.top = 0.6
    sheet.page_margins.bottom = 0.7
    sheet.print_options.horizontalCentered = True
    if first_header_row:
        sheet.print_title_rows = f"{first_header_row}:{first_header_row}"
    sheet.oddFooter.left.text = "&F"
    sheet.oddFooter.left.size = 8
    sheet.oddFooter.right.text = "Page &P of &N"
    sheet.oddFooter.right.size = 8


# ----------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------

_FONT_CANDIDATES = [
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf",
     "C:/Windows/Fonts/ariali.ttf", "C:/Windows/Fonts/arialbi.ttf"),
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf",
     "C:/Windows/Fonts/segoeuii.ttf", "C:/Windows/Fonts/segoeuiz.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
     "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf"),
]

_font_family_cache: dict = {}


def _font_family() -> tuple[str, bool]:
    """(family name, is_unicode). Prefers a system TrueType family so
    non-Latin party/item names print instead of turning into boxes."""
    if "family" in _font_family_cache:
        return _font_family_cache["family"]

    result = ("Helvetica", False)
    for index, paths in enumerate(_FONT_CANDIDATES):
        if not all(os.path.exists(p) for p in paths):
            continue
        try:
            name = f"TFReport{index}"
            for suffix, path in zip(("", "-Bold", "-Italic", "-BoldItalic"), paths):
                pdfmetrics.registerFont(TTFont(name + suffix, path))
            pdfmetrics.registerFontFamily(
                name,
                normal=name,
                bold=name + "-Bold",
                italic=name + "-Italic",
                boldItalic=name + "-BoldItalic",
            )
            result = (name, True)
            break
        except Exception:
            continue

    _font_family_cache["family"] = result
    return result


def _safe_text(text: str, unicode_ok: bool) -> str:
    if unicode_ok:
        return text
    return text.encode("cp1252", "replace").decode("cp1252")


def _xml(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


class _Heading(Paragraph):
    """Paragraph that registers a PDF bookmark / outline entry."""

    def __init__(self, text, style, outline):
        super().__init__(text, style)
        self.outline = outline


class _ReportDoc(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, _Heading):
            key = f"sec{self.page}_{id(flowable)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.outline, key, 0, 0)


def _make_canvas_class(company: str, title: str, period: str | None, unicode_ok: bool,
                       font: str):
    generated = datetime.now().strftime("%d-%b-%Y %H:%M")

    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_pages = []

        def showPage(self):
            self._saved_pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_pages)
            for state in self._saved_pages:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _decorate(self, total):
            width, height = self._pagesize
            margin = 12 * mm
            self.saveState()
            self.setFillColor(colors.HexColor("#" + NAVY))
            self.rect(0, height - 5 * mm, width, 5 * mm, stroke=0, fill=1)

            if self._pageNumber > 1:
                self.setFont(font, 8)
                self.setFillColor(colors.HexColor("#" + MUTED))
                self.drawString(
                    margin, height - 10 * mm, _safe_text(f"{company}  |  {title}", unicode_ok)
                )
                if period:
                    self.drawRightString(
                        width - margin, height - 10 * mm, _safe_text(period, unicode_ok)
                    )

            self.setStrokeColor(colors.HexColor("#" + GRID))
            self.setLineWidth(0.5)
            self.line(margin, 12 * mm, width - margin, 12 * mm)
            self.setFont(font, 7.5)
            self.setFillColor(colors.HexColor("#" + MUTED))
            self.drawString(margin, 8 * mm, f"Generated {generated}  |  Amounts in INR")
            self.drawRightString(width - margin, 8 * mm, f"Page {self._pageNumber} of {total}")
            self.restoreState()

    return NumberedCanvas


def _col_weights(columns: list, rows: list, size: float) -> list:
    weights = []
    for column in columns:
        longest = len(str(column.get("label", "")))
        for row in rows[:400]:
            text = format_cell(column, row.get(column["key"]))
            if text:
                longest = max(longest, len(text))
        if _is_numeric_col(column):
            weights.append(float(min(max(longest, 11), 20)))
        elif column.get("type") == "date":
            weights.append(float(max(longest, 10)))
        else:
            weights.append(float(min(max(longest, 7), 42)))
    return weights


def build_report_pdf(spec: dict) -> bytes:
    family, unicode_ok = _font_family()
    sections = spec.get("sections", [])
    max_cols = max([len(s.get("columns", [])) for s in sections] + [1])
    use_landscape = max_cols > 5
    pagesize = landscape(A4) if use_landscape else A4
    margin = 12 * mm
    avail = pagesize[0] - 2 * margin
    size = 8.5 if max_cols <= 7 else (7.5 if max_cols <= 9 else 7)

    company = spec.get("company_name") or spec.get("title") or "Report"
    title = spec.get("title") or "Report"
    period = spec.get("period")

    buffer = io.BytesIO()
    doc = _ReportDoc(
        buffer,
        pagesize=pagesize,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=15 * mm,
        bottomMargin=17 * mm,
        title=title,
        author="Tally Finance",
        subject=company,
    )
    doc.addPageTemplates([
        PageTemplate(
            id="main",
            frames=[Frame(margin, 17 * mm, avail, pagesize[1] - 32 * mm,
                          leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
        )
    ])

    def para_style(name, **kw):
        return ParagraphStyle(name, fontName=family, fontSize=size,
                              leading=size * 1.3, textColor=colors.HexColor("#" + TEXT), **kw)

    left = para_style("left", alignment=TA_LEFT)
    right = para_style("right", alignment=TA_RIGHT)
    head_left = ParagraphStyle("hl", fontName=family, fontSize=size, leading=size * 1.3,
                               textColor=colors.white, alignment=TA_LEFT)
    head_right = ParagraphStyle("hr", parent=head_left, alignment=TA_RIGHT)

    title_style = ParagraphStyle("t", fontName=family, fontSize=18, leading=22,
                                 textColor=colors.HexColor("#" + NAVY), alignment=TA_LEFT)
    subtitle_style = ParagraphStyle("st", fontName=family, fontSize=12.5, leading=16,
                                    textColor=colors.HexColor("#" + ACCENT), alignment=TA_LEFT)
    period_style = ParagraphStyle("p", fontName=family, fontSize=9.5, leading=13,
                                  textColor=colors.HexColor("#" + MUTED), alignment=TA_LEFT)
    section_style = ParagraphStyle("sec", fontName=family, fontSize=11.5, leading=15,
                                   textColor=colors.HexColor("#" + NAVY), spaceBefore=10,
                                   spaceAfter=4, keepWithNext=1)
    note_style = ParagraphStyle("note", fontName=family, fontSize=8, leading=11,
                                textColor=colors.HexColor("#" + MUTED), spaceBefore=4)

    def wrap(text, style_name, base_style, bold=False, italic=False, muted=False, indent=0):
        content = _xml(_safe_text(text, unicode_ok))
        if bold:
            content = f"<b>{content}</b>"
        if italic:
            content = f"<i>{content}</i>"
        if muted:
            content = f'<font color="#{MUTED}">{content}</font>'
        style = base_style
        if indent:
            style = ParagraphStyle(f"{style_name}{indent}", parent=base_style,
                                   leftIndent=indent * 8)
        return Paragraph(content or "&nbsp;", style)

    def bold_title(text, style):
        return Paragraph(f"<b>{_xml(_safe_text(text, unicode_ok))}</b>", style)

    story = [
        bold_title(company, title_style),
        Paragraph(_xml(_safe_text(title, unicode_ok)), subtitle_style),
    ]
    if period:
        story.append(Paragraph(_xml(_safe_text(period, unicode_ok)), period_style))
    story.append(Spacer(1, 4))

    rule = Table([[""]], colWidths=[avail], rowHeights=[2])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#" + ACCENT))]))
    story.append(rule)
    story.append(Spacer(1, 7))

    # ---- meta panel ----
    meta = [(k, v) for k, v in (spec.get("meta") or []) if v not in (None, "")]
    if meta:
        label_style = ParagraphStyle("ml", fontName=family, fontSize=7, leading=9,
                                     textColor=colors.HexColor("#" + MUTED))
        value_style = ParagraphStyle("mv", fontName=family, fontSize=9, leading=12,
                                     textColor=colors.HexColor("#" + TEXT))
        per_row = 3 if avail > 200 * mm else 2
        cells, line = [], []
        for label, value in meta:
            line.append([
                Paragraph(_xml(_safe_text(str(label).upper(), unicode_ok)), label_style),
                Paragraph(f"<b>{_xml(_safe_text(str(value), unicode_ok))}</b>", value_style),
            ])
            if len(line) == per_row:
                cells.append(line)
                line = []
        if line:
            while len(line) < per_row:
                line.append("")
            cells.append(line)
        meta_table = Table(cells, colWidths=[avail / per_row] * per_row)
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#" + LIGHT)),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#" + GRID)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 6))

    # ---- sections ----
    for section in sections:
        columns = section.get("columns", [])
        rows = list(section.get("rows") or [])
        totals = list(section.get("totals") or [])

        if section.get("heading"):
            story.append(_Heading(
                f"<b>{_xml(_safe_text(section['heading'], unicode_ok))}</b>",
                section_style, section["heading"],
            ))

        if not columns:
            continue

        header = [
            Paragraph(f"<b>{_xml(_safe_text(c['label'], unicode_ok))}</b>",
                      head_right if _is_numeric_col(c) else head_left)
            for c in columns
        ]
        table_rows = [header]
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + NAVY)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#" + GRID)),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#" + NAVY)),
        ]

        def build_line(data, force_style=None):
            line = []
            for column in columns:
                cell_style = force_style or _style_of(data, column["key"])
                text = format_cell(column, data.get(column["key"]))
                numeric = _is_numeric_col(column)
                line.append(wrap(
                    text, "r" if numeric else "l",
                    right if numeric else left,
                    bold=cell_style in ("bold", "total", "heading"),
                    italic=cell_style == "italic",
                    muted=cell_style == "muted",
                    indent=0 if numeric or column is not columns[0] else int(data.get("_indent") or 0),
                ))
            return line

        if not rows and not totals:
            empty = [wrap("No records found.", "l", left, italic=True, muted=True)] + [""] * (len(columns) - 1)
            table_rows.append(empty)

        zebra = 0
        for data in rows:
            style = _style_of(data)
            table_rows.append(build_line(data))
            index = len(table_rows) - 1
            if style == "heading":
                commands.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#" + LIGHT)))
                zebra = 0
            elif style == "bold":
                commands.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#F1F4F9")))
                zebra = 0
            elif zebra % 2 == 1:
                commands.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#" + ZEBRA)))
            zebra += 1

        for data in totals:
            table_rows.append(build_line(data, force_style="total"))
            index = len(table_rows) - 1
            commands.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#" + TOTAL_FILL)))
            commands.append(("LINEABOVE", (0, index), (-1, index), 0.9, colors.HexColor("#" + NAVY)))

        two_sided = [c.get("type", "text") for c in columns] == ["text", "amount", "text", "amount"]
        if two_sided:
            commands.append(("LINEAFTER", (1, 0), (1, -1), 0.9, colors.HexColor("#" + NAVY)))
        weights = _col_weights(columns, _all_rows(section), size)
        total_weight = sum(weights) or 1
        # Narrow reports (2-4 columns) should not stretch across the page.
        natural = total_weight * size * 0.52 + 8 * len(columns)
        floor = 0.8 if two_sided else 0.55
        target = min(avail, max(natural * 1.35, avail * floor))
        col_widths = [target * w / total_weight for w in weights]

        table = Table(table_rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle(commands))
        story.append(table)

        if section.get("note"):
            story.append(Paragraph(_xml(_safe_text(section["note"], unicode_ok)), note_style))

    for note in spec.get("notes") or []:
        story.append(Paragraph(_xml(_safe_text(note, unicode_ok)), note_style))

    canvas_class = _make_canvas_class(company, title, period, unicode_ok, family)
    doc.build(story, canvasmaker=canvas_class)
    return buffer.getvalue()


# ----------------------------------------------------------------------
# Backwards-compatible flat-table API
# ----------------------------------------------------------------------

def _infer_type(column: dict, rows: list) -> str:
    if column.get("type"):
        return column["type"]
    key = column["key"]
    values = [r.get(key) for r in rows if r.get(key) not in (None, "")]
    if values and all(_is_number(v) for v in values):
        lowered = key.lower()
        if "quantity" in lowered or lowered.endswith("_qty"):
            return "qty"
        if "days" in lowered:
            return "int"
        return "amount"
    return "text"


def _legacy_spec(title, columns, rows, company_name, footer, period) -> dict:
    prepared_rows = []
    for row in rows:
        new_row = dict(row)
        for column in columns:
            renderer = column.get("format")
            if renderer:
                new_row[column["key"]] = renderer(row.get(column["key"]))
        prepared_rows.append(new_row)

    typed = [{**c, "type": _infer_type(c, prepared_rows)} for c in columns]
    totals = []
    if footer:
        total_row = {typed[0]["key"]: footer["label"]}
        total_row[footer["key"]] = footer["value"]
        totals.append(total_row)

    return {
        "title": title,
        "company_name": company_name,
        "period": period,
        "sections": [{
            "columns": typed,
            "rows": prepared_rows,
            "totals": totals,
            "filterable": True,
        }],
    }


def build_excel(title, columns, rows, company_name=None, footer=None, period=None) -> bytes:
    return build_report_excel(_legacy_spec(title, columns, rows, company_name, footer, period))


def build_pdf(title, columns, rows, company_name=None, footer=None, period=None) -> bytes:
    return build_report_pdf(_legacy_spec(title, columns, rows, company_name, footer, period))
