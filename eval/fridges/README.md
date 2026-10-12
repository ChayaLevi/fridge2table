# Eval set: fridge / pantry photos

Used by `eval/run_vision_eval.py` to measure recognition quality.

## Layout

One folder per place (a fridge, a freezer or a pantry) of one household:

```
eval/fridges/<household>_<place>/
    1.jpg 2.jpg ...      # 1-4 photos of that place
    labels.json
```

Examples: `home1_fridge`, `home1_pantry`, `home2_fridge`, `home2_pantry`.
A pantry is often several shelves or cabinets: put them all in the same folder.

## labels.json

```json
{"location": "fridge",
 "items": [{"name": "milk", "alt": ["whole milk"]}, {"name": "egg"}, {"name": "spinach", "use_soon": true}]}
```

- `location`: `fridge`, `freezer` or `pantry`. It is passed to the model as the place tag.
- `items`: what a human sees in the photos of this folder (generic English names, no brands).
- `alt`: other names that should count as correct.
- `use_soon` (optional): mark items that are close to spoiling.

## What we need

4-6 sets: **at least 2 fridge sets and at least 2 pantry sets** (pantries test label reading on jars, cans and
packages). Freezer sets are optional. Mix your own and other people's kitchens.
Photos are not committed to git by default if they are private: add the folder to `.gitignore` if needed.
