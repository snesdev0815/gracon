#!/usr/bin/env python2.7

__author__ = "Matthias Nagler <matt@dforce.de>"
__url__ = ("dforce3000", "dforce3000.de")
__version__ = "0.1"

'''
compiles text files from language input
one line per textstring
linebreaks are not parsed
text format is utf8


textfile format is 
identifier=textstring

identifier is /[\w\d]*/

# at beginning of line denotes comment

textstring may contain control codes in the form of
<command [, arg0, arg1]>

looks for language folders in infolder.
each language folder may contain multiple textfiles like so:
_text
 |_en
   |_error.txt
   |_items.txt
 |_de
   |_error.txt
   |_items.txt

the resulting generated label names look like this:
error.sometextlabel

en is the default textfolder
any double entry inside one textfile will generate an error
any textstring inside default language folder but not present in other language folder will generate an error
unknown commands will generate an error

outfile will contain the following in wla-dx 65816 format:
-textstring id list (language agnostic, e.g. you can't select strings of different languages, these are handled internally)
  -max string id appended
-language id list
  -language max id appended
-language pointer list (contains pointers to language textstring pointertables)
-textstring pointer list, one for each language
-textstrings for each language
  


'''

import os
import re
import sys
import math
import time
import wave
import logging
import graconUserOptions

STRING_LENGTH_MAX = 62
logging.basicConfig( level=logging.ERROR, format='%(message)s')

def defaultControlCode(target, args):
  data = ".db %s" % target
  for arg in args:
    data += ", %s" % arg
  return data

def wordControlCode(target, args):
  data = ".db %s\n" % target
  data += ".dw %s" % ",".join([("%s" % arg) for arg in args])
  return data

def spriteControlCode(target, args):
  data = ".db %s\n" % target
  data += ".dw %s\n" % args[0]
  data += ".db %s, %s\n" % (args[1], args[2])
  return data

def numberControlCode(target, args):
  data = ".db %s" % target
  data += ", %s&$ff" % args[0]
  data += ", (%s>>8)&$ff" % args[0]
  data += ", %s>>16" % args[0]
  data += ", %s" % args[1]
  return data

def stringControlCode(target, args):
  data = ".db %s" % target
  data += ", %s&$ff" % args[0]
  data += ", (%s>>8)&$ff" % args[0]
  return data

def indirectPointerControlCode(target, args):
  data = ".db %s" % target
  data += ", %s&$ff" % args[0]
  data += ", (%s>>8)&$ff" % args[0]
  return data

def directPointerControlCode(target, args):
  data = ".db %s" % target
  data += ", %s&$ff" % args[0]
  data += ", (%s>>8)&$ff" % args[0]
  data += ", %s>>16" % args[0]
  return data  
  
controlCodes = {
  "end" : {
      "target" : "TC_end",
      "args" : 0,
      "callback" : defaultControlCode
  },
  "string" : {
      "target" : "TC_sub",
      "args" : 1,   #word-index of textstring
      "callback" : stringControlCode
  },
  "indirect-pointer" : {
      "target" : "TC_iSub",
      "args" : 1,   #indirect word-pointer to textstring
      "callback" : defaultControlCode
  },
  "direct-pointer" : {
      "target" : "TC_dSub",
      "args" : 1,
      "callback" : directPointerControlCode
  },
  "indirect-to-direct-pointer" : {
      "target" : "TC_diSub",
      "args" : 1,
      "callback" : indirectPointerControlCode
  },
  "position" : {
      "target" : "TC_pos",
      "args" : 2,   #x,y position in 8x8 tiles
      "callback" : defaultControlCode
  },
  "break" : {
      "target" : "TC_brk",
      "args" : 0,
      "callback" : defaultControlCode
  },
  "hex" : {
      "target" : "TC_hToS",
      "args" : 2,
      "callback" : numberControlCode
  },
  "decimal" : {
      "target" : "TC_dToS",
      "args" : 2,
      "callback" : numberControlCode
  },
  "option" : {
      "target" : "TC_opt",
      "args" : 1,
      "callback" : defaultControlCode
  },
  "sprite" : {
      "target" : "TC_sprite",
      "args" : 3,
      "callback" : spriteControlCode
  },  
}

