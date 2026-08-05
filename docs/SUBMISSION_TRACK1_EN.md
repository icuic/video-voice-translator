# Track 1 Submission Note

This document is the English submission companion for the 2026 AMD AI DevMaster Hackathon Track 1 entry: **Video Voice Translator**.

## Suggested Pull Request Title

Use the official format:

```text
Track 1, <Team Name or Your Name>, Video Voice Translator
```

## Submission Package Checklist

The repository is prepared to include the following materials:

1. **Project Source Code**
   - Main repository with frontend, backend, worker, and scripts
   - English README: `README_EN.md`
   - Supporting documentation under `docs/`

2. **Project Profile Document (PDF)**
   - Generated file: `deliverables/track1-project-profile.pdf`
   - Source markdown: `docs/PROJECT_PROFILE_TRACK1_EN.md`

3. **Demo Video**
   - Demo artifact: `data/demo/demo.mp4`

4. **Supplementary Material**
   - Poster artifact: `deliverables/track1-poster.svg`

## What the Project Demonstrates

Video Voice Translator is a multimodal content creation tool that:

- takes a source video or audio file,
- recognizes speech content,
- translates the transcript between English and Chinese,
- clones the original speaking style with IndexTTS2,
- and renders a dubbed output video for content localization.

## How Evaluators Can Review the Project

### Option A: Watch the demo first

Open:

- `data/demo/demo.mp4`

### Option B: Reproduce locally

1. Install dependencies:

   ```bash
   ./install_all.sh
   ```

2. Configure `.env` with a valid translation API key.

3. Start the demo stack:

   ```bash
   ./service.sh up
   ```

4. Open the frontend:

   ```text
   http://127.0.0.1:5173
   ```

5. Upload a short English video and run `English -> Chinese`.

## Main Technical Highlights

- Frontend/backend split architecture for a cleaner demo experience
- Task persistence for replaying completed results from history
- Progress reporting across extraction, ASR, translation, voice cloning, and final synthesis
- AMD/ROCm-oriented runtime tuning
- Practical scripts for installation, startup, and service management

## AMD Radeon / ROCm Notes

- Native `whisper` is the default ASR backend in this branch for better ROCm compatibility.
- ROCm PyTorch installation is handled by the install script on AMD cloud environments.
- `IndexTTS2` keeps FP16 enabled while disabling CUDA-only kernels that are not suitable for ROCm.

## Known Constraints

- The strongest demo path is short-form single-speaker content.
- Reverse-proxy deployments may need additional tuning for very long uploads.
- Multi-speaker processing exists but is not the main evaluation path for this submission.
