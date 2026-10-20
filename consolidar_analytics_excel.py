"""
consolidar_analytics_excel.py — Une os CSVs do Analytics (all-time) em um Excel único.

Lê todos os *.csv em downloads/analytics/, adiciona coluna programa/show_id,
grava planilha principal para o dashboard Power BI.

Uso:
    python consolidar_analytics_excel.py
    python consolidar_analytics_excel.py --dir downloads/analytics
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from orchestrator import STATIC_PODCASTS
from powerbi_dataset import COLS, load_clean_rows
from spoti_paths import ANALYTICS_EXPORTS_DIR, DATA_DIR, SPOTI_DATA_DIR

EXCEL_NAME = "spotify_analytics_historico.xlsx"
EXCEL_PATH = Path(SPOTI_DATA_DIR) / EXCEL_NAME

# Mapeia show_id -> nome oficial
SHOW_NAMES: dict[str, str] = {}
for p in STATIC_PODCASTS:
    uri = p["uri"]
    show_id = uri.split(":")[-1] if ":" in uri else uri
    SHOW_NAMES[show_id] = p["nome"]


def _parse_filename(path: Path) -> tuple[str, str]:
    """Extrai slug e show_id do padrão nome-slug_SHOWID.csv."""
    stem = path.stem
    m = re.match(r"^(.+)_([A-Za-z0-9]{22})$", stem)
    if m:
        return m.group(1), m.group(2)
    return stem, ""


def _read_csv(path: Path) -> pd.DataFrame:
    # UTF-8 com BOM (export Spotify)
    df = pd.read_csv(path, encoding="utf-8-sig")
    slug, show_id = _parse_filename(path)
    programa = SHOW_NAMES.get(show_id, slug.replace("-", " ").title())
    df.insert(0, "programa", programa)
    df.insert(1, "show_id", show_id)
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], dayfirst=True, errors="coerce")
    df["arquivo_origem"] = path.name
    df["consolidado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return df


def _snapshot_por_programa() -> pd.DataFrame:
    """Última coleta SpotiScript (seguidores + demografia) por programa."""
    rows, _ = load_clean_rows()
    if not rows:
        return pd.DataFrame(
            columns=[
                "programa",
                "seguidores",
                "pct_homens",
                "pct_mulheres",
                "pct_outros",
                "top_faixa_etaria",
            ]
        )
    snap = pd.DataFrame(rows)
    snap["data"] = pd.to_datetime(snap["data"], errors="coerce")
    latest = (
        snap.sort_values("data")
        .groupby("programa", as_index=False)
        .last()[
            [
                "programa",
                "seguidores",
                "pct_homens",
                "pct_mulheres",
                "pct_outros",
                "top_faixa_etaria",
            ]
        ]
    )
    return latest


def _build_spotify_dashboard(historico: pd.DataFrame, snapshot: pd.DataFrame) -> pd.DataFrame:
    """Aba Spotify — schema do PBIP (plays diários + snapshot demografia)."""
    base = historico.copy()
    base = base.rename(columns={"Data": "data", "Plays e downloads": "plays"})
    base["data"] = pd.to_datetime(base["data"], errors="coerce")
    base = base.dropna(subset=["data"])
    base["plays"] = pd.to_numeric(base["plays"], errors="coerce").fillna(0).astype(int)

    merged = base.merge(snapshot, on="programa", how="left")
    for col in ("seguidores", "pct_homens", "pct_mulheres", "pct_outros"):
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)
    if "top_faixa_etaria" in merged.columns:
        merged["top_faixa_etaria"] = merged["top_faixa_etaria"].fillna("N/A")

    out = merged[[c for c in COLS if c in merged.columns]].copy()
    return out.sort_values(["data", "programa"])


def _build_resumo(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    agg = (
        df.groupby("programa", as_index=False)
        .agg(
            show_id=("show_id", "first"),
            data_min=("Data", "min"),
            data_max=("Data", "max"),
            dias=("Data", "nunique"),
            plays_total=("Plays e downloads", "sum"),
            publico_total=("Público", "sum"),
        )
        .sort_values("programa")
    )
    return agg


def consolidar(csv_dir: Path, excel_path: Path) -> tuple[int, Path]:
    csv_files = sorted(csv_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"Nenhum CSV em {csv_dir}")

    frames = []
    for f in csv_files:
        try:
            frames.append(_read_csv(f))
            print(f"[OK] Lido: {f.name}", file=sys.stderr)
        except Exception as exc:
            print(f"[ERRO] Falha ao ler {f.name}: {exc}", file=sys.stderr)

    if not frames:
        raise RuntimeError("Nenhum CSV válido para consolidar.")

    dados = pd.concat(frames, ignore_index=True)
    dados = dados.sort_values(["programa", "Data"], na_position="last")
    resumo = _build_resumo(dados)
    snapshot = _snapshot_por_programa()
    spotify = _build_spotify_dashboard(dados, snapshot)

    excel_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        dados.to_excel(writer, sheet_name="Historico", index=False)
        spotify.to_excel(writer, sheet_name="Spotify", index=False)
        resumo.to_excel(writer, sheet_name="Resumo", index=False)

    # Cópia para pasta padrão do Power BI Desktop
    import shutil

    pbi_dir = Path(DATA_DIR)
    pbi_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(excel_path, pbi_dir / excel_path.name)

    # CSV — leitura mais estável no Power BI (mesmo schema da tabela Spotify)
    csv_out = spotify.copy()
    csv_out["data"] = pd.to_datetime(csv_out["data"]).dt.strftime("%Y-%m-%d")
    csv_path = pbi_dir / "spotify_historico_dashboard.csv"
    csv_out.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[OK] CSV Power BI: {csv_path}", file=sys.stderr)

    return len(csv_files), excel_path, len(dados), len(resumo), len(spotify)


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolida CSVs Analytics em Excel único")
    parser.add_argument("--dir", type=Path, default=Path(ANALYTICS_EXPORTS_DIR))
    parser.add_argument("--output", type=Path, default=EXCEL_PATH)
    args = parser.parse_args()

    try:
        n, path, linhas, programas, spotify_linhas = consolidar(args.dir, args.output)
    except Exception as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1

    print(f"\n[OK] {n} CSV(s) → {path}", file=sys.stderr)
    print(
        f"     Abas: Historico ({linhas}), Spotify ({spotify_linhas}), Resumo ({programas})",
        file=sys.stderr,
    )
    print(f"     Cópia PB: {Path(DATA_DIR) / path.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())