def main():
  options = graconUserOptions.Options( sys.argv, {
    'infolder'      : {
      'value'           : '',
      'type'            : 'str'
      },
    'outfile'      : {
      'value'           : '',
      'type'            : 'str'
      },
    'substlang'      : {
      'value'           : True,
      'type'            : 'bool'
      },      
    'defaultlang'      : {
      'value'           : 'en',
      'type'            : 'str'
      },      
  })

  regexComment = re.compile('^#')
  regexStringStart = re.compile('^[\d\w]*=')
  regexStringCapture = re.compile('(^[\d\w]*)=')  
  
  if not os.path.exists(options.get('infolder')):
    logging.error( 'Error, input folder "%s" is nonexistant.' % options.get('infolder') )
    sys.exit(1)

  languages = [folder for root, dirs, names in os.walk(options.get('infolder')) for folder in dirs]

  if not options.get('defaultlang') in languages:
    logging.error( 'Error, default language folder "%s" is nonexistant.' % options.get('defaultlang') )
    sys.exit(1)

  textstrings = {};
  for language in languages:
    textstrings[language] = {}
    currentPath = "%s%s/" % (options.get('infolder'), language)
    textfiles =  [filename for root, dirs, names in os.walk(currentPath) for filename in names]
    for textfile in textfiles:
      currentFile = open("%s%s" % (currentPath, textfile), 'r')
      currentTextstrings = currentFile.readlines()
      namespace = textfile.split('.')[0]
      textstrings[language][namespace] = {}
      currentIdentifier = None
      currentString = ''
      for line in currentTextstrings:
        if regexComment.search(line):
          nop()
        elif regexStringStart.search(line):
          #write out last found string
          if currentIdentifier:
            if not currentIdentifier in textstrings[language][namespace]:
              textstrings[language][namespace][currentIdentifier] = parseString(currentString)
            else:
              logging.error( 'Error, language "%s", namespace "%s" contains more than one instance of string "%s".' % (language, namespace, currentIdentifier) )
              sys.exit(1)

          match = regexStringCapture.split(line)
          currentIdentifier = match[1]
          currentString =  match[2]
        elif currentIdentifier:
          currentString += line
      if currentIdentifier:
        if not currentIdentifier in textstrings[language][namespace]:
          textstrings[language][namespace][currentIdentifier] = parseString(currentString)
        else:
          logging.error( 'Error, language "%s", namespace "%s" contains more than one instance of string "%s".' % (language, namespace, currentIdentifier) )
          sys.exit(1)

  outFile = open(options.get('outfile'), 'w')

  outFile.write(';autogenerated text file, do not edit manually\n\n')
  
  #language definition
  outFile.write('.enum 0 export ;language id definition\n')
  for language in languages:
    outFile.write(' LANGUAGE.%s db\n' % language.upper())
  outFile.write(' LANGUAGE.MAX ds 0\n')
  outFile.write('.ende\n\n')

  #default lanuguage
  outFile.write('.def STRING.LANGUAGE.DEFAULT LANGUAGE.%s ;default language\n' % options.get('defaultlang').upper())
  outFile.write('.export STRING.LANGUAGE.DEFAULT\n\n')
  
  #language lookup tables
  outFile.write('.section "text.language.lut" superfree\n')
  outFile.write('text.language.lut:\n')
  for language in languages:
    outFile.write(' .dw text.language.lut.%s\n' % language.lower())
    outFile.write(' .db :text.language.lut.%s\n' % language.lower())      
  outFile.write('.ends\n\n')
  
  #language-agnostic string id definition
  outFile.write('.enum 0 export ;string id definition\n')
  outFile.write(' text.void db\n')
  for namespace in textstrings[options.get('defaultlang')]:
    outFile.write(' ;namespace %s:\n' % namespace)
    for string in textstrings[options.get('defaultlang')][namespace]:
      outFile.write(' text.%s.%s db\n' % (namespace,string))
  outFile.write(' text.max.id ds 0\n')    
  outFile.write('.ende\n\n')
  
  #language string lookup tables
  for language in textstrings:
    outFile.write('.section "text.language.lut.%s" superfree\n' % language)
    outFile.write('text.language.lut.%s:\n' % language)
    outFile.write(' .dw 0\n')
    outFile.write(' .db 0\n')
    for namespace in textstrings[options.get('defaultlang')]:
      for string in textstrings[options.get('defaultlang')][namespace]:
        try:
          currentLang = textstrings[language][namespace][string]
          currentLang = language
        except KeyError:
          if not options.get('substlang'):
            logging.error( 'Error, language folder "%s", namespace "%s" is missing textstring "%s".' % (language, namespace, string) )
            sys.exit(1)

          currentLang = options.get('defaultlang')
        outFile.write(' .dw text.%s.%s.%s\n' % (currentLang, namespace, string))
        outFile.write(' .db :text.%s.%s.%s\n' % (currentLang, namespace, string))
    outFile.write('.ends\n\n')
  
  #actual textstrings
  for language in textstrings:
    outFile.write('.section "text.language.strings.%s" superfree\n' % language)
    for namespace in textstrings[language]:
      for string in textstrings[language][namespace]:
        outFile.write('\ntext.%s.%s.%s:\n' % (language, namespace, string))
        for data in textstrings[language][namespace][string]:
          outFile.write(data)
    outFile.write('\n.ends\n\n')
  
  logging.info('Successfully wrote some textfiles.')

def parseString(string):
  string = re.sub('[\t\r\n]*', '', string)
  result = []
  for substring in re.split('(<[\w\d\., \-\+&$%\(\)]*>)', string):
    if re.match('<[\w\d\., \-\+&$%\(\)]*>', substring):
      chunks = [chunk.strip() for chunk in substring[1:-1].split(',')]
      command = chunks.pop(0)
      args = chunks
      try:
        controlCodes[command]
      except KeyError:
        logging.error('Error, controlCode "%s" is unsupported.' % command)
        sys.exit(1)
      if len(args) != controlCodes[command]['args']:
        logging.error('Error, controlCode "%s" requires "%s" arguments, "%s" supplied.' % (command, controlCodes[command]['args'], len(args)))
        sys.exit(1)
      result.append(controlCodes[command]['callback'](controlCodes[command]['target'], args))
    elif '' != substring:
      if len(substring) > STRING_LENGTH_MAX:
        while len(substring) > STRING_LENGTH_MAX:
          result.append('.db "%s"' % substring[0:STRING_LENGTH_MAX])
          substring = substring[STRING_LENGTH_MAX:]
      result.append('.db "%s"' % substring)
  return "\n".join(result)

def nop():
  return False

if __name__ == "__main__":
	main()

