#!/usr/bin/env python2.7

__author__ = "Matthias Nagler <matt@dforce.de>"
__url__ = ("dforce3000", "dforce3000.de")
__version__ = "0.1"

'''
takes input graphics files(usually black/white png), converts and packs them into 
hdma list animation file for use with window registers.

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
	2 bytes : relative pointer to individual sprite frame
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
HDMA_TYPE_WINDOW = 0


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
    'single'       : {
      'value'           : False,
      'type'            : 'bool'
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

  outFile.write(chr(HDMA_TYPE_WINDOW))
  
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
  image = inputImage.convert('P', palette=Image.ADAPTIVE, colors=2).convert('RGB')
  if not image.size[0] == 256 or not image.size[1] == 224:
    logging.error( 'image %s must be of size 256x224, is %sx%s' % (filename, image.size[0], image.size[1]) )
    sys.exit(1)
    
  rawPixels = list(image.getdata())
  lineCounter = 1
  hdmaList = []
  lastLine = [1,0,1,0]

  for scanline in range( image.size[1] ):      
      pixelList = [False]
      for i in range( image.size[0] ):
        pixel = rawPixels.pop(0)
        pixelList.append(True if pixel[0] > 127 else False)
      pixelList.append(False)
      lastPixel = False
      edgeList = []      
      for i in range(len(pixelList)):
        if not lastPixel is pixelList[i]:
          if i > 256:
            i = 256
          edgeList.append(i-1)
        lastPixel = pixelList[i]
      if 0 is len(edgeList):
        if 127 is lineCounter or 0 is len(hdmaList):
          hdmaList.append({
            'count': lineCounter,
            'data': lastLine
          })
          lineCounter = 1
        elif 1 != lastLine[0] or 0 != lastLine[1] or 1 != lastLine[2] or 0 != lastLine[3]:
          currentLine = [1,0, 1, 0]       
          hdmaList.append({
            'count': 1,
            'data': currentLine
          })
          lastLine = currentLine
          lineCounter = 1        
          
        else:
          lineCounter += 1
        
      elif 2 is len(edgeList):
        currentLine = [edgeList[0], edgeList[1], 1, 0]       
        hdmaList.append({
          'count': lineCounter,
          'data': currentLine
        })
        lastLine = currentLine
        lineCounter = 1
      elif 3 is len(edgeList):
        currentLine = [edgeList[0], edgeList[1], 1, 0]       
        hdmaList.append({
          'count': lineCounter,
          'data': currentLine
        })
        lastLine = currentLine
        lineCounter = 1        
      elif 4 is len(edgeList):
        currentLine = [edgeList[0], edgeList[1], edgeList[2], edgeList[3]]
        hdmaList.append({
          'count': lineCounter,
          'data': currentLine
        })
        lastLine = currentLine
        lastLine = [edgeList[0], edgeList[1], edgeList[2], edgeList[3]]
        lineCounter = 1
      else:
        logging.info('Warning: file %s has %s edges on line %s, only 0, 2 or 4 edges allowed.' % (filename, len(edgeList), scanline))

  #terminator
  hdmaList.append({
    'count': 1,
    'data': [1,0,1,0]
  })

  stream = []
  #output single window?
  if options.get('single'):
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
    
  else:
    last = [128,0,0,0,0]
    for i in range(len(hdmaList)):
      try:
        count = hdmaList[i+1]['count']
      except IndexError:
        count = 1
      if last[1] == hdmaList[i]['data'][0] and last[2] == hdmaList[i]['data'][1] and last[3] == hdmaList[i]['data'][2] and last[4] == hdmaList[i]['data'][3] and last[0] + count < 128:
        stream[len(stream)-5] = last[0] + count
        last = [last[0] + count, hdmaList[i]['data'][0], hdmaList[i]['data'][1], hdmaList[i]['data'][2], hdmaList[i]['data'][3]]
      else:
        stream.append(count)
        stream.append(hdmaList[i]['data'][0])
        stream.append(hdmaList[i]['data'][1])
        stream.append(hdmaList[i]['data'][2])
        stream.append(hdmaList[i]['data'][3])
        last = [count, hdmaList[i]['data'][0], hdmaList[i]['data'][1], hdmaList[i]['data'][2], hdmaList[i]['data'][3]]
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

