import os

import kagglehub

# KAGGLE_DATASET_OUTPUT_DIR lets this run both ways: as a manual local-dev
# step (default, unchanged) and inside the dataset-init container, which
# sets it to /data (the shared volume producer/spark-job/spark-worker read
# from - see docker-compose.yml).
OUTPUT_DIR = os.getenv("KAGGLE_DATASET_OUTPUT_DIR", "./kaggle_repository")
CSV_NAME = "iot_telemetry_data.csv"


def main() -> None:
    target = os.path.join(OUTPUT_DIR, CSV_NAME)
    if os.path.exists(target):
        print(f"{target} already present - skipping download.")
        return

    try:
        path = kagglehub.dataset_download(
            handle="garystafford/environmental-sensor-data-132k",
            output_dir=OUTPUT_DIR,
            force_download=True,
        )
    except Exception as exc:
        raise SystemExit(
            "Failed to download the dataset. Set KAGGLE_USERNAME/KAGGLE_KEY in .env "
            "(from https://www.kaggle.com/settings -> API -> Create New Token), or "
            f"provide ~/.kaggle/kaggle.json. Original error: {exc}"
        ) from exc

    print("Path to dataset files:", path)


if __name__ == "__main__":
    main()
