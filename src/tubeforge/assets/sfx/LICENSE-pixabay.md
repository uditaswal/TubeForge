# Sound effects: license and provenance

The 19 `.mp3` files in this directory are sound effects originally sourced from
[Pixabay](https://pixabay.com/sound-effects/) and distributed under the
[Pixabay Content License](https://pixabay.com/service/license-summary/), which
permits free use for commercial and non-commercial purposes, modification,
and redistribution as part of a derivative work (such as a video rendered by
this pipeline), without an attribution requirement.

## Where these bytes came from

Vendored byte-for-byte (no re-encoding) on 2026-10-26 from the `heygen-com/hyperframes`
repository (Apache-2.0, `Graphify`-reviewed local checkout), path
`skills/media-use/audio/assets/sfx/`, at local commit `24965372dbbe` (24 Oct 2026).
That repository's own `CREDITS.md` for this directory names Pixabay as the
source and the Pixabay Content License as the terms; this file restates the
same chain of custody for this repository, per
`docs/reviews/2026-10-26-av-quality-hyperframes-voicestudio.md` §4.5.

HyperFrames' own license (Apache-2.0) covers its code, not these audio files;
the audio files carry the Pixabay Content License named above and in each
entry's `manifest.json` `license` field.

## Full text

See https://pixabay.com/service/license-summary/ for the current, canonical
license text. Summary as of this vendoring: Pixabay-licensed content may be
used free of charge for commercial and non-commercial purposes across digital
and print media, with or without modification, without attribution, except
where the specific media shows an identifiable person, recognizable brand, or
registered trademark (not applicable to these abstract UI/transition sound
effects).
