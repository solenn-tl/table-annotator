import requests
import json
import argparse
from pathlib import Path

def ligeo_iiif_manifest(manifest_url):
    """
    Fetches and returns the IIIF manifest from the given URL provided by the Ligeo software used by certain archive services.
    Args:
        manifest_url (str): The URL of the IIIF manifest.
    Returns:
        dict: The parsed IIIF manifest as a dictionary.
    Raises:
        requests.HTTPError: If the HTTP request returned an unsuccessful status code.
        ValueError: If the response content is not valid JSON.
    """
    headers = {
        "User-Agent": "ocr-viewer/1.0",
        "Accept": "application/json",
    }
    response = requests.get(manifest_url, headers=headers, timeout=30)
    response.raise_for_status()

    try:
        return response.json()
    except ValueError as error:
        content_type = response.headers.get("Content-Type", "")
        snippet = response.text[:200].replace("\n", " ").strip()
        raise ValueError(
            f"Invalid JSON manifest from {manifest_url}. "
            f"Content-Type={content_type!r}. Body starts with: {snippet!r}"
        ) from error


def ligeo_retrieve_collection(manifest_url, output_path="items.json"):
    """
    Retrieves a list of items from a IIIF manifest from the Ligeo software.
    Args:
        manifest_url (str or dict): The URL of the IIIF manifest or the manifest as a dictionary.
    Returns:
        list: A list of items, where each item is a dictionary containing information about a canvas.
    Raises:
        TypeError: If manifest_url is neither a string nor a dictionary.
    """
    if isinstance(manifest_url, dict):
        manifest = manifest_url
    elif isinstance(manifest_url, str):
        manifest = ligeo_iiif_manifest(manifest_url)
    else:
        raise TypeError("manifest_url must be a dict manifest or a manifest URL string")

    attribution = manifest.get("attribution", "Unknown")
    label = manifest.get("label", "Unknown")
    collection_cote = label.split(" - ")[0] if " - " in label else label
    collection_cote = collection_cote.replace(" ", "")   
    metadata = manifest.get("metadata", [])
    commune = "Unknown"
    date = "Unknown"
    type_ = "Unknown"
    for meta in metadata:
        if meta.get("label") == "Commune":
            print(f"Commune: {meta.get('value')}")
            commune = meta.get("value")
        
        if meta.get("label") == "Date":
            print(f"Date: {meta.get('value')}")
            date = meta.get("value")

        if meta.get("label") == "Type de document":
            print(f"Type de document: {meta.get('value')}")
            type_ = meta.get("value")

    sequence_list = manifest.get("sequences", [])
    if not sequence_list:
        return []

    sequences = sequence_list[0]
    canvases = sequences.get("canvases", [])
    items = []
    for canvas in canvases: 
        img_iiif = canvas.get("images", [])[0].get("resource", {}).get("service", {}).get("@id")
        cote = img_iiif.split("/")[-1]  # Extract the cote from the IIIF URL
        cote = cote.split(".")[0]  # Remove file extension if present (.jpg)
        item = {
            "cote": cote,
            "info": img_iiif + '/info.json',
            "img": img_iiif + '/full/full/0/default.jpg',
            "width": canvas.get("width"),
            "height": canvas.get("height"),
            "label_collection": label,
            "collection_cote": collection_cote,
            "commune": commune,
            "date": date,
            "type": type_,
            "attribution": attribution,
        }
        items.append(item)

    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(items, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )
    
    return items
    

def create_elements(items_or_json_path):
    if isinstance(items_or_json_path, (str, Path)):
        with open(items_or_json_path, "r", encoding="utf-8") as f:
            items = json.load(f)
    else:
        items = items_or_json_path

    elements = []

    for item in items:
        img_url = item["img"]
        width = item["width"]
        height = item["height"]
        if width > height:
            # Left part coordinates
            left_name = item["cote"] + "_left"
            left_coords = (0, 0, width // 2, height)
            left_iiif_img_url = img_url.replace("/full/full/0/default.jpg", f"/{left_coords[0]},{left_coords[1]},{left_coords[2]},{left_coords[3]}/full/0/default.jpg")
            left_annotation_json = item["cote"] + '_left.json'
            elements.append({
                "name": left_name,
                "image": left_iiif_img_url,
                "json": left_annotation_json
            })
            # Right part coordinates
            right_name = item["cote"] + "_right"
            right_coords = (width // 2, 0, width, height)
            right_iiif_img_url = img_url.replace("/full/full/0/default.jpg", f"/{right_coords[0]},{right_coords[1]},{right_coords[2]},{right_coords[3]}/full/0/default.jpg")
            right_annotation_json = item["cote"] + '_right.json'
            elements.append({
                "name": right_name,
                "image": right_iiif_img_url,
                "json": right_annotation_json
            })
        else:
            # Single part coordinates (full image)
            name = item["cote"]
            annotation_json = item["cote"] + '.json'
            elements.append({
                "name": name,
                "image": img_url,
                "json": annotation_json
            })
    return elements


def create_empty_json_files_from_elements(elements, output_dir):
    base_dir = Path(output_dir).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    created_count = 0
    for pair in elements:
        if not isinstance(pair, dict):
            continue

        json_name = pair.get("json")
        if not isinstance(json_name, str) or not json_name.strip():
            continue

        target = (base_dir / json_name).resolve()
        try:
            target.relative_to(base_dir)
        except ValueError:
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            continue

        target.write_text("[]\n", encoding="utf-8")
        created_count += 1

    return created_count

def build_parser():
    parser = argparse.ArgumentParser(
        description="Fetch a Ligeo IIIF manifest and extract collection items."
    )
    parser.add_argument("manifest_url", help="IIIF manifest URL")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Folder where JSON files are saved (default: current folder)",
    )
    parser.add_argument(
        "--items-output",
        default="items.json",
        help="Items JSON filename or path (default: items.json)",
    )
    parser.add_argument(
        "--manifest-output",
        default=None,
        help="Optional manifest JSON filename or path",
    )
    parser.add_argument(
        "--elements-output",
        default="elements.json",
        help="Pairs JSON filename or path (default: elements.json)",
    )
    return parser


def resolve_output_path(path_value, output_dir):
    output_path = Path(path_value)
    if output_path.is_absolute():
        return output_path
    return Path(output_dir) / output_path


def main():
    parser = build_parser()
    args = parser.parse_args()

    items_output_path = resolve_output_path(args.items_output, args.output_dir)
    elements_output_path = resolve_output_path(args.elements_output, args.output_dir)

    manifest = ligeo_iiif_manifest(args.manifest_url)
    items = ligeo_retrieve_collection(manifest, output_path=items_output_path)
    elements = create_elements(items)
    elements_output_path.parent.mkdir(parents=True, exist_ok=True)
    elements_output_path.write_text(
        json.dumps(elements, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    created_json_count = create_empty_json_files_from_elements(elements, args.output_dir)

    if args.manifest_output:
        manifest_output = resolve_output_path(args.manifest_output, args.output_dir)
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )

    print(f"Items extracted: {len(items)}")
    print(f"Items file: {items_output_path.resolve()}")
    print(f"Pairs file: {elements_output_path.resolve()}")
    print(f"Empty annotation JSON files created: {created_json_count}")
    if args.manifest_output:
        print(f"Manifest file: {manifest_output.resolve()}")


if __name__ == "__main__":
    main()
