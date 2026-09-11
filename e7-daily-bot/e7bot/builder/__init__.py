"""Build / inventory analysis module.

Reads gear + hero data exported from Fribbels Optimizer, fetches community
build patterns from Fribbels' public API, and produces actionable views:
  - priorities (wishlist + meta tier ranking)
  - junk pile (items that score poorly across your roster)
  - readiness (can I build this hero now?)
  - upgrade plans (what to enhance/farm to close the gap)
  - fit suggestions (best inventory items for a specific hero)
"""
from .fribbels_io import FribbelsSave, load_save, default_save_path
from .meta import MetaBuild, MetaLibrary, load_meta
from .scorer import GearScorer, ItemScore
from .analyzer import Analyzer, InventoryReport
from .wishlist import Wishlist, WishlistEntry, load_wishlist, save_wishlist
from .fribbels_api import FribbelsClient, CachedBuilds
from .build_aggregator import HeroBuilds, SetCombo, TargetStats, aggregate_builds, aggregate_by_recency
from .readiness import HeroReadiness, ReadinessChecker, SlotPick
from .upgrade import HeroUpgradePlan, UpgradeAction, UpgradeRecommender
from .compare import HeroComparator, HeroComparison, ComparisonResult
from .drop_check import DropChecker, DropAnalysis, HeroImpact
from .gw_meta import GwMetaClient, GwMetaSnapshot, Defense, HeroCodeBook

__all__ = [
    "FribbelsSave", "load_save", "default_save_path",
    "MetaBuild", "MetaLibrary", "load_meta",
    "GearScorer", "ItemScore",
    "Analyzer", "InventoryReport",
    "Wishlist", "WishlistEntry", "load_wishlist", "save_wishlist",
    "FribbelsClient", "CachedBuilds",
    "HeroBuilds", "SetCombo", "TargetStats", "aggregate_builds", "aggregate_by_recency",
    "HeroReadiness", "ReadinessChecker", "SlotPick",
    "HeroUpgradePlan", "UpgradeAction", "UpgradeRecommender",
    "HeroComparator", "HeroComparison", "ComparisonResult",
    "DropChecker", "DropAnalysis", "HeroImpact",
    "GwMetaClient", "GwMetaSnapshot", "Defense", "HeroCodeBook",
]
