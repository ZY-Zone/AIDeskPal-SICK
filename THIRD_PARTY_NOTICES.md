# Third-party notices

## Python dependencies

| Package | License | Use |
| --- | --- | --- |
| PySide6 / Qt for Python | LGPL-3.0 (Qt) / LGPLv3 for PySide6, with Qt commercial alternative | Windows UI and OpenGL surface |
| PyOpenGL | BSD-3-Clause | OpenGL bindings |
| NumPy | BSD-3-Clause | geometry, skinning, masks |
| Pillow | MIT-CMU | image loading and covers |
| pystray | LGPLv3 | Windows notification-area icon and native menu |
| httpx | BSD-3-Clause | AI and market HTTP |
| pytest | MIT | tests |

The launcher is a small VBScript (`src/aideskpal/start.vbs`) that runs the
local Python environment; it does not bundle the Python runtime or third-party
libraries.

## Fonts and assets

The UI uses system fonts (Microsoft YaHei UI / Segoe UI) and does not bundle font
files. UI screenshots are captures of the application under the project MIT
license; the default configuration in those screenshots references the local
example PMX but no model files are distributed.

## User-supplied models and actions

Models, character prompts and action packs added by users are not part of this
repository or its source distribution. They are copied into the local character
directory only. Users are responsible for complying with each model author's
license and redistribution terms.

The JSON animations in `actions/starling/` and the sample model under
`sample_content/starling/` are original project assets released under MIT. A
model + action bundle published through any market must have the model author's
permission.

## Starling Lumi sample model

`sample_content/starling/` and `actions/starling/` are procedurally generated for
this project and released under the MIT license. They contain no third-party
character assets.
