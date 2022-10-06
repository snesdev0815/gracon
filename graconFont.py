#!/usr/bin/env python2.7

__author__ = "Matthias Nagler <matt@dforce.de>"
__url__ = ("dforce3000", "dforce3000.de")
__version__ = "0.1"

'''
converts input grid image to special vwf font package file

command line options:
-infolder	input folder containing all animation frames, name-sorted
-outfile	output animation file

outfile format:
[hdma_overlay_animation{
  [header(8bytes){
	2 bytes : "VF", header magic
	1 bytes : pixel width
	1 byte : pixel height
	1 byte : bpp (always 4bpp)
	1 byte : number of characters
	32 bytes; palette
        charnum * 1 byte: tiles width/breakable config
	charnum * 32 bytes: tiles
  }],
}]  
'''

import os
import re
import sys
import math
import time
import graconUserOptions
import graconGfx
import logging
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import pprint

logging.basicConfig( level=logging.ERROR, format='%(message)s')

options = {}


INFINITY = 1e300000
HEADER_MAGIC = 'VF'
HEADER_SIZE = 11
ALLOWED_FRAME_FILETYPES = ('.png', '.gif', '.bmp')
HDMA_TYPE_COLOR = 2


def main():
  options = graconUserOptions.Options( sys.argv, {
	'infile'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
	'outfile'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
    'tilesize' : {
      'value'           : 8,
      'type'            : 'int',
      'max'         : 16,
      'min'         : 8
      },
    'bpp'       : {
      'value'           : 4,
      'type'            : 'int',
      'max'         : 8,
      'min'         : 1
      },
    'bgCol'       : {
      'value'           : 0,
      'type'            : 'int',
      'max'         : 3,
      'min'         : 0
      }
  })
  
  if not os.path.exists(options.get('infile')):
	logging.error( 'Error, input folder "%s" is nonexistant.' % options.get('infile') )
	sys.exit(1)

  try:
      inputImage = Image.open( options.get('infile') )
  except IOError:
      logging.error( 'Unable to load input image "%s"' % options.get('infile') )
      sys.exit(1)
      
  image = inputImage.convert('P', palette=Image.ADAPTIVE, colors=256).convert('RGB')
  
  palette = [getpixel(image, x, 0) for x in range(16,144,8)]

  subpalettes = list(chunks(palette,options.get('bpp')*options.get('bpp')))

  stop = getpixel(image,152, 0)
  grid = getpixel(image,160, 0)
  brk = getpixel(image,184, 0)
  
  logging.debug(stop)
  logging.debug(grid)
  logging.debug(brk)


  #crappy hack to get colors used and determine appropriate subpalette  
  currentY = 24
  currentX = 16
  colors = set()
  while grid == getpixel(image, currentX-1, currentY):
    for currentX in range(16,288,17):
        for tileY in range(currentY,currentY+options.get('tilesize')):
            for tileX in range(currentX,currentX+options.get('tilesize')):
                pixel = getpixel(image,tileX,tileY)

                if stop == pixel or brk == pixel:
                  pass
                else:
                  colors.add(pixel)
    currentY += 17

  logging.debug(colors)
  paletteId = -1
  for i in range(len(subpalettes)):
    if reduce(lambda carry,color: carry & (color in subpalettes[i]), colors, True):
      paletteId = i
      subpalette = subpalettes[i]

  if 0 > paletteId:
    logging.error( 'No suitable %d bpp palette found that fits all %d colors of font.' % (options.get('bpp'), len(colors)))
    sys.exit(1)

  logging.debug(paletteId)

  chars = []
  last = 0
  currentY = 24
  currentX = 16  
  while grid == getpixel(image, currentX-1, currentY):
    for currentX in range(16,288,17):
        width = len([pixel for pixel in [getpixel(image,col,currentY) for col in range(currentX,currentX+16)] if pixel != stop and pixel != brk and pixel != grid])
        breakable = 0 < len([pixel for pixel in [getpixel(image,col,currentY) for col in range(currentX,currentX+16)] if pixel == brk])
        pixels = [[],[],[],[]]
        for tileY in range(currentY,currentY+options.get('tilesize')):
            for tileX in range(currentX,currentX+options.get('tilesize')):
                pixel = getpixel(image,tileX,tileY)
                targetTile = 0
                if tileX-currentX > 7:
                  targetTile += 2
                if tileY-currentY > 7:
                  targetTile += 1                  
                if stop == pixel or brk == pixel:
                  pixels[targetTile].append(0)
                else:
                  try:
                    pixels[targetTile].append(subpalette.index(pixel))
                  except ValueError:
                      logging.error( 'Found invalid pixel %d not in font palette in character at %sx%s.' % (pixel, currentX, currentY))
                      sys.exit(1)
        chars.append({
          'tile': getTileWriteStream(pixels, options),
          'width': width,
          'breakable': breakable
        })
        if (0 < width):
          last = len(chars)
        
    currentY += 17
  
  try:
	outFile = open( options.get('outfile'), 'wb' )
  except IOError:
	logging.error( 'unable to access required output-file %s' % options.get('outfile') )
	sys.exit(1)

  outFile.write(HEADER_MAGIC)

  outFile.write(chr(options.get('tilesize'))) #width
  outFile.write(chr(options.get('tilesize'))) #height
  outFile.write(chr(options.get('bpp')))
  outFile.write(chr(paletteId)) #pal id

  outFile.write(chr(((options.get('tilesize')*options.get('tilesize'))/8)*options.get('bpp'))) #tilelength in bytes
  outFile.write(chr(last & 0xff))
  outFile.write(chr((last & 0xff00) >> 8 ))

  paletteHash = hash(str(palette)) & 0xffff
  outFile.write(chr(paletteHash & 0xff))
  outFile.write(chr((paletteHash & 0xff00) >> 8 ))
  
  outFile.seek(HEADER_SIZE)
  
  for color in palette:
    outFile.write(chr(color.getSNES() & 0xff))
    outFile.write(chr((color.getSNES() & 0xff00) >> 8 ))

  for char in chars[0:last]:
    widthBreak = char['width']
    if char['breakable']:
      widthBreak = widthBreak | 0x80
    outFile.write(chr(widthBreak))

  i = 0
  for char in chars[0:last]:
    i += 1
    for byte in char['tile']:
      outFile.write(byte)
    
  logging.info('Successfully wrote vwf font package file %s. containing %s chars.' % (options.get('outfile'),last))

def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in xrange(0, len(l), n):
        yield l[i:i+n]

def getTileWriteStream( tiles, options ):
  stream = []
  for tile in tiles:
    if len(tile) > 0:
      bitplanes = fetchBitplanes( tile, options )
      for i in range( 0, len( bitplanes ), 2 ):
        while bitplanes[i].notEmpty():
          stream.append(( chr( bitplanes[i].first() ) ))
          stream.append(( chr( bitplanes[i+1].first() ) ))
  return stream
  
def fetchBitplanes( tile, options ):
  bitplanes = []
  for bitPlane in range( options.get('bpp') ):
    bitplaneTile = graconGfx.BitStream()
    for pixel in tile:
      bitplaneTile.writeBit( pixel >> bitPlane )
    bitplanes.append( bitplaneTile )
  return bitplanes  

def getpixel(image, x, y):
  return graconGfx.Color(image.getpixel((x,y)))

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
	  
if __name__ == "__main__":
	main()

