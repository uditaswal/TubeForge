"""Immutable child drafts for one-scene operator edits."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from tubeforge.db.repositories import Artifact
from tubeforge.domain.contracts import ContentPackage, ScenePlan, ScriptSection, video_plan_from_package
from tubeforge.domain.states import JobState
from tubeforge.providers.content.prompts import validate_video_package

if TYPE_CHECKING:
    from tubeforge.core.runtime import Runtime


class StaleSceneRevision(ValueError):
    """The editor's reviewed package no longer matches the parent job."""


def create_scene_revision(
    runtime: Runtime, parent_id: str, *, scene_id: str,
    expected_content_sha256: str, actor: str, changes: dict[str, object],
) -> tuple[str, str]:
    """Fork one edited scene without mutating the reviewed parent artifact.

    Existing asset and phrase-voice manifests are snapshot hints. The worker
    revalidates their bytes and request/phrase identities before reuse.
    """
    parent = runtime.jobs.get(parent_id)
    if parent.claim_owner is not None or parent.state not in {
        JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_READY,
        JobState.FINAL_READY, JobState.PUBLICATION_APPROVAL_REQUIRED,
    }:
        raise ValueError("scene revisions require an unclaimed local review job")
    orchestrator = runtime.orchestrator
    source_artifact = orchestrator._required_artifact(parent_id, JobState.CONTENT_GENERATING, "content_package")
    if source_artifact.checksum_sha256 != expected_content_sha256:
        raise StaleSceneRevision("the script changed; reload the scene before saving")
    source = ContentPackage.model_validate(orchestrator._required_json(parent_id, JobState.CONTENT_GENERATING, "content_package"))
    scene_index = next((index for index, item in enumerate(source.scene_plans) if item.scene_id == scene_id), None)
    if scene_index is None:
        raise ValueError("scene does not exist in the reviewed script")
    section_index = next((index for index, item in enumerate(source.script_sections) if item.scene_id == scene_id), None)
    if section_index is None:
        raise ValueError("scene has no narration section")
    scene_fields = {key: value for key, value in changes.items() if key in {
        "visual_type", "visual_subject", "visual_purpose", "composition", "on_screen_text", "visual_elements",
    }}
    narration = changes.get("narration")
    scene = ScenePlan.model_validate({**source.scene_plans[scene_index].model_dump(mode="json"), **scene_fields})
    section = ScriptSection.model_validate({**source.script_sections[section_index].model_dump(mode="json"), **({"narration": narration} if narration is not None else {})})
    if scene == source.scene_plans[scene_index] and section == source.script_sections[section_index]:
        raise ValueError("change the narration or visual direction before saving")
    scenes = list(source.scene_plans)
    sections = list(source.script_sections)
    scenes[scene_index] = scene
    sections[section_index] = section
    request = parent.request.model_copy(update={"review_mode": "manual"})
    revised = ContentPackage.model_validate({
        **source.model_dump(mode="json"),
        "request": request.model_dump(mode="json"),
        "scene_plans": [item.model_dump(mode="json") for item in scenes],
        "script_sections": [item.model_dump(mode="json") for item in sections],
    })
    if request.aspect_ratio == "9:16":
        validate_video_package(revised, request, provider_name="Revised")

    job_id = uuid4().hex
    directory = orchestrator._artifact_path(job_id, "scene_revision.json").parent
    staged: list[Artifact] = []

    def stage(stage_state: JobState, name: str, value: object) -> Artifact:
        path = orchestrator._artifact_path(job_id, f"{name}.json")
        contents = json.dumps(value, sort_keys=True).encode("utf-8")
        orchestrator._atomic_write(path, contents)
        artifact = Artifact(job_id, stage_state, name, str(path), hashlib.sha256(contents).hexdigest(), {"generator": "scene-revision", "parent_job_id": parent_id})
        staged.append(artifact)
        return artifact

    try:
        content = stage(JobState.CONTENT_GENERATING, "content_package", revised.model_dump(mode="json"))
        stage(JobState.CONTENT_GENERATING, "video_plan", video_plan_from_package(revised, aspect_ratio=request.aspect_ratio).model_dump(mode="json"))
        stage(JobState.CONTENT_GENERATING, "script_revision", {"actor": actor, "content_package_checksum": content.checksum_sha256})
        stage(JobState.CONTENT_GENERATING, "scene_revision", {
            "parent_job_id": parent_id,
            "parent_content_sha256": source_artifact.checksum_sha256,
            "content_package_checksum": content.checksum_sha256,
            "scene_id": scene_id,
            "changed_narration": section != source.script_sections[section_index],
            "changed_visual": scene != source.scene_plans[scene_index],
            "actor": actor,
        })
        for stage_state, name in (
            (JobState.CONTENT_GENERATING, "source_packet"),
            (JobState.CONTENT_GENERATING, "effective_content_request"),
            (JobState.ASSET_ACQUISITION, "asset_manifest"),
            (JobState.VOICE_GENERATION, "voice_manifest"),
        ):
            value = orchestrator._load_json_artifact(parent_id, stage_state, name)
            if value is not None:
                stage(stage_state, name, value)
        runtime.jobs.create_scene_revision(
            job_id, parent_id, request, tuple(staged), scene_id=scene_id,
            actor=actor, content_checksum=content.checksum_sha256,
        )
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return job_id, content.checksum_sha256
