import argparse
import json
import shutil
from pathlib import Path

import cv2


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def process_image(image_path: Path, destination_dir: Path, relative_path: Path) -> str:
	image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
	if image is None:
		return f"Skipped unreadable file: {relative_path}"

	height, width = image.shape[:2]
	if width > height:
		split_x = width // 2
		left_image = image[:, :split_x]
		right_image = image[:, split_x:]

		left_path = destination_dir / f"{image_path.stem}_left{image_path.suffix}"
		right_path = destination_dir / f"{image_path.stem}_right{image_path.suffix}"

		cv2.imwrite(str(left_path), left_image)
		cv2.imwrite(str(right_path), right_image)
		return f"Split: {relative_path} -> {left_path.name}, {right_path.name}"

	destination = destination_dir / image_path.name
	shutil.copy2(image_path, destination)
	return f"Copied: {relative_path}"


def process_folder(folder_path: Path, save_dir: Path) -> tuple[int, int, int]:
	if not folder_path.exists() or not folder_path.is_dir():
		raise ValueError(f"Invalid folder_path: {folder_path}")

	save_dir.mkdir(parents=True, exist_ok=True)

	processed = 0
	skipped = 0
	split_count = 0

	resolved_save_dir = save_dir.resolve()

	image_files = sorted(
		path
		for path in folder_path.rglob("*")
		if path.is_file()
		and path.suffix.lower() in IMAGE_EXTENSIONS
		and resolved_save_dir not in path.resolve().parents
		and path.resolve() != resolved_save_dir
	)

	for image_path in image_files:
		relative_path = image_path.relative_to(folder_path)
		relative_parent = relative_path.parent
		destination_dir = save_dir / relative_parent
		destination_dir.mkdir(parents=True, exist_ok=True)

		result = process_image(image_path, destination_dir, relative_path)
		print(result)
		if result.startswith("Skipped"):
			skipped += 1
			continue
		processed += 1
		if result.startswith("Split"):
			split_count += 1

	return processed, split_count, skipped


def create_json_and_elements(save_dir: Path) -> tuple[int, int]:
	created_json_count = 0
	elements: list[dict[str, str]] = []

	for image_path in sorted(
		path
		for path in save_dir.rglob("*")
		if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
	):
		relative_image = image_path.relative_to(save_dir)
		json_path = image_path.with_suffix(".json")

		if not json_path.exists():
			json_path.write_text("[]\n", encoding="utf-8")
			created_json_count += 1

		relative_json = json_path.relative_to(save_dir)
		elements.append(
			{
				"name": relative_image.with_suffix("").as_posix(),
				"image": relative_image.as_posix(),
				"json": relative_json.as_posix(),
			}
		)

	elements_path = save_dir / "elements.json"
	elements_path.write_text(
		json.dumps(elements, ensure_ascii=False, indent=4) + "\n",
		encoding="utf-8",
	)

	return created_json_count, len(elements)


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="Split landscape images into left/right halves and copy others."
	)
	parser.add_argument("folder_path", type=Path, help="Folder containing source images")
	parser.add_argument("save_dir", type=Path, help="Folder where output images are saved")
	parser.add_argument(
		"--create-json-and-elements",
		action="store_true",
		help="Create missing empty sidecar JSON files and write elements.json in save_dir",
	)
	return parser


def main() -> None:
	parser = build_parser()
	args = parser.parse_args()

	processed, split_count, skipped = process_folder(args.folder_path, args.save_dir)
	print(
		f"Done. Processed: {processed}, Split images: {split_count}, Skipped unreadable: {skipped}"
	)

	if args.create_json_and_elements:
		created_json_count, pair_count = create_json_and_elements(args.save_dir)
		print(
			f"Created missing empty JSON: {created_json_count}, Pairs written: {pair_count}, File: {args.save_dir / 'elements.json'}"
		)


if __name__ == "__main__":
	main()
