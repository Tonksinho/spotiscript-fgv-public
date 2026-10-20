"""
Controle de status da coleta quinzenal do SpotiScript.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

STATUS_DIR = Path(__file__).resolve().parent / "data" / "coleta_status"
LOG_FILE = Path(__file__).resolve().parent / "data" / "coleta_agendada.log"
ULTIMA_OK_FILE = STATUS_DIR / "ultima_coleta_ok.json"

INTERVALO_DIAS = 15


def today_iso() -> str:
    return date.today().isoformat()


def status_path(day: Optional[str] = None) -> Path:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    return STATUS_DIR / f"{day or today_iso()}.json"


def append_log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {message}\n")


def load_status(day: Optional[str] = None) -> Optional[dict[str, Any]]:
    path = status_path(day)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def ultima_coleta_ok() -> Optional[dict[str, Any]]:
    if not ULTIMA_OK_FILE.exists():
        return None
    try:
        data = json.loads(ULTIMA_OK_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if data.get("ok") else None


def _parse_finished_at(rec: dict[str, Any]) -> Optional[datetime]:
    raw = rec.get("finished_at") or rec.get("date")
    if not raw:
        return None
    try:
        if "T" in str(raw):
            return datetime.fromisoformat(str(raw))
        return datetime.strptime(str(raw), "%Y-%m-%d")
    except Exception:
        return None


def dias_desde_ultima() -> Optional[int]:
    rec = ultima_coleta_ok()
    if not rec:
        return None
    finished = _parse_finished_at(rec)
    if not finished:
        return None
    delta = datetime.now() - finished
    return max(0, delta.days)


def deve_coletar(*, forcar: bool = False) -> bool:
    if forcar:
        return True
    dias = dias_desde_ultima()
    if dias is None:
        return True
    return dias >= INTERVALO_DIAS


def proxima_coleta_em() -> Optional[int]:
    dias = dias_desde_ultima()
    if dias is None:
        return 0
    restante = INTERVALO_DIAS - dias
    return max(0, restante)


def captura_ok_hoje() -> bool:
    """Compatibilidade: True se a última coleta quinzenal bem-sucedida foi hoje."""
    rec = ultima_coleta_ok()
    if not rec:
        return False
    finished = _parse_finished_at(rec)
    if not finished:
        return False
    return finished.date() == date.today()


def write_status(
    *,
    ok: bool,
    slot: str,
    exit_code: int,
    podcasts_ok: int = 0,
    podcasts_total: int = 0,
    analytics_ok: int = 0,
    analytics_total: int = 0,
    message: str = "",
) -> None:
    payload = {
        "date": today_iso(),
        "ok": ok,
        "slot": slot,
        "exit_code": exit_code,
        "podcasts_ok": podcasts_ok,
        "podcasts_total": podcasts_total,
        "analytics_ok": analytics_ok,
        "analytics_total": analytics_total,
        "message": message,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "intervalo_dias": INTERVALO_DIAS,
    }
    path = status_path()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if ok:
        ULTIMA_OK_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    level = "OK" if ok else "FALHA"
    append_log(
        f"[{level}] slot={slot} exit={exit_code} "
        f"snapshot={podcasts_ok}/{podcasts_total} "
        f"analytics={analytics_ok}/{analytics_total} msg={message or '-'}"
    )


def avaliar_captura(podcasts_ok: int, podcasts_total: int) -> bool:
    if podcasts_ok <= 0 or podcasts_total <= 0:
        return False
    minimo = max(1, int(podcasts_total * 0.9))
    return podcasts_ok >= minimo


def avaliar_analytics(analytics_ok: int, analytics_total: int) -> bool:
    if analytics_ok <= 0 or analytics_total <= 0:
        return False
    minimo = max(1, int(analytics_total * 0.9))
    return analytics_ok >= minimo