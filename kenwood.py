# Copyright (c) 2022 Stephen Hurd
# Developers:
# Stephen Hurd (W8BSD/VE5BSD) <shurd@sasktel.net>
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice, developer list, and this permission notice shall
# be included in all copies or substantial portions of the Software. If you meet
# us some day, and you think this stuff is worth it, you can buy us a beer in
# return
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import bitarray
import bitarray.util
import re
import serial
import sys
import threading
import enum

class tunerState(enum.IntEnum):
	STOPPED = 0
	ACTIVE = 1
	FAILED = 2

class AI(enum.IntEnum):
	OFF = 0
	OLD = 1
	EXTENDED = 2
	BOTH = 3

class BeatCanceller(enum.IntEnum):
	OFF = 0
	AUTO = 1
	MANUAL = 2

class tuningMode(enum.IntEnum):
	VFOA = 0
	VFOB = 1
	MEMORY = 2
	CALL = 3

class mode(enum.IntEnum):
	LSB = 1
	USB = 2
	CW  = 3
	FM  = 4
	AM  = 5
	FSK = 6
	CW_REVERSED = 7
	FSK_REVERSED = 9

class scanMode(enum.IntEnum):
	OFF = 0
	ON = 1
	MHZ_SCAN = 2
	VISUAL_SCAN = 3
	TONE_SCAN = 4
	CTCSS_SCAN = 5
	DCS_SCAN = 6

class offset(enum.IntEnum):
	NONE = 0
	POSITIVE = 1
	NEGATIVE = 2
	# -7.6MHz for 430 or -6MHz for 1.2GHz
	EURO_SPLIT = 3

class meter(enum.IntEnum):
	UNSELECTED = 0
	SWR = 1
	COMPRESSION = 2
	ALC = 3

class firmwareType(enum.IntEnum):
	OVERSEAS = 0
	JAP100W = 1
	JAP20W = 2

class toneType(enum.IntEnum):
	OFF = 0
	TONE = 1
	CTCSS = 2
	DCS = 3

def parse(fmt, args):
	ret = ()
	while len(fmt):
		for i in range(1, len(fmt) + 1):
			if not fmt[0:i].isdigit():
				break
		width = int(fmt[0:i-1])
		if width == 0:
			width = len(args)
		t = fmt[i-1:i]
		fmt = fmt[i:]
		# String types get to keep spaces
		if t == 'l':
			ret += (args[0:width],)
		elif args[0:width].isspace():
			ret += (None,)
		elif t == 'd':
			ret += (int(args[0:width], 10),)
		elif t == 'x':
			ret += (int(args[0:width], 16),)
		else:
			raise Exception('Unsupported type: "%s"' % t)
		args = args[width:]
	return ret

