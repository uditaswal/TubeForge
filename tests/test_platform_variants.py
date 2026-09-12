from tubeforge.pipeline.variants import plan_variants


def test_platform_variants_reuse_master_and_mark_portrait_derivatives() -> None:
    variants = plan_variants(master_path="/artifacts/master.mp4", title="A title", description="Description", tags=("software engineering", "AWS"))
    assert len(variants) == 5
    assert all(item.source_path == "/artifacts/master.mp4" for item in variants)
    assert next(item for item in variants if item.profile == "youtube_landscape").requires_derivative is False
    assert all(item.requires_derivative for item in variants if item.aspect_ratio == "9:16")
    assert "#softwareengineering" in next(item for item in variants if item.platform == "instagram").hashtags
