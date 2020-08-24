#!/usr/bin/env python2.7

import os
import re
import sys
import math
import logging

BRR_BLOCK_SAMPLES = 16
BRR_BLOCK_LENGTH = 9

BRR_ONE_SHOT_EXTEND = 25	#someone said non-looping samples are cut out 25 samples before their actual end. Adding these doesn't hurt, I guess...
BRR_MAX_RANGE_SHIFT	= 13
BRR_FILTERS = 4
SAMPLE_CUT_THRESHOLD = 256	#cut looping samples above this size instead of multipliying their size to make them divisible by 16

MOD_BYTES_PER_CHANNEL = 4
MOD_ROWS_PER_PATTERN = 64
MOD_PERIODS_PER_OCTAVE = 12
MOD_INSTRUMENT_DATA = 20
MOD_INSTRUMENT_DATA_LENGTH = 30
MOD_INSTRUMENT_COUNT = 31

#file offsets, converted modfile
SPCMOD_INSTRUMENT_DATA	= 0
SPCMOD_SONG_LENGTH		= 248
SPCMOD_CHANNEL_COUNT    = 249
SPCMOD_PATTERN_COUNT	= 250
SPCMOD_SEQUENCE			= 251
SPCMOD_PATTERN_POINTER	= 379
SPCMOD_PATTERN_DATA		= 509

SPCMOD_EMPTY_CHANNEL	= 0xff
SPCMOD_INVALID_PERIOD	= 0xff

INSTR_RES_MULTI = 1

validModSignatures = [ 'M.K.', '1CHN', '2CHN', '3CHN', '4CHN', '5CHN', '6CHN', '7CHN', '8CHN']


globalSampleBuffer = {
  'last'		: 0,
  'beforeLast'	: 0
}

statistics = {
  'samples'	: 0,
  'filter'	: { 0:0,1:0,2:0,3:0 },
  'range'	: { 0:0,1:0,2:0,3:0,4:0,5:0,6:0,7:0,8:0,9:0,10:0,11:0,12:0 },
  'maxError': 0,
  'minError': BRR_BLOCK_SAMPLES * 0xffff
}

logging.basicConfig(
                    level=logging.ERROR,
                    format='%(message)s')
                    

def main():
    if len( sys.argv ) < 3 or len( sys.argv ) > 4:
      logging.info( 'Pro tracker MOD to SNES format converter' )
      logging.info( '2011-01-02 matt@dforce3000.de' )
      logging.info( 'Usage:' )
      logging.info( '%s infile outfilebase [romfile]' % sys.argv[0] )
      logging.info( 'romfile is optional. If present, generated file will be appended to copy of romfile.' )
      logging.info( 'useful for reviewing purposes on real hardware.' )
      sys.exit(1)
      

    inFileName = sys.argv[1]
    outFileName = ( '%s.spcmod' % sys.argv[2] )
    
    if 4 == len( sys.argv ):
      inRomFileName = sys.argv[3]
      outRomFileName = '%s.sfc' % sys.argv[2]
    else:
      inRomFileName = False
      outRomFileName = False

    try:
      inFile = open( inFileName, 'rb' )
    except IOError:
      logging.error( 'unable to access input file %s' % inFileName )
      sys.exit(1)

    inRomFile = False
    if inRomFileName:
      try:
        inRomFile = open( inRomFileName, 'rb' )
      except IOError:
        logging.error( 'unable to access input rom file %s' % inRomFileName )
        sys.exit(1)
        
      
    inFileData = inFile.read()

    logging.debug( 'module files accessed successfully' )
    
    if not isValidModule( inFileData ):
      logging.error( '%s is not a valid MOD file.' % inFileName )
      sys.exit(1)
    
    moduleData = {}
    moduleData['name']				= getModuleName( inFileData )
    moduleData['channelCount']      = getModuleChannelCount(inFileData)
    moduleData['length']			= getModuleLength( inFileData )
    moduleData['sequence']			= getModulePlaySequence( inFileData )
    moduleData['patternCount']		= getModulePatternCount( moduleData['sequence'] )
    moduleData['sampleBufferPos']	= getModuleSampleBufferPosition( moduleData['patternCount'], moduleData['channelCount'])
    moduleData['instruments']		= getModuleInstruments( inFileData, moduleData['sampleBufferPos'] )
    moduleData['patterns']			= getModulePatterns( inFileData, moduleData['patternCount'], moduleData['channelCount'] )
    
    convertedModule = {
      'length'			: moduleData['length'],
      'channelCount'    : moduleData['channelCount'],
      'patternCount'	: moduleData['patternCount'],
      'sequence'		: moduleData['sequence'],
      'patterns'		: convertPatterns( moduleData['patterns'] ),
      'instruments'		: convertInstruments( moduleData['instruments'] )
    }
    
    try:
      outFile = open( outFileName, 'wb' )
    except IOError:
      logging.error( 'unable to access output file %s' % outFileName )
      sys.exit(1)

    outRomFile = False
    if outRomFileName:
      try:
        outRomFile = open( outRomFileName, 'wb' )
      except IOError:
        logging.error( 'unable to access output rom file %s' % outRomFileName )
        sys.exit(1)
        
    writeOutputFile( outFile, convertedModule )

    if inRomFileName and outRomFile:
      outFile.close()
      outFile = open( outFileName, 'rb' )
      outRomFile.write(inRomFile.read())
      
      outFile.seek(0,2)
      songSize = outFile.tell()
      outRomFile.write(chr(songSize & 0xff))
      outRomFile.write(chr((songSize >> 8) & 0xff))
      
      outFile.seek(0)
      outRomFile.write(outFile.read())
      outRomFile.seek( 0x7ffff )
      outRomFile.write(chr(0xa5))
      inRomFile.close()
      outRomFile.close()
      
    logging.info( 'Successfully wrote converted module %s to %s' % tuple( [moduleData['name'], outFileName] ) )
    outputStatistics()
    
    inFile.close()
    outFile.close()
    