class Kenwood:
	def init_19(self):
		# Errors
		self.command[b'?'] = {'update': self.__update_Error}
		self.command[b'E'] = {'update': self.__update_ComError}
		self.command[b'O'] = {'update': self.__update_IncompleteError}

		# State updates
		self.command[b'AC'] = {'update': self.__update_AC}
		self.command[b'AG'] = {'update': self.__update_AG}
		self.command[b'AI'] = {'update': self.__update_AI}
		self.command[b'AL'] = {'update': self.__update_AL}
		self.command[b'AM'] = {'update': self.__update_AM}
		self.command[b'AN'] = {'update': self.__update_AN}
		self.command[b'AR'] = {'update': self.__update_AR}
		# TODO: AS (auto mode configuration)
		self.command[b'BC'] = {'update': self.__update_BC}
		self.command[b'BP'] = {'update': self.__update_BP}
		self.command[b'BY'] = {'update': self.__update_BY}
		self.command[b'CA'] = {'update': self.__update_CA}
		self.command[b'CG'] = {'update': self.__update_CG}
		self.command[b'CM'] = {'update': self.__update_CM}
		# TODO: CN - CTCSS tone (uses a table)
		self.command[b'CT'] = {'update': self.__update_CT}
		self.command[b'DC'] = {'update': self.__update_DC}
		self.command[b'DQ'] = {'update': self.__update_DQ}
		self.command[b'EX'] = {'update': self.__update_EX}
		self.command[b'FA'] = {'update': self.__update_FA}
		self.command[b'FB'] = {'update': self.__update_FB}
		self.command[b'FC'] = {'update': self.__update_FC}
		self.command[b'FD'] = {'update': self.__update_FD}
		self.command[b'FR'] = {'update': self.__update_FR}
		self.command[b'FS'] = {'update': self.__update_FS}
		self.command[b'FT'] = {'update': self.__update_FT}
		self.command[b'FW'] = {'update': self.__update_FW}
		self.command[b'GT'] = {'update': self.__update_GT}
		self.command[b'IF'] = {'update': self.__update_IF}
		self.command[b'IS'] = {'update': self.__update_IS}
		self.command[b'KS'] = {'update': self.__update_KS}
		self.command[b'KY'] = {'update': self.__update_KY}
		self.command[b'LK'] = {'update': self.__update_LK}
		self.command[b'LM'] = {'update': self.__update_LM}
		self.command[b'LT'] = {'update': self.__update_LT}
		self.command[b'MC'] = {'update': self.__update_MC}
		self.command[b'MD'] = {'update': self.__update_MD}
		self.command[b'MF'] = {'update': self.__update_MF}
		self.command[b'MG'] = {'update': self.__update_MG}
		self.command[b'ML'] = {'update': self.__update_ML}
		self.command[b'MO'] = {'update': self.__update_MO}
		self.command[b'MR'] = {'update': self.__update_MR}
		self.command[b'MU'] = {'update': self.__update_MU}
		self.command[b'NB'] = {'update': self.__update_NB}
		self.command[b'NL'] = {'update': self.__update_NL}
		self.command[b'NR'] = {'update': self.__update_NR}
		self.command[b'NT'] = {'update': self.__update_NT}
		self.command[b'OF'] = {'update': self.__update_OF}
		self.command[b'OS'] = {'update': self.__update_OS}
		# TODO: OI Reads current memory data
		self.command[b'PA'] = {'update': self.__update_PA}
		self.command[b'PB'] = {'update': self.__update_PB}
		self.command[b'PC'] = {'update': self.__update_PC}
		self.command[b'PK'] = {'update': self.__update_PK}
		self.command[b'PL'] = {'update': self.__update_PL}
		self.command[b'PM'] = {'update': self.__update_PM}
		self.command[b'PR'] = {'update': self.__update_PR}
		self.command[b'PS'] = {'update': self.__update_PS}
		# TODO: QC set/read DCS code
		self.command[b'QR'] = {'update': self.__update_QR}
		self.command[b'RA'] = {'update': self.__update_RA}
		self.command[b'RD'] = {'update': self.__update_RD}
		self.command[b'RG'] = {'update': self.__update_RG}
		self.command[b'RL'] = {'update': self.__update_RL}
		self.command[b'RM'] = {'update': self.__update_RM}
		self.command[b'RT'] = {'update': self.__update_RT}
		self.command[b'RU'] = {'update': self.__update_RU}
		self.command[b'RX'] = {'update': self.__update_RX}
		self.command[b'SA'] = {'update': self.__update_SA}
		self.command[b'SB'] = {'update': self.__update_SB}
		self.command[b'SC'] = {'update': self.__update_SC}
		self.command[b'SD'] = {'update': self.__update_SD}
		self.command[b'SH'] = {'update': self.__update_SH}
		self.command[b'SL'] = {'update': self.__update_SL}
		self.command[b'SM'] = {'update': self.__update_SM}
		self.command[b'SQ'] = {'update': self.__update_SQ}
		# TODO: SS - "Program Scan pause frequency unintelligable docs
		# TODO: ST - Frequency steps for knob
		# TODO: SU - Program Scan pause frequency group stuff?
		self.command[b'TC'] = {'update': self.__update_TC}
		self.command[b'TI'] = {'update': self.__update_TI}
		self.command[b'TN'] = {'update': self.__update_TN}
		self.command[b'TO'] = {'update': self.__update_TO}
		# TODO: TS - Weird docs
		self.command[b'TX'] = {'update': self.__update_TX}
		self.command[b'TY'] = {'update': self.__update_TY}
		self.command[b'UL'] = {'update': self.__update_UL}
		self.command[b'VD'] = {'update': self.__update_VD}
		self.command[b'VG'] = {'update': self.__update_VG}
		self.command[b'VX'] = {'update': self.__update_VX}
		self.command[b'XT'] = {'update': self.__update_XT}

		# State names
		self.stateNames = {
			'tuner' : (b'AC',),
			'tunerRX' : (b'AC',),
			'tunerTX' : (b'AC',),
			'tunerState' : (b'AC',),
			'mainAFgain' : (b'AG', b'0',),
			'subAFgain' : (b'AG', b'1',),
			'autoInformation' : (b'AI',),
			'autoNotchLevel' : (b'AL',),
			'autoMode': (b'AM',),
			'antennaConnector': (b'AN',),
			'mainAutoSimplexOn': (b'AR', b'0',),
			'mainSimplexPossible': (b'AR', b'0',),
			'subAutoSimplexOn': (b'AR', b'1',),
			'subSimplexPossible': (b'AR', b'1',),
			'beatCanceller': (b'BC',),
			'autoBeatCanceller': (b'BC',),
			'manualBeatCanceller': (b'BC',),
			'manualBeatCancellerFrequency': (b'BP',),
			'mainBusy': (b'BY',),
			'subBusy': (b'BY',),
			'CWautoTune': (b'CA',),
			'carrierGain': (b'CG',),
			'packetClusterTune': (b'CM',),
			'CTCSS': (b'CT',),
			'TXmain': (b'DC',),
			'controlMain': (b'DC',),
			'DCS': (b'DQ',),
			'vfoAFrequency': (b'FA',),
			'vfoBFrequency': (b'FB',),
			'subReceiverFrequency': (b'FC',),
			'filterDisplayPattern': (b'FD',),
			'RXtuningMode': (b'FR',),
			'fineTuning': (b'FS',),
			'filterWidth': (b'FW',),
			'TXtuningMode': (b'FT',),
			'AGCconstant': (b'GT',),
			'ID' : (b'ID',),
			'currentReceiverTransmitting': (b'IF',),
			'mainTransmitting': (self.__update_mainTransmitting,),
			'IFshift' : (b'IS',),
			'keyerSpeed': (b'KS',),
			'keyerBufferFull': (b'KY',),
			'frequencyLock': (b'LK',),
			'allLock': (b'LK',),
			'rc2000Lock': (b'LK',),
			'recordingChannel': (b'LM',),
			'autoLockTuning': (b'LT',),
			'memoryChannel': (b'MC',),
			'mode': (b'MD',),
			'menuAB': (b'MF',),
			'microphoneGain': (b'MG',),
			'monitorLevel': (b'ML',),
			'skyCommandMonitor': (b'MO',),
			'memoryGroups': (b'MU',),
			'noiseBlanker': (b'NB',None,self.__noiseBlankerValid,),
			'noiseBlankerLevel': (b'NL',),
			'noiseReduction': (b'NR',),
			'noiseReduction1': (b'NR',),
			'noiseReduction2': (b'NR',),
			'autoNotch': (b'NT',),
			'offsetFrequency': (b'OF',),
			'mainPreAmp': (b'PA',),
			'subPreAmp': (b'PA',),
			'playbackChannel': (b'PB',),
			'outputPower': (b'PC',),
			'speechProcessorInputLevel': (b'PL',),
			'speechProcessorOutputLevel': (b'PL',),
			'programmableMemoryChannel': (b'PM',),
			'speechProcessor': (b'PR',),
			'powerOn': (b'PS',),
			'quickMemory': (b'QR',),
			'quickMemoryChannel': (b'QR',),
			'attenuator': (b'RA',),
			'scanSpeed': (b'RD',),
			'RFgain': (b'RG',),
			'noiseReductionLevel': (b'RL',None,self.__noiseReductionLevelValid,),
			'meterType': (b'RM',),
			'meterValue': (b'RM',),
			'SWRmeter': (b'RM',),
			'compressionMeter': (b'RM',),
			'ALCmeter': (b'RM',),
			'RIT': (b'RT',),
			'satelliteMode': (b'SA',),
			'satelliteMemoryChannel': (b'SA',),
			'satelliteMainUpSubDown': (b'SA',),
			'satelliteControlMain': (b'SA',),
			'satelliteTrace': (b'SA',),
			'satelliteTraceReverse': (b'SA',),
			'satelliteMultiKnobVFO': (b'SA',),
			'satelliteChannelName': (b'SA',),
			'subReceiver': (b'SB',),
			'scanMode': (b'SC',),
			'cwBreakInTimeDelay': (b'SD',),
			'voiceLowPassCutoff': (b'SH',None,self.__voiceCutoffValid,),
			'voiceHighPassCutoff': (b'SL',None,self.__voiceCutoffValid,),
			'mainSMeter': (b'SM', b'0',),
			'subSMeter': (b'SM', b'1',),
			'mainSMeterLevel': (b'SM', b'2',),
			'subSMeterLevel': (b'SM', b'3',),
			'mainSquelch': (b'SQ', b'0',),
			'subSquelch': (b'SQ', b'1',),
			'PCcontrolCommandMode': (b'TC',),
			'tnc96kLED': (b'TI',),
			'tncSTALED': (b'TI',),
			'tncCONLED': (b'TI',),
			'subToneFrequency': (b'TN',),
			'toneFunction': (b'TO',),
			'firmwareType': (b'TY',),
			'VOXdelayTime': (b'VD',),
			'VOXgain': (b'VG',),
			'VOX': (b'VX',),
			'XIT': (b'XT',),
			'tunerOnInRX': (b'EX', b'0270000'),
		}

		self.setStateMethods = {
			'vfoAFrequency': self.__set_vfoAFrequency,
			'vfoBFrequency': self.__set_vfoBFrequency,
			'RXtuningMode': self.__set_RXtuningMode,
			'up': self.__set_up,
			'down': self.__set_down,
			'bandUp': self.__set_bandUp,
			'bandDown': self.__set_bandDown,
			'mode': self.__set_mode,
			'tuner': self.__set_tuner,
			'tunerState': self.__set_tunerState,
			'tunerOnInRX': self.__set_tunerOnInRX,
			'mainPreAmp': self.__set_mainPreAmp,
			'attenuator': self.__set_attenuator,
			'RFgain': self.__set_RFgain,
			'mainAFgain': self.__set_mainAFgain,
			'mainSquelch': self.__set_mainSquelch,
			'outputPower': self.__set_outputPower,
			'voiceHighPassCutoff': self.__set_voiceHighPassCutoff,
			'voiceLowPassCutoff': self.__set_voiceLowPassCutoff,
			'filterWidth': self.__set_filterWidth,
			'AGCconstant': self.__set_AGCconstant,
			'noiseBlanker': self.__set_noiseBlanker,
			'noiseBlankerLevel': self.__set_noiseBlankerLevel,
			'noiseReduction': self.__set_noiseReduction,
			'noiseReduction1': self.__set_noiseReduction1,
			'noiseReduction2': self.__set_noiseReduction2,
			'noiseReductionLevel': self.__set_noiseReductionLevel,
			'autoNotch': self.__set_autoNotch,
			'autoNotchLevel': self.__set_autoNotchLevel,
			'beatCanceller': self.__set_beatCanceller,
			'autoBeatCanceller': self.__set_autoBeatCanceller,
			'manualBeatCanceller': self.__set_manualBeatCanceller,
			'manualBeatCancellerFrequency': self.__set_manualBeatCancellerFrequency,
			# TODO: b'CI' writes the current frequency to CALL channel
		}

		# Memories
		self.memories = [None] * 301

		# Initialization
		self.__write(b'AI2;')

	def __init__(self, port = "/dev/ttyU0", speed = 4800, stopbits = 2):
		self.init_done = False
		self.__terminate = False
		self.serial = serial.Serial(port = port, baudrate = speed, stopbits = stopbits, rtscts = True, timeout = 0.1, inter_byte_timeout = 0.5)
		self.error_count = 0
		self.__write(b'AI0;')
		self.command = dict()
		# We assume all rigs support the ID command (for no apparent reason)
		self.command[b'ID'] = {'update': self.__update_ID}
		self.stateNames = {
			'ID' : (b'ID',)
		}
		self.state = dict()
		self.callback = dict()
		self.waiting = None
		self.readThread = threading.Thread(target = self.__readThread, name = "Read Thread")
		self.readThread.start()
		resp = self.queryState('ID')
		self.last_command = None
		initFunction = 'init_' + str(resp)
		if callable(getattr(self, initFunction, None)):
			getattr(self, initFunction, None)()
		else:
			raise Exception("Unsupported rig (%d)!" % (resp))
		self.init_done = True

	def __del__(self):
		self.__write(b'AI0;')
		self.__terminate = True
		self.readThread.join()

	def terminate(self):
		self.__write(b'AI0;')
		self.__terminate = True
		self.readThread.join()

	def __write(self, barr):
		self.last_command = barr
		#print("Writing: '"+str(barr)+"'")
		self.serial.write(barr)

	def __read(self):
		ret = b'';
		while not self.__terminate:
			ret += self.serial.read_until(b';')
			if ret[-1:] == b';':
				#print("Read: '"+str(ret)+"'")
				return ret

	def __doCallbacks(self, updates):
		if updates is not None:
			if self.waiting is not None:
				if self.waiting in updates:
					self.event.set()
			for st in updates:
				m = re.match("^Memory([0-9]{3,3})$", st)
				if m:
					if 'MemoryData' in self.callback:
						self.callback['MemoryData'](int(m.group(1)))
				elif st in self.callback:
					param = self.state[st]
					self.callback[st](param)

	def __readThread(self):
		while not self.__terminate:
			cmdline = self.__read()
			if cmdline is not None:
				m = re.match(b"^([?A-Z]{1,2})([\x00-\x3a\x3c-\x7f]*);$", cmdline)
				if m:
					cmd = m.group(1)
					args = m.group(2).decode('ascii')
					if cmd in self.command:
						if 'update' in self.command[cmd]:
							updates = self.command[cmd]['update'](args)
							self.__doCallbacks(updates)
					else:
						if self.init_done:
							print('Unhandled command "%s" (args: "%s")' % (cmd, args), file=sys.stderr)
				else:
					print('Bad command line: "'+str(cmdline)+'"')

	def queryState(self, name):
		self.error_count = 0
		if not name in self.stateNames:
			raise Exception('Unknown state value name "%s"' % (name))
		if len(self.stateNames[name]) > 2:
			if not self.stateNames[name][2]():
				self.__doCallbacks(self.__updated(name, None))
				return None
		if not name in self.state or self.state[name] == None:
			self.__getResponse(self.stateNames[name], name)
		return self.state[name]

	def forceState(self, name):
		if name in self.state:
			del self.state[name]
		return self.queryState(name)

	def setState(self, name, value):
		self.error_count = 0
		if not name in self.setStateMethods:
			raise Exception('Unknown state value name "%s"' % (name))
		return self.setStateMethods[name](value)

	def queryMemory(self, channel):
		self.error_count = 0
		if self.memories[channel] is None:
			self.__getResponse((b'MR', bytes('0{:03d}'.format(channel), 'ascii')), 'Memory{:03d}'.format(channel))
		return self.memories[channel]

	# Sends the passed command and waits for the echo or an error
	def __getResponse(self, cmd, name):
		if callable(cmd[0]):
			cmd[0]()
		else:
			if not cmd[0] in self.command:
				raise KeyError('Unsupported command %s' % (cmd[0]))
			if not self.readThread.is_alive() or self.__terminate:
				raise EOFError('Read thread has exited')
			if hasattr(self, 'event'):
				raise Exception('Attempt recursive query')
			self.event = threading.Event()
			self.waiting = name
			if len(cmd) > 1 and cmd[1] is not None:
				self.__write(cmd[0] + cmd[1] + b';')
			else:
				self.__write(cmd[0] + b';')
			self.event.wait()
			self.waiting = None
			del self.event

	def __updated(self, name, value):
		if (not name in self.state) or self.state[name] != value:
			self.state[name] = value
			return (name,)
		return ()

	def __update_AC(self, args):
		split = parse('1d1d1d', args)
		ret = ()
		ret += self.__updated('tuner', (bool(split[0]) or bool(split[1])))
		ret += self.__updated('tunerRX', bool(split[0]))
		ret += self.__updated('tunerTX', bool(split[1]))
		ret += self.__updated('tunerState', tunerState(split[2]))
		return ret

	def __set_tuner(self, value):
		# NOTE: No matter what combination of arguments is used
		#       for the first two parameters, it just ORs them
		#       together for the state.  Use Menu 27 to change
		#       what actually happens
		self.__write(bytes('AC1{:1d}0;'.format(value), 'ascii'))

	def __set_tunerState(self, value):
		if value == tunerState.FAILED:
			raise Exception('Cannot set tuner to error state')
		self.__write(bytes('AC11{:1d};'.format(int(value)), 'ascii'))
		# TODO: We can't actually do a '2' here...

	def __update_AG(self, args):
		split = parse('1d3d', args)
		ret = ()
		if split[0] == 0:
			ret += self.__updated('mainAFgain', split[1]);
		else:
			ret += self.__updated('subAFgain', split[1])
		return ret

	def __set_mainAFgain(self, value):
		self.__write(bytes('AG0{:03d};'.format(value), 'ascii'))

	def __update_AI(self, args):
		split = parse('1d', args)
		return self.__updated('autoInformation', AI(split[0]))

	def __update_AL(self, args):
		split = parse('3d', args)
		return self.__updated('autoNotchLevel', split[0])

	def __set_autoNotchLevel(self, value):
		self.__write(bytes('AL{:03d};'.format(value), 'ascii'))

	def __update_AM(self, args):
		split = parse('1d', args)
		return self.__updated('autoMode', bool(split[0]))

	# TODO: None here means 2m or 440 fixed antenna
	#       maybe something better would be good?
	def __update_AN(self, args):
		split = parse('1d', args)
		ret = ()
		if split[0] == 0:
			ret += self.__updated('antennaConnector', None)
		else:
			ret += self.__updated('antennaConnector', split[0])
		return ret

	def __update_AR(self, args):
		split = parse('1d1d1d', args)
		ret = ()
		aso = bool(split[1])
		if split[0] == 0:
			ret += self.__updated('mainAutoSimplexOn', aso)
			if aso:
				ret += self.__updated('mainSimplexPossible', bool(split[2]))
			else:
				ret += self.__updated('mainSimplexPossible', False)
		else:
			ret += self.__updated('subAutoSimplexOn', aso)
			if aso:
				ret += self.__updated('subSimplexPossible', bool(split[2]))
			else:
				ret += self.__updated('subSimplexPossible', False)
		return ret

	def __update_BC(self, args):
		split = parse('1d', args)
		ret = ()
		ret += self.__updated('beatCanceller', BeatCanceller(split[0]))
		if split[0] == 0:
			ret += self.__updated('autoBeatCanceller', False)
			ret += self.__updated('manualBeatCanceller', False)
		elif split[0] == 1:
			ret += self.__updated('autoBeatCanceller', True)
			ret += self.__updated('manualBeatCanceller', False)
		elif split[0] == 2:
			ret += self.__updated('autoBeatCanceller', False)
			ret += self.__updated('manualBeatCanceller', True)
		return ret;

	def __set_beatCanceller(self, value):
		self.__write(bytes('BC{:01d};'.format(value), 'ascii'))

	def __set_autoBeatCanceller(self, value):
		self.__write(bytes('BC{:01d};'.format(1 if value else 0), 'ascii'))

	def __set_manualBeatCanceller(self, value):
		self.__write(bytes('BC{:01d};'.format(2 if value else 0), 'ascii'))

	def __set_bandDown(self, value):
		self.__write(b'BD;')

	def __update_BP(self, args):
		split = parse('3d', args)
		return self.__updated('manualBeatCancellerFrequency', split[0])

	def __set_manualBeatCancellerFrequency(self, value):
		self.__write(bytes('BP{:03d};'.format(value), 'ascii'))

	def __set_bandUp(self, value):
		self.__write(b'BU;')

	def __update_BY(self, args):
		split = parse('1d1d', args)
		ret = ()
		ret += self.__updated('mainBusy', bool(split[0]))
		ret += self.__updated('subBusy', bool(split[1]))
		return ret

	def __update_CA(self, args):
		split = parse('1d', args)
		return self.__updated('CWautoTune', bool(split[0]))

	def __update_CG(self, args):
		split = parse('3d', args)
		return self.__updated('carrierGain', split[0])

	def __update_CM(self, args):
		split = parse('1d', args)
		return self.__updated('packetClusterTune', bool(split[0]))

	def __update_CT(self, args):
		split = parse('1d', args)
		return self.__updated('CTCSS', bool(split[0]))

	def __update_DC(self, args):
		split = parse('1d1d', args)
		ret = ()
		ret += self.__updated('TXmain', not bool(split[0]))
		ret += self.__updated('controlMain', not bool(split[1]))
		return ret;

	def __set_down(self, value):
		if value is None:
			self.__write(b'DN;')
		else:
			self.__write(bytes('DN{:2d}'.format(value), 'ascii'))

	def __update_DQ(self, args):
		split = parse('1d', args)
		return self.__updated('DCS', bool(split[0]))

	def __update_EX(self, args):
		split = parse('3d2d1d1d0l', args)
		ret = ()
		if split[0] == 27:
			ret += self.__updated('tunerOnInRX', bool(int(split[4])))
		return ret

	def __set_tunerOnInRX(self, value):
		self.__write(bytes('EX0270000{:1d};'.format(value), 'ascii'))

	def __update_FA(self, args):
		split = parse('11d', args)
		return self.__updated('vfoAFrequency', split[0])

	def __set_vfoAFrequency(self, value):
		self.__write(bytes('FA{:011d};'.format(value), 'ascii'))

	def __update_FB(self, args):
		split = parse('11d', args)
		return self.__updated('vfoBFrequency', split[0])

	def __set_vfoBFrequency(self, value):
		self.__write(bytes('FB{:011d};'.format(value), 'ascii'))

	def __update_FC(self, args):
		split = parse('11d', args)
		return self.__updated('subReceiverFrequency', split[0])

	def __update_FD(self, args):
		split = parse('8x', args)
		return self.__updated('filterDisplayPattern', bitarray.util.int2ba(split[0], 32))

	def __update_FW(self, args):
		split = parse('4d', args)
		return self.__updated('filterWidth', split[0])

	def __set_filterWidth(self, value):
		self.__write(bytes('FW{:04d};'.format(value), 'ascii'))

	def __update_FR(self, args):
		split = parse('1d', args)
		return self.__updated('RXtuningMode', tuningMode(split[0]))

	def __set_RXtuningMode(self, value):
		self.__write(bytes('FR{:01d};'.format(value), 'ascii'))

	def __update_FS(self, args):
		split = parse('1d', args)
		return self.__updated('fineTuning', bool(split[0]))

	def __update_FT(self, args):
		split = parse('1d', args)
		return self.__updated('TXtuningMode', tuningMode(split[0]))

	def __update_GT(self, args):
		if args == '   ':
			return self.__updated('AGCconstant', None)
		split = parse('3d', args)
		return self.__updated('AGCconstant', split[0])

	def __set_AGCconstant(self, value):
		self.__write(bytes('GT{:03d};'.format(value), 'ascii'))

	def __update_ID(self, args):
		return self.__updated('ID', parse('3d', args)[0])

	def __update_IF(self, args):
		# TODO: Synchronize these with the single-value options
		# NOTE: Combined P6 and P7 since they're effectively one number on the TS-2000
		#'00003810000' '    ' ' 00000' '0' '0' '101' '0' '1' '0' '0' '0' '0' '08' '0'
		#'00003810000' '    ' ' 00000' '0' '0' '101' '0' '1' '0' '0' '0' '0' '08' '0'
		#     3810000,     0,       1,  0,  1,    0,  1,  0,  0,  0,  0,  0,   8,  0
		split = parse('11d4d6d1d1d3d1d1d1d1d1d1d2d1d', args)
		ret = ()
		ret += self.__updated('currentFrequency', split[0])
		ret += self.__updated('frequencyStep', split[1])
		ret += self.__updated('RIT_XITfrequency', split[2])
		ret += self.__updated('RIT', bool(split[3]))
		ret += self.__updated('XIT', bool(split[4]))
		ret += self.__updated('channelBank', split[5])
		ret += self.__updated('currentReceiverTransmitting', bool(split[6]))
		ret += self.__updated('mode', mode(split[7]))
		ret += self.__updated('tuningMode', tuningMode(split[8]))
		ret += self.__updated('scanMode', scanMode(split[9]))
		# TODO: Split is undocumented and full-duplex may be here?
		ret += self.__updated('splitMode', bool(split[10]))
		# TODO: TONE/CTCSS/DCS squished together here in split[11]
		# TODO: Tone frequency
		ret += self.__updated('shiftStatus', offset(split[13]))
		# Fun hack... in CALL mode, MC300 is updated via IF...
		# We handle this special case by asserting that if we get IF
		# when in MC300, the MC has been updated
		if 'memoryChannel' in self.state and self.state['memoryChannel'] == 300:
			self.memories[300] = None
			ret += ('memoryChannel',)
		return ret;

	def __update_mainTransmitting(self):
		return self.__updated('mainTransmitting', self.queryState('TXmain') and self.queryState('currentReceiverTransmitting'))

	def __update_IS(self, args):
		split = parse('5d', args)
		return self.__updated('IFshift', split[0])

	def __update_KS(self, args):
		split = parse('3d', args)
		return self.__updated('keyerSpeed', split[0])

	def __update_KY(self, args):
		split = parse('1d', args)
		return self.__updated('keyerBufferFull', bool(split[0]))

	def __update_LK(self, args):
		split = parse('1d1d', args)
		ret = ()
		if split[0] == 0:
			ret += self.__updated('frequencyLock', False)
			ret += self.__updated('allLock', False)
		elif split[0] == 1:
			ret += self.__updated('frequencyLock', True)
			ret += self.__updated('allLock', False)
		elif split[1] == 2:
			ret += self.__updated('frequencyLock', True)
			ret += self.__updated('allLock', True)
		ret += self.__updated('rc2000Lock', bool(split[1]))
		return ret

	def __update_LM(self, args):
		# TODO: Maybe false for 0?
		split = parse('1d1d', args)
		return self.__updated('recordingChannel', split[0])

	def __update_LT(self, args):
		split = parse('1d', args)
		return self.__updated('autoLockTuning', bool(split[0]))

	def __update_MC(self, args):
		split = parse('3d', args)
		# Any time we get an MC300; it means we entered CALL mode
		# The calling frequency *may* be different than last time!
		if split[0] == 300:
			self.memories[300] = None
		return self.__updated('memoryChannel', split[0])

	def __update_MD(self, args):
		split = parse('1d', args)
		return self.__updated('mode', mode(split[0]))

	def __set_mode(self, mode):
		self.__write(bytes('MD{:1d};'.format(int(mode)), 'ascii'))

	def __update_MF(self, args):
		split = parse('1d', args)
		if split[0] == 0:
			return self.__updated('menuAB', 'A')
		elif split[0] == 1:
			return self.__updated('menuAB', 'B')

	def __update_MG(self, args):
		split = parse('3d', args)
		return self.__updated('microphoneGain', split[0])

	def __update_ML(self, args):
		split = parse('3d', args)
		return self.__updated('monitorLevel', split[0])

	def __update_MO(self, args):
		split = parse('1d', args)
		return self.__updated('skyCommandMonitor', bool(split[0]))

	def __update_MR(self, args):
		split = parse('1d3d11d1d1d1d2d2d3d1d1d9d2d1d0l', args)
		self.memories[split[1]] = {
			'Channel': split[1],
			'Frequency': split[2],
			'Mode': mode(split[3]),
			'LockedOut': bool(split[4]),
			'ToneType': toneType(split[5]),
			# TODO: Tone Number mapping?
			'ToneNumber': split[6],
			'CTCSStoneNumber': split[7],
			'DCScode': split[8],
			'Reverse': bool(split[9]),
			'OffsetType': offset(split[10]),
			'OffsetFrequency': split[11],
			'StepSize': split[12],
			'MemoryGroup': split[13],
			'MemoryName': split[14]
		}
		if split[1] < 290 or split[1] > 299:
			self.memories[split[1]]['TX'] = bool(split[0])
		else:
			self.memories[split[1]]['Start'] = not bool(split[0])
		return ('Memory{:03d}'.format(split[1]),)

	def __update_MU(self, args):
		return self.__updated('memoryGroups', bitarray.bitarray(args))

	def __update_NB(self, args):
		split = parse('1d', args)
		return self.__updated('noiseBlanker', bool(split[0]))

	def __noiseBlankerValid(self):
		return self.queryState('mode') != mode.FM

	def __set_noiseBlanker(self, value):
		if self.__noiseBlankerValid():
			self.__write(bytes('NB{:01d};'.format(value), 'ascii'))

	def __update_NL(self, args):
		split = parse('3d', args)
		return self.__updated('noiseBlankerLevel', split[0])

	def __set_noiseBlankerLevel(self, value):
		self.__write(bytes('NL{:03d};'.format(value), 'ascii'))

	def __update_NR(self, args):
		split = parse('1d', args)
		ret = ()
		if split[0] == 0:
			ret += self.__updated('noiseReduction', False)
			ret += self.__updated('noiseReduction1', False)
			ret += self.__updated('noiseReduction2', False)
		elif split[0] == 1:
			ret += self.__updated('noiseReduction', split[0])
			ret += self.__updated('noiseReduction1', True)
			ret += self.__updated('noiseReduction2', False)
		else:
			ret += self.__updated('noiseReduction', split[0])
			ret += self.__updated('noiseReduction1', False)
			ret += self.__updated('noiseReduction2', True)
		return ret

	def __set_noiseReduction(self, value):
		self.__write(bytes('NR{:01d};'.format(value), 'ascii'))

	def __set_noiseReduction1(self, value):
		val = 1 if value else 0
		self.__write(bytes('NR{:01d};'.format(val), 'ascii'))

	def __set_noiseReduction2(self, value):
		val = 2 if value else 0
		self.__write(bytes('NR{:01d};'.format(val), 'ascii'))

	def __update_NT(self, args):
		split = parse('1d', args)
		return self.__updated('autoNotch', bool(split[0]))

	def __set_autoNotch(self, value):
		self.__write(bytes('NT{:01d};'.format(value), 'ascii'))

	def __update_OF(self, args):
		split = parse('9d', args)
		return self.__updated('offsetFrequency', split[0])

	def __update_OS(self, args):
		split = parse('1d', args)
		return self.__updated('offsetType', offset(split[0]))

	def __update_PA(self, args):
		split = parse('1d1d', args)
		ret = ()
		ret += self.__updated('mainPreAmp', bool(split[0]))
		ret += self.__updated('subPreAmp', bool(split[1]))
		return ret

	def __set_mainPreAmp(self, value):
		self.__write(bytes('PA{:1d};'.format(value), 'ascii'))

	def __update_PB(self, args):
		split = parse('1d', args)
		return self.__updated('playbackChannel', split[0])

	def __update_PC(self, args):
		split = parse('3d', args)
		return self.__updated('outputPower', split[0])

	def __set_outputPower(self, value):
		self.__write(bytes('PC{:03d};'.format(value), 'ascii'))

	def __update_PK(self, args):
		split = parse('11d12l20l5l', args)
		self.__updated('spotFrequency', split[0])
		self.__updated('spotCallsign', split[1])
		self.__updated('spotComments', split[2])
		self.__updated('spotTime', split[3])
		# NOTE: Always include all of them
		return ('spotFrequency', 'spotCallsign', 'spotComments', 'spotTime')

	def __update_PL(self, args):
		split = parse('3d3d', args)
		ret = ()
		ret += self.__updated('speechProcessorInputLevel', split[0])
		ret += self.__updated('speechProcessorOutputLevel', split[1])
		return ret

	def __update_PM(self, args):
		split = parse('1d', args)
		# TODO: Should this be None or False when it's off?
		return self.__updated('programmableMemoryChannel', split[0])

	def __update_PR(self, args):
		split = parse('1d', args)
		return self.__updated('speechProcessor', bool(split[0]))

	def __update_PS(self, args):
		split = parse('1d', args)
		return self.__updated('powerOn', bool(split[0]))

	def __update_QR(self, args):
		split = parse('1d1d', args)
		ret = ()
		ret += self.__updated('quickMemory', bool(split[0]))
		ret += self.__updated('quickMemoryChannel', split[1])
		return ret

	def __update_RA(self, args):
		split = parse('2d', args)
		return self.__updated('attenuator', bool(split[0]))

	def __set_attenuator(self, value):
		self.__write(bytes('RA{:02d};'.format(value), 'ascii'))

	# NOTE: Updates the same value as RU
	def __update_RD(self, args):
		split = parse('1d', args)
		return self.__updated('scanSpeed', split[0])

	def __update_RG(self, args):
		split = parse('3d', args)
		return self.__updated('RFgain', split[0])

	def __set_RFgain(self, value):
		self.__write(bytes('RG{:03d};'.format(value), 'ascii'))

	def __update_RL(self, args):
		split = parse('2d', args)
		return self.__updated('noiseReductionLevel', split[0])

	def __noiseReductionLevelValid(self):
		return self.forceState('noiseReduction') != False

	def __set_noiseReductionLevel(self, value):
		self.__write(bytes('RL{:02d};'.format(value), 'ascii'))

	def __update_RM(self, args):
		split = parse('1d4d', args)
		ret = ()
		ret += self.__updated('meterType', meter(split[0]))
		ret += self.__updated('meterValue', split[1])
		if split[0] == 1:
			ret += self.__updated('SWRmeter', split[1])
			ret += self.__updated('compressionMeter', 0)
			ret += self.__updated('ALCmeter', 0)
		elif split[0] == 2:
			ret += self.__updated('SWRmeter', 0)
			ret += self.__updated('compressionMeter', split[1])
			ret += self.__updated('ALCmeter', 0)
		if split[0] == 3:
			ret += self.__updated('SWRmeter', 0)
			ret += self.__updated('compressionMeter', 0)
			ret += self.__updated('ALCmeter', split[1])
		return ret

	# Note: Can only set RM2 when COMP is on

	def __update_RT(self, args):
		split = parse('1d', args)
		return self.__updated('RIT', bool(split[0]))

	# NOTE: Updates the same value as RD
	def __update_RU(self, args):
		split = parse('1d', args)
		return self.__updated('scanSpeed', split[0])

	def __update_RX(self, args):
		split = parse('1d', args)
		if split[0] == 0:
			return self.__updated('mainTransmitting', False)
		if split[0] == 1:
			return self.__updated('subTransmitting', False)

	def __update_SA(self, args):
		split = parse('1d1d1d1d1d1d1d8l', args)
		ret = ()
		ret += self.__updated('satelliteMode', bool(split[0]))
		ret += self.__updated('satelliteMemoryChannel', split[1])
		ret += self.__updated('satelliteMainUpSubDown', not bool(split[2]))
		ret += self.__updated('satelliteControlMain', not bool(split[3]))
		ret += self.__updated('satelliteTrace', bool(split[4]))
		ret += self.__updated('satelliteTraceReverse', bool(split[5]))
		ret += self.__updated('satelliteMultiKnobVFO', not bool(split[6]))
		ret += self.__updated('satelliteChannelName', split[7])

	def __update_SB(self, args):
		split = parse('1d', args)
		return self.__updated('subReceiver', bool(split[0]))

	def __update_SC(self, args):
		split = parse('1d', args)
		return self.__updated('scanMode', scanMode(split[0]))

	def __update_SD(self, args):
		split = parse('4d', args)
		return self.__updated('cwBreakInTimeDelay', split[0])

	def __update_SH(self, args):
		split = parse('2d', args)
		return self.__updated('voiceLowPassCutoff', split[0])

	def __voiceCutoffValid(self):
		return self.queryState('mode') in (mode.AM, mode.FM, mode.LSB, mode.USB)

	def __set_voiceLowPassCutoff(self, value):
		self.__write(bytes('SH{:02d};'.format(value), 'ascii'))

	def __update_SL(self, args):
		split = parse('2d', args)
		return self.__updated('voiceHighPassCutoff', split[0])

	def __set_voiceHighPassCutoff(self, value):
		self.__write(bytes('SL{:02d};'.format(value), 'ascii'))

	def __update_SM(self, args):
		split = parse('1d4d', args)
		# TODO: Figure out what 2 and 3 actually are...
		if split[0] == 0:
			return self.__updated('mainSMeter', split[1])
		if split[0] == 1:
			return self.__updated('subSMeter', split[1])
		if split[0] == 2:
			print('Got SM2!', file=sys.stderr)
			return self.__updated('mainSMeterLevel', split[1])
		if split[0] == 3:
			print('Got SM3!', file=sys.stderr)
			return self.__updated('subSMeterLevel', split[1])

	def __update_SQ(self, args):
		split = parse('1d3d', args)
		if split[0] == 0:
			return self.__updated('mainSquelch', split[1])
		elif split[0] == 1:
			return self.__updated('subSquelch', split[1])

	def __set_mainSquelch(self, value):
		self.__write(bytes('SQ0{:03d};'.format(value), 'ascii'))

	def __update_TC(self, args):
		split = parse('1d1d', args)
		return self.__updated('PCcontrolCommandMode', bool(split[1]))

	def __update_TI(self, args):
		split = parse('1d1d1d', args)
		ret = ()
		ret += self.__updated('tnc96kLED', bool(split[0]))
		ret += self.__updated('tncSTALED', bool(split[1]))
		ret += self.__updated('tncCONLED', bool(split[2]))
		return ret

	def __update_TN(self, args):
		split = parse('2d', args)
		# TODO: Smart mapping thing?
		return self.__updated('subToneFrequency', split[0])

	def __update_TO(self, args):
		split = parse('1d', args)
		return self.__updated('toneFunction', bool(split[0]))

	def __update_TX(self, args):
		split = parse('1d', args)
		if split[0] == 0:
			return self.__updated('mainTransmitting', True)
		if split[0] == 1:
			return self.__updated('subTransmitting', True)

	def __update_TY(self, args):
		split = parse('3d', args)
		return self.__updated('firmwareType', firmwareType(split[0]))

	def __update_UL(self, args):
		split = parse('1d', args)
		if split[0] == 1:
			raise Exception('PLL Unlocked!')
		return self.__updated('PLLunlock', bool(split[0]))

	def __set_up(self, value):
		if value is None:
			self.__write(b'UP;')
		else:
			self.__write(bytes('UP{:2d}'.format(value), 'ascii'))

	def __update_VD(self, args):
		split = parse('4d', args)
		return self.__updated('VOXdelayTime', split[0])

	def __update_VG(self, args):
		split = parse('3d', args)
		return self.__updated('VOXgain', split[0])

	def __update_VX(self, args):
		split = parse('1d', args)
		return self.__updated('VOX', bool(split[0]))

	def __update_XT(self, args):
		split = parse('1d', args)
		return self.__updated('XIT', bool(split[0]))

	def __update_Error(self, args):
		self.error_count += 1
		if self.error_count < 10:
			self.__write(self.last_command)
		else:
			raise Exception('Error count exceeded')

	def __update_ComError(self, args):
		self.error_count += 1
		if self.error_count < 10:
			self.__write(self.last_command)
		else:
			raise Exception('Error count exceeded')

	def __update_IncompleteError(self, args):
		self.error_count += 1
		if self.error_count < 10:
			self.__write(self.last_command)
		else:
			raise Exception('Error count exceeded')
