#!/usr/bin/env python2.7

__author__ = "Matthias Nagler <matt@dforce.de>"
__url__ = ("dforce3000", "dforce3000.de")
__version__ = "0.1"

'''
Takes input graphic files(usually  png), treats its red channel of leftmost pixel row as zbuffer height values(0-255).
Generates seamless looping hdma scroll lists.
In order for seamlessness to work, actually used background graphics must correspond to length and zbuffer image.


hdma list entry looks like this:
  0 count
  1 scroll low
  2 scroll hi
outfile format:
[hdma_overlay_animation{
  [header(8bytes){
	2 bytes : "HS", header magic
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
HDMA_TYPE_SCROLL = 3


def main():
  options = graconUserOptions.Options( sys.argv, {
  'infolder'    : {
    'value'     : '',
    'type'      : 'str'
    },
	'outfile'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
  'width'    : {
    'value'     : 256,
    'type'      : 'int',
    'max'     : 512,
    'min'     : 0
    },
  'offset'    : {
    'value'     : 0,
    'type'      : 'int',
    'max'     : 255,
    'min'     : 0
    },    
  'speed'       : {
    'value'           : 1,
    'type'            : 'float',
    'max'         : 4.00,
    'min'         : 0.25
    }
  })

  zBuffer = getZBuffer(options)
  frames = []

  for frameID in range(int(options.get('width')*options.get('speed'))):
    frames.append(getHdmaList(frameID, zBuffer, options))

  currentFramePointer = 0
  framePointers = []
  for frame in frames:
    framePointers.append(currentFramePointer)
    currentFramePointer += reduce(lambda carry, entry: carry + len(entry), frame, 0)

  try:
    outFile = open( options.get('outfile'), 'wb' )
  except IOError:
    logging.error( 'unable to access required output-file %s' % options.get('outfile') )
    sys.exit(1)

  outFile.write(HEADER_MAGIC)

  outFile.write(chr(HDMA_TYPE_SCROLL))
  
  outFile.write(chr(len(frames) & 0xff))
  outFile.write(chr((len(frames) & 0xff00) >> 8 ))

  outFile.seek(HEADER_SIZE)
  for framePointer in framePointers:
    framePointer += HEADER_SIZE + len(framePointers)*2
    outFile.write(chr(framePointer & 0xff))
    outFile.write(chr((framePointer & 0xff00) >> 8 ))

  #write frames
  for frame in frames:
    [outFile.write(byte) for entry in frame for byte in entry.getCharData()]

  logging.info('Successfully wrote hdma animation file %s.' % options.get('outfile'))

def getZBuffer(options):
  if not os.path.exists(options.get('infolder')):
    logging.error( 'Error, input folder "%s" is nonexistant.' % options.get('infolder') )
    sys.exit(1)

  files = [frame for root, dirs, names in os.walk(options.get('infolder')) for frame in names if os.path.splitext(frame)[1] in ALLOWED_FRAME_FILETYPES]

  files.sort()

  filename = options.get('infolder') + "/" + files[0]
  try:
    inputImage = Image.open(filename)

  except IOError:
    logging.error( 'Unable to access input file "%s".' % filename )
    sys.exit(1)

  image = inputImage.convert('P', palette=Image.ADAPTIVE, colors=256).convert('RGB')

  return [1.0 + graconGfx.Color(image.getpixel((0, scanline))).getBrightnessCoefficient() for scanline in range( image.size[1])]


def getHdmaList(frameID, zBuffer, options):
  scrollPosition = (frameID * options.get('speed')) % options.get('width')
  rawList = [int(scrollPosition*scanline+options.get('offset')) for scanline in zBuffer]
  return optimizeHdmaList(rawList)

def optimizeHdmaList(inList):

  #remove serial duplicates
  outList = []
  for entry in [Hdma(entry) for entry in inList]:
    if 0 == len(outList) or outList[-1] != entry:
      outList.append(entry)
    else:
      +outList[-1]

  #remove repeat counts
  outList2 = []
  for entry in outList:
    if 0 == len(outList2) or 1 != outList2[-1].count or 1 != entry.count:
      outList2.append(entry)
    else:
      outList2[-1].add(entry)

  #split entries over 127
  outList3 = []
  for entry in outList2:
    if 127 < entry.count:
      new = Hdma(0)
      new.count = 127
      new.value = entry.value
      new.repeat = entry.repeat
      entry.count = entry.count - 127
      outList3.append(new)
      outList3.append(entry)
    else:
      outList3.append(entry)

  outList3.append(Hdma(False))
  return outList3

class Hdma():
  def __init__(self, value):
    if False is value:
      self.count = 0
      self.repeat = False
      self.value = []
    else:
      self.count = 1
      self.repeat = False
      self.value = [value]

  def __eq__(self, other):
    return self.value == other.value

  def __ne__(self, other):
    return self.value != other.value

  def __pos__(self):
    self.count = self.count +1

  def __len__(self):
    return (len(self.value)*2)+1

  def __repr__(self):
    return "count:%s value%s repeat:%s" % (self.count, self.value, self.repeat)

  def add(self, other):
    self.repeat = True
    self.count = self.count +1
    self.value.append(other.value[0])

  def getCharData(self):
    out = []
    out.append(chr(self.count | 0x80 if self.repeat else self.count))
    for byte in self.value:
      out.append(chr(byte & 0xff))
      out.append(chr(byte >> 8 & 0xff))

    return out

if __name__ == "__main__":
	main()

