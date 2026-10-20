"""
coletar.py — pipeline quinzenal SpotiScript → planilha principal → dashboard.

A cada 15 dias (ou com --force):
    1. token_provider   → sessão Spotify Creators
    2. spotiscrap       → snapshot seguidores/demografia (JSONL)
    3. export_analytics_csv → CSV all-time de cada podcast
    4. consolidar_analytics_excel → spotify_analytics_historico.xlsx + CSV do Power BI
    5. export_para_sheets → Google Sheets (Historico + Spotify + Resumo — obrigatório)

Uso:
    python coletar.py
    python coletar.py --force          # ignora intervalo de 15 dias
    python coletar.py --sem-analytics  # só snapshot + consolidar CSVs já baixados

Agendamento: .\\agendar_tarefas.ps1
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import coleta_status
import token_provider
from orchestrator import STATIC_PODCASTS
from spoti_paths import ANALYTICS_EXCEL, ANALYTICS_EXPORTS_DIR, HISTORICO_CSV


def _abrir_dashboard() -> None:
    script = os.path.join(os.path.dirname(__file__), "atualizar_dashboard.ps1")
    if not os.path.isfile(script):
        print("       (atualizar_dashboard.ps1 não encontrado — abra o .pbip manualmente)")
        return
    try:
        import subprocess

        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script,
            ],
            cwd=os.path.dirname(__file__),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        print(f"       (não foi possível abrir o Power BI: {exc})")


def _falha(
    *,
    slot: str,
    exit_code: int,
    message: str,
    podcasts_ok: int = 0,
    podcasts_total: int = 0,
    analytics_ok: int = 0,
    analytics_total: int = 0,
) -> int:
    coleta_status.write_status(
        ok=False,
        slot=slot,
        exit_code=exit_code,
        podcasts_ok=podcasts_ok,
        podcasts_total=podcasts_total,
        analytics_ok=analytics_ok,
        analytics_total=analytics_total,
        message=message,
    )
    print(f"\n[ERRO] {message}", file=sys.stderr)
    return exit_code


def main(
    slot: str = "manual",
    *,
    forcar: bool = False,
    sem_analytics: bool = False,
) -> int:
    coleta_status.append_log(f"[INICIO] slot={slot} forcar={forcar}")

    if slot == "agendado" and not forcar and not coleta_status.deve_coletar():
        dias = coleta_status.dias_desde_ultima()
        restante = coleta_status.proxima_coleta_em()
        ultima = coleta_status.ultima_coleta_ok() or {}
        quando = ultima.get("finished_at", "?")
        print(
            f"[SKIP] Coleta quinzenal já feita há {dias} dia(s) ({quando}). "
            f"Próxima em ~{restante} dia(s). Use --force para rodar agora."
        )
        coleta_status.append_log("[SKIP] motivo=intervalo_quinzenal")
        return 0

    print(f"=== SpotiScript — coleta quinzenal (intervalo: {coleta_status.INTERVALO_DIAS} dias) ===\n")

    print("=== [1/5] Obtendo token do Spotify Creators (sessão salva) ===")
    token = token_provider.capturar_token(login=False)
    if not token:
        return _falha(
            slot=slot,
            exit_code=1,
            message="Não foi possível obter token. Rode: python token_provider.py --login",
        )
    os.environ["SPOTIFY_BEARER"] = token
    print("[OK] Token capturado.\n")

    print("=== [2/5] Coletando snapshot seguidores/demografia (spotiscrap) ===")
    import spotiscrap

    rc = spotiscrap.main()
    stats = spotiscrap.LAST_RUN_STATS
    podcasts_ok = int(stats.get("success", 0))
    podcasts_total = int(stats.get("total", 0))

    if rc == 1:
        return _falha(
            slot=slot,
            exit_code=rc,
            podcasts_ok=podcasts_ok,
            podcasts_total=podcasts_total,
            message="spotiscrap falhou",
        )
    if rc == 2:
        print(
            f"[AVISO] Snapshot parcial ({podcasts_ok}/{podcasts_total}). "
            "Seguindo com analytics/consolidação.",
            file=sys.stderr,
        )

    analytics_ok = 0
    analytics_total = len(STATIC_PODCASTS)

    if sem_analytics:
        print("\n=== [3/5] Export Analytics — PULADO (--sem-analytics) ===")
        csvs = list(Path(ANALYTICS_EXPORTS_DIR).glob("*.csv"))
        analytics_ok = len([f for f in csvs if f.stat().st_size > 0])
        print(f"[INFO] Usando {analytics_ok} CSV(s) já existentes em downloads/analytics/")
        if analytics_ok == 0:
            return _falha(
                slot=slot,
                exit_code=1,
                podcasts_ok=podcasts_ok,
                podcasts_total=podcasts_total,
                message="Nenhum CSV em downloads/analytics. Rode sem --sem-analytics.",
            )
    else:
        print("\n=== [3/5] Exportando CSVs all-time do Analytics (12 podcasts) ===")
        import export_analytics_csv

        analytics_ok, analytics_total = export_analytics_csv.run_exports(list(STATIC_PODCASTS))
        print(f"[RESUMO] Analytics: {analytics_ok}/{analytics_total} CSV(s).")
        if analytics_ok == 0:
            return _falha(
                slot=slot,
                exit_code=1,
                podcasts_ok=podcasts_ok,
                podcasts_total=podcasts_total,
                analytics_ok=analytics_ok,
                analytics_total=analytics_total,
                message="export_analytics_csv não gerou nenhum CSV",
            )

    print("\n=== [4/5] Consolidando planilha principal + CSV do dashboard ===")
    import consolidar_analytics_excel as consolidar_mod

    try:
        n_csv, excel_path, linhas, programas, spotify_linhas = consolidar_mod.consolidar(
            Path(ANALYTICS_EXPORTS_DIR),
            Path(ANALYTICS_EXCEL),
        )
    except Exception as exc:
        return _falha(
            slot=slot,
            exit_code=1,
            podcasts_ok=podcasts_ok,
            podcasts_total=podcasts_total,
            analytics_ok=analytics_ok,
            analytics_total=analytics_total,
            message=f"consolidar_analytics_excel falhou: {exc}",
        )

    print(
        f"[OK] {n_csv} CSV(s) → {excel_path}\n"
        f"     Abas: Historico ({linhas}), Spotify ({spotify_linhas}), Resumo ({programas})\n"
        f"     Dashboard: {HISTORICO_CSV}"
    )

    print("\n=== [5/5] Publicando no Google Sheets (Historico + Spotify + Resumo) ===")
    import export_para_sheets

    rc = export_para_sheets.main_from_consolidado(Path(excel_path))
    if rc != 0:
        return _falha(
            slot=slot,
            exit_code=rc,
            podcasts_ok=podcasts_ok,
            podcasts_total=podcasts_total,
            analytics_ok=analytics_ok,
            analytics_total=analytics_total,
            message="export_para_sheets falhou — dados não foram salvos na planilha Google",
        )

    snapshot_ok = coleta_status.avaliar_captura(podcasts_ok, podcasts_total)
    analytics_bom = coleta_status.avaliar_analytics(analytics_ok, analytics_total)
    pipeline_ok = analytics_bom
    if not snapshot_ok:
        print(
            f"[AVISO] Snapshot parcial ({podcasts_ok}/{podcasts_total}); "
            "demografia/seguidores podem estar desatualizados.",
            file=sys.stderr,
        )

    coleta_status.write_status(
        ok=pipeline_ok,
        slot=slot,
        exit_code=0 if pipeline_ok else 2,
        podcasts_ok=podcasts_ok,
        podcasts_total=podcasts_total,
        analytics_ok=analytics_ok,
        analytics_total=analytics_total,
        message="pipeline quinzenal completo" if pipeline_ok else "pipeline parcial",
    )

    if pipeline_ok:
        print("\n=== Pronto! Abra o Power BI e pressione F5 (Atualizar). ===")
        _abrir_dashboard()
        return 0

    print(
        "\n[AVISO] Pipeline terminou com lacunas. "
        f"Snapshot {podcasts_ok}/{podcasts_total}, Analytics {analytics_ok}/{analytics_total}.",
        file=sys.stderr,
    )
    return 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline quinzenal SpotiScript")
    parser.add_argument(
        "--slot",
        choices=["manual", "agendado", "manha", "tarde"],
        default="manual",
        help="manual ou agendado (respeita intervalo de 15 dias)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="ignora o intervalo de 15 dias",
    )
    parser.add_argument(
        "--sem-analytics",
        action="store_true",
        help="não exporta CSVs do Analytics; usa os já baixados",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    slot = "agendado" if args.slot in ("manha", "tarde") else args.slot
    raise SystemExit(
        main(
            slot=slot,
            forcar=args.force,
            sem_analytics=args.sem_analytics,
        )
    )