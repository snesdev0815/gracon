#!/usr/bin/env python2.7

__author__ = "Matthias Nagler <matt@dforce.de>"
__url__ = ("dforce3000", "dforce3000.de")
__version__ = "0.1"

'''
optimizations:
-flatten tile dict
  tile['data']
  
-flatten pixel arrays
  tile['data']['pixel']
  tile['data']['indexedPixel']
  

'''

'''
todo:
-check if images spanning multiple tilemaps have their tilemaps selected properly. probably not.
-have usage string if no parameter supplied or if parameter of unknown type found
'''

'''
convert graphics to snes bitplane format

options:
-bpp [1/2/4/8] (color depth mode, default: 4bpp)
-palnum [1-8] (maximum amount of palettes to allow, default: 1)
-mode [sprite|bg] (bg mode outputs tilemap, sprite mode outputs relative tilemap for 8x8 tiles)
-optimize [on|off] (don't rearrange tiles & don't output tilemap, default: on)
-transcol 0x[15bit transparent color] (every pixel having this color AFTER reducing image colordepth to snes 15bit format will be considered transparent. format: -bbbbbgg gggrrrrr default: 0x7C1F (pink))
-tilethreshold [int] (total difference in pixel color acceptable for two tiles to be considered the same. Cranking this value up potentially results in fewer tiles used in the converted image. this is meant to help identify parts of the image that may be optimized. default: 0)
-verify [on|off] (additionaly output converted image in png format(useful to verify that converted image looks fine)

possible input formats are: all supported by python Image module (png, gif, etc.)
input image alpha channel or transparency(gif/png) is dismissed completely. Relevant to transparent color of converted image is option -transcol" and nothing else.
image size will be padded to a multiple of tilesize and padded parts are filled with transparent color(palette color index 0).

format sprite tilemap (spritetilemap):
  x/y-offset relative to upper left corner of source image
  byte	0			1			2		3
		  cccccccc	vhopppcc	x-off	y-off
target format sprite tilemap:
  byte	0			1			2		3
		  x-off   y-off cccccccc	vhoopppN

  byte OBJ*4+0: xxxxxxxx
  byte OBJ*4+1: yyyyyyyy
  byte OBJ*4+2: cccccccc
  byte OBJ*4+3: vhoopppN

format bg tilemap:
  byte	0			1
		  cccccccc	vhopppcc
		  
directcolor mode:


'''

import os
import sys
import math
import time
import logging
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import graconUserOptions
import copy
import subprocess


logging.basicConfig( level=logging.ERROR, format='%(message)s')

MAX_COLOR_COUNT = 256
INFINITY = 1e300000
BG_TILEMAP_SIZE = 32
LOOKBACK_TILES = 128
NOISE_FACTOR = 700


