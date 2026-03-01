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
