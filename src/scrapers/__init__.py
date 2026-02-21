"""Job board scrapers for VC portfolio companies."""

from .base import BaseScraper
from .getro_base import GetroScraper
from .a16z import A16ZScraper
from .sequoia import SequoiaScraper
from .index_ventures import IndexVenturesScraper
from .general_catalyst import GeneralCatalystScraper
from .greylock import GreylockScraper
from .kleiner_perkins import KleinerPerkinsScraper
from .accel import AccelScraper
from .contrary import ContraryScraper
from .pear import PearScraper
from .battery import BatteryScraper
from .nea import NEAScraper
from .antler import AntlerScraper
from .lsvp import LSVPScraper
from .bvp import BVPScraper

ALL_SCRAPERS = [
    A16ZScraper,
    SequoiaScraper,
    IndexVenturesScraper,
    GeneralCatalystScraper,
    GreylockScraper,
    KleinerPerkinsScraper,
    AccelScraper,
    ContraryScraper,
    PearScraper,
    BatteryScraper,
    NEAScraper,
    AntlerScraper,
    LSVPScraper,
    BVPScraper,
]

__all__ = [
    "BaseScraper",
    "ALL_SCRAPERS",
    "A16ZScraper",
    "SequoiaScraper",
    "IndexVenturesScraper",
    "GeneralCatalystScraper",
    "GreylockScraper",
    "KleinerPerkinsScraper",
    "AccelScraper",
    "ContraryScraper",
    "PearScraper",
    "BatteryScraper",
    "NEAScraper",
    "AntlerScraper",
    "LSVPScraper",
    "BVPScraper",
]
