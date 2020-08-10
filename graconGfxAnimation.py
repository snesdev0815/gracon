#!/usr/bin/env python2.7

__author__ = "Matthias Nagler <matt@dforce.de>"
__url__ = ("dforce3000", "dforce3000.de")
__version__ = "0.1"

'''
takes input graphics files(usually png), converts and packs them into animation file
first file determines palette to use
nice2have:
  -calculate required palettes, insert new palettes as needed
	-start at first palette, keep in buffer, save there
	-if buffer satisfies subsequent frame, use buffer there aswell. else replace buffer
	
  -somehow decide between frame tile uploads and packing all tiles into one tileset

command line options:
-infolder	input folder containing all animation frames, name-sorted
-outfile	output animation file

outfile format:
[sprite_animation{
  [header(13bytes){
	2 bytes : "SP", header magic
	2 bytes : max tile-size(bytes) in animation(for vram/sprite allocation)
	2 bytes : max palette-size(bytes) in animation(for cgram allocation)
	2 bytes : frames in animation
	1 byte  : bpp
	2 byte  : width in pixels
	2 byte  : height in pixels
  }],
  [pointer{
	2 bytes : relative pointer to individual sprite frame
  }]
  [sprite_frame{
  [header(6bytes){
	2 bytes : tilesize(bytes): if 0, no tiles present(use previous)
	2 bytes : spritemapsize(byte)
	2 bytes : palettesize(byte): if 0, no tiles present(use previous)
  }],
  [tiles]
  [spritemap]
  [palette]
  }]
}]  
'''

'''
old frame format: (size 11)
  ANIMATION.FRAME.TILES.NORMAL.LENGTH dw
  ANIMATION.FRAME.TILEMAP.NORMAL.LENGTH dw
  ANIMATION.FRAME.PALETTE.LENGTH dw
  ANIMATION.FRAME.TILES.BIG.LENGTH dw
  ANIMATION.FRAME.TILEMAP.BIG.LENGTH dw
  ANIMATION.FRAME.DELAY db
  ANIMATION.FRAME.DATA dw

new frame format: (size 29) (all pointers: relative from start of frame header)
  ANIMATION.FRAME.DELAY db
  ANIMATION.FRAME.TILES.NORMAL.POINTER dw
  ANIMATION.FRAME.TILES.NORMAL.LENGTH dw
  ANIMATION.FRAME.TILES.BIG.POINTER dw
  ANIMATION.FRAME.TILES.BIG.LENGTH dw
  ANIMATION.FRAME.PALETTE.POINTER dw
  ANIMATION.FRAME.PALETTE.LENGTH dw
  ANIMATION.FRAME.TILEMAP.NORMAL.POINTER dw
  ANIMATION.FRAME.TILEMAP.NORMAL.LENGTH dw
  ANIMATION.FRAME.TILEMAP.BIG.POINTER dw
  ANIMATION.FRAME.TILEMAP.BIG.LENGTH dw
  ANIMATION.FRAME.TILEMAP.XMIRROR.NORMAL.POINTER dw
  ANIMATION.FRAME.TILEMAP.XMIRROR.NORMAL.LENGTH dw
  ANIMATION.FRAME.TILEMAP.XMIRROR.BIG.POINTER dw
  ANIMATION.FRAME.TILEMAP.XMIRROR.BIG.LENGTH dw
  ANIMATION.FRAME.DATA dw

framesNormal
0: tiles
1: tilemap
2: tilemap xmirrored
3: palette    
'''


import os
import re
import sys
import math
import time
import string
import graconUserOptions
import graconGfx
import logging
import struct
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import subprocess

logging.basicConfig( level=logging.ERROR, format='%(message)s')

options = {}


INFINITY = 1e300000
HEADER_MAGIC = 'SP'
HEADER_SIZE = 26
HEADER_STATIC_FLAG_PALETTES = 1
HEADER_STATIC_FLAG_TILES = 2
FRAME_HEADER_SIZE = 20
ALLOWED_FRAME_FILETYPES = ('.png', '.gif', '.bmp')

OAM_FORMAT_TILE = 0x1ff
OAM_FORMAT_HFLIP = 0x4000
OAM_FORMAT_VFLIP = 0x8000

FRAME_FLAG_TILES_PACKED = 0x1
FRAME_FLAG_TILEMAP_PACKED = 0x2
FRAME_FLAG_PALETTE_PACKED = 0x4

FRAME_TILEMAP_NORMAL_MAX = 100
FRAME_TILEMAP_BIG_MAX = 8

