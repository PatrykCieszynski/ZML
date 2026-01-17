# python
from pathlib import Path
from PIL import Image

INPUT_DIR: Path = Path("player_coords")
OUTPUT_TOP_DIR: Path = INPUT_DIR / "lon"
OUTPUT_BOTTOM_DIR: Path = INPUT_DIR / "lat"
LEFT_CROP: int = 42

def split_and_save(
    id: int,
    image_path: Path,
    out_top: Path = OUTPUT_TOP_DIR,
    out_bottom: Path = OUTPUT_BOTTOM_DIR,
    left_crop: int = LEFT_CROP
) -> None:
    """
    Otwiera obraz, obcina `left_crop` px z lewej, dzieli pozostały obraz na dwie połowy (góra/dół)
    i zapisuje górę do `out_top` jako pierwszą liczbę z nazwy, dół do `out_bottom` jako drugą.
    """
    stem = image_path.stem
    parts = stem.split("_", 1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        print(f"Pomijam (nie pasuje do wzorca): {image_path.name}")
        return

    a_name, b_name = parts[0], parts[1]
    ext = image_path.suffix or ".png"

    try:
        with Image.open(image_path) as img:
            width, height = img.size
            if left_crop >= width:
                print(f"Pomijam (left_crop >= width): {image_path.name}")
                return

            cropped = img.crop((left_crop, 0, width, height))
            c_width, c_height = cropped.size

            if c_height < 3:
                print(f"Pomijam (zbyt mała wysokość do podziału): {image_path.name}")
                return

            mid = c_height // 1.8
            top = cropped.crop((0, 0, c_width, mid))
            bottom = cropped.crop((0, mid, c_width, c_height))

            out_top.mkdir(parents=True, exist_ok=True)
            out_bottom.mkdir(parents=True, exist_ok=True)

            top_path = out_top / f"{id}_{a_name}{ext}"
            bottom_path = out_bottom / f"{id}_{b_name}{ext}"

            top.save(top_path)
            bottom.save(bottom_path)

            print(f"Zapisano: {top_path} , {bottom_path}")
    except Exception as e:
        print(f"Błąd przy przetwarzaniu {image_path.name}: {e}")

def process_all(
    input_dir: Path = INPUT_DIR,
    out_top: Path = OUTPUT_TOP_DIR,
    out_bottom: Path = OUTPUT_BOTTOM_DIR,
) -> None:
    """
    Przetwarza wszystkie pliki obrazów w katalogu wejściowym.
    Wyniki: góra -> `out_top`, dół -> `out_bottom`.
    """
    if not input_dir.exists():
        print(f"Katalog nie istnieje: {input_dir}")
        return

    id = 1
    for p in sorted(input_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            split_and_save(id, p, out_top, out_bottom)
            id += 1

if __name__ == "__main__":
    process_all()
