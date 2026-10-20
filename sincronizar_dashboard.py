"""
Baixa a aba Spotify do Google Sheets e grava o CSV local do Power BI.

Use na máquina do chefe (ou qualquer uma) após git pull — sem rodar coleta completa.

    python sincronizar_dashboard.py
"""
from __future__ import annotations

import csv
import os
import sys

import gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

from powerbi_dataset import COLS
from spoti_paths import DATA_DIR, HISTORICO_CSV, ensure_data_dir

TAB_SPOTIFY = "Spotify"


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


def main() -> int:
    cfg = _config()
    if not os.path.isfile(cfg["service_account_file"]):
        print(f"[ERRO] Service account não encontrada: {cfg['service_account_file']}")
        print("       Copie o JSON da service account para esta pasta (não vai pro git).")
        return 1

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        cfg["service_account_file"], scope
    )
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(cfg["spreadsheet_key"]).worksheet(TAB_SPOTIFY)
    records = ws.get_all_records()
    if not records:
        print("[ERRO] Aba Spotify vazia no Google Sheets.")
        return 1

    rows = []
    for rec in records:
        data = str(rec.get("data", "")).strip()[:10]
        programa = str(rec.get("programa", "")).strip()
        if not data or not programa:
            continue
        rows.append({c: rec.get(c, "") for c in COLS})

    if not rows:
        print("[ERRO] Nenhuma linha válida na aba Spotify.")
        return 1

    rows.sort(key=lambda r: (r["data"], r["programa"]))
    ensure_data_dir()
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(HISTORICO_CSV, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLS)
        writer.writeheader()
        writer.writerows(rows)

    datas = sorted({r["data"] for r in rows})
    url = f"https://docs.google.com/spreadsheets/d/{cfg['spreadsheet_key']}/edit"
    print(f"[OK] {len(rows)} linhas → {HISTORICO_CSV}")
    print(f"[OK] Período: {datas[0]} a {datas[-1]}")
    print(f"[OK] Fonte: {url} (aba {TAB_SPOTIFY})")
    print("[OK] Abra o PBIP e pressione F5.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())