def main():
  options = graconUserOptions.Options( sys.argv, {
	'bpp' 		: {
	  'value'			: 4,
	  'type'			: 'int',
	  'max'			: 8,
	  'min'			: 1
	  },
	'palettes'		: {
	  'value'			: 1,
	  'type'			: 'int',
	  'max'			: 8,
	  'min'			: 1
	  },
	'mode'		: {
	  'value'			: 'bg',
	  'type'			: 'str'
	  },
	'optimize'	: {
	  'value'			: True,
	  'type'			: 'bool'
	  },
    'directcolor'  : {
      'value'           : False,
      'type'            : 'bool'
      },	  
	'transcol'	: {
	  'value'			: 0xff00ff,
	  'type'			: 'hex',
	  'max'			: 0xffffff,
	  'min'			: 0x0
	  },
	'tilethreshold'	: {
	  'value'			: 1,
	  'type'			: 'int',
	  'max'			: 0xffff,
	  'min'			: 0
	  },	
	'verify'		: {
	  'value'			: False,
	  'type'			: 'bool'
	  },
    'partitionTilemap'        : {
      'value'           : False,
      'type'            : 'bool'
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
    'maxtiles' : {
      'value'           : 0x3ff,
      'type'            : 'int',
      'max'         : 0x3ff,
      'min'         : 0
      },	  
	'refpalette'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
	'infile'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
	'outfilebase'		: {
	  'value'			: '',
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
  'isPacked'        : {
    'value'           : False,
    'type'            : 'bool'
    },    
  'bigtilethreshold' : {  #number of empty tiles to allow when parsing big mode tiles (usually 32x32 sprites)
    'value'     : 2,
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
  'statictiles'        : {
    'value'           : False,
    'type'            : 'bool'
    },    
  'xMirrorTilemap'        : {
      'value'           : False,
      'type'            : 'bool'
    },
  'forcePalette'        : {
      'value'           : False,
      'type'            : 'bool'
    }
  })
  
  options.set('transcol', Color(getColorTuple(options.get('transcol'))))
    
  t0 = time.clock()

  if options.get('directcolor'):
    options.set('bpp', 8)
    options.set('palettes', 1)
  
  if not options.get('outfilebase'):
    options.set('outfilebase', options.get('infile'))
    
  inputImage = getInputImage( options, options.get('infile'))  
  tiles = parseTiles(inputImage, options)['normal']
  
  #lossy, gets global palette, but every color is in there only once
  optimizedPalette = fetchGlobalPaletteTileRelative(tiles, options)
  #lossless, gets global palette by merging down every palette of every tile as efficiently as possible. doesn't reduce color depth yet
  palettizedTiles = palettizeTiles( tiles, optimizedPalette, options )
  
  
  #stupid hack that ensures certain amount of tiles are never exceeded for any given picture
  adder = 10
  if options.get('optimize'):
    optimizedTiles = optimizeTilesNew( palettizedTiles, None, options )
    while len([tile for tile in optimizedTiles if tile['refId'] == None]) > options.get('maxtiles'):
      options.set('tilethreshold', options.get('tilethreshold') + adder)
      logging.info('maxtiles %s exceed, running again with threshold %s.' % (options.get('maxtiles'), options.get('tilethreshold')))
      optimizedTiles = optimizeTilesNew( palettizedTiles, None, options )
      adder = adder + (adder/2)
  else:
    optimizedTiles = palettizedTiles
    
  writeOutputFiles(optimizedTiles, optimizedPalette, inputImage, options)

  stats = Statistics(optimizedTiles, optimizedPalette, t0)
  logging.info('conversion complete, optimized from %s to %s tiles, %s palettes used. Wasted %s seconds' % (stats.totalTiles, stats.actualTiles, stats.actualPalettes, stats.timeWasted))

def debugLogTileStatus(tiles):
  for tile in tiles:
    debugLog({
      'id'  : tile['id'],
      'refId'  : tile['refId'],
      'xMirror'  : tile['xMirror'],
      'yMirror'  : tile['yMirror'],
    }, 'tile %s' % tile['id'])
  

def getReferencePaletteImage( options ):
	return getInputImageNoResolutionSet(options, options.get('refpalette')) if options.get('refpalette') else []

  
def writeOutputFiles(tiles, palettes, image, options):
  outTiles = augmentOutIds(tiles)
  outPalettes = augmentOutIds(palettes)
  
  tileFile = getOutputFile( options, ext='tiles' )
  [tileFile.write(char) for char in getTileWriteStream( outTiles, options )] 
  tileFile.close

  if not options.get('directcolor'):
    palFile = getOutputFile( options, ext='palette' )
    [palFile.write(char) for char in getPaletteWriteStream( outPalettes, options )] 
    palFile.close
    if options.get('verify'):
      writeSamplePalette(outPalettes, options)

  tilemapFile = getOutputFile( options, ext='tilemap' )
  tilemapStream = getSpriteTileMapStream(tiles, palettes, options, False, False) if options.get('mode') == 'sprite' else getBgTileMapStream(tiles, palettes, options, False, False)
  [tilemapFile.write(char) for char in tilemapStream] 
  tilemapFile.close
  
  if options.get('verify'):
	writeSampleImage(outTiles, outPalettes, image, options)


def augmentOutIds(elements):
  outElements = []
  outId = 0
  for element in elements:
	if element['refId'] == None:
	  element['outId'] = outId
	  outId += 1
	else:
	  element['outId'] = None
	outElements.append(element)
	
  return outElements

def writeSamplePalette(palettes, options):
  '''ugly hack, used to provide output sample w/o having to load the created files in an SNES program'''
  realPalettes = [pal for pal in palettes if pal['refId'] == None]
  sample = Image.new( "RGB", ( 2 ** options.get('bpp'), len(realPalettes) ), options.get('transcol').getPIL() )
  for yPos in range(len(realPalettes)):
	for xPos in range( 2 ** options.get('bpp') ):
	  try:
		  color = realPalettes[yPos]['color'][xPos]
	  except IndexError:
		  color = Color((0,0,0))
	  sample.putpixel((xPos,yPos), color.getPIL())
  outFileName = "%s.%s" % ( options.get('outfilebase'), 'palette.sample.png' )
  sample.save( outFileName, 'PNG' )


def writeSampleImage(tiles, palettes, image, options):
  '''ugly hack, used to provide output sample w/o having to load the created files in an SNES program'''
  sample = Image.new( "RGB", ( image['resolutionX'], image['resolutionY'] ), options.get('transcol').getPIL())
  for tile in tiles:
    tileConfig = fetchTileConfig( tile, tiles, palettes )
    if not options.get('directcolor'):
      tile['pixel'] = tiles[tileConfig['tileId']]['indexedPixel']	#hack, copy pixels of referenced tile into current tile

    actualTile = mirrorTile( tile, { 'x' : tileConfig['xMirror'], 'y' : tileConfig['yMirror'] } )
    actualPalette = palettes[tileConfig['palId']]
    for yPos in range(len(actualTile['pixel'])):
      for xPos in range(len(actualTile['pixel'][yPos])):
        if options.get('directcolor'):
          pixel = actualTile['pixel'][yPos][xPos]
        else:
          colorIndex = actualTile['pixel'][yPos][xPos]
          pixel = actualPalette['color'][colorIndex]
        pixelPos = (actualTile['x']+xPos, actualTile['y']+yPos)
        sample.putpixel(pixelPos,pixel.getPIL())
  outFileName = "%s.%s" % ( options.get('outfilebase'), 'image.sample.png' )
  sample.save( outFileName, 'PNG' )

def writeSampleTileset(tiles, palettes, image, options):
  '''ugly hack, used to provide output sample w/o having to load the created files in an SNES program'''
  sample = Image.new( "RGB", ( image['resolutionX'], image['resolutionY'] ), options.get('transcol').getPIL() )
  for tile in tiles:
    if tile['refId'] == None:
      tileConfig = fetchTileConfig( tile, tiles, palettes )
      if not options.get('directcolor'):
        tile['pixel'] = tiles[tileConfig['tileId']]['indexedPixel'] #hack, copy pixels of referenced tile into current tile

      actualTile = mirrorTile( tile, { 'x' : tileConfig['xMirror'], 'y' : tileConfig['yMirror'] } )
      actualPalette = palettes[tileConfig['palId']]
      for yPos in range(len(actualTile['pixel'])):
        for xPos in range(len(actualTile['pixel'][yPos])):
          if options.get('directcolor'):
            pixel = actualTile['pixel'][yPos][xPos]
          else:
            colorIndex = actualTile['pixel'][yPos][xPos]
            pixel = actualPalette['color'][colorIndex]
          pixelPos = (actualTile['x']+xPos, actualTile['y']+yPos)
          sample.putpixel(pixelPos,pixel.getPIL())
  outFileName = "%s.%s" % ( options.get('outfilebase'), 'tileset.sample.png' )
  sample.save( outFileName, 'PNG' )


def parseTiles(image, options, frameID=0):
  return parseSpriteTiles(image, options, frameID) if options.get('mode') == 'sprite' else parseBgTiles(image, options, frameID)


def writeTileMap(tiles, palettes, options):
  if options.get('mode') == 'sprite':
    writeSpriteTileMap(tiles, palettes, options)
  else:
    writeBgTileMapStraight(tiles, palettes, options)
  
#writes 32x32 blocks of tilemaps. useful if static image spanning multiple tilemaps should go directly to snes vram, but pretty useless for streaming (i.e. levels)
def writeBgTileMap(tiles, palettes, options):
  '''writes successive blocks of 32x32 tile tilemaps'''
  bgTilemaps = getBgTilemaps(tiles, palettes, options)
  outFile = getOutputFile( options, ext='tilemap' )
  for tile in [tile for tilemap in bgTilemaps for tile in tilemap]:
	outFile.write( chr( tile & 0xff ) )
	outFile.write( chr( (tile & 0xff00) >> 8 ) )
  outFile.close()

  
def getBgTileMapStreamGlobal(tiles, globalTiles, palettes, options, xMirror):
  resolutionX = options.get('resolutionx')/options.get('tilesizex')
  resolutionY = options.get('resolutiony')/options.get('tilesizey')
  emptyTile = getEmptyTileConfig(globalTiles, palettes)
  logging.debug("resolution: %s x %s " % (resolutionX, resolutionY))
  if options.get('partitionTilemap'):    
    screensize = 0x400
    if resolutionY > 32:
      screensize = screensize*2
    elif resolutionX > 32:
      screensize = screensize*2
    else:
      screensize = 0x400
  else:
    screensize = resolutionX * resolutionY
  bgTilemap = [emptyTile['concatConfig'] for i in range(screensize)]
  for tile in tiles:
    tilePosX = int(math.floor(tile['x'] / options.get('tilesizex')))
    tilePosY = int(math.floor(tile['y'] / options.get('tilesizey')))
    tileConfig = fetchTileConfig( tile, globalTiles, palettes )['concatConfig']
    if options.get('partitionTilemap'):
      partition = 0
      if resolutionX > 32 and resolutionY > 32:
        if tilePosX > 31:
          partition = partition + 0x400
        if tilePosY > 31:
          partition = partition + 0x800        
      else:
        if tilePosX > 31:
          partition = partition + 0x400
        if tilePosY > 31:
          partition = partition + 0x400
        
      bgTilemap[(tilePosX & 0x1f) + ((tilePosY & 0x1f) * 32) + partition] = tileConfig
    else:
      bgTilemap[tilePosX + (tilePosY * resolutionX)] = tileConfig
    
  stream = []
  for tile in bgTilemap:
    stream.append( chr( tile & 0xff ) )
    stream.append( chr( (tile & 0xff00) >> 8 ) )
  return stream
  
  
def getBgTileMapStream(tiles, palettes, options, xMirror, yMirror):
  '''writes single tilemap with dimensions of input image. useful for streaming'''

  resolutionX = options.get('resolutionx')/options.get('tilesizex')
  resolutionY = options.get('resolutiony')/options.get('tilesizey')
  emptyTile = getEmptyTileConfig(tiles, palettes)
  logging.debug("resolution: %s x %s " % (resolutionX, resolutionY))
  if options.get('partitionTilemap'):    
    screensize = 0x400
    if resolutionY > 32:
      screensize = screensize*2
    elif resolutionX > 32:
      screensize = screensize*2
    else:
      screensize = 0x400
  else:
    screensize = resolutionX * resolutionY
  bgTilemap = [emptyTile['concatConfig'] for i in range(screensize)]
  for tile in tiles:
    tilePosX = int(math.floor(tile['x'] / options.get('tilesizex')))
    tilePosY = int(math.floor(tile['y'] / options.get('tilesizey')))
    tileConfig = fetchTileConfig( tile, tiles, palettes )['concatConfig']
    if options.get('partitionTilemap'):
      partition = 0
      if resolutionX > 32 and resolutionY > 32:
        if tilePosX > 31:
          partition = partition + 0x400
        if tilePosY > 31:
          partition = partition + 0x800        
      else:
        if tilePosX > 31:
          partition = partition + 0x400
        if tilePosY > 31:
          partition = partition + 0x400
        
      bgTilemap[(tilePosX & 0x1f) + ((tilePosY & 0x1f) * 32) + partition] = tileConfig
    else:
      bgTilemap[tilePosX + (tilePosY * resolutionX)] = tileConfig
    
  stream = []
  for tile in bgTilemap:
    stream.append( chr( tile & 0xff ) )
    stream.append( chr( (tile & 0xff00) >> 8 ) )
  return stream


def getBgTilemaps(tiles, palettes, options):
  emptyTile = getEmptyTileConfig(tiles, palettes)
  bgTilemaps = [[emptyTile['concatConfig'] for i in range(BG_TILEMAP_SIZE * BG_TILEMAP_SIZE)] for i in range(getCurrentTilemap(options.get('resolutionx'), options.get('resolutiony'), options) + 1)]
  for tile in tiles:
    mapId = getCurrentTilemap(tile['x'], tile['y'], options)
    tilePos = getPositionInTilemap(tile['x'], tile['y'], options)
    tileConfig = fetchTileConfig( tile, tiles, palettes )['concatConfig']

    try:
      bgTilemaps[mapId][tilePos] = tileConfig
    except IndexError:
      logging.error( 'invalid tilemap access in getBgTilemaps, mapId: %s, tilePos: %s' % (mapId, tilePos) )
  return bgTilemaps


def getEmptyTileConfig(tiles, palettes):
  '''scans for empty tile, returns fake value if none found '''
  '''todo, do we really need an additional empty tile here sometimes?'''
  emptyTiles = [tile for tile in tiles if tileIsEmpty(tile)]
  try:
	return fetchTileConfig( emptyTiles.pop(), tiles, palettes )
  except IndexError:
	return { 'concatConfig': 0 }
	
	
def tileIsEmpty(tile):
  if tile['refId'] != None:
	return False
  for pixel in [pixel for scanline in tile['indexedPixel'] for pixel in scanline]:
	if pixel != 0:
	  return False
  return True


def getPositionInTilemap(xPos, yPos, options):
  xTilePos = int(math.floor((xPos / options.get('tilesizex')) % BG_TILEMAP_SIZE))
  yTilePos = int(math.floor((yPos / options.get('tilesizey')) % BG_TILEMAP_SIZE))
  return (BG_TILEMAP_SIZE * yTilePos) + xTilePos


def getCurrentTilemap(xPos, yPos, options):
  return int(math.floor(xPos / float(BG_TILEMAP_SIZE * options.get('tilesizex'))) * math.floor(yPos / float(BG_TILEMAP_SIZE * options.get('tilesizey'))))


def getSpriteTileMapStreamGlobal( tiles, globalTiles, palettes, options, xMirror, yMirror ):
  options.get('resolutionx')
  stream = []
  for tile in tiles:
    tileConfig = fetchSpriteTileConfig( tile, globalTiles, palettes, options )
    concatInfo = tileConfig['concatConfig']
    if xMirror:
      concatInfo = concatInfo ^ (1 << 14)
    if yMirror:
      concatInfo = concatInfo ^ (1 << 15)

    posX = max(options.get('resolutionx')-tileConfig['x']-(tileConfig['sizemultiplier']*options.get('tilesizex')),0) if xMirror == True else tileConfig['x']
    posY = max(options.get('resolutiony')-tileConfig['y']-(tileConfig['sizemultiplier']*options.get('tilesizey')),0) if yMirror == True else tileConfig['y']
    stream.append( chr( posX & 0xff) )
    stream.append( chr( posY & 0xff ) )
    stream.append( chr( concatInfo & 0xff ) )
    stream.append( chr( (concatInfo & 0xff00) >> 8 ) )

  return stream
  
def getSpriteTileMapStream( tiles, palettes, options, xMirror, yMirror ):
  stream = []
  for tile in tiles:
    tileConfig = fetchSpriteTileConfig( tile, tiles, palettes, options )
    concatInfo = tileConfig['concatConfig']
    if xMirror:
      concatInfo = concatInfo ^ (1 << 14)
    if yMirror:
      concatInfo = concatInfo ^ (1 << 15)

    posX = max(options.get('resolutionx')-tileConfig['x']-(tileConfig['sizemultiplier']*options.get('tilesizex')),0) if xMirror == True else tileConfig['x']
    posY = max(options.get('resolutiony')-tileConfig['y']-(tileConfig['sizemultiplier']*options.get('tilesizey')),0) if yMirror == True else tileConfig['y']
    stream.append( chr( posX & 0xff) )
    stream.append( chr( posY & 0xff ) )
    stream.append( chr( concatInfo & 0xff ) )
    stream.append( chr( (concatInfo & 0xff00) >> 8 ) )

  return stream



def writeSpriteTileMap( tiles, palettes, options ):
  outFile = getOutputFile( options, ext='spritemap' )
  for tile in tiles:
	tileConfig = fetchSpriteTileConfig( tile, tiles, palettes, options )
	outFile.write( chr( tileConfig['concatConfig'] & 0xff ) )
	outFile.write( chr( (tileConfig['concatConfig'] & 0xff00) >> 8 ) )
	outFile.write( chr( tileConfig['x'] & 0xff ) )
	outFile.write( chr( tileConfig['y'] & 0xff ) )
  outFile.close()


def fetchTileConfig( tile, tiles, palettes ):
  actualTile = fetchActualTile( tiles, tile['id'], False, False )

  #this is what it was before, and this produced bad palette ids for bg tiles in JPR. when using actualTile, everything was fine. Maybe there are cases where one or the other is correct?
  #I think the problem is that palette must be referenced across multiple tiles...
  actualPaletteTile = fetchActualPaletteTile( tiles, tile['id'] )
  actualPalette = fetchActualEntity( palettes, actualPaletteTile['palette']['id'] )

  x = 1 if actualTile['xMirror'] else 0
  y = 1 if actualTile['yMirror'] else 0
  return {
	'x' : tile['x'],
	'y' : tile['y'],
	'xMirror' : actualTile['xMirror'],
	'yMirror' : actualTile['yMirror'],
	'tileId' : actualTile['id'],
	'palId' : actualPalette['id'],
	'tileOutId' : actualTile['outId'],
	'palOutId' : actualPalette['outId'],	
	'concatConfig' : (y << 15) | (x << 14) | ((actualPalette['outId'] & 0x7) << 10) | (actualTile['outId'] & 0x3ff)
  }


def fetchSpriteTileConfig( tile, tiles, palettes, options ):
  actualTile = fetchActualTile( tiles, tile['id'], False, False )
  actualPalette = fetchActualEntity( palettes, actualTile['palette']['id'] )
  
  #this is for big tiles, 32x32 etc.
  idMultiplier = int(math.sqrt(len(tile['pixel']) / options.get('tilesizey')))
  if 0 == idMultiplier:
    idMultiplier = 1
  priority = 0x0
  x = 1 if tile['xMirror'] else 0
  y = 1 if tile['yMirror'] else 0
  return {
	'x' : tile['x'],
	'y' : tile['y'],
  'sizemultiplier' : idMultiplier, 
	'xMirror' : tile['xMirror'],
	'yMirror' : tile['yMirror'],
	'tileId' : actualTile['id'] * idMultiplier,
	'palId' : actualPalette['id'],
	'tileOutId' : actualTile['outId'],
	'palOutId' : actualPalette['outId'],	
	'concatConfig' : (y << 15) | (x << 14) | (priority << 12) | ((actualPalette['outId'] & 0x7) << 9) | (actualTile['outId'] & 0x1ff)
  }

def writeTiles( tiles, options ):
  outFile = getOutputFile( options, ext='tiles' )
  for tile in tiles:
    if tile['refId'] == None:
      writeBitplaneTile( outFile, tile, options )
  outFile.close()


def writeBitplaneTile( outFile, tile, options ):
  bitplanes = fetchBitplanes( tile, options )
  for i in range( 0, len( bitplanes ), 2 ):
    while bitplanes[i].notEmpty():
      outFile.write( chr( bitplanes[i].first() ) )
      outFile.write( chr( bitplanes[i+1].first() ) )


def getTileWriteStream( tiles, options ):
  stream = []
  partitioned = []
  target = 'pixel' if options.get('directcolor') else 'indexedPixel' 
  slices = [item for sublist in [chunks(scanline, 8) for tile in tiles for scanline in tile[target] if tile['refId'] == None] for item in sublist]
  #pp.pprint(slices)
  targetLength = len(slices)/8
  if 16 == options.get('tilesizey') and (targetLength & 0x7f) != 0:
    targetLength += 0x80

  for i in range(targetLength):
    tile = []
    for y in range(8):      
      src = i*8+y
      if 16 == options.get('tilesizex'):
        #barrel shift left lower 4 bits if tilewidth = 16
        src = (src & 0xFFF0) | ((src & 0x7) << 1) | ((src & 0x8) >> 3)
      if 16 == options.get('tilesizey'):
        #barrel shift left next 4 bits if tileheight = 16
        src = (src & 0xFF0F) | ((src & 0x70) << 1) | ((src & 0x80) >> 3)
        
      #pp.pprint('src $%03x -> $%03x' % (i*8+y, src))
      #pp.pprint(slices[src])
      try:
        tile.append(slices[src])
      except IndexError:
        tile.append([0,0,0,0,0,0,0,0])
    partitioned.append(tile)
    
  #pp.pprint(('tiles', partitioned))
  for tile in partitioned:
    bitplanes = fetchBitplanes2( tile, options )
    for i in range( 0, len( bitplanes ), 2 ):
      while bitplanes[i].notEmpty():
        stream.append(( chr( bitplanes[i].first() ) ))
        stream.append(( chr( bitplanes[i+1].first() ) ))
  return stream

def fetchBitplanes2( tile, options ):
  bitplanes = []
  for bitPlane in range( options.get('bpp') ):
    bitplaneTile = BitStream()
    for pixel in [pixel for scanline in tile for pixel in scanline]:
      bitplaneTile.writeBit( pixel >> bitPlane )
    bitplanes.append( bitplaneTile )
  return bitplanes

def getPaletteWriteStream( palettes, options ):
  stream = []
  for color in [pixel for palette in [palette for palette in palettes if palette['refId'] == None] for pixel in palette['color']]:
    stream.append(chr((color.getSNES() & 0xff)))
    stream.append(chr((color.getSNES() & 0xff00) >> 8 ))
  return stream


def fetchBitplanes( inputTile, options ):
  bitplanes = []
  target = 'pixel' if options.get('directcolor') else 'indexedPixel' 
  for tile in [inputTile[target]]:
    for bitPlane in range( options.get('bpp') ):
      bitplaneTile = BitStream()
      for pixel in [pixel for scanline in tile for pixel in scanline]:
        bitplaneTile.writeBit( pixel >> bitPlane )
      bitplanes.append( bitplaneTile )
  return bitplanes


def chunks(l, n):
    return [l[i:i+n] for i in range(0, len(l), n)]  
  
def writePalettes( palettes, options ):
  outFile = getOutputFile( options, ext='palette' )
  for color in [pixel for palette in [palette for palette in palettes if palette['refId'] == None] for pixel in palette['color']]:
    outFile.write(chr((color.getSNES() & 0xff)))
    outFile.write(chr((color.getSNES() & 0xff00) >> 8 ))
  outFile.close()


def getOutputFile( options, ext ):
  outFileName = "%s.%s" % ( options.get('outfilebase'), ext )
  try:
	outFile = open( outFileName, 'wb' )
  except IOError:
	logging.error( 'unable to access output file %s' % outFileName )
	sys.exit(1)
  return outFile


def palettizeTiles( tiles, palettes, options ):
  '''replaces direct tile colors with best-matching entries of assigned palette'''
  return [(tile if tile['refId'] != None else palettizeTile( tile, palettes, options )) for tile in tiles]


def findOptimumTilePalette(palettes, pixels):
  optimumPalette = { 'error' : INFINITY }
  for palette in [pal for pal in palettes if pal['refId'] == None]:
	squareError = 0
	for similarColor in [getSimilarColor( pixel, palette['color'] ) for scanline in pixels for pixel in scanline]:
		squareError += similarColor['error'] * similarColor['error']
	palette['error'] = math.sqrt(squareError)
	optimumPalette = palette if palette['error'] < optimumPalette['error'] else optimumPalette
  return optimumPalette


def palettizeTile( tile, palettes, options ):
  palette = findOptimumTilePalette(palettes, tile['pixel'])

  indexedScanlines = []
  scanlines = []

  for scanline in tile['pixel']:
    indexedPixels = []
    pixels = []
    for pixel in scanline:
      similarColor = getSimilarColor( pixel, palette['color'] )
      if options.get('forcePalette') and (similarColor['error'] != 0):
        maxi = 0
        indexedPixels.append(maxi)
        pixels.append(palette['color'][maxi])
      else:
        indexedPixels.append( palette['color'].index(similarColor['value']) )
        pixels.append(similarColor['value'])
    scanlines.append(pixels)
    indexedScanlines.append(indexedPixels)
  return {
	'indexedPixel'	: indexedScanlines,
	'pixel'			: scanlines,
  'pixhash'       : hash(str(scanlines)),
	'pixhashindexed'       : hash(str(indexedScanlines)),
	'palette'			: {
	  'color'				: [],
	  'id'				: palette['id'],
	  'refId'				: None
	},
	'id'			: tile['id'],
	'refId'			: tile['refId'],
	'x'				: tile['x'],
	'y'				: tile['y'],
	'xMirror'		: tile['xMirror'],
	'yMirror'		: tile['yMirror']
  }


def fetchActualTile( entities, entityId, xStatus, yStatus ):
  if entities[entityId]['refId'] == None:
    tile = entities[entityId]
    tile['xMirror'] = xStatus
    tile['yMirror'] = yStatus
    return tile
  else:
    return fetchActualTile( entities, entities[entityId]['refId'], entities[entityId]['xMirror'] ^ xStatus, entities[entityId]['yMirror'] ^ yStatus )

def fetchActualPaletteTile(entities, entityId):
  return entities[entityId] if entities[entityId]['palette']['refId'] == None else fetchActualPaletteTile( entities, entities[entityId]['palette']['refId'] )

def fetchActualEntity( entities, entityId ):
  return entities[entityId] if entities[entityId]['refId'] == None else fetchActualEntity( entities, entities[entityId]['refId'] )

def parseGlobalPalettes( tiles, options ):
  globalPalette = fetchGlobalPalette(tiles, options)
  
  while(len(globalPalette) > (((options.get('bpp') ** 2) - 1) * options.get('palettes'))):
	nearestIndices = getNearestPaletteIndices( globalPalette )
	globalPalette.pop( max( nearestIndices['id1'], nearestIndices['id2'] ) )
  return partitionGlobalPalette(globalPalette, options)

def partitionGlobalPalette(palettes, options):
  partitionedPalettes = []
  paletteCount = int(math.ceil(len(palettes)/float(((options.get('bpp') ** 2) - 1))))
  for palIndex in range(paletteCount):
	palette = []
	palette.append(options.get('transcol'))
	for colorIndex in range((options.get('bpp') ** 2) - 1):
	  try:
		palette.append(palettes.pop(0))
	  except IndexError:
		palette.append(Color((0,0,0)))
	  
	partitionedPalettes.append({
	  'color' : palette,
	  'refId'	: None,
	  'id'	: palIndex
	})
  return partitionedPalettes

def partitionGlobalPalette2(palettes, options):
  partitionedPalettes = []
  palIndex = 0
  for palette in palettes:
    paletteList = []
    paletteList.append(options.get('transcol'))
    for colorIndex in range((options.get('bpp') ** 2) - 1):
      try:
        paletteList.append(palette[colorIndex])
      except IndexError:
        paletteList.append(Color((0,0,0)))
      
    partitionedPalettes.append({
      'color' : paletteList,
      'refId'   : None,
      'id'  : palIndex
    })
    palIndex += 1
    
  return partitionedPalettes

def fetchGlobalPaletteReference(palettes, options):
  partitionedPalettes = []
  palIndex = 0
  for palette in palettes:
    paletteList = []
    for colorIndex in range((options.get('bpp') ** 2) ):
      try:
        paletteList.append(palette[colorIndex])
      except IndexError:
        paletteList.append(Color((0,0,0)))
      
    partitionedPalettes.append({
      'color' : paletteList,
      'refId'   : None,
      'id'  : palIndex
    })
    palIndex += 1
    
  return partitionedPalettes
  
def fetchGlobalPalette(tiles, options):
  refPaletteImg = getReferencePaletteImage(options)
  if refPaletteImg:
    return [pixel for scanline in refPaletteImg['pixels'] for pixel in scanline if pixel.getRGB() != options.get('transcol').getRGB()]
  else:
    return sorted([color for color in set([color for tile in tiles for color in tile['palette']['color'] if color.getRGB() != options.get('transcol').getRGB()])],sortColors)


def fetchGlobalPaletteTileRelative(tiles, options):
  logging.debug("palette fetch start")
  refPaletteImg = getReferencePaletteImage(options)  
  if refPaletteImg:
    return fetchGlobalPaletteReference(refPaletteImg['pixels'], options)
  else:
    palettes = set(reducePaletteColorDepth( tile['palette']['color'], options ) for tile in tiles)
    mergedPalettes = palettes.copy()
    
    logging.debug("done merging")
    newPalettes = removeRedundantPalettes(mergedPalettes, options)
    logging.debug("done removing redundant")

    newPalettes = mergeMatchingPalettes(newPalettes, options)
    logging.debug("done merging 2")

    while len(mergedPalettes) != len(newPalettes):
      logging.debug("retry lossless merge, palette size now %s, old one was %s" % (len(newPalettes), len(mergedPalettes)))
      mergedPalettes = newPalettes.copy()
      newPalettes = mergeMatchingPalettes(mergedPalettes, options)
    logging.debug("done reducing lossless")

    start = time.time()        
    newPalettes = mergeDownPaletteNew(newPalettes, options)
    logging.debug(("done reducing lossy", time.time() - start))

    part = partitionGlobalPalette2(newPalettes, options)
    logging.debug("palette done")
    return part

    
def removeRedundantPalettes(palettes, options):
  newPalettes = palettes.copy()
  maxlength = 2**options.get('bpp')
  for palette in palettes:
    for refPalette in [ref for ref in palettes if ref is not palette]:
      currentPalette = set(palette)
      referencePalette = set(refPalette)
      #continue here, remove all palettes contained in others
      if currentPalette.issubset(referencePalette):
        newPalettes.remove(palette)
        break

  #if everything was a subset of anything (1 different palette total), add longest entry in original palette
  biggestTilePalette = set()
  if 0 == len(newPalettes):
    for palette in palettes:
      if len(palette) > len(biggestTilePalette):
        biggestTilePalette = palette
    newPalettes.add(biggestTilePalette)
    
  return newPalettes
  
def mergeMatchingPalettes(palettes, options):
  newPalettes = palettes.copy()
  maxLength = 2**options.get('bpp')

  for palette in palettes:
    bestMatchLength = maxLength
    bestMatchRef = None
    for refPalette in [ref for ref in palettes if ref is not palette]:
      mergedPalette = tuple(set(refPalette+palette))

      if len(mergedPalette) < bestMatchLength and palette in newPalettes and refPalette in newPalettes:
        bestMatchLength = len(mergedPalette)
        bestMatchRef = refPalette
    if bestMatchRef:
      mergedPalette = tuple(set(bestMatchRef+palette))
      newPalettes.remove(palette)
      newPalettes.remove(bestMatchRef)
      newPalettes.add(mergedPalette)

  return set(newPalettes)

def mergeDownPalette(palettes, options):
  newPalettes = palettes.copy()
  maxLength = (2**options.get('bpp'))*2
  bestMatchLength = maxLength
  bestMatchRef = None
  bestMatchPal = None
  
  for palette in palettes:
    for refPalette in [ref for ref in palettes if ref is not palette]:
      mergedPalette = tuple(set(refPalette+palette))

      if len(mergedPalette) < bestMatchLength and palette in newPalettes and refPalette in newPalettes:
        bestMatchLength = len(mergedPalette)
        bestMatchRef = refPalette
        bestMatchPal = palette
  if bestMatchRef and bestMatchRef:
    mergedPalette = tuple(set(bestMatchRef+bestMatchPal))
    newPalettes.remove(bestMatchPal)
    newPalettes.remove(bestMatchRef)
    newPalettes.add(reducePaletteColorDepth(list(mergedPalette), options))

  return set(newPalettes)
  
def mergeDownPaletteNew(palettes, options):
  palettes = list(palettes)
  maxLength = (2**options.get('bpp'))*2
  while len(palettes) > options.get('palettes'):
    print("retry lossy merge, palette size now %s" % len(palettes))
    bestMatchLength = maxLength
    bestA = None
    bestB = None
    
    for t in ((i, j, len(set(palettes[i]+palettes[j]))) for i in range(len(palettes)) for j in range(len(palettes)) if j > i):
      if t[2] < bestMatchLength:
        bestMatchLength = t[2]
        bestA = t[0]
        bestB = t[1]

    if bestA is not None and bestB is not None:
      palettes.append(reducePaletteColorDepth(list(set(palettes[bestA]+palettes[bestB])), options))
      palettes[bestA] = None
      palettes[bestB] = None
    else:
      print("unable to reduce, palette size now %s" % len(palettes))
      sys.exit(1)

    palettes = [x for x in palettes if x is not None]

  return set(palettes)
  
def checkPaletteCount( palettes, options):
  palCount = len( [pal for pal in palettes if pal['refId'] == None] )
  if ( palCount > options.get('palettes') ):
	logging.error( 'Image needs %s palettes, exceeds allowed amount of %s.' % ( palCount, options.get('palettes') ) )
	sys.exit(1)
    

def optimizePalettes( palettes, options ):
  return [getNearestPalette( palette, palettes, options ) for palette in palettes]
  

def getPaletteById(palettes, palId):
  for palette in [pal for pal in palettes if pal['id'] == palId]:
	return palette
  logging.error( 'Unable find palette id %s in getPaletteById.' % palId )
  sys.exit(1)
  

def getSimilarPalette( inputPalette, refPalette ):
  squareError = 0
  for color in inputPalette['color']:
	similarColor = getSimilarColor( color, refPalette['color'] )
	squareError += similarColor['error'] * similarColor['error']
  return {
	'color' : [],#colors,
	'refId'	: refPalette['id'],
	'id'	: inputPalette['id'],
	'error'	: math.sqrt( squareError )
  }


def getSimilarColor( color, refPalette ):
  minError = {
	'error'	: INFINITY,
	'value'	: None
  }
  for refColor in refPalette:
	diff = compareColors( color, refColor )
	minError = minError if minError['error'] < diff else {
	  'error'	: diff,
	  'value'	: refColor
	}
  return minError


def getSimilarColorIndex( color, refPalette ):
  similarColor = getSimilarColor( color, refPalette )
  return refPalette.index( similarColor['value'] )
  
def reducePaletteColorDepth( palette, options ):
  while len( palette ) >= (2**options.get('bpp')):
    nearestIndices = getNearestPaletteIndices( palette )
    palette.pop( max( nearestIndices['id1'], nearestIndices['id2'] ) )

  palette = set(palette)
  if options.get('transcol') in palette:
    palette.remove(options.get('transcol'))
  return tuple(palette)

  
def getNearestPaletteIndices( palette ):
  diffTable = {}
  for i in range( 1, len( palette ) ):
    for iRef in range( 1, len( palette ) ):
      if i != iRef:
        diffIndex = "%s-%s" % ( min( i, iRef ), max( i, iRef ) )
        diffTable[diffIndex] = {
          'difference'	: compareColors( palette[i], palette[iRef] ),
          'id1'			: i,
          'id2'			: iRef
        }
  return getMinDifferenceIds( diffTable )


def getMinDifferenceIds( diffTable ):
  minDiff = { 'difference' : INFINITY }
  for diffName, diff in diffTable.iteritems():
	minDiff = diff if diff['difference'] < minDiff['difference'] else minDiff
  return minDiff

def tilesLengthCheck(tiles, options):
  returnSize = len([tile for tile in tiles if tile['refId'] == None])
  if returnSize > options.get('maxtiles'):
    logging.error('maxtiles %s exceed, got %s.' % (options.get('maxtiles'), returnSize))
    sys.exit(1)
  return tiles

def getDiffErr(tr, tg, tb, rr, rg, rb):
  return (((512+((tr+rr) / 2))*(tr-rr)*(tr-rr))>>8) + 4*(tg-rg)*(tg-rg) + (((767-((tr+rr) / 2))*(tb-rb)*(tb-rb))>>8)

def getTileDiffErr(bestErr, tile, ref):
  error = 0  
  for p in range(len(tile)):
    error += getDiffErr(tile[p][0],tile[p][1],tile[p][2], ref[p][0],ref[p][1],ref[p][2])
    if error > bestErr:
      break
  return error

def optimizeTilesNewHash( tiles, refTiles, options ):
  logging.debug("optimizeTilesNewHash")
  refhashes = {hash(str(item['indexedPixel'] if hasattr(item, 'indexedPixel') else item['pixel'])):item for sublist in [mirrorTiles(tile) for tile in refTiles] for item in sublist}

  for i in range(len(tiles)):
    try:
      match = refhashes[hash(str(tiles[i]['indexedPixel'] if hasattr(tiles[i], 'indexedPixel') else tiles[i]['pixel']))]
      if tiles[i]['id'] != match['id']:
        tiles[i]['refId'] = match['id']
        tiles[i]['xMirror'] = match['xMirror']
        tiles[i]['yMirror'] = match['yMirror']
    except KeyError:
      pass
  return tiles

def optimizeTilesNew( tiles, refTiles, options ):
  if not options.get('optimize'):
      return tiles

  if None is refTiles:
    refTiles = tiles
    chooseLessNoisy = True
  else:
    chooseLessNoisy = False

  if 0 is options.get('tilethreshold'):
    return optimizeTilesNewHash( tiles, refTiles, options )

  logging.debug("optimizeTilesNew")
  start = time.time()
  refpx = [(item['id'], [(pixel.r,pixel.g,pixel.b) for sublist in item['pixel'] for pixel in sublist], hash(str(item['indexedPixel'] if hasattr(item, 'indexedPixel') else [] ))) for item in refTiles if item['refId'] == None]
  px = [(item['id'],item['xMirror'],item['yMirror'], [(pixel.r,pixel.g,pixel.b) for sublist in item['pixel'] for pixel in sublist], hash(str(item['indexedPixel']))) for sublist in [mirrorTiles(tile) for tile in tiles] for item in sublist]
  logging.debug(("now converting", len(tiles), len(refTiles)))

  currID = -1
  for t in range(len(px)):
    if currID != px[t][0]:
      bestErr = INFINITY
    currID = px[t][0]
    currIdRelative = currID - tiles[0]['id']

    bestId = None
    bestX = False
    bestY = False
    for rr in range(len(refpx)):
      if currID != refpx[rr][0] and refTiles[refpx[rr][0]]['refId'] is None:
        error = getTileDiffErr(bestErr, px[t][3], refpx[rr][1])
        if error <= bestErr:
          bestErr = error
          bestId = refpx[rr][0]
          bestX = px[t][1]
          bestY = px[t][2]
    if math.sqrt(bestErr) < options.get('tilethreshold') and bestId != None:
      tiles[currIdRelative]['refId'] = bestId
      tiles[currIdRelative]['palette']['refId'] = bestId
      tiles[currIdRelative]['xMirror'] = bestX
      tiles[currIdRelative]['yMirror'] = bestY

  logging.debug(("done converting", time.time() - start))
  return tiles
  
def mirrorTiles( tile):
  return [
	tile,
	mirrorTile( tile, { 'x' : True, 'y' : False } ),
	mirrorTile( tile, { 'x' : False, 'y' : True } ),
	mirrorTile( tile, { 'x' : True, 'y' : True } ),
  ]


def mirrorTile( tile, config ):
  mirrorTile = []
  mirrorTileIndexed = []
  verticalRange = range( len( tile['pixel'] )-1, 0-1, -1 ) if config['y'] else range( len( tile['pixel'] ) )
  for yPos in verticalRange:
    horizontalRange = range( len( tile['pixel'][yPos] )-1, 0-1, -1 ) if config['x'] else range( len( tile['pixel'][yPos] ) )
    mirrorTile.append( [tile['pixel'][yPos][xPos] for xPos in horizontalRange] )
    if hasattr(tile, 'indexedPixel'):
      mirrorTileIndexed.append( [tile['indexedPixel'][yPos][xPos] for xPos in horizontalRange] )
        
  return {
	'id'		: tile['id'],
	'pixel'		: mirrorTile,
	'indexedPixel' : mirrorTileIndexed,
  'pixhash'     : hash(str(mirrorTile)),
	'pixhashindexed'     : hash(str(mirrorTileIndexed)),
	'palette'		: tile['palette'],
	'x'			: tile['x'],
	'y'			: tile['y'],
	'refId'		: None,
	'xMirror'	: config['x'],
	'yMirror'	: config['y']
  }

def sortColors(color1, color2):
  return -1 if color1.getHue() - color2.getHue() < 0 else 1

def compareColors( color1, color2 ):
  redMean = color1.r + color2.r / 2
  r = color1.r - color2.r
  g = color1.g - color2.g
  b = color1.b - color2.b
  return math.sqrt((((512+redMean)*r*r)>>8) + 4*g*g + (((767-redMean)*b*b)>>8))

def parseSpriteTiles( image, options, frameID):
  tiles = []
  pos = {'x':0,'y':0}
  currentLeft = 0
  bigYTarget = 0
  while pos['y'] < image['resolutionY']:
    if not checkLineFilled( image, pos, options ) and options.get('optimize'):
      pos['y'] += 1 if options.get('optimize') else options.get('tilesizey')
      continue

    pos['x'] = 0

    while pos['x'] < image['resolutionX']:
      if not checkTileRowFilled( image, pos, options ) and options.get('optimize'):
        pos['x'] += 1 if options.get('optimize') else options.get('tilesizex')
        continue

      if pos['y'] < bigYTarget:
        diff = pos['x'] - currentLeft
        pos['x'] -= diff%8

      elif checkBigTileFilledThreshold( image, pos, options ):
        bigYTarget = pos['y']+32
        currentLeft = pos['x']
      else:
        bigYTarget = 0

      if checkTileFilledThreshold( image, pos, options ):
        #try to have as many pixels as possible filled on right edge so that sprite flicker is less noticeable
        if options.get('optimize'):
          backpos = {'x':pos['x']+8,'y':pos['y']}
          while not (pos['y'] < bigYTarget) and not checkTileRowFilled( image, backpos, options ):
            backpos['x'] -= 1
          diff = ((pos['x']+8) - backpos['x'])%8
          if diff != 0:
            pos['x'] -= diff-1
          #prevent out of bounds sprites (also right border because of mirroring)
          pos['x'] = min(max(0, pos['x']), image['resolutionX']-options.get('tilesizex'))
        tile = fetchTile( image, pos, options, len( tiles ) )
        tiles.append( {
          'id'      : len( tiles ),
          'pixel'   : tile['pixel'],
          'pixhash' : tile['pixhash'],
          'palette' : tile['palette'],
          'frame': frameID,
          'x'       : pos['x'],
          'y'       : pos['y'],
          'refId'   : None,
          'xMirror' : False,
          'yMirror' : False
        } )
      pos['x'] += options.get('tilesizex')
    pos['y'] += options.get('tilesizey')
  
  if 1 < options.get('tilemultiplier'):
    return parseBigSpriteTiles(tiles, options)
  
  return {'normal':tiles, 'big':[]}

#combine adjacent default size to bigger sized sprites (e.g. 8x8 and 32x32)
def parseBigSpriteTiles(tiles, options):
  tilecounter = options.get('tilemultiplier')
  newTiles = list(tiles)
  newBigTiles = []
  if 0 < len(tiles):
    emptyTile = copy.deepcopy(tiles[0])
    for scanline in range(len(emptyTile['pixel'])):
      for pixel in range(len(emptyTile['pixel'][scanline])):
        emptyTile['pixel'][scanline][pixel] = options.get('transcol')
    emptyTile['palette']['color'] = []
    for tile in tiles:
      currentBigTile = []
      currentX = tile['x']
      currentY = tile['y']
      sizeX = options.get('tilesizex')
      sizeY = options.get('tilesizey')
      misses = 0
      breakOut = False
      for checkBigTile in newBigTiles:
        if ((currentX >= checkBigTile['x'] and currentX < checkBigTile['x']+32) or (currentX+32 >= checkBigTile['x'] and currentX+32 < checkBigTile['x']+32)) and ((currentY >= checkBigTile['y'] and currentY < checkBigTile['y']+32) or (currentY+32 >= checkBigTile['y'] and currentY+32 < checkBigTile['y']+32)):
          breakOut = True
          break
      if breakOut:
          continue
      for tileCountY in range(tilecounter):
        for tileCountX in range(tilecounter):

          compareTileFound = False
          for compareTile in newTiles:
            if compareTile['x'] == currentX + (tileCountX * sizeX) and compareTile['y'] == currentY + (tileCountY * sizeY):
              foundTile = compareTile.copy()
              currentBigTile.append(foundTile)
              compareTileFound = True
          if not compareTileFound:
              currentBigTile.append( {
                'id'      : None,
                'pixel'   : emptyTile['pixel'],
                'pixhash' : emptyTile['pixhash'],
                'palette' : emptyTile['palette'],
                'x'       : currentX + (tileCountX * sizeX),
                'y'       : currentY + (tileCountY * sizeY),
                'frame' : 0, #???
                'refId'   : None,
                'xMirror' : False,
                'yMirror' : False
              } )
              misses += 1
      
      if misses <= options.get('bigtilethreshold') and len(newBigTiles) < options.get('maxbigtiles'):
        mergedTile = None
        for tile in currentBigTile:
          if None == mergedTile:
            mergedTile = tile
          else:
            mergedTile['pixel'] = mergedTile['pixel'] + list(tile['pixel'])
            mergedTile['palette']['color'] = mergedTile['palette']['color'] + list(tile['palette']['color'])
        
        mergedTile['palette']['color'] = list(set(mergedTile['palette']['color']))
        newBigTiles.append(mergedTile)
        for bigSubTile in currentBigTile:
          for idx, newTile in enumerate(newTiles):
            if bigSubTile['id'] == newTile['id']:
              newTiles.pop(idx)

    currId = 0
    for tile in newTiles:
      tile['id'] = currId
      currId += 1

    currId = 0
    for tile in newBigTiles:
      tile['id'] = currId
      currId += 1

  #try to rearrange big tiles here:
  #convert list of tiles having 4 horizontal rows each (for 32x32 sprites, that is)
  #to 4 long sequential horizontal rows, so that one row can be transferred to vram with as few dma transfers as possible (ideally 1, if bigtile size is 32x32, total bigtile length is 0x800 bytes and vram for this sprite is allocated at 0xX000)
  #problem though: must be separated by frame. static tiles come all in at once with no way to discern which tile belongs to which frame...
  #left to do: put tiles into buckets according to their tile.frame first, then apply transform on them individually
  #for the time being, we just cop out and disable row merge for static tiles
  tiles = [chunks(tile['pixel'], len(tile['pixel'])/4) for tile in newBigTiles]
  rows = reduce(lambda x,y: x+y,
    [[row for tile in tiles for row in tile[0]],
    [row for tile in tiles for row in tile[1]],
    [row for tile in tiles for row in tile[2]],
    [row for tile in tiles for row in tile[3]]]
  )

  for i in range(len(newBigTiles)):
    newBigTiles[i]['pixel'] = rows[i*128:(i*128)+128]

  return {'normal':newTiles, 'big':newBigTiles}
  
          
def getTilePosList(tiles):
  return [{'id':tile['id'],'x':tile['x'],'y':tile['y']} for tile in tiles]  

def checkVlineFilled( image, pos, options ):
  for ypos in range( pos['y'], pos['y']+options.get('tilesizey') ):
    if isPixelOpaque( image['pixels'], ypos, pos['x'], options ):
      return True
  return False

def checkTileFilled( image, pos, options ):
  for ypos in range( pos['y'], pos['y']+options.get('tilesizey') ):
    for xpos in range( pos['x'], pos['x']+options.get('tilesizex') ):
      if isPixelOpaque( image['pixels'], ypos, xpos, options ):
        return True
  return False

def checkTileFilledThreshold( image, pos, options ):
  count = 0
  for ypos in range( pos['y'], pos['y']+options.get('tilesizey') ):
    for xpos in range( pos['x'], pos['x']+options.get('tilesizex') ):
      if isPixelOpaque( image['pixels'], ypos, xpos, options ):
        count += 1
  return 2 < count

def checkBigTileFilledThreshold( image, pos, options ):
  misses = 16
  for ypos in range( pos['y'], pos['y']+32, 8 ):
    for xpos in range( pos['x'], pos['x']+32, 8 ):
      if checkTileFilledThreshold( image, {'x':xpos,'y':ypos}, options ):
        misses -= 1
  return misses <= options.get('bigtilethreshold')



def checkTileRowFilled( image, pos, options ):
  if options.get('optimize'):
    for ypos in range( pos['y'], pos['y']+options.get('tilesizey') ):
      if isPixelOpaque( image['pixels'], ypos, pos['x'], options ):
        return True
    return False
  else:
    for xpos in range( pos['x'], pos['x']+options.get('tilesizex') ):
      for ypos in range( pos['y'], pos['y']+options.get('tilesizey') ):
        if isPixelOpaque( image['pixels'], ypos, xpos, options ):
          return True
    return False

def checkLineFilled( image, pos, options ):
  for xpos in range( image['resolutionX'] ):
    if isPixelOpaque( image['pixels'], pos['y'], xpos, options ):
      return True
  return False
  
def isPixelOpaque( pixels, yPos, xPos, options ):
  return getPixel( pixels, yPos, xPos, options ).getRGB() != options.get('transcol').getRGB()


def getPixel( pixels, yPos, xPos, options ):
  try:
	return pixels[yPos][xPos]
  except IndexError:
	 return options.get('transcol')


def getInitialSpritePosition( image, options ):
  for scanline in range( len( image['pixels'] ) ):
	for pixel in range( len( image['pixels'][scanline] ) ):
	  if isPixelOpaque( image['pixels'], scanline, pixel, options ):
		return {
		  'y' : scanline,
		  'x' : getInitialLeftmostPixelSprite( image, scanline, options )
		}
  return {	#no match found, be stupid and loop anyway
	'y' : 0,
	'x' : 0
  }


def getInitialLeftmostPixelSprite( image, top, options ):
  x = INFINITY
  for scanline in range( top, min(top + options.get('tilesizey'), len( image['pixels']))):
    for pixel in range( len( image['pixels'][scanline] ) ):
	  if isPixelOpaque( image['pixels'], scanline, pixel, options ):
		x = min( x, pixel )
  return x


def parseBgTiles( image, options, frameID ):
  '''normal bg tiles, parse whole image in tilesize-steps'''
  pos = {
    'x' : 0,
    'y' : 0
  }
  tiles = []
  while pos['y'] < image['resolutionY']:
	pos['x'] = 0
	while pos['x'] < image['resolutionX']:
	  tile = fetchTile( image, pos, options, len( tiles ) )
	  tiles.append( {
		'id' 		: len( tiles ),
		'pixel'		: tile['pixel'],
		'pixhash'   : tile['pixhash'],
		'palette'	: tile['palette'],
		'x'			: pos['x'],
		'y'			: pos['y'],
    'frame': frameID,
		'refId'		: None,
		'xMirror'	: False,
		'yMirror'	: False
	  } )
	  pos['x'] += options.get('tilesizex')
	pos['y'] += options.get('tilesizey')
  return {'normal':tiles, 'big':[]}


def fetchTile( image, pos, options, tileId ):
  tile = []
  palette = [options.get('transcol')]
  for yPos in range( pos['y'], pos['y']+options.get('tilesizey') ):
    tileLine = []
    for xPos in range( pos['x'], pos['x']+options.get('tilesizex') ):
	  pixel = getPixel( image['pixels'], yPos, xPos, options )
	  tileLine.append( pixel )
	  if pixel not in palette:
		palette.append( pixel )
    tile.append( tileLine )    
  return {
	'pixel'		: tile,
	'pixhash'   : hash(str(tile)),
	'palette'	: {
	  'id'			: tileId,
	  'color'		: palette,
	  'refId'	: None
	}
  }


def getInputImage( options, filename ):
  try:
	  inputImage = Image.open( filename )
  except IOError:
	  logging.error( 'Unable to load input image "%s"' % filename )
	  sys.exit(1)
  
  paddedImage = padImageReduceColdepth( inputImage, options )
  options.set('resolutionx', paddedImage.size[0])
  options.set('resolutiony', paddedImage.size[1])

  return {
	'resolutionX'	: paddedImage.size[0],
	'resolutionY'	: paddedImage.size[1],
	'pixels'	: getRgbPixels( paddedImage )
  }

#total hack...
def getInputImageNoResolutionSet( options, filename ):
  try:
      inputImage = Image.open( filename )
  except IOError:
      logging.error( 'Unable to load input image "%s"' % filename )
      sys.exit(1)
  
  paddedImage = ImageReduceColdepth( inputImage, options )

  return {
    'resolutionX'   : paddedImage.size[0],
    'resolutionY'   : paddedImage.size[1],
    'pixels'    : getRgbPixels( paddedImage )
  }

def getRgbPixels( image ):
  '''extract color-converted pixels from image'''
  rawPixels = list(image.getdata())
  outputPixels = []
  for y in range( image.size[1] ):
    outputPixels.append( [] )
    for x in range( image.size[0] ):
      outputPixels[y].append(Color(rawPixels.pop(0)))

  return outputPixels


def ImageReduceColdepth( inputImage, options):
  '''pad image to multiple of tilesize, fill blank areas with transparent color'''
  paddedWidth = inputImage.size[0]
  paddedHeight = inputImage.size[1]
    
  paddedImage = Image.new( 'RGB', ( paddedWidth, paddedHeight ), options.get('transcol').getPIL() )
  paddedImage.paste( inputImage, ( 0, 0 ) )
  
  #this would cause problems with loading reference palette that already has transparent color, one too much
  colorCount = ((options.get('bpp') ** 2) * options.get('palettes'))
  colorCount += 1
  reducedImage = paddedImage.convert('P', palette=Image.ADAPTIVE, colors=colorCount).convert('RGB')
  return reducedImage
  
def padImageReduceColdepth( inputImage, options):
  '''pad image to multiple of tilesize, fill blank areas with transparent color'''
  paddedWidth = inputImage.size[0] if ( inputImage.size[0] % options.get('tilesizex') == 0 ) else ( inputImage.size[0] - ( inputImage.size[0] % options.get('tilesizex') ) + options.get('tilesizex') )
  paddedHeight = inputImage.size[1] if ( inputImage.size[1] % options.get('tilesizey') == 0 ) else ( inputImage.size[1] - ( inputImage.size[1] % options.get('tilesizey') ) + options.get('tilesizey') )
    
  paddedImage = Image.new( 'RGB', ( paddedWidth, paddedHeight ), options.get('transcol').getPIL() )
  paddedImage.paste( inputImage, ( 0, 0 ) )
  
  #this would cause problems with loading reference palette that already has transparent color, one too much
  colorCount = ((options.get('bpp') ** 2) * options.get('palettes'))
  colorCount += 1
  reducedImage = paddedImage.convert('P', palette=Image.ADAPTIVE, colors=colorCount).convert('RGB')
  return reducedImage


def getColorTuple(inputColor):
  return (
    (inputColor & 0xff0000) >> 16,
    (inputColor & 0xff00) >> 8,
    inputColor & 0xff
  )

def compress(byteList):
  if 0 == len(byteList):
      return byteList
  filename = 'build/temp'
  packedname = filename + '.lz4'
  tempfile = open(filename, 'wb')
  [tempfile.write(byte) for byte in byteList]
  tempfile.close()
  subprocess.call(['lz4', '--content-size', '-9', '-f', filename, packedname])

  packedFile = open(packedname, 'rb' )
  lz4data = packedFile.read()
  packedFile.close()
  return lz4data

class BitStream():
  def __init__( self ):
	self.bitPos = 7
	self.byte = 0
	self.bitStream = []
	
  def writeBit(self, bit):
	self.byte |= (bit & 1) << self.bitPos
	self.bitPos -= 1
	if self.bitPos < 0:
	  self.bitStream.append(self.byte)
	  self.byte = 0
	  self.bitPos = 7

  def get(self):
	return self.bitStream

  def first(self):
	return self.bitStream.pop(0)

  def notEmpty(self):
	return len(self.bitStream) > 0


class Statistics():
  def __init__(self, tiles, palettes, startTime):
	self.totalTiles = len(tiles)
	self.actualTiles = len([tile for tile in tiles if tile['refId'] == None])
	self.actualPalettes = len([pal for pal in palettes if pal['refId'] == None])
	self.timeWasted = time.clock() - startTime


class Color():
  def __init__(self, rgbCol):
    self.r = rgbCol[0]
    self.g = rgbCol[1]
    self.b = rgbCol[2]

  #required for sort, compare, hash
  def __hash__(self):
    return self.getRGB()

  def __eq__(self, other):
    return self.getRGB() == other.getRGB()

  def __ne__(self, other):
    return self.getRGB() != other.getRGB()

  def __str__(self):
    return "%x" % self.getRGB()

  def __repr__(self):
    return "%x" % self.getRGB()
    
  def getLightness(self):
  	r = self.r / float(0x1f)
  	g = self.g / float(0x1f)
  	b = self.b / float(0x1f)
  	
  	cmin = min(r, g, b)
  	cmax = max(r, g, b)
  	return (cmax + cmin) / 2

  def getBrightnessCoefficient(self):
    return ((self.r + self.g + self.b)/3)/float(0xff)

  def getPIL(self):
    return (self.r, self.g, self.b)

  def getSNES(self):
    return ( (self.r & 0xf8) >> 3 ) | ( (self.g & 0xf8) << 2 ) | ( (self.b & 0xf8) << 7 )

  #source: -bbbbbgg gggrrrrr target: -bb---gg g--rrr--
  def getSNESdirect(self):
    return ( (self.r & 0xe0) >> 3 ) | ( (self.g & 0xe0) << 2 ) | ( (self.b & 0xc0) << 7 )

  def getRGB(self):
    return int(self.r) << 16 | int(self.g) << 8 | int(self.b)

  #returns 16bit color list, format: (r,g,b)
  def getRGBtuple(self):
    return(int(self.r), int(self.g), int(self.b))

  def getSaturation(self):
  	r = self.r / float(0x1f)
  	g = self.g / float(0x1f)
  	b = self.b / float(0x1f)
  	
  	cmin = min(r, g, b)
  	cmax = max(r, g, b)
  	cdelta = cmax - cmin
  	if cdelta == 0:
  	  return 0
  	clight = (cmax + cmin) / 2
  	return cdelta / (cmax + cmin) if clight < 0.5 else cdelta / (2 - cmax - cmin)

  def getHue(self):
  	r = self.r / float(0x1f)
  	g = self.g / float(0x1f)
  	b = self.b / float(0x1f)
  	
  	cmin = min(r, g, b)
  	cmax = max(r, g, b)
  	cdelta = cmax - cmin
  	if cdelta == 0:
  	  return 0
  	clight = (cmax + cmin) / 2
  	csaturation = cdelta / (cmax + cmin) if clight < 0.5 else cdelta / (2 - cmax - cmin)
  	
  	rdelta =(((cmax-r)/6)+(cdelta/2)) / cdelta
  	gdelta =(((cmax-g)/6)+(cdelta/2)) / cdelta
  	bdelta =(((cmax-b)/6)+(cdelta/2)) / cdelta
  	
  	if r == cmax:
  	  chue = bdelta - gdelta
  	elif g == cmax:
  	  chue = (1/3) + rdelta - bdelta
  	elif b == cmax:
  	  chue = (2/3) + gdelta - rdelta

  	if chue < 0:
  	  chue += 1
  	if chue > 1:
  	  chue -= 1
  	return chue


def debugLog( data, message = '' ):
	logging.debug( message )
	debugLogRecursive( data, '' )


def debugLogExit( data, message = '' ):
	logging.debug( message )
	debugLogRecursive( data, '' )
	sys.exit()


def debugLogRecursive( data, nestStr ):
  nestStr += ' '
  if type( data ) is dict:
	logging.debug( '%s dict{' % nestStr )	
	for k, v in data.iteritems():
	  logging.debug( ' %s %s:' % tuple( [nestStr, k] ) )
	  debugLogRecursive( v, nestStr )
	logging.debug( '%s }' % nestStr )

  elif type( data ) is list:
	logging.debug( '%s list[' % nestStr )
	for v in data:
	  debugLogRecursive( v, nestStr )
	logging.debug( '%s ]' % nestStr )

  else:
	if type( data ) is int:
	  logging.debug( ' %s 0x%x %s ' % ( nestStr, data, type( data ) ) )
	else:
	  logging.debug( ' %s "%s" %s' % ( nestStr, data, type( data ) ) )

if __name__ == "__main__":
	main()

