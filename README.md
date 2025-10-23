# generate3Ddata

This repository contains a small utility that can render a stylised bottle
mock-up from a flat label image. It is useful when you have a PNG/JPG of a
brand label (for example *Coca-Cola* or *Bon Aqua*) and want to quickly see how
it might look when wrapped around a plastic bottle.

## Requirements

The script only depends on [Pillow](https://python-pillow.org/). Install it via

```bash
pip install pillow
```

## Usage

```
python generate_bottle.py path/to/label.png path/to/background.jpg --output bottle.png
```

If you omit `--output`, the script will write three files next to the label
named `<label>_bottle_left.png`, `<label>_bottle_center.png`, and
`<label>_bottle_right.png`. Supplying `--output` lets you choose the base file
name; the `_left`, `_center`, and `_right` suffixes are still appended
automatically.

### Optional parameters

* `--bottle-color` – change the tint of the transparent plastic (hex or colour name).
* `--cap-color` – colour of the bottle cap (defaults to the average colour of the label).

The command below creates a darker bottle on a white background:

```
python generate_bottle.py label.png studio_background.jpg \
    --bottle-color "#2f8ba6" \
    --cap-color "#1c4c5c"
```

Each PNG contains transparency for the bottle silhouette, subtle lighting to
hint at depth, and the label centred on the front of the bottle. Three crops of
the label (left, centre, right) are rendered to mimic slight rotations of the
bottle as it sits on the provided background.
