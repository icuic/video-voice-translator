import os
import sys


def main() -> int:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    hf_cache = os.path.join(project_root, "index-tts", ".cache", "hf")
    os.makedirs(hf_cache, exist_ok=True)

    endpoint = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")

    try:
        import requests
        from huggingface_hub import configure_http_backend, snapshot_download

        def backend_factory():
            s = requests.Session()
            if os.getenv("HF_INSECURE", "") in ("1", "true", "yes"):
                s.verify = False
            return s

        configure_http_backend(backend_factory=backend_factory)

        repos = [
            "facebook/w2v-bert-2.0",
            "amphion/MaskGCT",
            "funasr/campplus",
            "nvidia/bigvgan_v2_22khz_80band_256x",
        ]

        for repo in repos:
            print(f"📥 预热缓存: {repo}")
            snapshot_download(
                repo_id=repo,
                cache_dir=hf_cache,
                endpoint=endpoint,
                local_dir_use_symlinks=False,
                resume_download=True,
            )

        print(f"✅ 预热完成: {hf_cache}")
        return 0
    except Exception as e:
        print(f"❌ 预热失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