def main():
  options = graconUserOptions.Options( sys.argv, {
	'palettes' 		: {
	  'value'			: 1,
	  'type'			: 'int',
	  'max'			: 8,
	  'min'			: 0
	  },
	'transcol'	: {
	  'value'			: 0xff00ff,
	  'type'			: 'hex',
	  'max'			: 0xffffff,
	  'min'			: 0x0
	  },	  
	'infolder'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
	'outfile'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
    'outfilebase'       : {
      'value'           : '',
      'type'            : 'str'
      },	  
	'refpalette'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
	'tilesizex'	: {
	  'value'			: 8,
	  'type'			: 'int',
	  'max'			: 16,
	  'min'			: 8
	  },
	'tilesizey'	: {
	  'value'			: 8,
	  'type'			: 'int',
	  'max'			: 16,
	  'min'			: 8
	  },
	'optimize'	: {
	  'value'			: True,
	  'type'			: 'bool'
	  },
  'createAllocationDummy'  : {
    'value'     : True,
    'type'      : 'bool'
    },    
    'partitionTilemap'        : {
      'value'           : False,
      'type'            : 'bool'
      },	  
    'directcolor'  : {
      'value'           : False,
      'type'            : 'bool'
      },      
	'tilethreshold'	: {
	  'value'			: 0,
	  'type'			: 'int',
	  'max'			: 0xffff,
	  'min'			: 0
	  },
    'maxtiles' : {
      'value'           : 0x3ff,
      'type'            : 'int',
      'max'         : 0xfff,
      'min'         : 0
      },      	  
	'bpp' 		: {
	  'value'			: 4,
	  'type'			: 'int',
	  'max'			: 8,
	  'min'			: 1
	  },
	'mode'		: {
	  'value'			: 'bg',
	  'type'			: 'str'
	  },
	'resolutionx'	: {
	  'value'			: 256,
	  'type'			: 'int',
	  'max'			: 0xffff,
	  'min'			: 1
	  },	  
	'resolutiony'	: {
	  'value'			: 224,
	  'type'			: 'int',
	  'max'			: 0xffff,
	  'min'			: 1
	  },
  'tilemultiplier' : { #used for 16x16(2), 32x32(4), 64x64(8) sprite tiles etc
    'value'           : 1,
    'type'            : 'int',
    'max'         : 8,
    'min'         : 1
    },
  'baseframerate' : {
    'value'           : 0,
    'type'            : 'int',
    'max'         : 3,
    'min'         : 0
    },                
  'verify'        : {
    'value'           : False,
    'type'            : 'bool'
    },
  'statictiles'        : {
    'value'           : False,
    'type'            : 'bool'
    },
  'isPacked'        : {
    'value'           : False,
    'type'            : 'bool'
    },
  'bigtilethreshold' : {  #number of empty tiles to allow when parsing big mode tiles (usually 32x32 sprites)
    'value'     : 1,
    'type'      : 'int',
    'max'     : 16,
    'min'     : 0
  },
  'maxbigtiles' : {  #number of big tiles allowed per animation frame
    'value'     : 4,
    'type'      : 'int',
    'max'     : 16,
    'min'     : 0
    },     
  'xMirrorTilemap'        : {
    'value'           : False,
    'type'            : 'bool'
  },
  'yMirrorTilemap'        : {
    'value'           : False,
    'type'            : 'bool'
  },  
  'compileTilemapCode'        : {
    'value'           : False,
    'type'            : 'bool'
    },
  'forcePalette'        : {
      'value'           : False,
      'type'            : 'bool'
    }    
  })

  sys.setrecursionlimit(10000)

  options.set('transcol', graconGfx.Color(graconGfx.getColorTuple(options.get('transcol'))))
  
  if not os.path.exists(options.get('infolder')):
	logging.error( 'Error, input folder "%s" is nonexistant.' % options.get('infolder') )
	sys.exit(1)

  tileFiles = [frame for root, dirs, names in os.walk(options.get('infolder')) for frame in names if os.path.splitext(frame)[1] in ALLOWED_FRAME_FILETYPES]
  tileFiles.sort()
  presetPalette = "palette.png"
  if presetPalette in tileFiles:
    tileFiles.remove(presetPalette)
    options.set('refpalette', "%s/%s" % (options.get('infolder'), presetPalette))
    #set transparent color to first color in reference palette
    refPaletteImg = graconGfx.getReferencePaletteImage(options)
    options.set('transcol', refPaletteImg['pixels'][0][0])
    logging.debug("transparent color now %x" % options.get('transcol').getRGB())

  options.set('isPacked', None != re.search('\.packed\.', options.get('infolder')))

  #todo: set loop start point if framename contains ".loopstart." and add new field loopstart in animation file (default:0)
  #idea: animations not having any loopstart-frame could default to: no loop. but this would be tricky if code requires animation to finish to continue...
  loopstart = 0
  frameDelays = [0 for frame in range(len(tileFiles))]
  index = 0
  for frame in tileFiles:
      if None != re.search('\.loopstart\.', frame):
        loopstart = index        
        logging.debug("found loopstart %s." % loopstart)
      try:        
        delay = int((re.search('\.delay[\d]{3}', frame)).group(0)[-3:])
      except ValueError:
        delay = 0      
      except AttributeError:
        delay = 0      

      if None != re.search('\.slow\.', frame):      
        delay = 2
      logging.debug("got delay %s" % delay)
      
      frameDelays[index] = delay
      index += 1
    
    
  options.set('outfilebase', options.get('outfile'))
  logging.debug("parsing tiles")
  tileFrames = [graconGfx.parseTiles(graconGfx.getInputImage(options, "%s/%s" % (options.get('infolder'), tileFiles[i])), options, i) for i in range(len(tileFiles))]

  if not 0 < len(tileFrames):
	logging.error( 'Error, input folder "%s" does not contain any parseable frame image files.' % options.get('infolder') )
	sys.exit(1)
    
  firstImage = graconGfx.getInputImage(options, "%s/%s" % (options.get('infolder'), tileFiles[0]))
  
  globalTilesNormal = [tile for tileFrame in tileFrames for tile in tileFrame['normal']]
  globalTilesBig = [tile for tileFrame in tileFrames for tile in tileFrame['big']]
  
  paletteTiles = [tile for tileFrame in tileFrames for tile in tileFrame['normal']] + [tile for tileFrame in tileFrames for tile in tileFrame['big']]
  logging.debug("fetching palette")
  palette = graconGfx.fetchGlobalPaletteTileRelative(paletteTiles, options) if "" == options.get('refpalette') else graconGfx.parseGlobalPalettes(paletteTiles, options)
  
  logging.debug("optimising tiles")
  if options.get('statictiles'):
    for i in range(len(globalTilesNormal)):
      globalTilesNormal[i]['id'] = i
    logging.debug("is static")
    tileFramesNormal = [graconGfx.augmentOutIds(graconGfx.tilesLengthCheck(graconGfx.optimizeTilesNew(graconGfx.palettizeTiles(frame['normal'], palette, options), globalTilesNormal, options),options)) for frame in tileFrames]
  else:
    logging.debug("non static")
    tileFramesNormal = [graconGfx.augmentOutIds(graconGfx.tilesLengthCheck(graconGfx.optimizeTilesNew(graconGfx.palettizeTiles(frame['normal'], palette, options), None, options), options)) for frame in tileFrames]
  
  if options.get('statictiles'):
    for i in range(len(globalTilesBig)):
      globalTilesBig[i]['id'] = i
    tileFramesBig = [graconGfx.augmentOutIds(graconGfx.palettizeTiles(frame['big'], palette, options)) for frame in tileFrames]
  else:
    tileFramesBig = [graconGfx.augmentOutIds(graconGfx.palettizeTiles(frame['big'], palette, options)) for frame in tileFrames]    

  palette = graconGfx.augmentOutIds(palette)

  framesNormals = getCompletedFrames(tileFramesNormal, globalTilesNormal, palette, options)
  framesBigs = getCompletedFrames(tileFramesBig, globalTilesBig, palette, options)

  frames = [Frame(framesNormals[i],framesBigs[i],options) for i in range(len(framesNormals))]

  maxTileLengthNormal = 0
  maxTileLengthBig = 0
  maxTilemapLength = 0
  maxPaletteLength = 0
  framecount = len(tileFrames)
  currentFramePointer = 0
  framePointers = []
  imageSizeX = firstImage['resolutionX']
  imageSizeY = firstImage['resolutionY']
  
  labelPrefix = "%x" % abs(hash(string.replace(options.get('infolder'), "/", ".")))
  logging.debug("calculating pointers")
  for frame in frames:
    framePointers.append(currentFramePointer)
    currentFramePointer += frame.getLength()

    maxTileLengthNormal = frame.allocLenTilesNormal if maxTileLengthNormal < frame.allocLenTilesNormal else maxTileLengthNormal
    maxTileLengthBig = frame.allocLenTilesBig if maxTileLengthBig < frame.allocLenTilesBig else maxTileLengthBig
    maxTilemapLength = (frame.allocTilemapLength + frame.allocTilemapBigLength) if maxTilemapLength < (frame.allocTilemapLength + frame.allocTilemapBigLength) else maxTilemapLength
    maxPaletteLength = frame.allocPaletteLength if maxPaletteLength < frame.allocPaletteLength else maxPaletteLength
  
  
  try:
    outFile = open( options.get('outfile'), 'wb')
    incFile = open("%s.i" % options.get('outfile'), 'w')
  except IOError:
    logging.error( 'unable to access required output-file %s' % options.get('outfile') )
    sys.exit(1)

  #write header
  incFile.write('__%s.st: \n' % labelPrefix)

  outFile.write(HEADER_MAGIC)
  incFile.write('.db "%s" \n' % HEADER_MAGIC)

  outFile.write(chr(maxTileLengthNormal & 0xff))
  outFile.write(chr((maxTileLengthNormal & 0xff00) >> 8 ))
  incFile.write('.dw %s \n' % maxTileLengthNormal)

  outFile.write(chr(maxTileLengthBig & 0xff))
  outFile.write(chr((maxTileLengthBig & 0xff00) >> 8 ))
  incFile.write('.dw %s \n' % maxTileLengthBig)
  
  outFile.write(chr(maxPaletteLength & 0xff))
  outFile.write(chr((maxPaletteLength & 0xff00) >> 8 ))
  incFile.write('.dw %s \n' % maxPaletteLength)

  outFile.write(chr(maxTilemapLength & 0xff))
  outFile.write(chr((maxTilemapLength & 0xff00) >> 8 ))
  incFile.write('.dw %s \n' % maxTilemapLength)


  outFile.write(chr(framecount & 0xff))
  outFile.write(chr((framecount & 0xff00) >> 8 ))
  incFile.write('.dw %s \n' % framecount)


  outFile.write(chr(loopstart & 0xff))
  outFile.write(chr((loopstart & 0xff00) >> 8 ))
  incFile.write('.dw %s \n' % loopstart)


  outFile.write(chr(int(options.get('bpp')/2) & 0xff))
  incFile.write('.db %s \n' % int(options.get('bpp')/2))

  outFile.write(chr(int(options.get('tilemultiplier')) & 0xff))
  incFile.write('.db %s \n' % int(options.get('tilemultiplier')))

  outFile.write(chr(imageSizeX & 0xff))
  outFile.write(chr((imageSizeX & 0xff00) >> 8 ))
  incFile.write('.dw %s \n' % imageSizeX)


  outFile.write(chr(imageSizeY & 0xff))
  outFile.write(chr((imageSizeY & 0xff00) >> 8 ))
  incFile.write('.dw %s \n' % imageSizeY)
  

  staticFlags = 0
  staticFlags |= HEADER_STATIC_FLAG_PALETTES
  if options.get('statictiles'):
    staticFlags |= HEADER_STATIC_FLAG_TILES

  outFile.write(chr(staticFlags))
  incFile.write('.db %s \n' % staticFlags)
  

  tileHash = hash(str([frame.tiles for frame in frames])) & 0xffff

  outFile.write(chr(tileHash & 0xff))
  outFile.write(chr((tileHash & 0xff00) >> 8 ))
  incFile.write('.dw %s  ;tilehash\n' % tileHash)

  paletteHash = hash(str([pal['color'] for pal in palette if pal['refId'] == None])) & 0xffff

  logging.debug("palette hash: %x" % (paletteHash & 0xffff))
  
  outFile.write(chr(paletteHash & 0xff))
  outFile.write(chr((paletteHash & 0xff00) >> 8 ))
  incFile.write('.dw %s  ;palhash\n' % paletteHash)


  logging.debug("tile hash: %x" % tileHash)
  logging.debug("palette hash: %x" % paletteHash)
  
  if 0 == options.get('baseframerate'):
    framerateMask = 0x0
  elif 1 == options.get('baseframerate'):
    framerateMask = 0x1
  elif 2 == options.get('baseframerate'):
    framerateMask = 0x3
  elif 3 == options.get('baseframerate'):
    framerateMask = 0x7
    
  outFile.write(chr(framerateMask & 0xff))
  incFile.write('.db %s \n' % framerateMask)
  
  #write framepointerlist
  outFile.seek(HEADER_SIZE)

  for framePointer in framePointers:
  	framePointer += HEADER_SIZE + len(framePointers)*2
  	outFile.write(chr(framePointer & 0xff))
  	outFile.write(chr((framePointer & 0xff00) >> 8 ))

  for i in range(len(frames)):
    incFile.write('.dw __%s.f%s - __%s.st \n' % (labelPrefix,i,labelPrefix))


  #write frames
  for i in range(len(frames)):

    flags = (FRAME_FLAG_TILES_PACKED | FRAME_FLAG_TILEMAP_PACKED) if options.get('isPacked') else FRAME_FLAG_TILEMAP_PACKED

    frame = frames[i]
    #write frame header
    pointer = FRAME_HEADER_SIZE
    incFile.write('\n__%s.f%s:\n' % (labelPrefix,i))

    tilesHash = "stln%s" % abs(hash(getByteList(frame.tiles)))
    paletteLongHash = "pal%s" % abs(hash(getByteList(frame.palette)))

    #frame delay
    outFile.write(chr(frameDelays[i] & 0xff))
    incFile.write('.db %s \n' % frameDelays[i])

    #flags
    outFile.write(chr(flags & 0xff))
    incFile.write('.db %s \n' % flags)

    #tiles normal
    outFile.write(chr(pointer & 0xff))
    outFile.write(chr(pointer >> 8 ))
    if "stln0" == tilesHash:
      incFile.write('.db 0,0,0\n')
    else:
      incFile.write('.dw %s\n' % tilesHash)
      incFile.write('.db :%s\n' % tilesHash)

    #tiles normal length
    outFile.write(chr(frame.allocLenTilesNormal & 0xff))
    outFile.write(chr((frame.allocLenTilesNormal & 0xff00) >> 8 ))
    incFile.write('.dw %s \n' % frame.allocLenTilesNormal)

    logging.debug("frm 0x%02x tile len normal: 0x%04x, len big: 0x%04x, len total: 0x%04x" % (i, frame.allocLenTilesNormal, frame.allocLenTilesBig, frame.allocLenTilesNormal+frame.allocLenTilesBig))
    pointer += len(frame.tiles)

    #tiles big length
    outFile.write(chr(frame.allocLenTilesBig & 0xff))
    outFile.write(chr((frame.allocLenTilesBig & 0xff00) >> 8 ))
    incFile.write('.dw %s \n' % frame.allocLenTilesBig)

    #palette pointer
    outFile.write(chr(pointer & 0xff))
    outFile.write(chr(pointer >> 8 ))

    if "pal0" == paletteLongHash:
      incFile.write('.db 0,0,0\n')
    else:
      incFile.write('.dw %s\n' % paletteLongHash)
      incFile.write('.db :%s\n' % paletteLongHash)

    #palette length
    outFile.write(chr(frame.allocPaletteLength & 0xff))
    outFile.write(chr((frame.allocPaletteLength & 0xff00) >> 8 ))
    incFile.write('.dw %s \n' % frame.allocPaletteLength)

    pointer += len(frame.palette)

    #tilemap normal
    hashList = [""]
    for tile in chunks(frame.mapNormal, 4):
      for tilly in tile:
          hashList.append("n%x" % ord(tilly))
    for tile in chunks(frame.mapBig, 4):
      for tilly in tile:
          hashList.append("b%x" % ord(tilly))

    tilemapHash = string.replace("%x" % hash(reduce(lambda x,y: "%s_%s" % (x,y) , hashList)), "-", "_")
    logging.debug("tilemap hash: %s" % tilemapHash)

    #tilemap norm pointer
    outFile.write(chr(pointer & 0xff))
    outFile.write(chr(pointer >> 8 ))
    incFile.write('.dw stm%s\n' % tilemapHash)
    incFile.write('.db :stm%s\n' % tilemapHash)

    #tilemap norm length
    outFile.write(chr(frame.allocTilemapLength & 0xff))
    outFile.write(chr((frame.allocTilemapLength & 0xff00) >> 8 ))

    incFile.write('.dw %s \n' % frame.allocTilemapLength)

    pointer += len(frame.tilemap)

    #tilemap big length
    outFile.write(chr(frame.allocTilemapBigLength & 0xff))
    outFile.write(chr((frame.allocTilemapBigLength & 0xff00) >> 8 ))

    #tilemap x-normal pointer
    outFile.write(chr(pointer & 0xff))
    outFile.write(chr(pointer >> 8 ))

    hashList = [""]
    for tile in chunks(frame.xMapNormal, 4):
      for tilly in tile:
          hashList.append("n%x" % ord(tilly))
    for tile in chunks(frame.xMapBig, 4):
      for tilly in tile:
          hashList.append("b%x" % ord(tilly))

    xtilemapHash = string.replace("%x" % hash(reduce(lambda x,y: "%s_%s" % (x,y) , hashList)), "-", "_")
    logging.debug("xtilemap hash: %s" % xtilemapHash)

    incFile.write('.dw stm%s\n' % xtilemapHash)
    incFile.write('.db :stm%s\n' % xtilemapHash)

    pointer += len(frame.xTilemap)

    [outFile.write(byte) for byte in frame.tiles]
    if not "stln0" == tilesHash:
      incFile.write("""
.ifndef %s.defined
  .def %s.defined 1
  .export %s.defined
%s:
  %s
.else
  .PRINTT "omit dupe oamtiles %s.\\n"
.endif
""" % (tilesHash,tilesHash,tilesHash,tilesHash,getByteList(frame.tiles),tilesHash))

    [outFile.write(byte) for byte in frame.palette]
    if not "pal0" == paletteLongHash:
      incFile.write("""
.ifndef %s.defined
  .def %s.defined 1
  .export %s.defined
%s:
  %s
.else
  .PRINTT "omit dupe oampalette %s.\\n"
.endif
""" % (paletteLongHash,paletteLongHash,paletteLongHash,paletteLongHash,getByteList(frame.palette),paletteLongHash))


    [outFile.write(byte) for byte in frame.tilemap]
    incFile.write("""
.ifndef stm%s.defined
  .def stm%s.defined 1
  .export stm%s.defined
stm%s:
    """ % (tilemapHash,tilemapHash,tilemapHash,tilemapHash))

    counter = 0
    incFile.write('.accu 16\n.index 16\n')
    for tile in chunks(frame.mapBig, 4):
      incFile.write('\tGENERATE_SPRITE_BIG $%02x $%02x $%02x%02x $%02x \n' % (ord(tile[0]), ord(tile[1]), ord(tile[3]), ord(tile[2]), counter))
      counter += 1
    for tile in chunks(frame.mapNormal, 4):
      incFile.write('\tGENERATE_SPRITE_NORMAL $%02x $%02x $%02x%02x $%02x \n' % (ord(tile[0]), ord(tile[1]), ord(tile[3]), ord(tile[2]), counter))
      counter += 1
    incFile.write('rtl\n')

    incFile.write("""
.else
  .PRINTT "omit dupe oamtilemap %s.\\n"
.endif
""" % (tilemapHash))

    incFile.write("""
.ifndef stm%s.defined
  .def stm%s.defined 1
  .export stm%s.defined
stm%s:
""" % (xtilemapHash,xtilemapHash,xtilemapHash,xtilemapHash))

    [outFile.write(byte) for byte in frame.xTilemap]

    counter = 0
    incFile.write('.accu 16\n.index 16\n')
    for tile in chunks(frame.xMapBig, 4):
      incFile.write('\tGENERATE_SPRITE_BIG $%02x $%02x $%02x%02x $%02x \n' % (ord(tile[0]), ord(tile[1]), ord(tile[3]), ord(tile[2]), counter))
      counter += 1
    for tile in chunks(frame.xMapNormal, 4):
      incFile.write('\tGENERATE_SPRITE_NORMAL $%02x $%02x $%02x%02x $%02x \n' % (ord(tile[0]), ord(tile[1]), ord(tile[3]), ord(tile[2]), counter))
      counter += 1
    incFile.write('\trtl\n')

    incFile.write("""
.else
  .PRINTT "omit dupe oamtilemap %s.\\n"
.endif
""" % (xtilemapHash))

  incFile.write(';EOF\n')
  
  incFile.close()
  if options.get('verify'):
    graconGfx.writeSamplePalette(palette, options)
    if not options.get('statictiles'):   
      writeSampleImageAnimation(tileFramesNormal, tileFramesBig, palette, imageSizeX, imageSizeY, options)

  labelPrefix = "d" + labelPrefix

  #extremly bad hack to determine maximum allocation size of animation pack folders
  if options.get('createAllocationDummy'):
    dummyFileName = "%s/dummy.gfx_sprite.animation" % os.path.dirname(options.get('outfile'))
    logging.debug("opening dummy file %s " % dummyFileName)
    try:
      dummyFileRead = open( dummyFileName, 'rb' )
      dummyFileRead.seek(2)
      dummyMaxTilesNormal = max(maxTileLengthNormal, struct.unpack('<H', dummyFileRead.read(2))[0])
      dummyMaxTilesBig = max(maxTileLengthBig, struct.unpack('<H', dummyFileRead.read(2))[0])
      dummyMaxPalette = max(maxPaletteLength, struct.unpack('<H', dummyFileRead.read(2))[0])
      dummyMaxTilemap = max(maxTilemapLength, struct.unpack('<H', dummyFileRead.read(2))[0])

      dummyFileRead.seek(16)
      dummyMaxSizeX = max(imageSizeX, struct.unpack('<H', dummyFileRead.read(2))[0])
      dummyMaxSizeY = max(imageSizeY, struct.unpack('<H', dummyFileRead.read(2))[0])

      dummyFileRead.close()

    except IOError:
      dummyMaxTilesNormal = maxTileLengthNormal
      dummyMaxTilesBig = maxTileLengthBig
      dummyMaxPalette = maxPaletteLength
      dummyMaxTilemap = maxTilemapLength
      dummyMaxSizeX = imageSizeX
      dummyMaxSizeY = imageSizeY

    try:
      dummyFile = open( dummyFileName, 'wb' )
      incFileDummy = open("%s.i" % dummyFileName, 'w')

    except IOError:
      logging.error( 'unable to access required dummy-file %s' % dummyFileName)
      sys.exit(1)

    incFileDummy.write('__%s.st: \n' % labelPrefix)

    dummyFile.write(HEADER_MAGIC)
    incFileDummy.write('.db "%s" \n' % HEADER_MAGIC)

    dummyFile.write(chr(dummyMaxTilesNormal & 0xff))
    dummyFile.write(chr((dummyMaxTilesNormal & 0xff00) >> 8 ))
    incFileDummy.write('.dw %s \n' % dummyMaxTilesNormal)

    dummyFile.write(chr(dummyMaxTilesBig & 0xff))
    dummyFile.write(chr((dummyMaxTilesBig & 0xff00) >> 8 ))
    incFileDummy.write('.dw %s \n' % dummyMaxTilesBig)
    
    dummyFile.write(chr(dummyMaxPalette & 0xff))
    dummyFile.write(chr((dummyMaxPalette & 0xff00) >> 8 ))
    incFileDummy.write('.dw %s \n' % dummyMaxPalette)

    dummyFile.write(chr(dummyMaxTilemap & 0xff))
    dummyFile.write(chr((dummyMaxTilemap & 0xff00) >> 8 ))
    incFileDummy.write('.dw %s \n' % dummyMaxTilemap)

    dummyFile.write(chr(0 & 0xff))
    dummyFile.write(chr((0 & 0xff00) >> 8 ))
    incFileDummy.write('.dw %s \n' % 0)

    dummyFile.write(chr(0 & 0xff))
    dummyFile.write(chr((0 & 0xff00) >> 8 ))
    incFileDummy.write('.dw %s \n' % 0)

    dummyFile.write(chr(int(options.get('bpp')/2) & 0xff))
    incFileDummy.write('.db %s \n' % int(options.get('bpp')/2))
    dummyFile.write(chr(int(options.get('tilemultiplier')) & 0xff))
    incFileDummy.write('.db %s \n' % int(options.get('tilemultiplier')))

    dummyFile.write(chr(imageSizeX & 0xff))
    dummyFile.write(chr((imageSizeX & 0xff00) >> 8 ))
    incFileDummy.write('.dw %s \n' % imageSizeX)

    dummyFile.write(chr(imageSizeY & 0xff))
    dummyFile.write(chr((imageSizeY & 0xff00) >> 8 ))
    incFileDummy.write('.dw %s \n' % imageSizeY)
    
    dummyFile.write(chr(0))
    incFileDummy.write('.db %s \n' % 0)
    

    tileHash = 0x0
    dummyFile.write(chr(tileHash & 0xff))
    dummyFile.write(chr((tileHash & 0xff00) >> 8 ))
    incFileDummy.write('.dw %s ;tilehash\n' % tileHash)

    #why is this zeroed-out? we need palette hash to be able to try to allocate palette with dummy animation to see if we are able to allocate or need to bail out gracefully.
    dummyFile.write(chr(paletteHash & 0xff))
    dummyFile.write(chr((paletteHash & 0xff00) >> 8 ))
    incFileDummy.write('.dw %s ;palhash\n' % paletteHash)

    dummyFile.write(chr(framerateMask & 0xff))
    incFileDummy.write('.db %s \n' % framerateMask)

    #write one dummy frame
    dummyFile.seek(HEADER_SIZE)
    framePointers = [0]
    for framePointer in framePointers:
      framePointer += HEADER_SIZE + len(framePointers)*2
      dummyFile.write(chr(framePointer & 0xff))
      dummyFile.write(chr((framePointer & 0xff00) >> 8 ))

    for i in range(len(framePointers)):
      incFileDummy.write('.dw __%s.f%s - __%s.st \n' % (labelPrefix,i,labelPrefix))


    framesNormal = [([],[],[],[])]
    framesBig = [([],[],[],[])]
    for i in range(len(framesNormal)):
      pointer = FRAME_HEADER_SIZE
      incFileDummy.write('__%s.f%s:\n' % (labelPrefix,i))

      #frame delay
      dummyFile.write(chr(0 & 0xff))
      incFileDummy.write('.db %s \n' % frameDelays[i])

      #tiles normal
      dummyFile.write(chr(pointer & 0xff))
      dummyFile.write(chr(pointer >> 8 ))
      incFileDummy.write('.dw %s \n' % pointer)

      dummyFile.write(chr(len(framesNormal[i][0]) & 0xff))
      dummyFile.write(chr((len(framesNormal[i][0]) & 0xff00) >> 8 ))
      incFileDummy.write('.dw %s \n' % len(framesNormal[i][0]))

      pointer += len(framesNormal[i][0])

      #tiles big
      dummyFile.write(chr(pointer & 0xff))
      dummyFile.write(chr(pointer >> 8 ))
      incFileDummy.write('.dw %s \n' % pointer)

      dummyFile.write(chr(len(framesBig[i][0]) & 0xff))
      dummyFile.write(chr((len(framesBig[i][0]) & 0xff00) >> 8 ))
      incFileDummy.write('.dw %s \n' % len(framesBig[i][0]))

      pointer += len(framesBig[i][0])

      #palette
      dummyFile.write(chr(pointer & 0xff))
      dummyFile.write(chr(pointer >> 8 ))
      incFileDummy.write('.dw %s \n' % pointer)

      dummyFile.write(chr(len(framesNormal[i][3]) & 0xff))
      dummyFile.write(chr((len(framesNormal[i][3]) & 0xff00) >> 8 ))
      incFileDummy.write('.dw %s \n' % len(framesNormal[i][3]))

      pointer += len(framesNormal[i][3])

      #tilemap normal
      dummyFile.write(chr(pointer & 0xff))
      dummyFile.write(chr(pointer >> 8 ))
      incFileDummy.write('.dw extern.Sprite.dummyOamWrite\n')
      incFileDummy.write('.db :extern.Sprite.dummyOamWrite\n')
      dummyFile.write(chr(len(framesNormal[i][1]) & 0xff))
      dummyFile.write(chr((len(framesNormal[i][1]) & 0xff00) >> 8 ))

      lengthy = len(framesNormal[i][1])+len(framesBig[i][1])
      incFileDummy.write('.dw %s \n' % lengthy)

      pointer += len(framesNormal[i][1])

      #tilemap big
      dummyFile.write(chr(pointer & 0xff))
      dummyFile.write(chr(pointer >> 8 ))
      dummyFile.write(chr(len(framesBig[i][1]) & 0xff))
      dummyFile.write(chr((len(framesBig[i][1]) & 0xff00) >> 8 ))
      incFileDummy.write('.dw 0 \n')

      pointer += len(framesBig[i][1])

      #tilemap x-normal
      dummyFile.write(chr(pointer & 0xff))
      dummyFile.write(chr(pointer >> 8 ))
      dummyFile.write(chr(len(framesNormal[i][2]) & 0xff))
      dummyFile.write(chr((len(framesNormal[i][2]) & 0xff00) >> 8 ))

      pointer += len(framesNormal[i][2])

      #tilemap x-big
      dummyFile.write(chr(pointer & 0xff))
      dummyFile.write(chr(pointer >> 8 ))

      dummyFile.write(chr(len(framesBig[i][2]) & 0xff))
      dummyFile.write(chr((len(framesBig[i][2]) & 0xff00) >> 8 ))

      incFileDummy.write('.dw extern.Sprite.dummyOamWrite\n')
      incFileDummy.write('.db :extern.Sprite.dummyOamWrite\n')
      incFileDummy.write('.dw 0 \n')

      pointer += len(framesBig[i][2])

    dummyFile.close()
    incFileDummy.write(';EOF\n')

    incFileDummy.close()



  logging.info('Successfully wrote animation file %s.' % options.get('outfile'))

