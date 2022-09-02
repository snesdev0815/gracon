#!/usr/bin/env python2.7

__author__ = "Matthias Nagler <matt@dforce.de>"
__url__ = ("dforce3000", "dforce3000.de")
__version__ = "0.1"


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

logging.basicConfig( level=logging.DEBUG, format='%(message)s')
pp = pprint.PrettyPrinter(indent=2)

options = {}

INFINITY = 1e300000
ALLOWED_FRAME_FILETYPES = ('.png', '.gif', '.bmp')


def main():
  options = graconUserOptions.Options( sys.argv, {
	'infile'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
	'outfolder'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
	'flags'		: {
	  'value'			: 'gfx_sprite',
	  'type'			: 'str'
	  }    
  })

  if sys.hexversion < 0x02060000 or sys.hexversion >= 0x03000000:
    logging.error( 'Sorry, this program only runs with python 2.6+, but not 3.x+ at the moment.')
    sys.exit(1)
  
  if not os.path.exists(options.get('infile')):
	logging.error( 'Error, input folder "%s" is nonexistant.' % options.get('infile'))
	sys.exit(1)

  try:
      inputImage = Image.open(options.get('infile'))
  except IOError:
      logging.error( 'Unable to load input image "%s"' % options.get('infile'))
      sys.exit(1)
      
  spritesheet = inputImage.convert('P', palette=Image.ADAPTIVE, colors=256).convert('RGB')
  
  palette = [getpixel(spritesheet, x, 0) for x in range(0,64,4)]
  mask = getpixel(spritesheet, spritesheet.width-1, 0)

  #calculate frame width
  i = 0;
  while mask != getpixel(spritesheet, (i+1)*8, 16):
      i = i+1

  width = i*8

  
  #get tile under palette:
  o = 0
  while mask != getpixel(spritesheet, 8, (o)*8):
      o += 1

  #calculate frame height
  i = 0
  while mask != getpixel(spritesheet, 8, (i+o+1)*8):
      i += 1

  height = i*8

  print (width,height)
  
  definitions = open(re.sub(r"\.[a-zA-Z]+$", '.txt', options.get('infile')), 'r')

  ensureDirectory(options.get('outfolder'))

  animation = 0
  for definition in re.findall(r"([a-zA-Z0-9\._]+) ([0-9]+|STOP) PAL([0-9]{1}) ([0-9A-Z]+)", definitions.read()):
      print definition
      animFolder = '%s/%s.%s' % (options.get('outfolder'), definition[0], options.get('flags'))
      ensureDirectory(animFolder)

      savePalette(palette, animFolder)

      loopstart = len(definition[3])-1 if definition[1] == 'STOP' else int(definition[1])

      for i in range(len(definition[3])):
          delay = int( definition[3][i] if unicode(definition[3][i], 'utf-8').isnumeric() else ord(definition[3][i]) - ord('A') + 10 )
          frame = Image.new( "RGB", (width,height))
          x = i*(width+8)+8
          y = animation*(height+8)+((o+1)*8)
          region = spritesheet.crop((x, y, x+width, y+height))
          frame.paste(region,(0,0,width,height))
          frame.save('%s/%03d.delay%03d%s.png' % (animFolder,i, delay, '.loopstart' if i == loopstart and i > 0 else ''), 'PNG')
      
      animation += 1
      
def savePalette(palette, folder):
    image = Image.new( "RGB", (len(palette),1))
    for x in range(len(palette)):
        image.putpixel((x,0), palette[x].getPIL())
    image.save('%s/palette.png' % folder, 'PNG')


def ensureDirectory(folder):
  if not os.path.exists(folder):
    os.makedirs(folder)

def getpixel(image, x, y):
  return graconGfx.Color(image.getpixel((x,y)))

if __name__ == "__main__":
	main()

