import argparse
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

import requests


def arkotheque_iiif_info(info_url):
	"""
	Fetch and return one IIIF Image API info.json document.
	"""
	headers = {
		"User-Agent": "ocr-viewer/1.0",
		"Accept": "application/json",
	}
	response = requests.get(info_url, headers=headers, timeout=30)
	response.raise_for_status()

	try:
		return response.json()
	except ValueError as error:
		content_type = response.headers.get("Content-Type", "")
		snippet = response.text[:200].replace("\n", " ").strip()
		raise ValueError(
			f"Invalid JSON info from {info_url}. "
			f"Content-Type={content_type!r}. Body starts with: {snippet!r}"
		) from error


def build_indexed_info_url(first_info_url, index):
	"""
	Replace the penultimate path segment (e.g. /0/info.json) with `index`.
	"""
	parsed = urlsplit(first_info_url)
	parts = parsed.path.split("/")

	if len(parts) < 3 or parts[-1] != "info.json":
		raise ValueError("first_info_url must end with /<index>/info.json")

	parts[-2] = str(index)
	new_path = "/".join(parts)
	return urlunsplit((parsed.scheme, parsed.netloc, new_path, parsed.query, parsed.fragment))


def _extract_cote_from_service_id(service_id, fallback):
	if not isinstance(service_id, str) or not service_id.strip():
		return fallback
	decoded_service_id = unquote(service_id)
	last_segment = decoded_service_id.rstrip("/").split("/")[-1]
	if "." in last_segment:
		return last_segment.rsplit(".", 1)[0]
	return last_segment


def _extract_name_from_image_url(image_url, fallback):
	"""
	Extract image filename stem from a IIIF image URL, decoding URL-encoded paths.
	Example: .../FRAD078_..._00001.jpg/full/full/0/default.jpg -> FRAD078_..._00001
	"""
	if not isinstance(image_url, str) or not image_url.strip():
		return fallback

	decoded = unquote(image_url)
	parts = [part for part in decoded.split("/") if part]

	# Typical IIIF Image API URL ends with .../<region>/<size>/<rotation>/default.jpg
	# where <region> can be "full" or coordinates and the source image filename sits 4 segments before default.jpg.
	if len(parts) >= 5 and parts[-1].lower() == "default.jpg":
		candidate = parts[-5]
		if "." in candidate:
			return candidate.rsplit(".", 1)[0]

	for part in reversed(parts):
		if "." in part and part.lower() != "default.jpg":
			return part.rsplit(".", 1)[0]

	return fallback


def arkotheque_retrieve_collection(
	first_info_url,
	image_count,
	output_path="items.json",
	label_collection=None,
	collection_cote=None,
	commune=None,
	date=None,
	type_=None,
	attribution=None,
):
	"""
	Build a collection-like item list by iterating Arkotheque image indices.
	"""
	if image_count <= 0:
		raise ValueError("image_count must be > 0")

	image_group_id = None
	split_parts = urlsplit(first_info_url).path.split("/")
	if "image" in split_parts:
		image_pos = split_parts.index("image")
		if image_pos + 1 < len(split_parts):
			image_group_id = split_parts[image_pos + 1]
	if not image_group_id:
		image_group_id = "unknown"

	resolved_collection_cote = collection_cote or str(image_group_id).replace(" ", "")
	resolved_label = label_collection or f"Arkotheque image group {image_group_id}"
	resolved_commune = commune or "Unknown"
	resolved_date = date or "Unknown"
	resolved_type = type_ or "Unknown"
	resolved_attribution = attribution or "Unknown"

	items = []
	fetched_infos = []
	for idx in range(image_count):
		info_url = build_indexed_info_url(first_info_url, idx)
		info = arkotheque_iiif_info(info_url)
		fetched_infos.append(info)

		service_id = info.get("@id") or info.get("id")
		fallback_cote = f"{image_group_id}_{idx + 1:05d}"
		cote = _extract_cote_from_service_id(service_id, fallback_cote)

		if not service_id:
			raise ValueError(f"Missing @id/id in info.json: {info_url}")

		item = {
			"cote": cote,
			"info": info_url,
			"img": service_id.rstrip("/") + "/full/full/0/default.jpg",
			"width": info.get("width"),
			"height": info.get("height"),
			"label_collection": resolved_label,
			"collection_cote": resolved_collection_cote,
			"commune": resolved_commune,
			"date": resolved_date,
			"type": resolved_type,
			"attribution": resolved_attribution,
		}
		items.append(item)

	if output_path:
		output_file = Path(output_path)
		output_file.parent.mkdir(parents=True, exist_ok=True)
		output_file.write_text(
			json.dumps(items, ensure_ascii=False, indent=4) + "\n",
			encoding="utf-8",
		)

	return items, fetched_infos


