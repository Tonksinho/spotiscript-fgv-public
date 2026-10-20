"""
Orquestrador principal do SpotiScript.

Responsável por:
- Carregar a lista de podcasts (dinâmica via API ou estática)
- Para cada podcast: buscar dados → construir PodcastReport → enviar para todos os writers
- Tratamento de erro isolado por podcast (um falhando não derruba os outros)
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from models import Podcast, PodcastReport, today_str
from parsers import parse_audience_metrics
from spotify_client import PersistedQueryRegistry, SpotifyCreatorsClient
from writers import DataWriter

logger = logging.getLogger(__name__)

# Lista estática de fallback (mantida exatamente como no original)
STATIC_PODCASTS: list[dict] = [
    {"nome": "Aluno Executivo", "uri": "spotify:show:7GDWYNVQr5UmpadyfVrrH0"},
    {"nome": "Conexão Econômica", "uri": "spotify:show:0Dr3IlFJY7GFfEiFJbrChW"},
    {"nome": "Diálogos Amazônicos", "uri": "spotify:show:7FRNnAU6m3BWhtWjFxBXyz"},
    {"nome": "Economia em 15", "uri": "spotify:show:1Rqqx06tuL03Dm18l1BUcc"},
    {"nome": "Empreendedorismo EAESP", "uri": "spotify:show:1WS7PHdQ9TWtkMRXLlpQok"},
    {"nome": "FGV In Company", "uri": "spotify:show:0mr9jnORUWpD92RiRxb3Wh"},
    {"nome": "FGV LAW", "uri": "spotify:show:77FrWaG9UMirv3bYxILOv2"},
    {"nome": "FGV Marketing Talks", "uri": "spotify:show:3hGCp3FkS361kinh0ZPXaZ"},
    {"nome": "Impacto Social FGV", "uri": "spotify:show:7u0hA4H6nGNeWlfG4ViZFJ"},
    {"nome": "Justicast FGV", "uri": "spotify:show:3kD7L2D6O9NBUCQKK8FsXJ"},
    {"nome": "Let´s Talk", "uri": "spotify:show:7ecMeMlvklGUWb4YRwllqo"},
    {"nome": "Radar FGV", "uri": "spotify:show:2N1RPYnelIJvMWTP5EDViU"},
]


class AnalyticsOrchestrator:
    """
    Classe limpa que substitui o antigo PodcastExtractor + 235 linhas de run().

    Design:
    - Recebe dependências por injeção (facilita testes futuros)
    - Cada podcast é processado de forma isolada
    - Todos os efeitos colaterais são delegados aos Writers
    """

    def __init__(
        self,
        client: SpotifyCreatorsClient,
        writers: list[DataWriter],
        registry: Optional[PersistedQueryRegistry] = None,
        use_dynamic_shows: bool = True,
    ):
        self.client = client
        self.writers = writers
        self.registry = registry or client.registry
        self.use_dynamic_shows = use_dynamic_shows
        self.podcasts: list[Podcast] = []

    # ------------------------------------------------------------------
    # Carregamento de podcasts
    # ------------------------------------------------------------------

    def load_podcasts(self) -> None:
        """Carrega lista de podcasts (dinâmica primeiro, fallback estático)."""
        if not self.use_dynamic_shows:
            self.podcasts = [Podcast(p["nome"], p["uri"]) for p in STATIC_PODCASTS]
            logger.info(f"Usando lista estática com {len(self.podcasts)} podcasts.")
            return

        logger.info("Carregando shows do usuário via API...")
        data = self.client.get_user_shows(page=1, page_size=50)

        dynamic: list[Podcast] = []
        if data and data.get("data"):
            shows_data = (
                data.get("data", {}).get("showsForUser", {}).get("shows", [])
                or data.get("data", {}).get("user", {}).get("shows", [])
                or []
            )

            for item in shows_data:
                show = item.get("show") or item
                uri = show.get("uri")
                name = show.get("name") or show.get("title") or "Sem nome"
                if uri:
                    dynamic.append(Podcast(nome=name, uri=uri))

        if dynamic:
            self.podcasts = dynamic
            logger.info(f"→ {len(self.podcasts)} shows carregados dinamicamente.")
        else:
            logger.warning("Falha ao carregar via API. Usando lista estática como fallback.")
            self.podcasts = [Podcast(p["nome"], p["uri"]) for p in STATIC_PODCASTS]

    # ------------------------------------------------------------------
    # Processamento de um único podcast
    # ------------------------------------------------------------------

    def _process_one(self, podcast: Podcast) -> Optional[PodcastReport]:
        """Busca todos os dados de um podcast e retorna um PodcastReport."""
        try:
            # 1. Métricas principais
            header = self.client.get_show_header_stats(podcast.uri)
            demo = self.client.get_audience_demographics(podcast.uri)

            if header == "EXPIRED" or demo == "EXPIRED":
                logger.error("❌ Token expirou! Pegue um novo Bearer Token.")
                return None

            audience = parse_audience_metrics(header, demo)

            # Monta o relatório (sem campos avançados - removidos a pedido do usuário)
            report = PodcastReport(
                date=today_str(),
                podcast=podcast,
                audience=audience,
            )

            return report

        except Exception as e:
            logger.exception(f"Erro inesperado processando {podcast.nome}: {e}")
            return None

    # ------------------------------------------------------------------
    # Execução principal
    # ------------------------------------------------------------------

    def run(self) -> tuple[int, int]:
        """Executa o pipeline completo. Retorna (sucessos, total)."""
        self.load_podcasts()
        total = len(self.podcasts)

        logger.info("\n" + "X" * 65)
        logger.info("DASHBOARD CONSOLIDADO FGV: TERMINAL + PLANILHA")
        logger.info("X" * 65 + "\n")

        # (Aviso de campos avançados removido, pois essas colunas não são mais usadas)

        success_count = 0

        for podcast in self.podcasts:
            report = self._process_one(podcast)

            if report is None:
                logger.warning(f"⚠️  Pulando {podcast.nome} (sem dados ou erro)")
                logger.info("-" * 55)
                time.sleep(1)
                continue

            # Envia para TODOS os writers configurados
            written = False
            for writer in self.writers:
                try:
                    if writer.write(report):
                        written = True
                except Exception as e:
                    logger.error(f"Writer {writer.__class__.__name__} falhou: {e}")

            if written:
                success_count += 1
                logger.info("   [OK] Gravado com sucesso!")
            else:
                logger.warning("   [WARN] Nenhum writer conseguiu gravar os dados")

            logger.info("-" * 55)
            time.sleep(1)  # polidez com a API do Spotify

        logger.info(
            f"\n[OK] RELATÓRIO FINALIZADO — {success_count}/{total} podcasts processados com sucesso."
        )
        return success_count, total