def writeSampleImageAnimation(tileFramesNormal, tileFramesBig, palette, imageSizeX, imageSizeY, options):
  sample = Image.new( "RGBA", ( len(tileFramesNormal)*imageSizeX, imageSizeY ), options.get('transcol').getPIL())
  grid = Image.new( "RGBA", ( len(tileFramesNormal)*imageSizeX, imageSizeY ), (0,0,0))
  draw = ImageDraw.Draw(grid)
  outFileName = "%s.%s" % ( options.get('outfile'), 'image.sample.png' )
  for frameID in range(len(tileFramesNormal)):
    baseX = frameID*imageSizeX
    for tile in tileFramesBig[frameID]:

      tiles = tileFramesBig[frameID]
      tileConfig = graconGfx.fetchTileConfig( tile, tiles, palette )
      tile['pixel'] = tiles[tileConfig['tileId']]['indexedPixel'] #hack, copy pixels of referenced tile into current tile
      actualTile = graconGfx.mirrorTile( tile, { 'x' : tileConfig['xMirror'], 'y' : tileConfig['yMirror'] } )
      actualPalette = palette[tileConfig['palId']]
      draw.rectangle([(actualTile['x']+baseX,actualTile['y']),(actualTile['x']+baseX+32,actualTile['y']+32)])
      for yPos in range(len(actualTile['pixel'])):
        for xPos in range(len(actualTile['pixel'][yPos])):
          colorIndex = actualTile['pixel'][yPos][xPos]
          pixel = actualPalette['color'][colorIndex]
          pixelPos = (actualTile['x']+xPos+baseX+((yPos>>3 << 3)%32), actualTile['y']+(yPos%8)+(yPos>>5<<3) )
          if 0 < colorIndex:
            try:
              sample.putpixel(pixelPos,pixel.getPIL())
            except IndexError:
              pass

    for tile in tileFramesNormal[frameID]:
      tiles = tileFramesNormal[frameID]
      tileConfig = graconGfx.fetchTileConfig( tile, tiles, palette )
      tile['pixel'] = tiles[tileConfig['tileId']]['indexedPixel'] #hack, copy pixels of referenced tile into current tile
      actualTile = graconGfx.mirrorTile( tile, { 'x' : tileConfig['xMirror'], 'y' : tileConfig['yMirror'] } )
      actualPalette = palette[tileConfig['palId']]
      draw.rectangle([(actualTile['x']+baseX,actualTile['y']),(actualTile['x']+baseX+8,actualTile['y']+8)])
      for yPos in range(len(actualTile['pixel'])):
        for xPos in range(len(actualTile['pixel'][yPos])):
          colorIndex = actualTile['pixel'][yPos][xPos]
          pixel = actualPalette['color'][colorIndex]
          pixelPos = (actualTile['x']+xPos+baseX, actualTile['y']+yPos)
          if 0 < colorIndex:
            try:
              sample.putpixel(pixelPos,pixel.getPIL())
            except IndexError:
              pass
  if 'bg' == options.get('mode'):
    sample.save( outFileName, 'PNG' )
  else:
    blended = Image.blend(sample, grid, 0.3)
    blended.save( outFileName, 'PNG' )