def outputStatistics():
  global statistics
  
  outputTuple = tuple([
    statistics['samples'],
    statistics['minError'],
    statistics['maxError'],
    statistics['filter'][0],
    statistics['filter'][1],
    statistics['filter'][2],
    statistics['filter'][3],
    statistics['range'][0],
    statistics['range'][1],
    statistics['range'][2],
    statistics['range'][3],
    statistics['range'][4],
    statistics['range'][5],
    statistics['range'][6],
    statistics['range'][7],
    statistics['range'][8],
    statistics['range'][9],
    statistics['range'][10],
    statistics['range'][11],
    statistics['range'][12],
  ])
  
  logging.info( 'Converted %d BRR samples with error range %d-%d.\nFilter usage: 0:%d 1:%d 2:%d 3:%d\nRange usage: 0:%d 1:%d 2:%d 3:%d 4:%d 5:%d 6:%d 7:%d 8:%d 9:%d 10:%d 11:%d 12:%d' % outputTuple )

def getModuleLength( mod ):
  return ord( mod[950] )


def getModuleName( mod ):
  return mod[0:20]


def isValidModule( mod ):  
  global validModSignatures
  return mod[1080:1084] in validModSignatures

def getModuleChannelCount(mod):
  signature = mod[1080:1084]
  if '1CHN' == signature:
    return 1
  elif '2CHN' == signature:
    return 2
  elif '3CHN' == signature:
    return 3
  elif signature in ['M.K.', '4CHN']:
    return 4
  elif '5CHN' == signature:
    return 5
  elif '6CHN' == signature:
    return 6
  elif '7CHN' == signature:
    return 7
  elif '8CHN' == signature:
    return 8
  else:
    return 0
  
def writeOutputFile( outFile, mod ):
  writeChar( outFile, SPCMOD_SONG_LENGTH, mod['length'] )
  writeChar( outFile, SPCMOD_CHANNEL_COUNT, mod['channelCount'] )
  writeChar( outFile, SPCMOD_PATTERN_COUNT, mod['patternCount'] )
  
  writeSequence( outFile, mod['sequence'] )
  patternPointers = writePatterns( outFile, mod['patterns'] )
  writePatternPointers( outFile, patternPointers['patterns'] )
  samplePointers = writeSamples2( outFile, patternPointers['end'], mod['instruments'] )
  writeInstruments( outFile, samplePointers, mod['instruments'] )
  


def writeChar( outFile, offset, data ):
  outFile.seek( offset )
  outFile.write( chr( data ) )


def writeSequence( outFile, sequence ):
  outFile.seek( SPCMOD_SEQUENCE )
  for pattern in sequence:
    outFile.write( chr( pattern ) )


def writePatterns( outFile, patterns ):
  patternPointer = []
  outFile.seek( SPCMOD_PATTERN_DATA )
  for pattern in patterns:
    patternPointer.append( outFile.tell() - SPCMOD_PATTERN_DATA )	#relative pointer to pattern
    for channel in pattern:
      if channel['valid']:
        outFile.write( chr( channel['instrument'] ) )
        outFile.write( chr( channel['period'] ) )
        outFile.write( chr( channel['effectCommand'] ) )
        outFile.write( chr( channel['effectData'] ) )
      else:
        outFile.write( chr( SPCMOD_EMPTY_CHANNEL ) )
  
  patternPointer.append( outFile.tell() - SPCMOD_PATTERN_DATA )	#relative pointer to end of last pattern.
  return {
    'patterns'	: patternPointer,
    'end'		: outFile.tell()
  }


