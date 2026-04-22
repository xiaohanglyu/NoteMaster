"""Download the mlx-whisper model before first use."""
from pathlib import Path
from huggingface_hub import snapshot_download, try_to_load_from_cache
from notemaster.config import WHISPER_MODEL

REPO_ID = f"mlx-community/whisper-{WHISPER_MODEL}-mlx"


def model_is_cached() -> bool:
    result = try_to_load_from_cache(REPO_ID, "config.json")
    return result is not None and result != "not_in_cache"


def main():
    print(f"Model: {REPO_ID}")

    if model_is_cached():
        print("Already downloaded. Nothing to do.")
        return

    print("Downloading… (this may take a few minutes)")
    path = snapshot_download(REPO_ID)
    print(f"Done. Cached at {path}")


if __name__ == "__main__":
    main()
