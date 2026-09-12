"""Componentes pequeños y reutilizables del módulo de Estadísticas."""

from app.modules.statistics.ranking import (
    RANKING_PAGE_SIZE,
    RankingPage,
    paginate_ranking,
)

__all__ = ["RANKING_PAGE_SIZE", "RankingPage", "paginate_ranking"]
