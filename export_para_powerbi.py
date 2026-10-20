"""
Exportador para o Power BI (CSV local — fallback).

Lê o backup `fgv-spotify-backup.jsonl` e gera
``C:/DadosPowerBI/spotify-fgv/spotify_dashboard.csv``.

O fluxo principal do dashboard pode usar Google Sheets via export_para_sheets.py.
"""
from __future__ import annotations

import csv
import os

import spoti_paths as paths
from powerbi_dataset import COLS, load_clean_rows

OUT = paths.DATA_CSV


def main() -> int:
    try:
        data_sorted, total_lidas = load_clean_rows(paths.BACKUP_JSONL)
    except FileNotFoundError as e:
        print(f"[ERRO] {e}")
        return 1

    os.makedirs(paths.DATA_DIR, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in data_sorted:
            w.writerow(r)

    datas = sorted({r["data"] for r in data_sorted})
    print(f"[OK] {total_lidas} linhas lidas -> {len(data_sorted)} linhas limpas (deduplicadas).")
    print(f"[OK] Datas no arquivo: {', '.join(datas)}")
    print(f"[OK] CSV gerado: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())