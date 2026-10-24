"""Deterministic local stock ranking; metadata relevance is a review signal."""
from __future__ import annotations

import math
from collections import Counter
from functools import lru_cache
from urllib.parse import urlparse

from tubeforge.providers.media.library import words
from tubeforge.providers.media.pixabay import LICENSE, StockAsset

VERSION = "stock-rank-v1"


@lru_cache(maxsize=4096)
def _features(text: str) -> frozenset[str]:
    aliases = {"coding": "code", "programming": "code", "programmer": "developer",
               "developers": "developer", "computers": "computer", "laptops": "laptop"}
    return frozenset(aliases.get(word, word) for word in words(text))


def rank_assets(assets: list[StockAsset], *, query: str, scene_text: str,
                used_ids: set[str] | frozenset[str] = frozenset(),
                previous_tags: tuple[str, ...] = (), min_duration: float = 4.0) -> list[dict]:
    """Rank only rights/size/duration-eligible assets; never infer claim proof.

    The query is the model-authored visual subject, and must match at least half
    its content terms. Reviewed narration is only a small tie-breaker. Prior
    tags discourage repetitive shots but cannot rescue an irrelevant clip.
    """
    wanted = _features(query)
    if not wanted:
        return []
    eligible = [asset for asset in assets if asset.asset_id not in used_ids
                and asset.kind in {"video", "image"} and asset.license_name == LICENSE
                and urlparse(asset.page_url).hostname == "pixabay.com"
                and asset.width >= 720 and asset.height >= 720
                and (asset.kind == "image" or (asset.duration or 0) >= min_duration)]
    tag_features = {asset.asset_id: _features(asset.tags) for asset in eligible}
    document_frequency = Counter(word for tags in tag_features.values() for word in tags)
    weight = {word: 1 + math.log((len(eligible) + 1) / (document_frequency[word] + 1)) for word in wanted}
    total_weight = sum(weight.values())
    scene_words = _features(scene_text)
    previous = tuple(_features(tags) for tags in previous_tags)
    ranked = []
    for asset in eligible:
        tags = tag_features[asset.asset_id]
        matched = wanted & tags
        query_coverage = sum(weight[word] for word in matched) / total_weight
        if len(matched) / len(wanted) < .5 or query_coverage < .5:
            continue
        narration_overlap = len(scene_words & tags) / max(1, len(scene_words))
        repetition = max((len(tags & prior) / max(1, len(tags | prior)) for prior in previous), default=0.0)
        portrait = .06 if asset.height > asset.width else 0.0
        resolution = .04 * min(asset.height, 1920) / 1920
        score = query_coverage + .08 * narration_overlap + portrait + resolution - .15 * repetition
        ranked.append({"asset": asset, "score": round(score, 5),
                       "query_coverage": round(query_coverage, 5),
                       "matched_terms": sorted(matched), "repetition_penalty": round(.15 * repetition, 5),
                       "asset_id": asset.asset_id})
    return sorted(ranked, key=lambda row: (-row["score"], row["asset_id"]))
