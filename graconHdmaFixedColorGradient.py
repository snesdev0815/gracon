#!/usr/bin/env python2.7

__author__ = "Matthias Nagler <matt@dforce.de>"
__url__ = ("dforce3000", "dforce3000.de")
__version__ = "0.1"

'''
takes input graphics files(usually  png), converts and packs them into 
hdma list animation file for use with COLDATA register.

command line options:
-infolder	input folder containing all animation frames, name-sorted
-outfile	output animation file

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
  [tiles]
  [spritemap]
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
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont


logging.basicConfig( level=logging.ERROR, format='%(message)s')

options = {}


INFINITY = 1e300000
HEADER_MAGIC = 'HO'
HEADER_SIZE = 8
ALLOWED_FRAME_FILETYPES = ('.png', '.gif', '.bmp')
HDMA_TYPE_COLOR = 2


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
  })
  
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
        frameDelays.append(int(re.sub('\.delay[\d]{3}', '', frame)[-3:]))
      except ValueError:
        pass
      index += 1
  
  images = [getHdmaList(options.get('infolder') + "/" + image) for image in files]

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

  outFile.write(chr(HDMA_TYPE_COLOR))
  
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

def getHdmaList(filename):
  try:
      inputImage = Image.open( filename )
  except IOError:
      logging.error( 'Unable to load input image "%s"' % filename )
      sys.exit(1)
  image = inputImage.convert('P', palette=Image.ADAPTIVE, colors=256).convert('RGB')
  hdmaList = []
  last = [0xff,0xff,0xff]
  for scanline in range( image.size[1] ):
      pixel = graconGfx.Color(image.getpixel((0, scanline))).getSNES()
      r = (pixel & 0x1f) #| 0x20
      g = ((pixel >> 5) & 0x1f) #| 0x40
      b = ((pixel >> 10) & 0x1f) #| 0x80
      
      current = [r, g, b]
      currentBuff = list(current)
      #purge unmodified 
      
      if last[0] == current[0]:
        current[0] = None
      if last[1] == current[1]:
        current[1] = None
      if last[2] == current[2]:
        current[2] = None
      
      out = []
      if current[0] == current[1] and current[0] == current[2]:
        if None != current[0]:
          out.append(current[0] | 0x20 | 0x40 | 0x80)
      if current[0] == current[1]:
        if None != current[0]:
          out.append(current[0] | 0x20 | 0x40)
        if None != current[2]:
          out.append(current[2] | 0x80)
      elif current[0] == current[2]:
        if None != current[0]:
          out.append(current[0] | 0x20 | 0x80)
        if None != current[1]:
          out.append(current[1] | 0x40)
      elif current[1] == current[2]:
        if None != current[0]:
          out.append(current[0] | 0x20)
        if None != current[1]:
          out.append(current[1] | 0x40 | 0x80)
      else:
        if None != current[0]:
          out.append(current[0] | 0x20)
        if None != current[1]:
          out.append(current[1] | 0x40)
        if None != current[2]:
          out.append(current[2] | 0x80)
      
      while len(out) < 2:
        out.append(0x0)

      #@todo: must force change for colors that were not servicable this round
      last = currentBuff
      
      #force refresh on next line for colors that had to be omitted in current line
      if len(out) > 2:
        if out[2] & 0x20:
          last[0] = 0xff
        if out[2] & 0x40:
          last[1] = 0xff
        if out[2] & 0x80:
          last[2] = 0xff
        logging.info('Warning: unable to meet requested color fidelity on frame %s, line %s.' % (filename, scanline))
      
      hdmaList.append({
            'count': 1,
            'data': [out[0], out[1]]
          })

  stream = []
  last = [128,0,0]
  for i in range(len(hdmaList)):
    try:
      count = hdmaList[i+1]['count']
    except IndexError:
      count = 1
    if last[1] == hdmaList[i]['data'][0] and last[2] == hdmaList[i]['data'][1] and last[0] + count < 128:
      stream[len(stream)-3] = last[0] + count
      last = [last[0] + count, hdmaList[i]['data'][0], hdmaList[i]['data'][1]]
    else:
      stream.append(count)
      stream.append(hdmaList[i]['data'][0])
      stream.append(hdmaList[i]['data'][1])
      last = [count, hdmaList[i]['data'][0], hdmaList[i]['data'][1]]
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