def create_elements(items_or_json_path):
	if isinstance(items_or_json_path, (str, Path)):
		with open(items_or_json_path, "r", encoding="utf-8") as f:
			items = json.load(f)
	else:
		items = items_or_json_path

	elements = []

	for item in items:
		img_url = item["img"]
		base_name = _extract_name_from_image_url(img_url, item.get("cote", "image"))
		width = item["width"]
		height = item["height"]

		if width is None or height is None:
			continue

		if width > height:
			left_name = base_name + "_left"
			left_coords = (0, 0, width // 2, height)
			left_iiif_img_url = img_url.replace(
				"/full/full/0/default.jpg",
				f"/{left_coords[0]},{left_coords[1]},{left_coords[2]},{left_coords[3]}/full/0/default.jpg",
			)
			left_annotation_json = base_name + "_left.json"
			elements.append(
				{
					"name": left_name,
					"image": left_iiif_img_url,
					"json": left_annotation_json,
				}
			)

			right_name = base_name + "_right"
			right_coords = (width // 2, 0, width, height)
			right_iiif_img_url = img_url.replace(
				"/full/full/0/default.jpg",
				f"/{right_coords[0]},{right_coords[1]},{right_coords[2]},{right_coords[3]}/full/0/default.jpg",
			)
			right_annotation_json = base_name + "_right.json"
			elements.append(
				{
					"name": right_name,
					"image": right_iiif_img_url,
					"json": right_annotation_json,
				}
			)
		else:
			name = base_name
			annotation_json = base_name + ".json"
			elements.append(
				{
					"name": name,
					"image": img_url,
					"json": annotation_json,
				}
			)

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
		description=(
			"Fetch Arkotheque IIIF info.json documents by index and extract collection items."
		)
	)
	parser.add_argument("info_url", help="First image IIIF info.json URL (index 0)")
	parser.add_argument("image_count", type=int, help="Number of images in the collection")
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
		"--infos-output",
		default=None,
		help="Optional raw fetched infos JSON filename or path",
	)
	parser.add_argument(
		"--elements-output",
		default="elements.json",
		help="Pairs JSON filename or path (default: elements.json)",
	)
	parser.add_argument(
		"--label-collection",
		default=None,
		help="Override label_collection value in items.json",
	)
	parser.add_argument(
		"--collection-cote",
		default=None,
		help="Override collection_cote value in items.json",
	)
	parser.add_argument(
		"--commune",
		default=None,
		help="Override commune value in items.json",
	)
	parser.add_argument(
		"--date",
		default=None,
		help="Override date value in items.json",
	)
	parser.add_argument(
		"--type",
		dest="doc_type",
		default=None,
		help="Override type value in items.json",
	)
	parser.add_argument(
		"--attribution",
		default=None,
		help="Override attribution value in items.json",
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

	items, infos = arkotheque_retrieve_collection(
		args.info_url,
		args.image_count,
		output_path=items_output_path,
		label_collection=args.label_collection,
		collection_cote=args.collection_cote,
		commune=args.commune,
		date=args.date,
		type_=args.doc_type,
		attribution=args.attribution,
	)
	elements = create_elements(items)

	elements_output_path.parent.mkdir(parents=True, exist_ok=True)
	elements_output_path.write_text(
		json.dumps(elements, ensure_ascii=False, indent=4) + "\n",
		encoding="utf-8",
	)
	created_json_count = create_empty_json_files_from_elements(elements, args.output_dir)

	if args.infos_output:
		infos_output = resolve_output_path(args.infos_output, args.output_dir)
		infos_output.parent.mkdir(parents=True, exist_ok=True)
		infos_output.write_text(
			json.dumps(infos, ensure_ascii=False, indent=4) + "\n",
			encoding="utf-8",
		)

	print(f"Items extracted: {len(items)}")
	print(f"Items file: {items_output_path.resolve()}")
	print(f"Pairs file: {elements_output_path.resolve()}")
	print(f"Empty annotation JSON files created: {created_json_count}")
	if args.infos_output:
		print(f"Infos file: {infos_output.resolve()}")


if __name__ == "__main__":
	main()
