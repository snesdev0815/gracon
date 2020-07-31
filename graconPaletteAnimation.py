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
  [header(8bytes){
	2 bytes : "PA", header magic
	2 bytes : max palette-size(bytes) in animation(for cgram allocation)
	2 bytes : frames in animation
	2 bytes: loopstart
  }],
  [pointer{
	2 bytes : relative pointer to individual sprite frame
  }]
  [sprite_frame{
    [palette]
  }]
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
import pprint

logging.basicConfig( level=logging.ERROR, format='%(message)s')

options = {}


INFINITY = 1e300000
HEADER_MAGIC = 'PA'
HEADER_SIZE = 10
ALLOWED_FRAME_FILETYPES = ('.png', '.gif', '.bmp')


def main():
  options = graconUserOptions.Options( sys.argv, {	  
        'palettes'              : {
          'value'                       : 8,
          'type'                        : 'int',
          'max'                 : 8,
          'min'                 : 0
          },
        'transcol'      : {
          'value'                       : 0x7c1f,
          'type'                        : 'hex',
          'max'                 : 0x7fff,
          'min'                 : 0x0
          },      
        'infolder'              : {
          'value'                       : '',
          'type'                        : 'str'
          },
        'outfile'               : {
          'value'                       : '',
          'type'                        : 'str'
          },
    'outfilebase'       : {
      'value'           : '',
      'type'            : 'str'
      },          
        'refpalette'            : {
          'value'                       : '',
          'type'                        : 'str'
          },
        'tilesizex'     : {
          'value'                       : 8,
          'type'                        : 'int',
          'max'                 : 16,
          'min'                 : 8
          },
        'tilesizey'     : {
          'value'                       : 1,
          'type'                        : 'int',
          'max'                 : 16,
          'min'                 : 1
          },
        'optimize'      : {
          'value'                       : True,
          'type'                        : 'bool'
          },
    'directcolor'  : {
      'value'           : False,
      'type'            : 'bool'
      },      
        'tilethreshold' : {
          'value'                       : 0,
          'type'                        : 'int',
          'max'                 : 0xffff,
          'min'                 : 0
          },
    'maxtiles' : {
      'value'           : 0x3ff,
      'type'            : 'int',
      'max'         : 0x3ff,
      'min'         : 0
      },          
        'bpp'           : {
          'value'                       : 4,
          'type'                        : 'int',
          'max'                 : 8,
          'min'                 : 1
          },
        'mode'          : {
          'value'                       : 'bg',
          'type'                        : 'str'
          },
        'resolutionx'   : {
          'value'                       : 256,
          'type'                        : 'int',
          'max'                 : 0xffff,
          'min'                 : 1
          },      
        'resolutiony'   : {
          'value'                       : 224,
          'type'                        : 'int',
          'max'                 : 0xffff,
          'min'                 : 1
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
      'max'         : 2,
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
  })

  sys.setrecursionlimit(10000)
    
  if not os.path.exists(options.get('infolder')):
	logging.error( 'Error, input folder "%s" is nonexistant.' % options.get('infolder') )
	sys.exit(1)

  options.set('transcol', graconGfx.Color(graconGfx.getColorTuple(options.get('transcol'))))

  tileFiles = [frame for root, dirs, names in os.walk(options.get('infolder')) for frame in names if os.path.splitext(frame)[1] in ALLOWED_FRAME_FILETYPES]
  tileFiles.sort()

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
        frameDelays.append(int(re.sub('\.delay[\d]{3}', '', frame)[-3:]))
      except ValueError:
        pass
      index += 1
    
    
  options.set('outfilebase', options.get('outfile'))
  logging.debug("parsing tiles")
  paletteFrames = []
  for frame in tileFiles:
    #just a hack...
    options.set('refpalette', "%s/%s" % (options.get('infolder'), frame))
    #set transparent color to first color in reference palette
    palette = [item for sublist in graconGfx.getReferencePaletteImage(options)['pixels'] for item in sublist]
        
    paletteFrames.append(palette)

  if not 0 < len(paletteFrames):
	logging.error( 'Error, input folder "%s" does not contain any parseable frame image files.' % options.get('infolder') )
	sys.exit(1)
	
  maxPaletteLength = 0
  framecount = len(paletteFrames)
  currentFramePointer = 0
  framePointers = []
  
  logging.debug("calculating pointers")
  for i in range(len(paletteFrames)):    
    framePointers.append(currentFramePointer)
    currentFramePointer += len(paletteFrames[i])*2
    maxPaletteLength = len(paletteFrames[i])*2 if maxPaletteLength < len(paletteFrames[i])*2 else maxPaletteLength
  
  
  try:
	outFile = open( options.get('outfile'), 'wb' )
  except IOError:
	logging.error( 'unable to access required output-file %s' % options.get('outfile') )
	sys.exit(1)

  outFile.write(HEADER_MAGIC)
  
  outFile.write(chr(maxPaletteLength & 0xff))
  outFile.write(chr((maxPaletteLength & 0xff00) >> 8 ))

  outFile.write(chr(framecount & 0xff))
  outFile.write(chr((framecount & 0xff00) >> 8 ))

  outFile.write(chr(loopstart & 0xff))
  outFile.write(chr((loopstart & 0xff00) >> 8 ))

  paletteHash = hash(str([[color for palette in paletteFrames for color in palette]])) & 0xffff

  logging.debug("palette hash: %x" % (paletteHash & 0xffff))

  outFile.write(chr(paletteHash & 0xff))
  outFile.write(chr((paletteHash & 0xff00) >> 8 ))

  #write framepointerlist
  outFile.seek(HEADER_SIZE)
  for framePointer in framePointers:
	framePointer += HEADER_SIZE + len(framePointers)*2
	outFile.write(chr(framePointer & 0xff))
	outFile.write(chr((framePointer & 0xff00) >> 8 ))

  #write frames
  for i in range(len(paletteFrames)):
    for color in paletteFrames[i]:
      outFile.write(chr(color.getSNES() & 0xff))
      outFile.write(chr((color.getSNES() & 0xff00) >> 8 ))

  logging.info('Successfully wrote animation file %s.' % options.get('outfile'))

  
  
if __name__ == "__main__":
	main()

