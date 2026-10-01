"""Convert DatasetNinja (Supervisely) road-vehicle dataset to YOLO format."""
import json
import pathlib
import shutil

SRC = pathlib.Path(r"C:\Users\princ\Downloads\road-vehicle-DatasetNinja")
DST = pathlib.Path(r"I:\raipur_netra\models\dataset")
DST.mkdir(parents=True, exist_ok=True)

meta = json.loads((SRC / "meta.json").read_text(encoding="utf-8"))
classes = [c["title"] for c in meta["classes"]]
print("classes:", len(classes))

data_yaml = ["path: " + str(DST).replace("\\", "/"),
             "train: train/images", "val: valid/images", f"nc: {len(classes)}", "names:"]
for i, c in enumerate(classes):
    data_yaml.append(f"  {i}: {c}")
(DST / "data.yaml").write_text("\n".join(data_yaml), encoding="utf-8")
print("wrote data.yaml")

stats = {"copied": 0, "boxes": 0, "empty": 0, "skipped_geo": 0}
for split in ("train", "valid"):
    (DST / split / "images").mkdir(parents=True, exist_ok=True)
    (DST / split / "labels").mkdir(parents=True, exist_ok=True)
    for ann_path in (SRC / split / "ann").glob("*.json"):
        j = json.loads(ann_path.read_text(encoding="utf-8"))
        W, Hh = j["size"]["width"], j["size"]["height"]
        stem = ann_path.stem[:-5] if ann_path.name.endswith(".jpg.json") else ann_path.stem
        stem = ann_path.name[: -len(".json")]
        stem = stem[: -len(".jpg")] if stem.endswith(".jpg") else stem
        img_src = SRC / split / "img" / (stem + ".jpg")
        if not img_src.exists():
            continue
        lines = []
        for ob in j["objects"]:
            if ob.get("geometryType") != "rectangle":
                stats["skipped_geo"] += 1
                continue
            (x1, y1), (x2, y2) = ob["points"]["exterior"]
            cx = ((x1 + x2) / 2) / W
            cy = ((y1 + y2) / 2) / Hh
            bw = abs(x2 - x1) / W
            bh = abs(y2 - y1) / Hh
            cx, cy, bw, bh = max(0, min(1, cx)), max(0, min(1, cy)), max(1e-6, min(1, bw)), max(1e-6, min(1, bh))
            cid = classes.index(ob["classTitle"])
            lines.append(f"{cid} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
            stats["boxes"] += 1
        if not lines:
            stats["empty"] += 1
        (DST / split / "labels" / (stem + ".txt")).write_text("\n".join(lines), encoding="utf-8")
        shutil.copy2(img_src, DST / split / "images" / (stem + ".jpg"))
        stats["copied"] += 1

print("conversion done:", stats)
