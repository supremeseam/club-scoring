import csv
import io


def safe(v) -> str:
    """Neutralise spreadsheet formula injection from user-entered text."""
    t = "" if v is None else str(v)
    return "'" + t if t[:1] in ("=", "+", "-", "@", "\t", "\r") else t


def fmt_pts(p) -> str:
    if p is None:
        return ""
    p = float(p)
    return str(int(p)) if p == int(p) else f"{p:.1f}"


def race_csv(res: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["fleet", "place", "boat", "sail_number", "skipper", "rating_type", "rating",
                "elapsed", "corrected", "status", "points"])
    for blk in res["fleets"]:
        for r in blk["rows"]:
            b = r["boat"]
            w.writerow([safe(blk["fleet_name"]), r["place"] or "", safe(b["name"]),
                        safe(b["sail_number"]), safe(b["skipper"]), r["rating_type"],
                        "" if r["rating"] is None else r["rating"], r["elapsed"] or "",
                        r["corrected"] or "", r["code"] or "", fmt_pts(r["points"])])
    return out.getvalue()


def standings_csv(st: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    blocks = st["fleets"] + ([st["combined"]] if st.get("combined") else [])
    for blk in blocks:
        w.writerow([safe(blk["fleet_name"])])
        w.writerow(["rank", "boat", "sail_number"] + [f"R{r['number']}" for r in blk["races"]]
                   + ["total"])
        for row in blk["standings"]:
            cells = []
            for sc in row["scores"]:
                t = fmt_pts(sc["points"])
                if sc["code"]:
                    t = f"{t} {sc['code']}"
                cells.append(f"({t})" if sc["discarded"] else t)
            w.writerow([row["rank"], safe(row["boat"]["name"]), safe(row["boat"]["sail_number"])]
                       + cells + [fmt_pts(row["total"])])
        w.writerow([])
    return out.getvalue()
