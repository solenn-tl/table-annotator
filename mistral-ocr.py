import base64
import json
import mimetypes
import os
from pathlib import Path
import time
import glob
import cv2
from dotenv import load_dotenv
from mistralai import Mistral


ROOT_DIR = Path(__file__).resolve().parent
IMAGES_DIR = ROOT_DIR / "images"
CUT_IMAGES_DIR = ROOT_DIR / "cut_images"
TRANSCRIPT_DIR = ROOT_DIR / "transcript"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
MAX_RETRIES = int(os.getenv("MISTRAL_MAX_RETRIES", "8"))
BASE_BACKOFF_SECONDS = float(os.getenv("MISTRAL_BASE_BACKOFF_SECONDS", "5"))
MAX_BACKOFF_SECONDS = float(os.getenv("MISTRAL_MAX_BACKOFF_SECONDS", "120"))
INTER_REQUEST_DELAY_SECONDS = float(os.getenv("MISTRAL_INTER_REQUEST_DELAY_SECONDS", "3"))

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "lignes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "contribuable": {
                        "type": "string",
                        "description": "Nom du Contribuable ou Propriétaire (sous-colonne 'Contribuables, Propriétaires, Domaniers, et Usufruitiers')",
                    },
                    "adresseContribuable": {
                        "type": "string",
                        "description": "Adresse du Contribuable (sous-colonne 'Propriétaires fonciers')",
                    },
                    "numeroListe": {
                        "type": "number",
                        "description": "Index du contribuable (colonne 'Numéro de la liste')",
                    },
                    "numeroParcelle": {
                        "type": "number",
                        "description": "Numéro de la parcelle sur le plan (colonne 'N° du plan')",
                    },
                    "adresseParcelle": {
                        "type": "string",
                        "description": "Lieu-dit (sous-colonne 'Villages, Fermes, Canton ou Triage')",
                    },
                    "nomParcelle": {
                        "type": "string",
                        "description": "Nom de la parcelle (sous-colonne 'Parcelles')",
                    },
                    "natureParcelle": {
                        "type": "string",
                        "description": "Occupation du sol (colonne 'Nature des propriétés')",
                    },
                },
            },
        }
    },
}

PROMPT = f"""Tu es un assistant d'extraction de données à partir d'images de registres cadastraux du Finistère (implique du lexique breton dans les noms de familles et adresses).
Voici les instructions pour extraire les données de chaque ligne du registre cadastral :
1. Les données à extraire sont localiser dans les nom de colonnes simples ou dans les noms de sous colonnes.
2. L'intitulé de la sous-colonne peut ne pas correspondre aux informations réellement indiqués
3. Pour chaque ligne du registre, extrais les informations suivantes des colonnes ou sous-colonnes correspondantes : 
    - "contribuable" : le nom du contribuable ou propriétaire (sous-colonne "Contribuables, Propriétaires, Domaniers, et Usufruitiers")
    - "adresseContribuable" : l'adresse du contribuable (sous-colonne "Propriétaires fonciers")
    - "numeroListe" : l'index du contribuable (colonne "Numéro de la liste")
    - "numeroParcelle" : le numéro de la parcelle sur le plan (colonne "N° du plan")
    - "adresseParcelle" : le lieu-dit (sous-colonne "Villages, Fermes, Canton ou Triage")
    - "nomParcelle" : le nom de la parcelle (sous-colonne "Parcelles")
    - "natureParcelle" : l'occupation du sol (colonne "Nature des propriétés")
4. Si une cellule contient un trait partant d'une valeur située dans une ligne précédente, ou la valeur idem OU id dans une ligne précédente, indique la balise <IDEM> pour la valeur de cette cellule puis transcrit la valeur de la cellule précédente correspondante à cette ligne.
5. Retourne les données extraites au format JSON suivant, en respectant strictement ce format :
{{JSON_SCHEMA}}.

TRANSCRIPTION :
"""

load_dotenv()
api_key = os.getenv("MISTRAL_API_KEY")
if not api_key:
    raise ValueError("MISTRAL_API_KEY manquante. Ajoute-la dans le fichier .env.")

client = Mistral(api_key=api_key)

def encode_image(image_path):
    """Encode l'image locale en base64 pour l'envoi."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def extract_table_data(image_path):
    # Encodage de l'image
    base64_image = encode_image(image_path)
    image_data_url = f"data:image/jpeg;base64,{base64_image}"

    # 2. Requête vers le modèle de vision
    # On utilise mistral-large-latest qui excelle dans l'extraction structurée
    ocr_response = client.ocr.process(
        model="mistral-ocr-latest", # Ou mistral-ocr-latest selon votre accès
        document={
            "type": "image_url",
            "image_url": image_data_url,
        }
    )

    transcription_markdown = ocr_response.pages[0].markdown

    chat_response = client.chat.complete(
        model="mistral-large-latest",
        messages=[
            {"role": "user", "content": f"{PROMPT}\n\n{transcription_markdown}"}
        ],
        response_format={"type": "json_object"}
    )

    return chat_response.choices[0].message.content

LS_IMAGES = glob.glob(str(CUT_IMAGES_DIR / "*.*"))

# 3. Exécution
try:
    for image in LS_IMAGES:
        resultat = extract_table_data(image)
        data = json.loads(resultat)
        print(json.dumps(data, indent=4, ensure_ascii=False))
        
        with open(f"{image.replace('.jpg', '')}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

except Exception as e:
    print(f"Erreur lors de l'extraction : {e}")