def getCompletedFrames(tileFrames, globalTiles, palette, options):
  if options.get('statictiles'):
    tileMapGetter = graconGfx.getSpriteTileMapStreamGlobal if options.get('mode') == 'sprite' else graconGfx.getBgTileMapStreamGlobal
    globalTileStuff = graconGfx.augmentOutIds(graconGfx.tilesLengthCheck(graconGfx.optimizeTilesNew(graconGfx.palettizeTiles(globalTiles, palette, options), None, options), options))

    frames = [(graconGfx.getTileWriteStream([], options), tileMapGetter(tileFrame, globalTileStuff, palette, options, False, False), tileMapGetter(tileFrame, globalTileStuff, palette, options, options.get('xMirrorTilemap'), options.get('yMirrorTilemap')) if options.get('xMirrorTilemap') or options.get('yMirrorTilemap') else [], graconGfx.getPaletteWriteStream([], options)) for tileFrame in tileFrames]
    if options.get('directcolor'):
      frames[0] = (graconGfx.getTileWriteStream(globalTileStuff, options), tileMapGetter(tileFrames[0], globalTileStuff, palette, options, False, False), tileMapGetter(tileFrames[0], globalTileStuff, palette, options, options.get('xMirrorTilemap'), options.get('yMirrorTilemap')) if options.get('xMirrorTilemap') or options.get('yMirrorTilemap') else [], graconGfx.getPaletteWriteStream([], options))
    else:
      frames[0] = (graconGfx.getTileWriteStream(globalTileStuff, options), tileMapGetter(tileFrames[0], globalTileStuff, palette, options, False, False), tileMapGetter(tileFrames[0], globalTileStuff, palette, options, options.get('xMirrorTilemap'), options.get('yMirrorTilemap')) if options.get('xMirrorTilemap') or options.get('yMirrorTilemap') else [], graconGfx.getPaletteWriteStream(palette, options))
      
  else:
    tileMapGetter = graconGfx.getSpriteTileMapStream if options.get('mode') == 'sprite' else graconGfx.getBgTileMapStream
    frames = [(graconGfx.getTileWriteStream(tileFrame, options), tileMapGetter(tileFrame, palette, options, False, False), tileMapGetter(tileFrame, palette, options, options.get('xMirrorTilemap'), options.get('yMirrorTilemap')) if options.get('xMirrorTilemap') or options.get('yMirrorTilemap') else [], graconGfx.getPaletteWriteStream([], options)) for tileFrame in tileFrames]
    if not options.get('directcolor'):
      frames[0] = (graconGfx.getTileWriteStream(tileFrames[0], options), tileMapGetter(tileFrames[0], palette, options, False, False), tileMapGetter(tileFrames[0], palette, options, options.get('xMirrorTilemap'), options.get('yMirrorTilemap')) if options.get('xMirrorTilemap') or options.get('yMirrorTilemap') else [], graconGfx.getPaletteWriteStream(palette, options))
  return frames

