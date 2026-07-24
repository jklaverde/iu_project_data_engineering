import kagglehub

# Download latest version
path = kagglehub.dataset_download(handle="garystafford/environmental-sensor-data-132k", output_dir='./kaggle_repository', force_download=True)

print("Path to dataset files:", path)