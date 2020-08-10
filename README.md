gracon
======

A collection of python scripts that convert data to formats used in my SNES projects.
Primarily written for personal use, unfit for general public usage.

|  Script             | Purpose   | Remarks |
|  ------             | -------   | ------- |
|  graconFont.py      | Converts bitmap font file to VWF bitplane format. | Graphics data must strictly adhere to expected grid layout. |
|  graconGfx.py      | Converts graphics file (png, gif, bmp etc.) to SNES bitplane format. | Features: optional lossy optimization, optional lz4 compression, direct color mode, sprite/background mode, meta sprites, reference palette etc. |
|  graconGfxAnimation.py      | Converts folder of graphics files (png, gif, bmp etc.) to animation in SNES bitplane format. | Features: sprite/background animations, speed/delay/loop options. |
|  graconHdmaFixedColorGradient.py      | Converts folder of graphics files (png, gif, bmp etc.) to animation of HDMA lists targetting PPU COLDATA register. | Only leftmost pixel column of input image is used. |
|  graconHdmaPaletteGradient.py      | Converts folder of graphics files (png, gif, bmp etc.) to animation of HDMA lists targetting PPU CGRAM entry. | Only leftmost pixel column of input image is used. Target CGRAM entry is fixed.  |
|  graconHdmaWindowOverlay.py      | Converts folder of graphics files (png, gif, bmp etc.) to animation of HDMA lists targetting PPU window registers.  | Input images are treated as monochrome and leftmost/rightmost white pixel is regarded as left/right window position for each scanline. |
|  graconMap.py      | Converts [tiled](https://www.mapeditor.org/) xml map files to assembler include files (wla-dx format). | Multiple background layers (2bpp, 4bpp with corresponding tileset and optional reference palette each), collision layer, metatiles, optional lz4 compression, modifiable tiles, objects having custom properties |
|  graconMusic.py      | Converts ProTracker mod-file to custom music format. | Sample length and loop points should be multiple of 16. |
|  graconPaletteAnimation.py      | Converts folders of graphics files (png, gif, bmp etc.) to palette animation targetting PPU CGRAM. | |
|  graconText.py      | Converts folder of text files to assembler include files (wla-dx format). | Supports multiple languages, generates corresponding lookup tables. |

> **Dependencies**
> - python2.7
> - [lz4](https://github.com/lz4/lz4)


Installation
------------

```
make install # may require root permissions
```