def generateSpriteNormal(incFile, tile, counter):
  if 0 is ord(tile[1]):
    yPos = "lda.b $34"
  else:
    yPos = """lda.w #$%x
  clc
  adc.b $34
  cmp.w #233
  bcc ++
    lda.w #233
++
  sec
  sbc.w #8""" % (ord(tile[1])+8)

  if 0 is ord(tile[0]):
    xPos = "lda.b $32"
  else:
    xPos = """lda.w #$%x
  clc
  adc.b $32
  cmp.w #256
  bcs +
  sec
  sbc.w #8""" % (ord(tile[0])+8)

  if 0 is ord(tile[2]):
    flags = "lda $62"
  else:
    flags = """lda.w #$%x
clc
adc $62
""" % ord(tile[2])

  incFile.write("""\t
%s
    sta.w $1ca4+$%x,y
    and.w #$100
    sta.w $217f
%s
    sta.w $1ca5+$%x,y
%s
    sta.w $1ca6+$%x,y
+
""" % (xPos, counter*4,yPos,1+counter*4,flags,2+counter*4))

def generateSpriteBig(incFile, tile, counter):
  if 0 is ord(tile[1]):
    yPos = "lda.b $34"
  else:
    yPos = """lda.w #$%x
  clc
  adc.b $34
  cmp.w #233
  bcc ++
    lda.w #233
++
  sec
  sbc.w #8""" % (ord(tile[1])+8)

  if 0 is ord(tile[0]):
    xPos = "lda.b $32"
  else:
    xPos = """lda.w #$%x
  clc
  adc.b $32
  cmp.w #256
  bcs +
  sec
  sbc.w #8""" % (ord(tile[0])+8)

  if 0 is ord(tile[2]):
    flags = "lda $62"
  else:
    flags = """lda.w #$%x
clc
adc $62
""" % ord(tile[2])

  if 0 is ord(tile[2]) & OAM_FORMAT_TILE:
    flags1 = "lda $60"
  else:
    flags1 = """lda.w #$%x
    clc
    adc $60
""" % (ord(tile[2]) & OAM_FORMAT_TILE)


  if 0 is ord(tile[2]) & (OAM_FORMAT_HFLIP | OAM_FORMAT_VFLIP):
    flags2 = "lda $64"
  else:
    flags2 = """lda.w #$%x
    clc
    adc $64""" % (ord(tile[2]) & (OAM_FORMAT_HFLIP | OAM_FORMAT_VFLIP))


  incFile.write("""\t
%s
    sta.w $1ca4+$%x,y
    and.w #$100
    ora.w #$200
    sta.w $217f
%s
    sta.w $1ca5+$%x,y
%s
    asl a
    tax
%s
    clc
    adc.l sprite32x32id.lut,x
    sta.w $1ca6+$%x,y
+    
""" % (xPos, counter*4,yPos,1+counter*4,flags1,flags2,2+counter*4))


