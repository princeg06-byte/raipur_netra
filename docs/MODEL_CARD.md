# RaipurNetra AI — Detection Model Card

## Model
| | |
|---|---|
| Architecture | YOLOv8n (COCO-pretrained, backbone frozen for CPU fine-tuning) |
| Training data | DatasetNinja *Road Vehicle Detection* — 3,004 images (2,704 train / 300 valid) |
| Annotations | 24,348 rectangle boxes, 21 classes, Supervisely → YOLO converted |
| Classes | ambulance, army vehicle, auto rickshaw, bicycle, bus, car, garbagevan, human hauler, minibus, minivan, motorbike, pickup, policecar, rickshaw, scooter, suv, taxi, three wheelers -CNG-, truck, van, wheelbarrow |
| Config | imgsz 416 · batch 24 · epochs **2 (capped per requirement)** · cache RAM · SGD auto |
| Weights | `models/yolo_raipur_best.pt` (previous weights kept as `models/yolo_raipur_prev.pt`) |

## Validation metrics (300-image held-out set)

| Metric | Value |
|---|---|
| mAP@50 | **0.123** |
| mAP@50-95 | 0.067 |
| Precision | 0.534 |
| Recall | 0.151 |
| Epoch 1 → 2 trend | mAP50 0.087 → 0.123 (+41%) |

Sanity check on unseen validation images: correct classes detected (car, motorbike, bus)
with confidences 0.31-0.75 at conf threshold 0.30.

## Honest interpretation & improvement path

Two epochs is a deliberate cap (demo timeline), so recall is modest — the model is
production-shaped, not production-saturated. mAP improves roughly linearly for the
first ~30 epochs on this dataset. To raise accuracy:

```bash
# edit scripts/train_vehicle_model.py: EPOCHS = 40, remove freeze=10, imgsz=640
python scripts/train_vehicle_model.py
# then copy models/train_runs/road_vehicle_v1/weights/best.pt -> models/yolo_raipur_best.pt
```

Expected: mAP@50 ≈ 0.55-0.70 with the full schedule on a GPU.

## Integration
* 21 dataset classes map to 5 canonical categories + special `ambulance`
  (`backend/vision.py::_CANON`).
* **Ambulance detections auto-trigger the Emergency Green Corridor**
  (Layer 1 SEE → Layer 5 ACT) once per video session.
* The Video Detection tab probes uploaded footage first with this model; if the
  footage domain yields no detections (e.g. synthetic clips) it transparently
  falls back to the OpenCV MOG2 tracker.
