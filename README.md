# Historical table annotator

This repository contains a demo of a tool to annotate digitized historical tables.

### Virtual environnement
```bash
python -m venv ocr-test

ocr-test\Scripts\activate
.\ocr-test\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Environment variables
Create a `.env` file at the project root:

```bash
MISTRAL_API_KEY=your_mistral_api_key_here
```

You can copy from `.env.example`.

### Run Mistral transcription
!!! The results are not good. !!!
```bash
python mistral-ocr.py
```

### Run OLMO OCR v2 transcription (JSON only)

Add these variables in `.env` (adapt to your endpoint/model):

```bash
OLMO_OCR_ENDPOINT=http://localhost:11434/v1/chat/completions
OLMO_OCR_MODEL=allenai/olmOCR-2-7B-1025-FP8
# Optional if your endpoint requires auth:
# OLMO_API_KEY=your_api_key
```

Download the model from Hugging Face:

```bash
python olmo-ocr-v2.py --download-hf-model --hf-repo https://huggingface.co/allenai/olmOCR-2-7B-1025-FP8
```

Optional auth (if required):

```bash
HF_TOKEN=your_hf_token
```

Then run:

```bash
python olmo-ocr-v2.py
```

The script reads all images from `cut_images/` and writes one JSON file per image in the same folder.

You can also set custom folders:

```bash
python olmo-ocr-v2.py --input-dir ./images --output-dir ./ocr_json
```
