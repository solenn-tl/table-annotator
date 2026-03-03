import base64
import argparse
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
CUT_IMAGES_DIR = ROOT_DIR / "cut_images"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
DEFAULT_HF_REPO = "allenai/olmOCR-2-7B-1025-FP8"

SYSTEM_PROMPT = """Tu es un moteur d'extraction de données de registres cadastraux historiques.
Tu dois retourner STRICTEMENT un objet JSON valide.
Interdiction de retourner du HTML, du Markdown, du texte explicatif, ou des tableaux.
"""

JSON_SCHEMA_DESCRIPTION = {
	"type": "object",
	"properties": {
		"lignes": {
			"type": "array",
			"items": {
				"type": "object",
				"properties": {
					"contribuable": {"type": "string"},
					"adresseContribuable": {"type": "string"},
					"numeroListe": {"type": ["number", "string", "null"]},
					"numeroParcelle": {"type": ["number", "string", "null"]},
					"adresseParcelle": {"type": "string"},
					"nomParcelle": {"type": "string"},
					"natureParcelle": {"type": "string"},
				},
				"required": [
					"contribuable",
					"adresseContribuable",
					"numeroListe",
					"numeroParcelle",
					"adresseParcelle",
					"nomParcelle",
					"natureParcelle",
				],
			},
		}
	},
	"required": ["lignes"],
}

USER_PROMPT = f"""Extrais les lignes d'un tableau cadastral historique.
Retourne uniquement un objet JSON respectant ce schéma:
{json.dumps(JSON_SCHEMA_DESCRIPTION, ensure_ascii=False)}

Règles:
- Ne retourne jamais du HTML.
- Ne retourne jamais de markdown.
- Si une valeur est absente, retourne une chaîne vide ("").
- Si la cellule contient "idem"/"id" ou un trait de rappel, propage la valeur de la ligne précédente et ajoute le suffixe " <IDEM>".
"""


def encode_image_to_data_url(image_path: Path) -> str:
	with image_path.open("rb") as image_file:
		encoded = base64.b64encode(image_file.read()).decode("utf-8")
	mime_type = "image/jpeg"
	if image_path.suffix.lower() == ".png":
		mime_type = "image/png"
	elif image_path.suffix.lower() in {".tif", ".tiff"}:
		mime_type = "image/tiff"
	elif image_path.suffix.lower() == ".webp":
		mime_type = "image/webp"
	elif image_path.suffix.lower() == ".bmp":
		mime_type = "image/bmp"
	return f"data:{mime_type};base64,{encoded}"


def extract_json_payload(text: str) -> Any:
	text = text.strip()
	try:
		return json.loads(text)
	except json.JSONDecodeError:
		pass

	fenced_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text, flags=re.DOTALL)
	if fenced_match:
		return json.loads(fenced_match.group(1))

	object_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
	if object_match:
		return json.loads(object_match.group(1))

	raise ValueError("Réponse modèle non-JSON et impossible à parser.")


def call_olmo_ocr(image_path: Path, endpoint: str, model: str, api_key: str | None, timeout_s: float) -> dict[str, Any]:
	data_url = encode_image_to_data_url(image_path)

	payload: dict[str, Any] = {
		"model": model,
		"temperature": 0,
		"messages": [
			{"role": "system", "content": SYSTEM_PROMPT},
			{
				"role": "user",
				"content": [
					{"type": "text", "text": USER_PROMPT},
					{"type": "image_url", "image_url": {"url": data_url}},
				],
			},
		],
		"response_format": {"type": "json_object"},
	}

	headers = {"Content-Type": "application/json"}
	if api_key:
		headers["Authorization"] = f"Bearer {api_key}"

	with httpx.Client(timeout=timeout_s) as client:
		response = client.post(endpoint, json=payload, headers=headers)
		response.raise_for_status()
		raw = response.json()

	try:
		content = raw["choices"][0]["message"]["content"]
	except (KeyError, IndexError, TypeError) as exc:
		raise ValueError(f"Réponse API inattendue: {raw}") from exc

	if not isinstance(content, str):
		raise ValueError(f"Contenu réponse inattendu (non string): {content}")

	parsed = extract_json_payload(content)
	if not isinstance(parsed, dict):
		raise ValueError("Le JSON retourné n'est pas un objet JSON.")
	return parsed


