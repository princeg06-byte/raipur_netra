"""Train YOLOv8n on the DatasetNinja road-vehicle dataset (MAX 2 EPOCHS).

CPU-optimized fine-tune:
  * COCO-pretrained backbone, first 10 layers frozen (transfer learning)
  * RAM-cached images, imgsz 416, batch 24
  * best checkpoint tracked on val mAP50-95, then validated per-class
"""
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(r"I:\raipur_netra")
DATA = ROOT / "models" / "dataset" / "data.yaml"
EPOCHS = 2  # hard cap (per requirement)

model = YOLO("yolov8n.pt")
model.train(
    data=str(DATA),
    epochs=EPOCHS,
    patience=EPOCHS,
    imgsz=416,
    batch=24,
    workers=8,
    device="cpu",
    cache="ram",
    freeze=10,               # frozen COCO backbone -> fast CPU fine-tune
    plots=True,
    project=str(ROOT / "models" / "train_runs"),
    name="road_vehicle_v1",
    exist_ok=True,
)

best = ROOT / "models" / "train_runs" / "road_vehicle_v1" / "weights" / "best.pt"
print("\nTRAINING DONE — best:", best)
if best.exists():
    m = YOLO(str(best))
    val = m.val(data=str(DATA), imgsz=416, batch=24, device="cpu", workers=8, plots=False)
    print("mAP50-95:", round(float(val.box.map), 4))
    print("mAP50:", round(float(val.box.map50), 4))
    print("per-class AP50:")
    for i, ap in enumerate(val.box.ap50):
        print(f"  {m.names[i]}: {ap:.3f}")
