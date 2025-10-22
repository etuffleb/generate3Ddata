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

If you omit `--output`, the script will write a new file next to the label
named `<label>_bottle.png`.

### Optional parameters

* `--bottle-color` – change the tint of the transparent plastic (hex or colour name).
* `--cap-color` – colour of the bottle cap.

The command below creates a darker bottle on a white background:

```
python generate_bottle.py label.png studio_background.jpg \
    --bottle-color "#2f8ba6" \
    --cap-color "#1c4c5c"
```

The resulting PNG contains transparency for the bottle silhouette, subtle
lighting to hint at depth, and your label centred on the front of the bottle.