def debugLog( data, message = '' ):
	logging.info( message )
	debugLogRecursive( data, '' )


def debugLogExit( data, message = '' ):
	logging.info( message )
	debugLogRecursive( data, '' )
	sys.exit()


def debugLogRecursive( data, nestStr ):
  nestStr += ' '
  if type( data ) is dict:
	logging.info( '%s dict{' % nestStr )	
	for k, v in data.iteritems():
	  logging.info( ' %s %s:' % tuple( [nestStr, k] ) )
	  debugLogRecursive( v, nestStr )
	logging.info( '%s }' % nestStr )

  elif type( data ) is list:
	logging.info( '%s list[' % nestStr )
	for v in data:
	  debugLogRecursive( v, nestStr )
	logging.info( '%s ]' % nestStr )

  else:
	if type( data ) is int:
	  logging.info( ' %s 0x%x %s ' % ( nestStr, data, type( data ) ) )
	else:
	  logging.info( ' %s "%s" %s' % ( nestStr, data, type( data ) ) )

def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in xrange(0, len(l), n):
        yield l[i:i+n]

def getByteList(data):
  if 0 == len(data):
    return ''
  else:
    return '.db %s' % ','.join([str(ord(byte)) for byte in data])

class Frame():
  def __init__(self, normal, big, options):
    self.tiles = [chr(ord(byte)) for byte in graconGfx.compress(normal[0] + big[0])] if options.get('isPacked') else normal[0] + big[0]
    self.allocLenTilesNormal = len(normal[0])
    self.allocLenTilesBig = len(big[0])

    logging.debug("tilemap len norm %s big %s" % (len(normal[1]), len(big[1])))
    #self.tilemap = [chr(ord(byte)) for byte in graconGfx.compress(normal[1])] if 'bg' == options.get('mode') else [chr(ord(byte)) for byte in self.compileSpriteTilemapCode(normal[1], big[1])]
    if 'bg' == options.get('mode'):
        self.tilemap = [chr(ord(byte)) for byte in graconGfx.compress(normal[1])]
        self.allocTilemapLength = len(normal[1])
        self.allocTilemapBigLength = 0
    elif options.get('compileTilemapCode'):
        self.tilemap = [chr(ord(byte)) for byte in self.compileSpriteTilemapCode(normal[1], big[1])]
        self.allocTilemapLength = len(normal[1])
        self.allocTilemapBigLength = len(big[1])
    else:
        self.tilemap = [chr(ord(byte)) for byte in normal[1] + big[1]]
        self.allocTilemapLength = len(normal[1])
        self.allocTilemapBigLength = len(big[1])
        if (FRAME_TILEMAP_NORMAL_MAX*4) < len(normal[1]):
          logging.error('sprite normal tilemap is %s entries long, but only %s are allowed maximum' % (len(normal[1])/4, FRAME_TILEMAP_NORMAL_MAX))
          sys.exit(1)
        if (FRAME_TILEMAP_BIG_MAX*4) < (len(big[1])):
          logging.error('sprite big tilemap is %s entries long, but only %s are allowed maximum' % (len(big[1])/4, FRAME_TILEMAP_BIG_MAX))
          sys.exit(1)

    self.mapNormal = normal[1]
    self.mapBig = big[1]
    self.xMapNormal = normal[2]
    self.xMapBig = big[2]

    #self.xTilemap = [chr(ord(byte)) for byte in graconGfx.compress(normal[2])] if 'bg' == options.get('mode') else [chr(ord(byte)) for byte in self.compileSpriteTilemapCode(normal[2], big[2])]
    if 'bg' == options.get('mode'):
        self.xTilemap = [chr(ord(byte)) for byte in graconGfx.compress(normal[2])]
    elif options.get('compileTilemapCode'):
        self.xTilemap = [chr(ord(byte)) for byte in self.compileSpriteTilemapCode(normal[2], big[2])]
    else:
        self.xTilemap = [chr(ord(byte)) for byte in normal[2] + big[2]]

    self.palette = normal[3]
    self.allocPaletteLength = len(normal[3])


  #required for sort, compare, hash
  def getLength(self):
    return FRAME_HEADER_SIZE + len(self.tiles + self.tilemap + self.xTilemap + self.palette)

  def compileSpriteTilemapCode(self, normal, big):
    lnkFile = open("build/lnk/sprite.lst", 'w')
    lnkFile.write("[objects]\nbuild/temp.o")
    lnkFile.close()
    srcFile = open("build/temp", 'w')
    srcFile.write('''
      .include "src/config/config.inc"

      ;zp-vars,just a reference
      .enum 0
        iterator INSTANCEOF iteratorStruct
        dimension INSTANCEOF dimensionStruct
        animation INSTANCEOF animationStruct
        oam INSTANCEOF oamStruct
      zpLen ds 0
      .ende

      .ramsection "oam buffer zp" bank 0 slot 6
        GLOBAL.oamBuffer INSTANCEOF oamSlot OAM_SLOTS
        GLOBAL.oamBuffer.end ds 0
        GLOBAL.oamBufferHi ds OAM_SLOTS
        GLOBAL.oamBufferHi.end ds 0
      .ends

      ;object class static flags, default properties and zero page 
      .define CLASS.FLAGS OBJECT.FLAGS.Present
      .define CLASS.PROPERTIES 0
      .define CLASS.ZP_LENGTH zpLen
      .define CLASS.IMPLEMENTS interface.dimension

/*
      .base BSL
      .bank STATIC.32X32_LUT >> 16
      .org 0
      .section "sprite32x32id.lut" force
        .include "src/object/sprite/32x32id.lut"
      .ends
*/
      ;crappy hack
      .def sprite32x32id.lut (STATIC.32X32_LUT | (BSL << 16))

      .base BSL
      .bank 0 slot 0      
    ''')

    counter = 0
    srcFile.write('.accu 16\n.index 16\n')
    for tile in chunks(big, 4):
      srcFile.write('\tGENERATE_SPRITE_BIG $%02x $%02x $%02x%02x $%02x \n' % (ord(tile[0]), ord(tile[1]), ord(tile[3]), ord(tile[2]), counter))
      counter += 1
    for tile in chunks(normal, 4):
      srcFile.write('\tGENERATE_SPRITE_NORMAL $%02x $%02x $%02x%02x $%02x \n' % (ord(tile[0]), ord(tile[1]), ord(tile[3]), ord(tile[2]), counter))
      counter += 1
    srcFile.write('\trtl\n')
    srcFile.close()

    try:
      subprocess.check_call(['wla-65816', '-o', 'build/temp', 'build/temp.o'])
      subprocess.check_call(['wlalink', '-b', 'build/lnk/sprite.lst', 'build/sprite.bin'])
    except subprocess.CalledProcessError as e:
      logging.error( 'Error while compiling sprite code.')
      sys.exit(1)

    binFile = open('build/sprite.bin', 'rb' )
    bindata = binFile.read()
    binFile.close()
    return bindata


if __name__ == "__main__":
	main()

