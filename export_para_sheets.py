"""
Publica no Google Sheets a extração consolidada dos 12 podcasts.

Abas gravadas (fonte de verdade na nuvem):
  - Historico  → CSVs all-time dos 12 podcasts unificados
  - Spotify    → schema do dashboard Power BI (plays diários + demografia)
  - Resumo     → totais por programa
  - Calendario / DemografiaGenero → auxiliares do modelo
"""
from __future__ import annotations

import os
from pathlib import Path

import gspread
import pandas as pd
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

from powerbi_dataset import COLS, build_calendario_rows, build_demografia_rows
from spoti_paths import ANALYTICS_EXCEL, DATA_DIR, HISTORICO_CSV

TAB_HISTORICO = "Historico"
TAB_SPOTIFY = "Spotify"
TAB_RESUMO = "Resumo"
TAB_CALENDARIO = "Calendario"
TAB_DEMOGRAFIA = "DemografiaGenero"


def _config() -> dict:
    load_dotenv()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sa = os.getenv("SERVICE_ACCOUNT_FILE", "service-account.json")
    if not os.path.isabs(sa):
        sa = os.path.join(script_dir, sa)
    return {
        "spreadsheet_key": os.getenv(
            "SPREADSHEET_KEY",
            "YOUR_SPREADSHEET_ID",
        ),
        "service_account_file": sa,
    }


def _client(cfg: dict):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        cfg["service_account_file"], scope
    )
    return gspread.authorize(creds)


def _get_or_create_ws(spreadsheet, title: str, rows: int = 1000, cols: int = 20):
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)
    return ws


def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell_value(value) -> str | int | float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%Y-%m-%d")
        except Exception:
            return str(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def _dataframe_to_values(df: pd.DataFrame) -> list[list]:
    headers = [str(c) for c in df.columns]
    values: list[list] = [headers]
    for row in df.itertuples(index=False, name=None):
        values.append([_cell_value(v) for v in row])
    return values


def _write_dataframe(ws, df: pd.DataFrame) -> int:
    values = _dataframe_to_values(df)
    nrows = len(values)
    ncols = len(values[0]) if values else 1
    if ws.row_count < nrows or ws.col_count < ncols:
        ws.resize(rows=max(nrows + 50, ws.row_count), cols=max(ncols, ws.col_count))
    ws.clear()
    if nrows == 0:
        ws.update([[]], "A1")
        return 0
    ws.update(values, f"A1:{_col_letter(ncols)}{nrows}")
    return nrows - 1


def _write_table(ws, headers: list[str], rows: list[dict]) -> int:
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=headers)
    else:
        df = df.reindex(columns=headers)
    return _write_dataframe(ws, df)


def _resolve_excel_path(excel_path: Path | None) -> Path:
    candidates = []
    if excel_path is not None:
        candidates.append(Path(excel_path))
    candidates.extend(
        [
            Path(ANALYTICS_EXCEL),
            Path(DATA_DIR) / "spotify_analytics_historico.xlsx",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "Planilha consolidada não encontrada. Rode consolidar_analytics_excel.py antes."
    )


def _spotify_rows_from_df(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for _, row in df.iterrows():
        data = row.get("data")
        if pd.isna(data):
            continue
        if hasattr(data, "strftime"):
            data = data.strftime("%Y-%m-%d")
        rows.append(
            {
                "data": str(data)[:10],
                "programa": str(row.get("programa", "")).strip(),
                "plays": int(row.get("plays") or 0),
                "seguidores": int(row.get("seguidores") or 0),
                "pct_homens": float(row.get("pct_homens") or 0),
                "pct_mulheres": float(row.get("pct_mulheres") or 0),
                "pct_outros": float(row.get("pct_outros") or 0),
                "top_faixa_etaria": str(row.get("top_faixa_etaria") or "N/A"),
            }
        )
    rows.sort(key=lambda r: (r["data"], r["programa"]))
    return rows


def main_from_consolidado(excel_path: Path | None = None) -> int:
    """Sobe Historico + Spotify + Resumo (12 podcasts) para o Google Sheets."""
    cfg = _config()
    if not os.path.isfile(cfg["service_account_file"]):
        print(f"[ERRO] Service account não encontrada: {cfg['service_account_file']}")
        return 1

    try:
        path = _resolve_excel_path(excel_path)
    except FileNotFoundError as exc:
        print(f"[ERRO] {exc}")
        return 1

    try:
        historico = pd.read_excel(path, sheet_name=TAB_HISTORICO)
        spotify_df = pd.read_excel(path, sheet_name=TAB_SPOTIFY)
        resumo = pd.read_excel(path, sheet_name=TAB_RESUMO)
    except Exception as exc:
        print(f"[ERRO] Falha ao ler {path}: {exc}")
        return 1

    if historico.empty:
        print("[ERRO] Aba Historico vazia — nada para publicar.")
        return 1

    spotify_rows = _spotify_rows_from_df(spotify_df)
    if not spotify_rows:
        print("[ERRO] Aba Spotify vazia após consolidação.")
        return 1

    calendario_rows = build_calendario_rows(spotify_rows)
    demografia_rows = build_demografia_rows()

    gc = _client(cfg)
    ss = gc.open_by_key(cfg["spreadsheet_key"])

    ws_hist = _get_or_create_ws(ss, TAB_HISTORICO, rows=max(len(historico) + 100, 5000), cols=20)
    ws_spotify = _get_or_create_ws(ss, TAB_SPOTIFY, rows=max(len(spotify_rows) + 100, 5000), cols=12)
    ws_resumo = _get_or_create_ws(ss, TAB_RESUMO, rows=max(len(resumo) + 20, 100), cols=12)
    ws_cal = _get_or_create_ws(ss, TAB_CALENDARIO, rows=max(len(calendario_rows) + 50, 5000), cols=4)
    ws_demo = _get_or_create_ws(ss, TAB_DEMOGRAFIA, rows=10, cols=4)

    n_hist = _write_dataframe(ws_hist, historico)
    n_spotify = _write_table(ws_spotify, COLS, spotify_rows)
    n_resumo = _write_dataframe(ws_resumo, resumo)
    _write_table(ws_cal, ["data"], calendario_rows)
    _write_table(ws_demo, ["Genero"], demografia_rows)

    programas = historico["programa"].nunique() if "programa" in historico.columns else "?"
    datas = sorted({r["data"] for r in spotify_rows})
    url = f"https://docs.google.com/spreadsheets/d/{cfg['spreadsheet_key']}/edit"

    print(f"[OK] Google Sheets atualizado: {url}")
    print(f"[OK] {TAB_HISTORICO}: {n_hist} linhas ({programas} programas)")
    print(f"[OK] {TAB_SPOTIFY}: {n_spotify} linhas | {TAB_RESUMO}: {n_resumo} linhas")
    print(f"[OK] Auxiliares: {TAB_CALENDARIO}, {TAB_DEMOGRAFIA}")
    print(f"[OK] Período dashboard: {datas[0]} a {datas[-1]}")
    return 0


def main_from_historico() -> int:
    """Compatibilidade: publica só Spotify a partir do CSV local."""
    if not os.path.isfile(HISTORICO_CSV):
        print(f"[ERRO] CSV não encontrado: {HISTORICO_CSV}")
        return 1
    path = _resolve_excel_path(None)
    return main_from_consolidado(path)


def main() -> int:
    return main_from_consolidado()


if __name__ == "__main__":
    raise SystemExit(main())