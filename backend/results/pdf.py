"""Podium score sheet and series standings PDFs (ReportLab, pure Python)."""
import io
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from racing.models import Race, Series
from racing.services import race_results, series_standings

from .csv_export import fmt_pts

STYLES = getSampleStyleSheet()
def _brand():
    import re
    hx = settings.BRAND_COLOR_HEX
    return colors.HexColor(hx if re.fullmatch(r"#[0-9a-fA-F]{6}", hx or "") else "#1f3a5f")


def _logo_flowable():
    """The club logo if CLUB_LOGO_URL points at a PNG/JPG under frontend/public (WebP is not supported)."""
    url = settings.CLUB_LOGO_URL
    if not url.startswith("/") or not url.lower().endswith((".png", ".jpg", ".jpeg")):
        return None
    path = settings.BASE_DIR.parent / "frontend" / "public" / url.lstrip("/")
    if not path.is_file():
        return None
    from reportlab.lib.utils import ImageReader
    w, h = ImageReader(str(path)).getSize()
    width = 3.4 * inch
    img = Image(str(path), width=width, height=width * h / w)
    img.hAlign = "LEFT"
    return img


GRID = TableStyle([
    ("FONTSIZE", (0, 0), (-1, -1), 8),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f7")]),
    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c2cf")),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
])


def _p(text, style="Normal"):
    return Paragraph(escape(str(text)), STYLES[style])


def _table(data, widths=None):
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(GRID)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), _brand())]))
    return t


def _race_tables(res):
    story = []
    for blk in res["fleets"]:
        head = f"{blk['fleet_name']}: {blk['course'] or 'course n/a'}"
        if blk["distance_nm"] is not None:
            head += f", {float(blk['distance_nm']):.2f} nm"
        story += [_p(head, "Heading3")]
        data = [["Pl", "Boat", "Sail #", "Skipper", f"Rating ({blk['rating_type']})",
                 "Elapsed", "Corrected", "Pts"]]
        mark = {"fallback": " †", "manual": " ‡"}
        for r in blk["rows"]:
            rating = "" if r["rating"] is None else f"{float(r['rating']):g}{mark.get(r['rating_source'], '')}"
            pts = fmt_pts(r["points"]) + (f" {r['code']}" if r["code"] else "")
            data.append([r["place"] or "", r["boat"]["name"], r["boat"]["sail_number"],
                         r["boat"]["skipper"], rating, r["elapsed"] or "",
                         r["corrected"] or "", pts])
        story += [_table(data), Spacer(1, 4)]
        for r in blk["rows"]:
            if r.get("note"):
                story.append(_p(f"{r['boat']['name']} ({r['code'] or r['status'] or ''}): {r['note']}", "Italic"))
        story.append(Spacer(1, 10))
    return story


def _standings_tables(st, heading_prefix=""):
    story = []
    blocks = st["fleets"] + ([st["combined"]] if st.get("combined") else [])
    for blk in blocks:
        story.append(_p(f"{heading_prefix}{blk['fleet_name']}", "Heading3"))
        data = [["Rk", "Boat", "Sail #"] + [f"R{r['number']}" for r in blk["races"]] + ["Total"]]
        for row in blk["standings"]:
            cells = []
            for sc in row["scores"]:
                t = fmt_pts(sc["points"]) + (f" {sc['code']}" if sc["code"] else "")
                cells.append(f"({t})" if sc["discarded"] else t)
            data.append([row["rank"], row["boat"]["name"], row["boat"]["sail_number"]]
                        + cells + [fmt_pts(row["total"])])
        story += [_table(data), Spacer(1, 10)]
    for w in st.get("warnings", []):
        story.append(_p(w, "Italic"))
    return story


def _build(story, many_cols: bool, footer: str) -> bytes:
    buf = io.BytesIO()
    size = landscape(letter) if many_cols else letter

    def footer_fn(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(0.5 * inch, 0.35 * inch, footer)
        canvas.drawRightString(size[0] - 0.5 * inch, 0.35 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=size, leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.6 * inch)
    doc.build(story, onFirstPage=footer_fn, onLaterPages=footer_fn)
    return buf.getvalue()


def _footer(final: bool, url: str) -> str:
    gen = timezone.now().strftime("%Y-%m-%d %H:%M")
    note = "" if final else " Provisional: results subject to protest."
    return f"Generated {gen}.{note} {url}"


def podium_pdf(race: Race) -> bytes:
    res = race_results(race, public=True)
    st = series_standings(race.series, public=True)
    status = "FINAL" if race.results_final else "PROVISIONAL"
    story = [_logo_flowable() or _p(settings.CLUB_NAME, "Title"), Spacer(1, 6),
             _p(f"{res['series_name']}: Race {race.number}, {race.date:%B %d, %Y}", "Heading2"),
             _p(f"Results status: {status}", "Heading4"), Spacer(1, 6),
             _p("Race results", "Heading2")]
    story += _race_tables(res)
    story += [PageBreak(), _p("Series standings after this race", "Heading2")]
    story += _standings_tables(st)
    many = any(len(b["races"]) > 6 for b in st["fleets"])
    url = f"{settings.PUBLIC_URL}/races/{race.id}"
    return _build(story, many, _footer(race.results_final, url))


def standings_pdf(series: Series) -> bytes:
    st = series_standings(series, public=True)
    story = [_logo_flowable() or _p(settings.CLUB_NAME, "Title"), Spacer(1, 6), _p(f"{series} standings", "Heading2")]
    story += _standings_tables(st)
    many = any(len(b["races"]) > 6 for b in st["fleets"])
    return _build(story, many, _footer(series.status == "complete",
                                       f"{settings.PUBLIC_URL}/series/{series.id}"))
