# Duplicate Image Scanner

A Streamlit web application that uses **Perceptual Hashing** to detect duplicate and similar images in your file system.

## Features

- 🖼️ Scans folders recursively for images
- 🔍 Uses perceptual hashing to identify visually similar images (not just identical files)
- 📊 Displays results with image previews
- 🚀 Interactive web interface powered by Streamlit
- ⚡ Fast processing with progress tracking

## Supported Formats

- JPG/JPEG
- PNG
- WebP
- BMP

## Requirements

- Python 3.7+
- Streamlit
- Pillow (PIL)
- ImageHash

## Installation

1. Clone this repository:
```bash
git clone https://github.com/WanderingFrogg/duplicate-image-scanner.git
cd duplicate-image-scanner
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the application:
```bash
streamlit run dupscan.py
```

Then:
1. Paste a folder path in the application
2. The scanner will recursively search for images
3. View duplicate groups with image previews
4. Delete duplicates directly from the interface (optional)

## How It Works

The app uses **perceptual hashing** to generate a visual "fingerprint" of each image. Images with the same fingerprint are considered duplicates, even if the files are different sizes or have slight compression differences.

## License

MIT

## Contributing

Contributions are welcome! Feel free to submit issues and pull requests.
