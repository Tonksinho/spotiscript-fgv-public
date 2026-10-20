"""Dados limpos para Power BI (CSV local ou abas Google Sheets)."""
from __future__ import annotations

import json
import os

COLS = [
    "data",
    "programa",
    "plays",
    "seguidores",
    "pct_homens",
    "pct_mulheres",
    "pct_outros",
    "top_faixa_etaria",
]


def to_float_pct(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("%", "").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return None


def iso_date(d: str) -> str:
    try:
        dd, mm, yy = d.split("/")
        return f"{yy}-{mm.zfill(2)}-{dd.zfill(2)}"
    except Exception:
        return d


def _record_from_raw(o: dict) -> dict | None:
    data = o.get("date") or o.get("data")
    prog = o.get("programa")
    if not data or not prog:
        return None

    seg = o.get("seguidores", o.get("followers"))
    ph = to_float_pct(o.get("pct_homens"))
    pm = to_float_pct(o.get("pct_mulheres"))
    po = to_float_pct(o.get("pct_outros"))
    if po is None and ph is not None and pm is not None:
        po = round(max(0.0, 100.0 - ph - pm), 1)

    return {
        "data": iso_date(str(data)),
        "programa": str(prog).strip(),
        "plays": int(o.get("plays") or 0),
        "seguidores": int(seg or 0),
        "pct_homens": round(ph, 1) if ph is not None else 0.0,
        "pct_mulheres": round(pm, 1) if pm is not None else 0.0,
        "pct_outros": round(po, 1) if po is not None else 0.0,
        "top_faixa_etaria": o.get("top_faixa_etaria") or "N/A",
    }


def _sorted_rows(rows: dict[tuple[str, str], dict]) -> list[dict]:
    return sorted(rows.values(), key=lambda r: (r["data"], -r["plays"]))


def load_clean_rows(src: str | None = None) -> tuple[list[dict], int]:
    """Lê JSONL e retorna linhas deduplicadas por (data, programa)."""
    from spoti_paths import BACKUP_JSONL

    path = src or BACKUP_JSONL
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Backup não encontrado: {path}")

    rows: dict[tuple[str, str], dict] = {}
    total_lidas = 0

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            total_lidas += 1
            rec = _record_from_raw(o)
            if rec:
                rows[(rec["data"], rec["programa"])] = rec

    return _sorted_rows(rows), total_lidas


def load_clean_rows_from_visao_geral(
    spreadsheet_key: str | None = None,
    sheet_name: str = "Visão Geral",
    service_account_file: str | None = None,
) -> tuple[list[dict], int]:
    """Lê a aba de coleta (histórico completo da extração) no Google Sheets."""
    import gspread
    from dotenv import load_dotenv
    from oauth2client.service_account import ServiceAccountCredentials

    load_dotenv()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sa = service_account_file or os.getenv(
        "SERVICE_ACCOUNT_FILE", "service-account.json"
    )
    if not os.path.isabs(sa):
        sa = os.path.join(script_dir, sa)
    if not os.path.isfile(sa):
        raise FileNotFoundError(f"Service account não encontrada: {sa}")

    key = spreadsheet_key or os.getenv(
        "SPREADSHEET_KEY", "YOUR_SPREADSHEET_ID"
    )
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    gc = gspread.authorize(
        ServiceAccountCredentials.from_json_keyfile_name(sa, scope)
    )
    ws = gc.open_by_key(key).worksheet(sheet_name)
    raw = ws.get_all_records()
    rows: dict[tuple[str, str], dict] = {}
    for o in raw:
        rec = _record_from_raw(o)
        if rec:
            rows[(rec["data"], rec["programa"])] = rec
    return _sorted_rows(rows), len(raw)


def load_clean_rows_for_export() -> tuple[list[dict], dict[str, int]]:
    """
    Fonte unificada para publicar no Power BI:
    1) Visão Geral (extração spotiscrap, todo o histórico)
    2) JSONL (complementa/atualiza o que faltar no backup local)
    """
    merged: dict[tuple[str, str], dict] = {}
    stats = {"visao_geral": 0, "jsonl": 0, "jsonl_extra": 0}

    try:
        visao_rows, stats["visao_geral"] = load_clean_rows_from_visao_geral()
        for rec in visao_rows:
            merged[(rec["data"], rec["programa"])] = rec
    except Exception as exc:
        print(f"[AVISO] Visão Geral indisponível ({exc}); usando só JSONL.")

    try:
        jsonl_rows, stats["jsonl"] = load_clean_rows()
        before = len(merged)
        for rec in jsonl_rows:
            merged[(rec["data"], rec["programa"])] = rec
        stats["jsonl_extra"] = len(merged) - before
    except FileNotFoundError as exc:
        if not merged:
            raise exc

    return _sorted_rows(merged), stats


def build_calendario_rows(spotify_rows: list[dict]) -> list[dict]:
    dates = sorted({r["data"] for r in spotify_rows})
    return [{"data": d} for d in dates]


def build_demografia_rows() -> list[dict]:
    return [{"Genero": "Homens"}, {"Genero": "Mulheres"}]