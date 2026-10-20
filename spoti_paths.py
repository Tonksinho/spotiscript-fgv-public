"""Caminhos centralizados do SpotiScript + Power BI PBIP (iguais nas duas máquinas)."""
from __future__ import annotations

import os

SPOTISCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Repositório Git (PBIP versionado)
REPO_DIR = os.path.join(SPOTISCRIPT_DIR, "powerbi-dashboards")
PBIP_DIR = os.path.join(REPO_DIR, "dashboards", "spotify-fgv")
PROJ = "SpotifyDashboardFGV"
PBIP_FILE = os.path.join(PBIP_DIR, f"{PROJ}.pbip")

# Dados para o Power BI — mesmo caminho em todas as máquinas
DATA_DIR = r"C:\DadosPowerBI\spotify-fgv"
DATA_CSV = os.path.join(DATA_DIR, "spotify_dashboard.csv")
HISTORICO_CSV = os.path.join(DATA_DIR, "spotify_historico_dashboard.csv")

# Logs/status da coleta (ficam no projeto SpotiScript)
SPOTI_DATA_DIR = os.path.join(SPOTISCRIPT_DIR, "data")
BACKUP_JSONL = os.path.join(SPOTISCRIPT_DIR, "fgv-spotify-backup.jsonl")
LAYOUT_DIR = os.path.join(SPOTISCRIPT_DIR, "report_layout")

# CSVs exportados do Analytics (botão Exportar → All time)
ANALYTICS_EXPORTS_DIR = os.path.join(SPOTISCRIPT_DIR, "downloads", "analytics")
ANALYTICS_EXCEL = os.path.join(SPOTI_DATA_DIR, "spotify_analytics_historico.xlsx")


def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)