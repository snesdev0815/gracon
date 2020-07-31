#!/usr/bin/env python2.7

__author__ = "Matthias Nagler <matt@dforce.de>"
__url__ = ("dforce3000", "dforce3000.de")
__version__ = "0.1"

'''
takes input graphics files(usually  png), converts and packs them into 
hdma list animation file for use with cgram registers.

because of the way cgram/hdma works, it's easiest to hardcode the color id
during list generation.

command line options:
-infolder	input folder containing all animation frames, name-sorted
-outfile	output animation file

hdma list entry looks like this:
  0 count
  1 cgram address
  2 cgram address (redundant, but required because of hdma register access modes)
  3 color data lo
  4 color data hi
outfile format:
[hdma_overlay_animation{
  [header(8bytes){
	2 bytes : "HO", header magic
    1 byte : type
	2 bytes : frames in animation
  }],
  [pointer{
	2 bytes : relative pointer to individual frame
  }]
  [hdma_frame{
  }],
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
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont


logging.basicConfig( level=logging.ERROR, format='%(message)s')

options = {}


INFINITY = 1e300000
HEADER_MAGIC = 'HO'
HEADER_SIZE = 8
ALLOWED_FRAME_FILETYPES = ('.png', '.gif', '.bmp')
HDMA_TYPE_PALETTE = 1


def main():
  options = graconUserOptions.Options( sys.argv, {
	'infolder'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
	'outfile'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
  'colorID'    : {
    'value'     : 0,
    'type'      : 'int',
    'max'     : 255,
    'min'     : 0
    },
  })

  if sys.hexversion < 0x02060000 or sys.hexversion >= 0x03000000:
    logging.error( 'Sorry, this program only runs with python 2.6+, but not 3.x+ at the moment.')
    sys.exit(1)
  
  if not os.path.exists(options.get('infolder')):
	logging.error( 'Error, input folder "%s" is nonexistant.' % options.get('infolder') )
	sys.exit(1)

  files = [frame for root, dirs, names in os.walk(options.get('infolder')) for frame in names if os.path.splitext(frame)[1] in ALLOWED_FRAME_FILETYPES]

  files.sort()

  loopstart = 0
  frameDelays = [0 for frame in range(len(files))]
  index = 0
  for frame in files:
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


  images = [getHdmaList(options.get('infolder') + "/" + image, options.get('colorID')) for image in files]

  currentFramePointer = 0
  framePointers = []
  for image in images:
    framePointers.append(currentFramePointer)
    currentFramePointer += len(image)
  
  try:
	outFile = open( options.get('outfile'), 'wb' )
  except IOError:
	logging.error( 'unable to access required output-file %s' % options.get('outfile') )
	sys.exit(1)

  outFile.write(HEADER_MAGIC)

  outFile.write(chr(HDMA_TYPE_PALETTE))
  
  outFile.write(chr(len(images) & 0xff))
  outFile.write(chr((len(images) & 0xff00) >> 8 ))
  
  outFile.write(chr(loopstart & 0xff))
  outFile.write(chr((loopstart & 0xff00) >> 8 ))

  outFile.seek(HEADER_SIZE)
  for framePointer in framePointers:
	framePointer += HEADER_SIZE + len(framePointers)*2
	outFile.write(chr(framePointer & 0xff))
	outFile.write(chr((framePointer & 0xff00) >> 8 ))

  #write frames
  for image in images:
    [outFile.write(chr(byte)) for byte in image]

  logging.info('Successfully wrote hdma animation file %s.' % options.get('outfile'))

def getHdmaList(filename, colorID):
  try:
      inputImage = Image.open( filename )
  except IOError:
      logging.error( 'Unable to load input image "%s"' % filename )
      sys.exit(1)
  image = inputImage.convert('P', palette=Image.ADAPTIVE, colors=256).convert('RGB')
  hdmaList = []

  #due to cgram dma transfer limitations, one hdma channel can only write into one cgram color adress.
  #if multiple colors of a palette are to be written, multiple hdma effects must be used.
  if not image.size[0] == 256 or not image.size[1] == 224:
    logging.error( 'image %s must be of size 256x224, is %sx%s' % (filename, image.size[0], image.size[1]) )
    sys.exit(1)

  for scanline in range( image.size[1] ):
      hdmaList.append({
            'count': 1,
            'data': graconGfx.Color(image.getpixel((0, scanline))).getSNES()

          })

  stream = []
  last = [128,0xffff]
  for i in range(len(hdmaList)):
    try:
      count = hdmaList[i+1]['count']
    except IndexError:
      count = 1
    if last[1] == hdmaList[i]['data'] and last[0] + count < 128:
      stream[len(stream)-5] = last[0] + count
      last = [last[0] + count, hdmaList[i]['data']]
    else:
      stream.append(count)
      stream.append(colorID)
      stream.append(colorID) #redundancy required for hdma cgram access
      stream.append(hdmaList[i]['data'] & 0xff)
      stream.append((hdmaList[i]['data'] & 0xff00) >> 8)
      last = [count, hdmaList[i]['data']]
  stream.append(0)    #terminator
  return stream
  
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