def writePatternPointers( outFile, patternPointers ):
  outFile.seek( SPCMOD_PATTERN_POINTER )
  for pointer in patternPointers:
    outFile.write( chr( (pointer & 0xff00) >> 8 ) )
    outFile.write( chr( (pointer & 0xff) ) )

def writeSamples2( outFile, sampleBufferPos, instruments ):
  outFile.seek( sampleBufferPos )
  
  samplePointer = []
  for instrument in instruments:
    samplePointer.append( {
      'start'   : outFile.tell(),
      'repeatStart' : outFile.tell() + ( (instrument['repeatStart'] // BRR_BLOCK_SAMPLES) * BRR_BLOCK_LENGTH )
    } )
    for i in range( len( instrument['samples'] ) ):
      outFile.write( chr( instrument['samples'][i] ) )
  return samplePointer

def writeSamples( outFile, sampleBufferPos, instruments ):
  outFile.seek( sampleBufferPos )
  
  samplePointer = []
  for instrument in instruments:
    samplePointer.append( {
      'start'		: outFile.tell(),
      'repeatStart' : outFile.tell() + ( (instrument['repeatStart'] // BRR_BLOCK_SAMPLES) * BRR_BLOCK_LENGTH )
    } )
    logging.debug("writing instrument %x, sample block length %x (effective samples %x), block repeat %x, modfile start: %x, repeat %x" % (instrument['id']+1, len(instrument['samples']), len(instrument['samples'])*16, instrument['repeatStart'] // BRR_BLOCK_SAMPLES, samplePointer[len(samplePointer)-1]['start'], samplePointer[len(samplePointer)-1]['repeatStart'] ) )
    for i in range( len( instrument['samples'] ) ):
      sampleBlock = instrument['samples'][i]
      loop = 1 if instrument['repeatFlag'] else 0
      end = 1 if ( i == len( instrument['samples'] ) - 1 ) else 0
      header = ( sampleBlock['range'] << 4 ) | ( sampleBlock['filter'] << 2 ) | ( loop << 1 ) | end
      
      outFile.write( chr( header ) )
      for i in range( 8 ):
        outFile.write( chr( mergeBrrSample( i, sampleBlock['samples'] ) ) )
  return samplePointer


def mergeBrrSample( pos, samples ):
  return ( samples[pos*2] << 4 ) | samples[(pos*2)+1] 


def writeInstruments( outFile, samplePointers, instruments ):
  outFile.seek( SPCMOD_INSTRUMENT_DATA )
  for i in range(len(instruments)):
    outFile.write( chr( (samplePointers[i]['start'] & 0xff00) >> 8 ) )
    outFile.write( chr( (samplePointers[i]['start'] & 0xff) ) )
    outFile.write( chr( instruments[i]['finetune'] ) )
    outFile.write( chr( instruments[i]['volume'] ) )
    outFile.write( chr( (samplePointers[i]['repeatStart'] & 0xff00) >> 8 ) )
    outFile.write( chr( (samplePointers[i]['repeatStart'] & 0xff) ) )
    outFile.write( chr(  (instruments[i]['adsr'] & 0xff00) >> 8  ) )
    outFile.write( chr(  (instruments[i]['adsr'] & 0xff)  ) )

def convertInstruments( inputInstruments ):
  convertedInstruments = []
  for instrument in inputInstruments:
    convertedInstruments.append( convertInstrument( instrument ) )
  return convertedInstruments


def convertInstrument( inputInstrument ):
  multipliedInstrument = multiplyInstrumentResolution( inputInstrument, INSTR_RES_MULTI )
  paddedInstrument = padInstrumentSamples( multipliedInstrument )
  return {
    'id'          : inputInstrument['id'],
    'finetune'		: paddedInstrument['finetune'],
    'volume'		: paddedInstrument['volume'],
    'repeatStart'	: paddedInstrument['repeatStart'],
    'repeatFlag'	: paddedInstrument['repeatFlag'],
    'adsr' : inputInstrument['adsr'],
    'samples'		: convertInstrumentSamples2( paddedInstrument['samples'], paddedInstrument['repeatStart'], paddedInstrument['repeatFlag'] )
  }

def multiplyInstrumentResolution( inputInstrument, factor ):
  return {
    'id' : inputInstrument['id'],
    'finetune'		: inputInstrument['finetune'],
    'volume'		: inputInstrument['volume'],
    'repeatStart'	: inputInstrument['repeatStart'] * factor,
    'repeatLength'	: inputInstrument['repeatLength'] * factor,
    'samples'		: multiplySampleResolution( inputInstrument['samples'], factor )
  }


def multiplySampleResolution( samples, factor ):
  outputSamples = []
  for sample in samples:
    for i in range( factor ):
      outputSamples.append( sample )
  return outputSamples

def padInstrumentSamples( inputInstrument ):
  preLoopSamples = inputInstrument['samples'][:inputInstrument['repeatStart']]
  if inputInstrument['repeatLength'] > 0:
    postLoopSamples = inputInstrument['samples'][inputInstrument['repeatStart']:inputInstrument['repeatStart']+inputInstrument['repeatLength']]
    repeatFlag = True
  else:
    repeatFlag = False
    postLoopSamples = inputInstrument['samples'][inputInstrument['repeatStart']:]
  postLoopSamplesOrig = postLoopSamples

  #pad sample start - repeat start until multiple of 16
  while len( preLoopSamples ) % BRR_BLOCK_SAMPLES != 0:
    preLoopSamples.insert( 0, getEmptySample() )

  
  #prepend 16 samples to any sample to avoid click on note trigger
  for i in range(BRR_BLOCK_SAMPLES):
    preLoopSamples.insert( 0, getEmptySample() )


  #append 25 samples to one shot-instrument
  if not repeatFlag:
    for i in range(BRR_ONE_SHOT_EXTEND):
      postLoopSamples.append( getEmptySample() )

  #pop samples of big looping or one-shot samples until multiple of 16
  if len( postLoopSamples ) > SAMPLE_CUT_THRESHOLD or not repeatFlag:
    while len( postLoopSamples ) % BRR_BLOCK_SAMPLES != 0:
      postLoopSamples.pop()
  #multiply short looping samples until they are multiple of 16
  else:
    while len( postLoopSamples ) % BRR_BLOCK_SAMPLES != 0:
      postLoopSamples.extend( postLoopSamplesOrig )
  
  return {
    'finetune'		: inputInstrument['finetune'],
    'volume'		: inputInstrument['volume'],
    'repeatStart'	: len( preLoopSamples ),
    'repeatFlag'	: repeatFlag,
    'samples'		: groupSamples( preLoopSamples + postLoopSamples ) if len( inputInstrument['samples'] ) >= BRR_BLOCK_SAMPLES else []
  }


def getEmptySample():
  return 0


#group samples into blocks of 16 sample each
def groupSamples( inputSamples ):
  groupedSamples = []
  while len( inputSamples ) > 0:
    sampleBlock = []
    for i in range( BRR_BLOCK_SAMPLES ):
      sampleBlock.append( inputSamples.pop( 0 ) )
    groupedSamples.append( sampleBlock )
  return groupedSamples

def convertInstrumentSamples2( wav_data, loop_start, loop_enabled ):
  brr_data = []
  base_adjust_rate = 0.0004
  adjust_rate = base_adjust_rate
  loop_block = loop_start / 16
  wimax = len(wav_data)
  wi = 0
  best_samp = range(18)
  best_samp[0] = 0
  best_samp[1] = 0

  total_blocks = wimax
  total_error = 0
  avg_error = 0
  min_error = 1e20
  max_error = 0
  overflow = 0

  while(wi != wimax):
    if not overflow:
      p = [int16(sample) for sample in wav_data[wi]]
    best_err = 1e20
    blk_samp = range(18)
    blk_samp[0] = best_samp[0]
    blk_samp[1] = best_samp[1]
    best_data = range(9)
    for iFilter in range(BRR_FILTERS):
      if (iFilter != 0):
        if ((wi == 0) | (wi == loop_block)):
          continue
      #starting from 2nd sample: too many loops, brr 0-15
      for iRange in range(BRR_MAX_RANGE_SHIFT-1, 0, -1):

        rhalf = (1 << iRange) >> 1
        blk_err = 0
        blk_data = range(16)
        for n in range(16):

          #blk_ls = len(blk_samp) + n
          if (3 is iFilter):
            filter_s  = blk_samp[1+n] << 1  # add 128/64
            filter_s += -(blk_samp[1+n] + (blk_samp[1+n] << 2) + (blk_samp[1+n] << 3)) >> 6   # add (-13)/64
            filter_s += -blk_samp[0+n]  # add (-16)/16
            filter_s += (blk_samp[0+n] + (blk_samp[0+n] << 1)) >> 4  # add 3/16          

          elif (2 is iFilter):
            filter_s  = blk_samp[1+n] << 1  # add 64/32
            filter_s += -(blk_samp[1+n] + (blk_samp[1+n] << 1)) >> 5  # add (-3)/32
            filter_s += -blk_samp[0+n]  # add (-16)/16
            filter_s += blk_samp[0+n] >> 4  # add 1/16

          elif (1 is iFilter):
            filter_s  = blk_samp[1+n]  # add 16/16
            filter_s += -blk_samp[1+n] >> 4  # add (-1)/16

          else:
            filter_s = 0

          #undo 15 -> 16 bit conversion
          xs = p[n] >> 1

          # undo 16 -> 15 bit wrapping
          # check both possible 16-bit values
          s1 = int16(xs & 0x7FFF)
          s2 = int16(xs | 0x8000)

          # undo filtering
          s1 -= filter_s
          s2 -= filter_s

          # restore low bit lost during range decoding
          s1 <<= 1
          s2 <<= 1

          s1 = (s1 + rhalf) >> iRange
          s2 = (s2 + rhalf) >> iRange

          s1 = clamp(s1,4)
          s2 = clamp(s2,4)

          rs1 = s1 & 0xF
          rs2 = s2 & 0xF

          # -16384 to 16383
          s1 = (s1 << iRange) >> 1
          s2 = (s2 << iRange) >> 1

          # BRR accumulates to 17 bits, saturates to 16 bits, and then wraps to 15 bits
          if (iFilter >= 2):
            s1 = clamp(s1 + filter_s, 16)
            s2 = clamp(s2 + filter_s, 16)
          else:
            # don't clamp - result does not overflow 16 bits
            s1 += filter_s
            s2 += filter_s

          # wrap to 15 bits, sign-extend to 16 bits
          s1 = int16(s1 << 1) >> 1;
          s2 = int16(s2 << 1) >> 1;
          
          d1 = xs - s1
          d2 = xs - s2

          d1 *= d1
          d2 *= d2
          
          # If d1 == d2, prefer s2 over s1.
          if (d1 < d2):
            blk_err += d1
            blk_samp[2+n] = s1
            blk_data[n] = rs1
          else:
            blk_err += d2
            blk_samp[2+n] = s2
            blk_data[n] = rs2

        if (blk_err < best_err):
          best_err = blk_err
          for n in range(16):
            best_samp[n + 2] = blk_samp[n + 2]

          best_data[0] = (iRange << 4) | (iFilter << 2)

          for n in range(8):
            best_data[n + 1] = (blk_data[n * 2] << 4) | blk_data[n * 2 + 1]

      #range
    #filter loop
    overflow = 0
    for n in range(16):
      b = test_overflow(best_samp, n)
      overflow = (overflow << 1) | b

    if (overflow):
      f = range(16)
      for n in range(16):
        f[n] = adjust_rate

      for n in range(16):
        overflow <<= 1
        if (overflow & 0x8000):
          t = 0.05
          for i in range(n, 0, -1):
            t *= 0.1
            f[i] *= 1.0 + t

          t = 0.05 * 0.1
          for i in range(16):
            t *= 0.1
            f[i] *= 1.0 + t

      for n in range(16):
        p[n] = int16(p[n] * (1.0 - f[n]))
      adjust_rate *= 1.1
    else:
      adjust_rate = base_adjust_rate
      best_samp[0] = best_samp[16]
      best_samp[1] = best_samp[17]

      total_error += best_err

      if (best_err < min_error):
       min_error = best_err

      if (best_err > max_error):
       max_error = best_err

      for byte in best_data:
        brr_data.append(byte)
      
      wi += 1;

  #wi loop
  if (wimax == 0):
   min_error = 0
  else:
   avg_error = total_error / (wimax*16)

  if (0 is len(brr_data) or (not loop_enabled)):
    for asd in range(9):
      brr_data.append(0)
  brr_data[len(brr_data)-9] |= (int(loop_enabled) << 1) | 1

  return brr_data

def test_gauss(G4,G3,G2,brr_data,n):
  s = int32(G4*brr_data[0+n]) >> 11
  s += int32(G3*brr_data[1+n]) >> 11
  s += int32(G2*brr_data[2+n]) >> 11
  return (s > 0x3FFF) | (s < -0x4000)

def test_overflow(brr_data, n):
    r = test_gauss(370,1305,374,brr_data,n)
    r |= test_gauss(366,1305,378,brr_data,n)
    r |= test_gauss(336,1303,410,brr_data,n)
    return int8(r)

def convertInstrumentSamples( inputSamples, repeatStart, repeatFlag ):
  convertedSamples = []
  
  noFilterSamples = [ 0, 1, 2, repeatStart, repeatStart + 1, repeatStart + 2, len(inputSamples)-1, len(inputSamples)-2, len(inputSamples)-3 ]
  
  i = 0
  while i < len( inputSamples ):
    sampleBlock = inputSamples[i]
    forceNoFilter = True if i in noFilterSamples else False
    convertedSamples.append( convertSample( sampleBlock, forceNoFilter ) )
    i += 1
  return convertedSamples


def convertSample( inputSampleBlock, forceNoFilter ):
  optimumSample = {
    'blockError' : BRR_BLOCK_SAMPLES * 0xffff	#max possible error
  }
  globalSampleBuffer = {
    'last'			: 0,
    'beforeLast'	: 0
  }
  debugLog("starting new sample")
  for rangeVal in range( BRR_MAX_RANGE_SHIFT ):
      for filterVal in range ( BRR_FILTERS ):
        currentFilter = filterVal if forceNoFilter == False else 0
        sampleBlock = convertSampleBlock( inputSampleBlock, { 'filter' : currentFilter, 'range' : rangeVal } )
        
        
        if sampleBlock['blockError'] < optimumSample['blockError']:
          debugLog("filter %s having range %s is better having error %s instead of %s" % (currentFilter, rangeVal, sampleBlock['blockError'], optimumSample['blockError']))
          optimumSample = sampleBlock

  updateStatistics( optimumSample )
  
  globalSampleBuffer['last']		= optimumSample['simulatedSamples'].pop()	#selected optimum sample becomes last in buffer
  globalSampleBuffer['beforeLast']	= optimumSample['simulatedSamples'].pop()

  return {
    'filter'	: optimumSample['filter'],
    'range'		: optimumSample['range'],
    'samples'	: optimumSample['convertedCharSamples'],
  }


def convertSampleBlock( inputSampleBlock, config ):
  blockError = 0.0
  convertedSamples = []
  simulatedSamples = []
  convertedCharSamples = []
  
  for sample in inputSampleBlock:
    signedSample = unsigned16BitToSigned( sample )
    convertedSignedSample = convertSingleSample( signedSample, config )
    convertedCharSample = signedToUnsigned4Bit( convertedSignedSample )
    simulatedBrrSample = simulateBrrSample( convertedSignedSample, config )
    
    convertedSamples.append( convertedSignedSample )	
    simulatedSamples.append( simulatedBrrSample )
    convertedCharSamples.append( convertedCharSample )

    error = calculateBrrError( signedSample, simulatedBrrSample )
    blockError += error * error
    
    globalSampleBuffer['beforeLast']	= globalSampleBuffer['last']
    globalSampleBuffer['last']			= simulatedBrrSample
  
  return {
    'blockError'			: math.sqrt( blockError ),
    'convertedSamples'		: convertedSamples,
    'convertedCharSamples'	: convertedCharSamples,
    'simulatedSamples'		: simulatedSamples,
    'originalSamples'		: inputSampleBlock,
    'filter'				: config['filter'],
    'range'					: config['range'],
  }


def convertSingleSample( inputSample, config ):
  if inputSample < 0:
    return -( ( abs( inputSample ) >> config['range'] ) & 0x7 )
  else:
    return ( inputSample >> config['range'] ) & 0x7


#restrict range of sample
def clampSignedSampleToRange( inputSample, limit ):
  return min( limit, max( -limit, inputSample ) )


def unsigned16BitToSigned( sample ):
  return sample if sample < 0x8000 else sample - 0x10000


def signedToUnsigned4Bit( sample ):
  return sample if sample >= 0 else ( abs( sample ) ^ 0xf ) + 1


def simulateBrrSample ( brrSample, config ):
  sample = brrSample
  sample <<= config['range']
  sample >>= 1
  brrFilterLUT = getBrrFilterLUT()
  sample += brrFilterLUT[config['filter']]()
  sample = clampSignedSampleToRange( sample, 0x7fff )
  sample <<= 1
  return sample


def calculateBrrError( inputSample, brrSample ):
  return max( inputSample, brrSample ) - min( inputSample, brrSample )


def getBrrFilterLUT():
  return {
    0	: applyNoFilter,
    1	: applyFilter1,
    2	: applyFilter2,
    3	: applyFilter3
  }  


def applyNoFilter():
  return 0


def applyFilter1():
  s = globalSampleBuffer['last'] >> 1
  s += (-globalSampleBuffer['last']) >> 5
  return s


def applyFilter2():
  s = globalSampleBuffer['last'];
  s -= globalSampleBuffer['beforeLast'] >> 1;
  s += globalSampleBuffer['beforeLast'] >> 5;
  s += (globalSampleBuffer['last'] * -3) >> 6;  
  return s


def applyFilter3():
  s = globalSampleBuffer['last'];
  s -= globalSampleBuffer['beforeLast'] >> 1;
  s += (globalSampleBuffer['last'] * -13) >> 7;
  s += ((globalSampleBuffer['beforeLast'] >> 1) * 3) >> 4;  
  return s


def updateStatistics( optimumSample ):
  global statistics
  
  statistics['samples'] += 1
  statistics['filter'][optimumSample['filter']] += 1
  statistics['range'][optimumSample['range']] += 1
  statistics['maxError'] = max( statistics['maxError'], optimumSample['blockError'] )
  statistics['minError'] = min( statistics['minError'], optimumSample['blockError'] )


def convertPatterns( inputPatterns ):
  convertedPatterns = []
  
  for pattern in inputPatterns:
    convertedPatterns.append( convertPattern( pattern ) )
  return convertedPatterns


def convertPattern( pattern ):
  convertedPattern = []
  
  for row in pattern:
    for channel in row:
      convertedPattern.append( convertChannel( channel ) )
  return convertedPattern


def convertChannel( channel ):
  convertedPeriod = convertPeriod( channel['period'] )
  
  return {
    'instrument'	: channel['instrument'],
    'period'		: SPCMOD_INVALID_PERIOD if convertedPeriod is False else convertedPeriod,
    'effectCommand'	: channel['effectCommand'] if channel['effectCommand'] + channel['effectData'] > 0 else SPCMOD_INVALID_PERIOD,
    'effectData'	: channel['effectData'] if channel['effectCommand'] + channel['effectData'] > 0 else SPCMOD_INVALID_PERIOD,
    'valid'			: True
  } if convertedPeriod or channel['effectData'] > 0 or channel['effectCommand'] > 0 or channel['instrument'] > 0 else {
    'valid'			: False
  }


def convertPeriod( inputPeriod ):
  periodLUT = getPeriodLUT()
  
  if not inputPeriod in periodLUT:
    if inputPeriod > 0:
      logging.info( 'input period %s is out of conversion range.' % inputPeriod )
    return False

  return 2 * ( periodLUT[inputPeriod] + ( MOD_PERIODS_PER_OCTAVE * ( INSTR_RES_MULTI - 1 ) ) )


def getModuleSampleBufferPosition( patternCount, channelCount ):
  return ( ( patternCount + 1 ) * MOD_ROWS_PER_PATTERN * channelCount * MOD_BYTES_PER_CHANNEL ) + 1084


def getModulePatternCount( sequence ):
  return max( sequence )


def getModulePlaySequence( mod ):
  sequence = []
  for char in mod[952:1080]:
    sequence.append( ord( char ) )
  return sequence


def getModulePatterns( mod, patternCount, channelCount ):
  patterns = []

  i = 0
  while i <= patternCount:
    patterns.append( getModulePattern( mod, i, channelCount ) )
    i += 1
  return patterns


def getModulePattern( mod, patternId, channelCount ):
  rows = []
  
  patternData = mod[ ( patternId * MOD_ROWS_PER_PATTERN * channelCount * MOD_BYTES_PER_CHANNEL ) + 1084 : ( ( patternId + 1 ) * MOD_ROWS_PER_PATTERN * channelCount * MOD_BYTES_PER_CHANNEL ) + 1084 ]

  for i in range( MOD_ROWS_PER_PATTERN ):
    rows.append( getModulePatternRow( patternData, i, channelCount ) )
  return rows


def getModulePatternRow( patternData, rowId, channelCount ):
  channels = []

  channelData = patternData[ rowId * channelCount * MOD_BYTES_PER_CHANNEL : ( rowId + 1 ) * channelCount * MOD_BYTES_PER_CHANNEL ]

  i = 0
  while i < channelCount:
    channels.append( getModulePatternRowChannel( channelData, i ) )
    i += 1
  return channels


def getModulePatternRowChannel( channelData, channelId ):
  singleChannelData = channelData[ channelId * MOD_BYTES_PER_CHANNEL : ( channelId + 1 ) * MOD_BYTES_PER_CHANNEL ]
  return {
    'instrument'	: ( ord( singleChannelData[0] ) & 0xf0 ) | ( ( ord( singleChannelData[2] ) & 0xf0 ) >> 4 ),
    'period'		: ( ( ord( singleChannelData[0] ) & 0xf ) << 8 ) | ord( singleChannelData[1] ),
    'effectCommand'	: ord( singleChannelData[2] ) & 0xf,
    'effectData'	: ord( singleChannelData[3] )
  }


def getModuleInstruments( mod, currentSampleBufferPosition ):
  instruments = []
  instrumentData = mod[MOD_INSTRUMENT_DATA:MOD_INSTRUMENT_DATA + ( MOD_INSTRUMENT_DATA_LENGTH * MOD_INSTRUMENT_COUNT )]

  for i in range( MOD_INSTRUMENT_COUNT ):
    instruments.append( getModuleInstrument( i, instrumentData, mod, currentSampleBufferPosition ) )
    currentSampleBufferPosition += instruments[i]['length']

  return instruments


def getModuleInstrument( instrumentId, instrumentData, mod, sampleBufferPosition ):
  singleInstrument = instrumentData[ instrumentId * MOD_INSTRUMENT_DATA_LENGTH : ( instrumentId + 1 ) * MOD_INSTRUMENT_DATA_LENGTH ]
  name = singleInstrument[0:22]

  m = re.search(r'(ADSR:(0x?[0-9A-Fa-f]{4}))', name)
  #use ADSR default if sample has no ADSR information
  adsr = 0x8EE0 if None is m else int(m.group(2), 16)

  instrument = {
    'id'        : instrumentId,
    'name'			: name,
    'start'			: sampleBufferPosition,
    'length'		: checkInstrumentLength( charWordToInt( singleInstrument[22:24] ) ),
    'finetune'		: ord( singleInstrument[24] ),
    'volume'		: ord( singleInstrument[25] ),
    'repeatStart'	: charWordToInt( singleInstrument[26:28] ),
    'repeatLength'	: checkInstrumentLength( charWordToInt( singleInstrument[28:30] ) ),
    'adsr' : adsr

  }

  instrument['samples'] = getInstrumentSamples(
    instrument['start'],
    instrument['length'],
    mod
  )
  
  return instrument


def checkInstrumentLength( length ):
  return length if length >= BRR_BLOCK_SAMPLES else 0

def getInstrumentSamples( start, length, sampleData ):
  samples = []
  for char in sampleData[ start : start+length ]:
    samples.append( (( ord( char ) << 8 )) ^0xff00 )	#fetch 16bit samples without dither and reverse, because whatever, maybe amiga samples are the other way round.
  return samples


def charWordToInt( char ):
  return ( ord( char[1] ) + ( ord( char[0] ) << 8 ) ) * 2


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
    if type( data ).__name__ == 'int':
      logging.debug( ' %s %x' % tuple( [nestStr, data] ) )
    else:
      logging.debug( ' %s %s' % tuple( [nestStr, data] ) )

#ugly lookup table, hopefully replaceable by something more elegant
def getPeriodLUT():
  return {
    0x0358 : 0,	#oct 1, C
    0x0328 : 1,
    0x02FA : 2,
    0x02D0 : 3,
    0x02A6 : 4,
    0x0280 : 5,
    0x025C : 6,
    0x023A : 7,
    0x021A : 8,
    0x01FC : 9,
    0x01E0 : 10,
    0x01C5 : 11,
    0x01AC : 12, #oct 2, C
    0x0194 : 13,
    0x017D : 14,
    0x0168 : 15,
    0x0153 : 16,
    0x0140 : 17,
    0x012E : 18,
    0x011D : 19,
    0x010D : 20,
    0x00FE : 21,
    0x00F0 : 22,
    0x00E2 : 23,
    0x00D6 : 24, #oct 3, C
    0x00CA : 25,
    0x00BE : 26,
    0x00B4 : 27,
    0x00AA : 28,
    0x00A0 : 29,
    0x0097 : 30,
    0x008F : 31,
    0x0087 : 32,
    0x007F : 33,
    0x0078 : 34,
    0x0071 : 35,
    0x006B : 36,
    0x0065 : 37,
    0x005F : 38,
    0x005A : 39,
    0x0055 : 40,
    0x0050 : 41,
    0x004B : 42,
    0x0047 : 43,
    0x0043 : 44,
    0x003F : 45,
    0x003C : 46,
    0x0038 : 47,
    0x0035 : 48,
    0x0032 : 49,
    0x002F : 50,
    0x002D : 51,
    0x002A : 52,
    0x0028 : 53,
    0x0025 : 54,
    0x0023 : 55,
    0x0021 : 56,
    0x001F : 57,
    0x001e : 58,
    0x001c : 59
  }


def clamp(x, bits):
  low = -1 << (bits-1)
  msb = 1 << (bits-1)
  high = msb -1

  if (x > high):
    x = high
  elif (x < low):
    x = low
  return x


def int8(val):
  if not (float('inf') > val):
    val = 0x7f
  elif not (None < val):
    val = 0xff
  val = int(val) & 0xff
  return val if 0x0 is (val & 0x80) else -((val ^ 0xff)+1)

def int16(val):
  
  if not (float('inf') > val):
    val = 0x7fff
  elif not (None < val):
    val = 0xffff
  val = int(val) & 0xffff
  return val if 0x0 is (val & 0x8000) else -((val ^ 0xffff)+1)

def int32(val):
  if not (float('inf') > val):
    val = 0x7fffffff
  elif not (None < val):
    val = 0xffffffff
  val = int(val) & 0xffffffff
  return val if 0x0 is (val & 0x80000000) else -((val ^ 0xffffffff)+1)


if __name__ == "__main__":
    main()
