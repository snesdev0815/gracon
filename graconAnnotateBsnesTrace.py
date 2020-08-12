#!/usr/bin/env python2.7

__author__ = "Matthias Nagler <matt@dforce.de>"
__url__ = ("dforce3000", "dforce3000.de")
__version__ = "0.1"

'''
annotates bsnes trace file according to symbol file generated by wla-dx
'''

import os
import re
import sys
import math
import time
import string
import graconUserOptions
import logging
import struct
import subprocess

logging.basicConfig( level=logging.DEBUG, format='%(message)s')

options = {}


def main():
  options = graconUserOptions.Options( sys.argv, {
	'tracefile'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
	'outfile'		: {
	  'value'			: '',
	  'type'			: 'str'
	  },
    'symbolfile'       : {
      'value'           : '',
      'type'            : 'str'
      },	  
	'indentstack'	: {
	  'value'			: True,
	  'type'			: 'bool'
	  },
  'annotatefunction'  : {
    'value'     : True,
    'type'      : 'bool'
    },    
    'annotatetarget'        : {
      'value'           : True,
      'type'            : 'bool'
      }
  })

  
  try:
    trace = open("%s" % options.get('tracefile'), 'r')
  except IOError:
    logging.error( 'unable to access required file %s' % options.get('tracefile'))
    sys.exit(1)  

  try:
    sym = open("%s" % options.get('symbolfile'), 'r')
  except IOError:
    logging.error( 'unable to access required file %s' % options.get('symbolfile'))
    sys.exit(1)  

  try:
    output = open("%s" % options.get('outfile'), 'w')
  except IOError:
    logging.error( 'unable to access required file %s' % options.get('outfile'))
    sys.exit(1)  

  traceLines = trace.readlines()

  #get rom, ram symbols
  symbols = {}
  symLines = sym.readlines()
  symLines = symLines[symLines.index('''[labels]
''')+1:symLines.index('''[definitions]
''')]
  [symbols.update({line[:2]+line[3:7]: line[8:]}) for line in symLines]

  stackMax = reduce(lambda val, memo: max(val,memo),[int(line[54:57],16) for line in traceLines if line[:2] != '..'])

  for line in traceLines:
    if options.get('annotatefunction'):
      try:
        val = symbols[line[:6]]
        line = "%s %s" % (line[:-1], val)
      except KeyError:
        pass

    if options.get('annotatetarget'):
      try:
        val = symbols[line[22:28]]
        line = "%s [%s" % (line[:-1], val)

      except KeyError:
        pass

    if options.get('indentstack'):
      try:
        indent = (stackMax-int(line[54:57],16))/2
      except ValueError:
        indent = 0

      line = "%s%s" % (indent*" ", line)

    output.write(line)

  logging.info('Done!')


class Symbol():
  def __init__(self, line):
    self.adress = int(line[4:10], 16)
    self.label = line[11:]

  def getLabel(self):
    return self.label

  #required for sort, compare, hash
  def __hash__(self):
    return self.adress

  #comparators
  def __eq__(self, other):
    return self.adress == other.adress if isinstance(other, Symbol) else self.adress == other

  def __cmp__(self, other):
    return self.adress == other.adress if isinstance(other, Symbol) else self.adress == other

  def __ne__(self, other):
    return self.adress != other.adress if isinstance(other, Symbol) else self.adress != other

if __name__ == "__main__":
	main()
