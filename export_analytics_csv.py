"""
export_analytics_csv.py — Exporta CSV all-time do Analytics de cada podcast FGV.

Para cada show:
  1. Abre a página Analytics no Spotify for Creators (Chrome real via CDP)
  2. Seleciona período "All time" / "Todo o período"
  3. Clica em Exportar
  4. Salva o CSV em downloads/analytics/

Uso:
    python export_analytics_csv.py
    python export_analytics_csv.py --limit 1          # teste com 1 podcast
    python export_analytics_csv.py --podcast "Radar FGV"
    python export_analytics_csv.py --probe           # inspeciona UI do 1º podcast

Requer sessão Chrome em %LOCALAPPDATA%\\SpotiScript\\chrome-profile
e SPOTIFY_EMAIL / SPOTIFY_PASSWORD no .env (mesmo fluxo do token_provider).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError, Page, sync_playwright

from orchestrator import STATIC_PODCASTS
from spoti_paths import ANALYTICS_EXPORTS_DIR

# Reuso do Chrome CDP + login automático
import token_provider
from token_provider import (  # noqa: PLC2701
    CDP_PORT,
    _abrir_chrome,
    _find_chrome,
    _port_aberta,
    _precisa_login,
)

ALL_TIME_LABELS = (
    "Tudo",
    "Até o momento",
    "All time",
    "Todo o período",
    "Todo o periodo",
    "Em todo o período",
    "Em todo o periodo",
    "Desde o início",
    "Desde o inicio",
    "Todo o tempo",
    "Lifetime",
    "Todo o histórico",
    "Histórico completo",
)

ALL_TIME_PATTERN = re.compile(
    r"^tudo$|até\s*o\s*momento|all\s*time|todo\s*o\s*per[ií]odo|lifetime|hist[oó]rico|since\s*launch|desde\s*o\s*in[ií]cio",
    re.IGNORECASE,
)

EXPORT_LABELS = ("Export", "Exportar", "Export data", "Exportar dados")

DATE_RANGE_LABELS = (
    "Últimos 30 dias",
    "Last 30 days",
    "Last 7 days",
    "Últimos 7 dias",
    "Primeiros 7 dias",
    "Last 28 days",
    "Últimos 28 dias",
    "Last 90 days",
    "Últimos 90 dias",
    "Custom",
    "Personalizado",
    "All time",
    "Todo o período",
)


def _show_id_from_uri(uri: str) -> str:
    if uri.startswith("spotify:show:"):
        return uri.split(":", 2)[-1]
    return uri


def _slug(nome: str) -> str:
    s = nome.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s)
    return s or "podcast"


def _analytics_urls(show_id: str) -> list[str]:
    return [
        f"https://creators.spotify.com/analytics/show/{show_id}/overview",
        f"https://creators.spotify.com/pod/show/{show_id}/home",
        "https://creators.spotify.com/analytics/",
    ]


def _dispensar_cookies(page: Page) -> None:
    for label in (
        "Confirmar minhas escolhas",
        "Aceitar todos",
        "Accept all",
        "Permitir todos",
    ):
        try:
            btn = page.get_by_role("button", name=label, exact=False).first
            if btn.is_visible(timeout=1500):
                btn.click(timeout=3000)
                page.wait_for_timeout(800)
                return
        except Exception:
            continue


def _abrir_estatisticas_sidebar(page: Page) -> bool:
    for label in ("Estatísticas", "Estatisticas", "Analytics", "Statistics"):
        try:
            link = page.get_by_role("link", name=label, exact=True).first
            if link.is_visible(timeout=2500):
                link.click(timeout=5000)
                page.wait_for_timeout(3000)
                return True
        except Exception:
            pass
        try:
            link = page.locator(f'a:has-text("{label}")').first
            if link.is_visible(timeout=2500):
                link.click(timeout=5000)
                page.wait_for_timeout(3000)
                return True
        except Exception:
            continue
    return False


def _garantir_chrome() -> None:
    if _port_aberta(CDP_PORT):
        return
    chrome = _find_chrome()
    if not chrome:
        raise RuntimeError("Chrome não encontrado. Edite CHROME_CANDIDATES em token_provider.py.")
    print("[INFO] Abrindo Chrome com perfil SpotiScript...", file=sys.stderr)
    _abrir_chrome(chrome, offscreen=False)
    for _ in range(40):
        if _port_aberta(CDP_PORT):
            return
        time.sleep(0.5)
    raise RuntimeError(f"Chrome não abriu a porta CDP {CDP_PORT}.")


def _garantir_sessao() -> bool:
    """Garante login via fluxo já testado do token_provider (captura Bearer)."""
    print("[INFO] Validando sessão Creators (token_provider)...", file=sys.stderr)
    try:
        token = token_provider.capturar_token(login=False, auto_login=True)
        if token:
            print("[OK] Sessão ativa.", file=sys.stderr)
            return True
    except Exception as exc:
        print(f"[AVISO] capturar_token interrompido: {exc}", file=sys.stderr)

    if _port_aberta(CDP_PORT):
        print(
            "[AVISO] Token não capturado, mas Chrome CDP está aberto — "
            "tentando export com perfil salvo.",
            file=sys.stderr,
        )
        return True

    print(
        "[ERRO] Sessão inválida. Configure .env ou rode: python token_provider.py --login",
        file=sys.stderr,
    )
    return False


def _clicar_primeiro(page: Page, labels: tuple[str, ...], *, role: str = "button") -> bool:
    for label in labels:
        try:
            el = page.get_by_role(role, name=label, exact=False).first
            if el.is_visible(timeout=1500):
                el.click(timeout=5000)
                return True
        except Exception:
            pass
        try:
            el = page.get_by_text(label, exact=False).first
            if el.is_visible(timeout=1500):
                el.click(timeout=5000)
                return True
        except Exception:
            continue
    return False


def _abrir_seletor_periodo(page: Page) -> bool:
    """Abre dropdown de período se ainda não estiver aberto."""
    for label in DATE_RANGE_LABELS:
        try:
            el = page.get_by_role("button", name=label, exact=False).first
            if el.is_visible(timeout=1200):
                el.click(timeout=3000)
                page.wait_for_timeout(600)
                return True
        except Exception:
            pass
        try:
            el = page.get_by_text(label, exact=False).first
            if el.is_visible(timeout=1200):
                el.click(timeout=3000)
                page.wait_for_timeout(600)
                return True
        except Exception:
            continue

    # Combobox genérico (Encore)
    for selector in (
        '[data-encore-id="buttonTertiary"]',
        'button[aria-haspopup="listbox"]',
        'button[aria-haspopup="menu"]',
        '[role="combobox"]',
    ):
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=1200):
                el.click(timeout=3000)
                page.wait_for_timeout(600)
                return True
        except Exception:
            continue
    return False


def _listar_opcoes_periodo(page: Page) -> list[str]:
    textos: list[str] = []
    for selector in ('[role="menuitem"]', '[role="option"]', '[role="radio"]'):
        try:
            for item in page.locator(selector).all():
                txt = (item.inner_text(timeout=400) or "").strip().replace("\n", " | ")
                if txt and len(txt) < 80 and txt not in textos:
                    textos.append(txt)
        except Exception:
            continue
    return textos


def _clicar_opcao_all_time_fuzzy(page: Page) -> bool:
    for selector in ('[role="menuitem"]', '[role="option"]', '[role="radio"]', "li", "button"):
        try:
            for item in page.locator(selector).all():
                txt = (item.inner_text(timeout=400) or "").strip()
                if txt and ALL_TIME_PATTERN.search(txt):
                    item.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    return True
        except Exception:
            continue
    return False


def _selecionar_personalizado_largo(page: Page) -> bool:
    if not _clicar_primeiro(page, ("Personalizado", "Custom")):
        return False
    page.wait_for_timeout(1200)
    for selector in ('input[type="date"]', 'input[placeholder*="Data"]', 'input[aria-label*="Data"]'):
        inputs = page.locator(selector).all()
        if len(inputs) >= 2:
            try:
                inputs[0].fill("2020-01-01", timeout=3000)
                inputs[1].fill(time.strftime("%Y-%m-%d"), timeout=3000)
                if _clicar_primeiro(page, ("Apply", "Aplicar", "Confirmar")):
                    page.wait_for_timeout(2000)
                    return True
            except Exception:
                pass
    return False


def _periodo_atual_all_time(page: Page) -> bool:
    for label in ALL_TIME_LABELS:
        try:
            if page.get_by_role("button", name=label, exact=False).first.is_visible(timeout=1000):
                return True
        except Exception:
            pass
    return False


def _selecionar_all_time(page: Page) -> bool:
    page.wait_for_timeout(2000)
    _dispensar_cookies(page)

    if _periodo_atual_all_time(page):
        print("[INFO] Período já é All time.", file=sys.stderr)
        return True

    opened = False
    for label in DATE_RANGE_LABELS:
        if label in ALL_TIME_LABELS:
            continue
        try:
            buttons = page.get_by_role("button", name=label, exact=False).all()
            for btn in buttons:
                if btn.is_visible(timeout=800):
                    btn.click(timeout=3000)
                    opened = True
                    page.wait_for_timeout(900)
                    break
            if opened:
                break
        except Exception:
            continue

    if not opened:
        opened = _abrir_seletor_periodo(page)

    if not opened:
        return False

    opcoes = _listar_opcoes_periodo(page)
    if opcoes:
        print(f"[INFO] Opções de período: {', '.join(opcoes[:8])}", file=sys.stderr)

    for role in ("option", "menuitem", "radio"):
        if _clicar_primeiro(page, ALL_TIME_LABELS, role=role):
            page.wait_for_timeout(2000)
            if _periodo_atual_all_time(page):
                return True

    if _clicar_opcao_all_time_fuzzy(page) and _periodo_atual_all_time(page):
        return True

    if _clicar_primeiro(page, ALL_TIME_LABELS):
        page.wait_for_timeout(2000)
        if _periodo_atual_all_time(page):
            return True

    # Shows novos podem não ter "All time" — usa o maior intervalo disponível.
    for fallback in ("Últimos 90 dias", "Last 90 days", "Últimos 30 dias", "Last 30 days"):
        if _clicar_primeiro(page, (fallback,), role="option") or _clicar_primeiro(page, (fallback,)):
            page.wait_for_timeout(1500)
            print(f"[AVISO] All time indisponível; usando {fallback}.", file=sys.stderr)
            return True

    if _selecionar_personalizado_largo(page):
        print("[INFO] Período personalizado (2020 → hoje) aplicado.", file=sys.stderr)
        return True

    return False


def _clicar_exportar(page: Page) -> bool:
    # Preferir o Exportar do gráfico principal (Visão geral / plays)
    for label in EXPORT_LABELS:
        try:
            buttons = page.get_by_role("button", name=label, exact=False).all()
            for btn in buttons:
                if btn.is_visible(timeout=1000):
                    btn.click(timeout=5000)
                    return True
        except Exception:
            pass
        try:
            buttons = page.locator(f'button:has-text("{label}")').all()
            for btn in buttons:
                if btn.is_visible(timeout=1000):
                    btn.click(timeout=5000)
                    return True
        except Exception:
            continue
    return False


def _pagina_404(page: Page) -> bool:
    try:
        if page.get_by_text("Opa! Tivemos um probleminha", exact=False).first.is_visible(timeout=1200):
            return True
    except Exception:
        pass
    try:
        if page.get_by_text("404", exact=True).first.is_visible(timeout=800):
            return True
    except Exception:
        pass
    return False


def _tem_botao_exportar(page: Page) -> bool:
    for label in EXPORT_LABELS:
        try:
            if page.get_by_role("button", name=label, exact=False).first.is_visible(timeout=1200):
                return True
        except Exception:
            pass
        try:
            if page.locator(f'button:has-text("{label}")').first.is_visible(timeout=800):
                return True
        except Exception:
            continue
    return False


def _pagina_analytics_pronta(page: Page, show_id: str) -> bool:
    if _pagina_404(page):
        return False
    if _tem_botao_exportar(page):
        return True
    url = page.url.lower()
    return (
        f"/show/{show_id.lower()}" in url
        and any(k in url for k in ("metric", "stat", "analytic", "audience", "engagement", "overview"))
    )


def _navegar_analytics(page: Page, show_id: str) -> bool:
    for url in _analytics_urls(show_id):
        try:
            print(f"[INFO] Tentando {url}", file=sys.stderr)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            if _precisa_login(page):
                return False
            _dispensar_cookies(page)
            if _pagina_404(page):
                print("[AVISO] Página 404 — tentando menu Estatísticas.", file=sys.stderr)
                _abrir_estatisticas_sidebar(page)
                _dispensar_cookies(page)
            elif not _pagina_analytics_pronta(page, show_id):
                print("[INFO] Abrindo Estatísticas no menu lateral...", file=sys.stderr)
                _abrir_estatisticas_sidebar(page)
                _dispensar_cookies(page)
                page.wait_for_timeout(2500)
            if _pagina_analytics_pronta(page, show_id):
                return True
        except Exception as exc:
            print(f"[AVISO] URL falhou: {exc}", file=sys.stderr)
    return False


def _destino_csv(nome: str, show_id: str) -> Path:
    pasta = Path(ANALYTICS_EXPORTS_DIR)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / f"{_slug(nome)}_{show_id}.csv"


def exportar_podcast(page: Page, nome: str, uri: str) -> Path | None:
    show_id = _show_id_from_uri(uri)
    destino = _destino_csv(nome, show_id)

    print(f"\n=== [{nome}] show={show_id} ===", file=sys.stderr)

    if not _navegar_analytics(page, show_id):
        print(f"[ERRO] Não abri Analytics de {nome}.", file=sys.stderr)
        return None

    if not _selecionar_all_time(page):
        print(f"[AVISO] Não confirmei All time em {nome}; tentando exportar mesmo assim.", file=sys.stderr)

    try:
        with page.expect_download(timeout=90000) as download_info:
            if not _clicar_exportar(page):
                print(f"[ERRO] Botão Exportar não encontrado em {nome}.", file=sys.stderr)
                return None
        download = download_info.value
        suggested = download.suggested_filename or f"{_slug(nome)}.csv"
        if not str(destino).endswith(".csv"):
            destino = destino.with_suffix(".csv")
        download.save_as(destino)
        print(f"[OK] Salvo: {destino} (origem: {suggested})", file=sys.stderr)
        return destino
    except PlaywrightError as exc:
        print(f"[ERRO] Download falhou em {nome}: {exc}", file=sys.stderr)
        return None


def probe_ui(page: Page, nome: str, uri: str) -> int:
    """Lista botões visíveis na página Analytics (debug)."""
    show_id = _show_id_from_uri(uri)
    if not _navegar_analytics(page, show_id):
        print("[PROBE] Falha ao abrir Estatísticas.", file=sys.stderr)
        return 1
    print(f"\n[PROBE] URL atual: {page.url}", file=sys.stderr)
    print(f"[PROBE] Export visível: {_tem_botao_exportar(page)}", file=sys.stderr)
    print(f"[PROBE] All time ativo: {_periodo_atual_all_time(page)}", file=sys.stderr)
    if _abrir_seletor_periodo(page):
        print("[PROBE] Opções de período (menu):", file=sys.stderr)
        for txt in _listar_opcoes_periodo(page):
            print(f"  - {txt}", file=sys.stderr)
    try:
        buttons = page.locator("button").all()
        print(f"[PROBE] {len(buttons)} botões na página:", file=sys.stderr)
        for i, btn in enumerate(buttons[:30]):
            try:
                txt = (btn.inner_text(timeout=500) or "").strip().replace("\n", " | ")
                if txt:
                    print(f"  button[{i}]: {txt[:120]}", file=sys.stderr)
            except Exception:
                pass
    except Exception as exc:
        print(f"[PROBE] Erro listando botões: {exc}", file=sys.stderr)
    shot = Path(ANALYTICS_EXPORTS_DIR) / f"probe_{_slug(nome)}.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(shot), full_page=True)
    print(f"[PROBE] Screenshot: {shot}", file=sys.stderr)
    return 0


def run_exports(
    podcasts: list[dict],
    *,
    probe: bool = False,
) -> tuple[int, int]:
    _garantir_chrome()
    if not _garantir_sessao():
        return 0, len(podcasts)

    ok = 0
    total = len(podcasts)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        if probe:
            rc = probe_ui(page, podcasts[0]["nome"], podcasts[0]["uri"])
            return (1 if rc == 0 else 0), 1

        for item in podcasts:
            path = exportar_podcast(page, item["nome"], item["uri"])
            if path and path.is_file() and path.stat().st_size > 0:
                ok += 1
            page.wait_for_timeout(1200)

    return ok, total


def _filtrar_podcasts(nome: str | None, limit: int | None) -> list[dict]:
    items = list(STATIC_PODCASTS)
    if nome:
        alvo = nome.strip().lower()
        items = [p for p in items if p["nome"].lower() == alvo or alvo in p["nome"].lower()]
        if not items:
            raise SystemExit(f"Podcast não encontrado: {nome}")
    if limit is not None and limit > 0:
        items = items[:limit]
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta CSV all-time do Analytics (Spotify Creators).")
    parser.add_argument("--limit", type=int, default=None, help="limita quantidade de podcasts (teste)")
    parser.add_argument("--podcast", type=str, default=None, help="exporta só um podcast pelo nome")
    parser.add_argument("--probe", action="store_true", help="inspeciona UI do primeiro podcast")
    args = parser.parse_args()

    try:
        podcasts = _filtrar_podcasts(args.podcast, args.limit)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        f"[INFO] Exportando {len(podcasts)} podcast(s) → {ANALYTICS_EXPORTS_DIR}",
        file=sys.stderr,
    )

    ok, total = run_exports(podcasts, probe=args.probe)
    print(f"\n[RESUMO] {ok}/{total} CSV(s) exportado(s).", file=sys.stderr)

    if args.probe:
        return 0 if ok else 1
    if ok == 0:
        return 1
    if ok < total:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())