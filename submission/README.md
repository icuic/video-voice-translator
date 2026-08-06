# Video Voice Translator — Submission Snapshot

This folder is a **local snapshot copy** of the materials submitted to the 2026 AMD AI DevMaster Hackathon, Track 1, for reference and offline reproducibility.

The **authoritative submission** lives in the fork PR at:

- Fork repository: [icuic/Radeon-hackathon-2026-07](https://github.com/icuic/Radeon-hackathon-2026-07)
- Submission package (browse online in fork): [`submissions/track1-video-voice-translator/`](https://github.com/icuic/Radeon-hackathon-2026-07/tree/track1-icuic-video-voice-translator/submissions/track1-video-voice-translator) (branch `track1-icuic-video-voice-translator` @ `53c0542`)
- Submission directory: `submissions/track1-video-voice-translator/`
- Authoritative source repository: [icuic/video-voice-translator](https://github.com/icuic/video-voice-translator)
  - Submission branch: [amd-track1-video-voice-translator](https://github.com/icuic/video-voice-translator/tree/amd-track1-video-voice-translator)
  - Evaluated snapshot: [234f231](https://github.com/icuic/video-voice-translator/tree/234f231)
- Submission branch: [amd-track1-video-voice-translator](https://github.com/icuic/video-voice-translator/tree/amd-track1-video-voice-translator)
- Evaluated commit: [234f231](https://github.com/icuic/video-voice-translator/tree/234f231)

## Files in This Snapshot

| File | Purpose |
|---|---|
| `README.md` (this file) | Local snapshot index |
| `PROJECT_PROFILE.md` | Editable markdown source for the Project Profile PDF |
| `track1-project-profile.pdf` | Final PDF artifact (required) |
| `track1-poster.svg` | Poster artifact (required, supplementary material) |

> **Note:**
> - The **bundled demo video** is not duplicated here to avoid large files in two places. Use either the PR-local artifact in the fork (`submissions/track1-video-voice-translator/demo.mp4`) or the canonical source copy: [data/demo/demo.mp4](../data/demo/demo.mp4).
> - The **authoritative submission README** (with full checklist + reproduction steps + AMD/ROCm notes) is the one inside the fork PR: `submissions/track1-video-voice-translator/README.md`. The source repository's top-level [README.md](../README.md) contains the canonical install/run docs used by that submission README.

## Quick Links (Evaluated Commit [234f231](https://github.com/icuic/video-voice-translator/tree/234f231))

- Submission branch: <https://github.com/icuic/video-voice-translator/tree/amd-track1-video-voice-translator>
- Evaluated snapshot: <https://github.com/icuic/video-voice-translator/tree/234f231>
- Source repo README: <https://github.com/icuic/video-voice-translator/blob/amd-track1-video-voice-translator/README.md>
- Demo video mirror: <https://github.com/icuic/video-voice-translator/blob/amd-track1-video-voice-translator/data/demo/demo.mp4>
- Install guide: [docs/INSTALL.md](../docs/INSTALL.md)
- Usage guide: [docs/USAGE.md](../docs/USAGE.md)
- Demo guide: [docs/DEMO.md](../docs/DEMO.md)

## Mandated Track 1 Artifacts

All four mandated artifacts are delivered. The local-reproduction equivalents are:

1. **Project Source Code** — this repository, branch [amd-track1-video-voice-translator](https://github.com/icuic/video-voice-translator/tree/amd-track1-video-voice-translator), commit [234f231](https://github.com/icuic/video-voice-translator/tree/234f231)
2. **Project Profile PDF** — `track1-project-profile.pdf` (with `PROJECT_PROFILE.md` as source)
3. **Demo Video** — canonical copy at [data/demo/demo.mp4](../data/demo/demo.mp4); fork PR copy at `submissions/track1-video-voice-translator/demo.mp4`
4. **Supplementary material (Poster)** — `track1-poster.svg`

## Reproduction Shortcut

```bash
git clone https://github.com/icuic/video-voice-translator.git
cd video-voice-translator
git checkout amd-track1-video-voice-translator
git reset --hard 234f231

./install_all.sh
# edit .env with a valid LLM endpoint + key, then:
./service.sh up
# open http://127.0.0.1:5173
```

The fork PR's submission README (the authoritative one, not this local snapshot) contains the full evaluator checklist and step-by-step review order.