def list_input_images(directory: Path) -> list[Path]:
	images = [
		path
		for path in sorted(directory.iterdir())
		if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
	]
	return images


def normalize_hf_repo(repo_or_url: str) -> str:
	repo_or_url = repo_or_url.strip()
	if repo_or_url.startswith("http://") or repo_or_url.startswith("https://"):
		parsed = urlparse(repo_or_url)
		if parsed.netloc.lower() != "huggingface.co":
			raise ValueError(f"URL Hugging Face invalide: {repo_or_url}")
		path = parsed.path.strip("/")
		if not path:
			raise ValueError(f"Repo Hugging Face invalide: {repo_or_url}")
		return path
	return repo_or_url


def download_hf_model(repo_or_url: str, local_dir: Path | None, token: str | None) -> str:
	from huggingface_hub import snapshot_download

	repo_id = normalize_hf_repo(repo_or_url)
	kwargs: dict[str, Any] = {
		"repo_id": repo_id,
		"token": token,
	}
	if local_dir is not None:
		kwargs["local_dir"] = str(local_dir)
		kwargs["local_dir_use_symlinks"] = False
	return snapshot_download(**kwargs)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Extraction JSON de tables historiques via OLMO OCR v2")
	parser.add_argument(
		"--input-dir",
		type=Path,
		default=CUT_IMAGES_DIR,
		help="Dossier contenant les images à traiter (défaut: ./cut_images)",
	)
	parser.add_argument(
		"--output-dir",
		type=Path,
		default=None,
		help="Dossier de sortie des JSON (défaut: même dossier que --input-dir)",
	)
	parser.add_argument(
		"--download-hf-model",
		action="store_true",
		help="Télécharge le modèle depuis Hugging Face puis quitte.",
	)
	parser.add_argument(
		"--hf-repo",
		type=str,
		default=DEFAULT_HF_REPO,
		help=f"Repo ou URL Hugging Face (défaut: {DEFAULT_HF_REPO})",
	)
	parser.add_argument(
		"--hf-local-dir",
		type=Path,
		default=ROOT_DIR / "models" / "olmOCR-2-7B-1025-FP8",
		help="Dossier local pour télécharger le modèle Hugging Face.",
	)
	return parser.parse_args()


def main() -> None:
	load_dotenv()
	args = parse_args()
	input_dir = args.input_dir
	output_dir = args.output_dir or input_dir

	endpoint = os.getenv("OLMO_OCR_ENDPOINT", "http://localhost:11434/v1/chat/completions")
	model = os.getenv("OLMO_OCR_MODEL", DEFAULT_HF_REPO)
	api_key = os.getenv("OLMO_API_KEY")
	hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
	timeout_s = float(os.getenv("OLMO_TIMEOUT_SECONDS", "120"))

	if args.download_hf_model:
		local_dir = args.hf_local_dir
		local_dir.mkdir(parents=True, exist_ok=True)
		print(f"Téléchargement du modèle Hugging Face: {args.hf_repo}")
		model_path = download_hf_model(args.hf_repo, local_dir, hf_token)
		print(f"Modèle disponible dans: {model_path}")
		return

	if not input_dir.exists():
		raise FileNotFoundError(f"Dossier introuvable: {input_dir}")

	output_dir.mkdir(parents=True, exist_ok=True)

	images = list_input_images(input_dir)
	if not images:
		print(f"Aucune image trouvée dans: {input_dir}")
		return

	print(f"Extraction OLMO OCR v2 JSON sur {len(images)} image(s)...")
	for image_path in images:
		print(f"- Traitement: {image_path.name}")
		try:
			result = call_olmo_ocr(image_path, endpoint, model, api_key, timeout_s)
			output_path = output_dir / f"{image_path.stem}.json"
			with output_path.open("w", encoding="utf-8") as output_file:
				json.dump(result, output_file, indent=2, ensure_ascii=False)
			print(f"  OK -> {output_path.name}")
		except Exception as exc:
			print(f"  ERREUR -> {image_path.name}: {exc}")


if __name__ == "__main__":
	main()
