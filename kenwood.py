# Copyright (c) 2022 Stephen Hurd
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
import copy
import enum
import re
import serial
import sys
import threading
import time
import queue

from types import SimpleNamespace

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

class CTCSStone(enum.IntEnum):
	CTCSS_67_0 = 1
	CTCSS_71_9 = 2
	CTCSS_74_4 = 3
	CTCSS_77_0 = 4
	CTCSS_79_7 = 5
	CTCSS_82_5 = 6
	CTCSS_85_4 = 7
	CTCSS_88_5 = 8
	CTCSS_91_5 = 9
	CTCSS_94_8 = 10
	CTCSS_97_4 = 11
	CTCSS_100_0 = 12
	CTCSS_103_5 = 13
	CTCSS_107_2 = 14
	CTCSS_110_9 = 15
	CTCSS_114_8 = 16
	CTCSS_118_8 = 17
	CTCSS_123_0 = 18
	CTCSS_127_3 = 19
	CTCSS_131_8 = 20
	CTCSS_136_5 = 21
	CTCSS_141_3 = 22
	CTCSS_146_2 = 23
	CTCSS_151_4 = 24
	CTCSS_156_7 = 25
	CTCSS_162_2 = 26
	CTCSS_167_9 = 27
	CTCSS_173_8 = 28
	CTCSS_179_9 = 29
	CTCSS_186_2 = 30
	CTCSS_192_8 = 31
	CTCSS_203_5 = 32
	CTCSS_210_7 = 33
	CTCSS_218_1 = 34
	CTCSS_225_7 = 35
	CTCSS_233_6 = 36
	CTCSS_241_8 = 37
	CTCSS_250_3 = 38
	TONE_1750 = 39

class rigLock(enum.IntEnum):
	OFF = 0
	F_LOCK = 1
	A_LOCK = 2

class recordingChannel(enum.IntEnum):
	OFF = 0
	CH1 = 1
	CH2 = 2
	CH3 = 3

class noiseReduction(enum.IntEnum):
	OFF = 0
	NR1 = 1
	NR2 = 2

class DCScode(enum.IntEnum):
	DCS_23 = 0
	DCS_25 = 1
	DCS_26 = 2
	DCS_31 = 3
	DCS_32 = 4
	DCS_36 = 5
	DCS_43 = 6
	DCS_47 = 7
	DCS_51 = 8
	DCS_53 = 9
	DCS_54 = 10
	DCS_65 = 11
	DCS_71 = 12
	DCS_72 = 13
	DCS_73 = 14
	DCS_74 = 15
	DCS_114 = 16
	DCS_115 = 17
	DCS_116 = 18
	DCS_122 = 19
	DCS_125 = 20
	DCS_131 = 21
	DCS_132 = 22
	DCS_134 = 23
	DCS_143 = 24
	DCS_145 = 25
	DCS_152 = 26
	DCS_155 = 27
	DCS_156 = 28
	DCS_162 = 29
	DCS_165 = 30
	DCS_172 = 31
	DCS_174 = 32
	DCS_205 = 33
	DCS_212 = 34
	DCS_223 = 35
	DCS_225 = 36
	DCS_226 = 37
	DCS_243 = 38
	DCS_244 = 39
	DCS_245 = 40
	DCS_246 = 41
	DCS_251 = 42
	DCS_252 = 43
	DCS_255 = 44
	DCS_261 = 45
	DCS_263 = 46
	DCS_265 = 47
	DCS_266 = 48
	DCS_271 = 49
	DCS_274 = 50
	DCS_306 = 51
	DCS_311 = 52
	DCS_315 = 53
	DCS_325 = 54
	DCS_331 = 55
	DCS_332 = 56
	DCS_343 = 57
	DCS_346 = 58
	DCS_351 = 59
	DCS_356 = 60
	DCS_364 = 61
	DCS_365 = 62
	DCS_371 = 63
	DCS_411 = 64
	DCS_412 = 65
	DCS_413 = 66
	DCS_423 = 67
	DCS_431 = 68
	DCS_432 = 69
	DCS_445 = 70
	DCS_446 = 71
	DCS_452 = 72
	DCS_454 = 73
	DCS_455 = 74
	DCS_462 = 75
	DCS_464 = 76
	DCS_465 = 77
	DCS_466 = 78
	DCS_503 = 79
	DCS_506 = 80
	DCS_516 = 81
	DCS_523 = 82
	DCS_526 = 83
	DCS_532 = 84
	DCS_546 = 85
	DCS_565 = 86
	DCS_606 = 87
	DCS_612 = 88
	DCS_624 = 89
	DCS_627 = 90
	DCS_631 = 91
	DCS_632 = 92
	DCS_654 = 93
	DCS_662 = 94
	DCS_664 = 95
	DCS_703 = 96
	DCS_712 = 97
	DCS_723 = 98
	DCS_731 = 99
	DCS_732 = 100
	DCS_734 = 101
	DCS_743 = 102
	DCS_754 = 103

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

# Command has:
# command string - To look up the parser
# method         - to parse it

# TODO: Should we record if the command is ACKed in AI2?
class StateValue():
	def __init__(self, rig, **kwargs):
		self.name = None
		self._read_only = kwargs.get('read_only')
		self._rig = rig
		self._works_powered_off = kwargs.get('works_powered_off')
		self._set_format = kwargs.get('set_format')
		self._set_method = kwargs.get('set_method')
		if self._set_format is not None and self._set_method is not None:
			raise Exception('Only one of set_method or set_format may be specified')
		self._validity_check = kwargs.get('validity_check')
		self._range_check = kwargs.get('range_check')
		self._query_command = kwargs.get('query_command')
		self._query_method = kwargs.get('query_method')
		self._echoed = kwargs.get('echoed')
		if  self._query_command is not None and self._query_method is not None:
			raise Exception('Only one of query_command or query_method may be specified')
		self._cached_value = None
		self._callbacks = ()
		self._wait_callbacks = ()

	@property
	def _cached(self):
		return self._cached_value

	@_cached.setter
	def _cached(self, value):
		if self._cached_value != value:
			self._cached_value = value
			for cb in self._callbacks:
				cb(value)
		for cb in self._wait_callbacks:
			cb(self, value)

	def query_string(self):
		if not self.valid():
			self._cached = None
			return None
		if self._query_method is not None:
			return self._query_method()
		elif self._query_command is not None:
			return self._query_command
		print('Attempt to query value "'+self.name+'" without a query command or method', file=sys.stderr)
		return None

	@property
	def value(self):
		if self._cached is None and not self._rig._killing_cache:
			self._rig._query(self)
		# We just deepcopy it as an easy hack
		return copy.deepcopy(self._cached)

	def set_string(self, value):
		if not self.range_check(value):
			self._cached = None
			return None
		if self._set_format is not None:
			return self._set_format.format(value)
		elif self._set_method is not None:
			return self._set_method(value)
		print('Attempt to set value "'+self.name+'" without a set command or method', file=sys.stderr)

	@value.setter
	def value(self, value):
		if not self._read_only:
			self._rig._set(self, value)

	@property
	def uncached_value(self):
		if not self._read_only:
			self._cached_value = None
		return self.value

	def valid(self):
		if not self._works_powered_off:
			if not self._rig.powerOn:
				return False
		if self._validity_check is not None:
			return self._validity_check()
		return True

	def range_check(self, value):
		if not self.valid():
			return False
		if self._range_check is not None:
			return self._range_check(value)
		return True

	def add_callback(self, cb):
		self._callbacks += (cb,)

	def _add_wait_callback(self, cb):
		self._wait_callbacks += (cb,)

	def remove_callback(self, cb):
		self._callbacks = tuple(filter(lambda x: x == cb, self._callbacks))

	def _remove_wait_callback(self, cb):
		self._wait_callbacks = tuple(filter(lambda x: x is cb, self._wait_callbacks))

class IntStateValue(int, StateValue):
	def __iadd__(self, other):
		super().__iadd__(self, other)
		self._cached = int(self)

class MemoryArray:
	def __init__(self, rig, **kwargs):
		self.memories = [None] * 301
		self._rig = rig
		for i in range(len(self.memories)):
			self.memories[i] = StateValue(rig, query_command = 'MR0{:03d};MR1{:03d}'.format(i, i))

	def __len__(self):
		return self.memories.len()

	def __getitem__(self, key):
		# TODO: Support slices...
		if isinstance(key, slice):
			raise IndexError('Sorry, no slicing support yet')
		return self.memories[key].value

	def __setitem__(self, key, value):
		self.memories[key].value = value

	def __iter__(self):
		for x in self.memories:
			yield self.memories[x].value

class Kenwood:
	def _update_mainTransmitting(self):
		self._state['mainTransmitting']._cached = self._state['TXmain']._cached and self._state['currentReceiverTransmitting']._cached
		return ''

	def _update_subTransmitting(self):
		self._state['subTransmitting']._cached = (not self._state['TXmain']._cached) and self._state['currentReceiverTransmitting']._cached
		return ''

	def _noiseBlankerValid(self):
		if self._state['mode']._cached is None:
			return False
		return self._state['mode']._cached != mode.FM

	def _set_manualBeatCanceller(self, value):
		return 'BC{:01d}'.format(BeatCanceller.MANUAL if value else BeatCanceller.OFF)

	def _set_frequencyLock(self, value):
		rc = self._state['rc2000Lock']._cached
		if rc is None:
			return None
		return 'LK{:01d}{:01d}'.format(value, rc)

	def _set_allLock(self, value):
		rc = self._state['rc2000Lock']._cached
		if rc is None:
			return None
		return 'LK{:01d}{:01d}'.format(2 if value else 0, rc)

	def _set_rigLock(self, value):
		rc = self._state['rc2000Lock']._cached
		if rc is None:
			return None
		return 'LK{:01d}{:01d}'.format(value, rc)

	def _set_rc2000Lock(self, value):
		fa = self._state['rigLock']._cached
		if fa is None:
			return None
		return 'LK{:01d}{:01d}'.format(fa, value)

	def _set_memoryGroups(self, value):
		return 'MU{:1d}{:1d}{:1d}{:1d}{:1d}{:1d}{:1d}{:1d}{:1d}{:1d};MU'.format(value[0], value[1], value[2], value[3], value[4], value[5], value[6], value[7], value[8], value[9])

	def _set_noiseReduction2(self, value):
		return 'NR{:01d}'.format(noiseReduction.NR2 if value else noiseReduction.OFF)

	def _set_speechProcessorInputLevel(self, value):
		ol = self._state['speechProcessorOutputLevel']._cached
		if ol is None:
			return None
		return 'PL{:03d}{:03d}'.format(value, ol)

	def _set_speechProcessorOutputLevel(self, value):
		ol = self._state['speechProcessorInputLevel']._cached
		if ol is None:
			return None
		return 'PL{:03d}{:03d}'.format(ol, value)

	def _set_quickMemory(self, value):
		qm = self._state['quickMemoryChannel']._cached
		if qm is None:
			return None
		return 'QR{:01d}{:01d}'.format(value, qm)

	def _set_quickMemoryChannel(self, value):
		qm = self._state['quickMemory']._cached
		if qm is None:
			return None
		return 'QR{:01d}{:01d}'.format(qm, value)

	def _RITupDownValid(self):
		return self._state['scanMode']._cached == scanMode.OFF

	def _scanSpeedUpDownValid(self):
		if self._state['scanMode']._cached is None:
			return False
		return self._state['scanMode']._cached != scanMode.OFF

	def _noiseReductionLevelValid(self):
		if self._state['noiseReduction']._cached is None:
			return False
		return self._state['noiseReduction']._cached != noiseReduction.OFF

	def _mainReceiverOnly(self):
		return self._state['controlMain']._cached

	def _voiceCutoffValid(self):
		if not self._state['controlMain']._cached:
			return False
		return self._state['mode']._cached in (mode.AM, mode.FM, mode.LSB, mode.USB)

	def _inMemoryMode(self):
		return self._state['tuningMode']._cached == tuningMode.MEMORY

	def _set_mainTransmitting(self, value):
		if value:
			return 'TX'
		else:
			return 'RX'

	def _set_subTransmitting(self, value):
		if value:
			return 'TX'
		else:
			return 'RX'

	def _set_currentTransmitting(self, value):
		if value:
			return 'TX'
		else:
			return 'RX'

	def _checkMeterValue(self, value):
		if meter(value) == meter.COMPRESSION and not self._state['speechProcessor']._cached:
			return False
		return True

	def _checkMainFrequencyValid(self, value):
		ranges = {
			'HF': [30000, 60000000],
			'VHF': [142000000, 151999999],
			'UHF': [420000000, 449999999],
		}
		for r in ranges:
			if value >= ranges[r][0] and value <= ranges[r][1]:
				return True
		return False

	def _checkSubFrequencyValid(self, value):
		ranges = {
			'VHF': [142000000, 151999999],
			'UHF': [420000000, 449999999],
		}
		for r in ranges:
			if value >= ranges[r][0] and value <= ranges[r][1]:
				return True
		return False

	def _antennaRangeCheck(self, value):
		if self._state['currentFrequency']._cached is None:
			return False
		if self._state['currentFrequency']._cached <= 60000000 and (value == 1 or value == 2):
			return True
		return False

	def _antenna1Valid(self):
		return self._antennaRangeCheck(1)

	def _antenna2Valid(self):
		return self._antennaRangeCheck(2)

	def _setAntenna1(self, value):
		return ('AN' + '1' if value else '2')

	def _setAntenna2(self, value):
		return ('AN' + '2' if value else '1')

	def _cwAutoTuneRange(self, value):
		if not self._state['mode']._cached in (mode.CW, mode.CW_REVERSED, ):
			return False
		if value:
			return True
		if self.CWautoTune:
			return True
		return False

	def _cwAutoTuneValid(self):
		if self._state['mode']._cached in (mode.CW, mode.CW_REVERSED, ):
			return True
		return False

	def _memoryGroupRange(self, value):
		if not 1 in value:
			return False
		return True

	def _filterWidthValid(self):
		if not self._state['controlMain']._cached:
			return False
		if self._state['mode']._cached in (mode.LSB, mode.USB,):
			return False
		return True

	def _query_VFOmode(self, cm, m, sv):
		if cm == self._state['controlMain']._cached and (m is None or m == self._state['RXtuningMode']._cached):
			sv._cached = self._state['mode']._cached
			return
		old_cm = None
		if not self._state['controlMain']._cached == cm:
			old_cm = self._state['controlMain']._cached
			self._set(self._state['controlMain'], cm)
		old_tm = None
		if m is not None:
			if not self._state['RXtuningMode']._cached == m:
				old_tm = self._state['RXtuningMode']._cached
				self._set(self._state['RXtuningMode'], m)
		if old_tm is not None:
			self._set(self._state['RXtuningMode'], old_tm)
		if old_cm is not None:
			self._set(self._state['controlMain'], old_cm)

	def _query_VFOAmode(self):
		self._query_VFOmode(True, tuningMode.VFOA, self._state['VFOAmode'])

	def _query_VFOBmode(self):
		self._query_VFOmode(True, tuningMode.VFOB, self._state['VFOBmode'])

	def _query_subMode(self):
		self._query_VFOmode(False, tuningMode.VFOA, self._state['subMode'])

	def _query_mainMode(self):
		self._query_VFOmode(True, None, self._state['mainMode'])

	def _set_controlMain(self, value):
		if self._state['TXmain']._cached is None:
			return None
		return 'DC{:1d}{:1d}'.format(not self._state['TXmain']._cached, not value)

	def _set_TXmain(self, value):
		if self._state['controlMain']._cached is None:
			return None
		return 'DC{:1d}{:1d}'.format(not value, not self._state['controlMain']._cached)

	def _mainTransmittingValid(self, value):
		if self._state['TXmain']._cached:
			return self._state['mainTransmitting']._cached != value
		return False

	def _subTransmittingValid(self, value):
		if self._state['TXmain']._cached:
			return False
		return self._state['subTransmitting']._cached != value

	def _currentTransmittingValid(self, value):
		return self._state['currentReceiverTransmitting']._cached != value

	def _check_transmitSet(self, value):
		if not value:
			return True
		return self._state['split']._cached

	def _never(self):
		return False

	def _check_notSimplex(self):
		if self.offsetFrequency == 0:
			return True

	def _set_mainRXtuningMode(self, value):
		return 'FR{:01d}'.format(int(value))

	def _set_mainTXtuningMode(self, value):
		return 'FT{:01d}'.format(int(value))

	def _check_mainRXtuningMode(self, value):
		if not self._state['controlMain']._cached:
			return False
		return True

	def _check_mainTXtuningMode(self, value):
		if not self._state['controlMain']._cached:
			return False
		if value == tuningMode.CALL:
			return self._state['RXtuningMode']._cached == tuningMode.CALL
		elif self._state['TXtuningMode']._cached == tuningMode.CALL:
			return False
		return True

	def _notInTransmitSet(self):
		return self._state['transmitSet'] == False

	def _init_19(self):
		# Errors
		self._command = {
			b'?': self._update_Error,
			b'E': self._update_ComError,
			b'O': self._update_IncompleteError,

			# State updates
			b'AC': self._update_AC,
			b'AG': self._update_AG,
			b'AI': self._update_AI,
			b'AL': self._update_AL,
			b'AM': self._update_AM,
			b'AN': self._update_AN,
			b'AR': self._update_AR,
			# TODO: AS (auto mode configuration)
			b'BC': self._update_BC,
			b'BP': self._update_BP,
			b'BY': self._update_BY,
			b'CA': self._update_CA,
			b'CG': self._update_CG,
			b'CM': self._update_CM,
			b'CN': self._update_CN,
			b'CT': self._update_CT,
			b'DC': self._update_DC,
			b'DQ': self._update_DQ,
			b'EX': self._update_EX,
			b'FA': self._update_FA,
			b'FB': self._update_FB,
			b'FC': self._update_FC,
			b'FD': self._update_FD,
			b'FR': self._update_FR,
			b'FS': self._update_FS,
			b'FT': self._update_FT,
			b'FW': self._update_FW,
			b'GT': self._update_GT,
			b'ID': self._update_ID,
			b'IF': self._update_IF,
			b'IS': self._update_IS,
			b'KS': self._update_KS,
			b'KY': self._update_KY,
			b'LK': self._update_LK,
			b'LM': self._update_LM,
			b'LT': self._update_LT,
			b'MC': self._update_MC,
			b'MD': self._update_MD,
			b'MF': self._update_MF,
			b'MG': self._update_MG,
			b'ML': self._update_ML,
			b'MO': self._update_MO,
			b'MR': self._update_MR,
			b'MU': self._update_MU,
			b'NB': self._update_NB,
			b'NL': self._update_NL,
			b'NR': self._update_NR,
			b'NT': self._update_NT,
			b'OF': self._update_OF,
			b'OS': self._update_OS,
			# TODO: OI appears to be IF for the non-active receiver... not sure if that's PTT or CTRL
			b'PA': self._update_PA,
			b'PB': self._update_PB,
			b'PC': self._update_PC,
			b'PK': self._update_PK,
			b'PL': self._update_PL,
			b'PM': self._update_PM,
			b'PR': self._update_PR,
			b'PS': self._update_PS,
			b'QC': self._update_QC,
			b'QR': self._update_QR,
			b'RA': self._update_RA,
			b'RD': self._update_RD,
			b'RG': self._update_RG,
			b'RL': self._update_RL,
			b'RM': self._update_RM,
			b'RT': self._update_RT,
			b'RU': self._update_RU,
			b'RX': self._update_RX,
			b'SA': self._update_SA,
			b'SB': self._update_SB,
			b'SC': self._update_SC,
			b'SD': self._update_SD,
			b'SH': self._update_SH,
			b'SL': self._update_SL,
			b'SM': self._update_SM,
			b'SQ': self._update_SQ,
			# TODO: SS - "Program Scan pause frequency unintelligable docs
			b'ST': self._update_ST,
			# TODO: SU - Program Scan pause frequency group stuff?
			b'TC': self._update_TC,
			b'TI': self._update_TI,
			b'TN': self._update_TN,
			b'TO': self._update_TO,
			b'TS': self._update_TS,
			b'TX': self._update_TX,
			b'TY': self._update_TY,
			b'UL': self._update_UL,
			b'VD': self._update_VD,
			b'VG': self._update_VG,
			b'VX': self._update_VX,
			b'XT': self._update_XT,
		}

		self._state = {
			# State objects
			'tuner':                        StateValue(self, echoed = True,  query_command = 'AC',  set_format = 'AC1{:1d}0'),
			'tunerRX':                      StateValue(self, query_command = 'AC'),
			'tunerTX':                      StateValue(self, query_command = 'AC'),
			'tunerState':                   StateValue(self, echoed = True,  query_command = 'AC',  set_format = 'AC11{:1d}'),
			'mainAFgain':                   StateValue(self, echoed = False, query_command = 'AG0', set_format = 'AG0{:03d}'),
			'subAFgain':                    StateValue(self, echoed = False, query_command = 'AG1', set_format = 'AG1{:03d}'),
			'autoInformation':              StateValue(self, echoed = True,  query_command = 'AI',  set_format = 'AI{:01d}'),
			'autoNotchLevel':               StateValue(self, echoed = False, query_command = 'AL',  set_format = 'AL{:03d}'),
			'autoMode':                     StateValue(self, echoed = True,  query_command = 'AM',  set_format = 'AM{:01d}'),
			'antennaConnector':             StateValue(self, echoed = True,  query_command = 'AN',  set_format = 'AN{:01d}', range_check = self._antennaRangeCheck),
			'antenna1':                     StateValue(self, echoed = True,  query_command = 'AN',  set_method = self._setAntenna1, validity_check = self._antenna1Valid),
			'antenna2':                     StateValue(self, echoed = True,  query_command = 'AN',  set_method = self._setAntenna2, validity_check = self._antenna2Valid),
			'mainAutoSimplexOn':            StateValue(self, echoed = True,  query_command = 'AR0', set_format = 'AR0{:01d}1'),
			'mainSimplexPossible':          StateValue(self, echoed = True,  query_command = 'AR0'),
			'subAutoSimplexOn':             StateValue(self, echoed = True,  query_command = 'AR1', set_format = 'AR1{:01d}1'),
			'subSimplexPossible':           StateValue(self, echoed = True,  query_command = 'AR1'),
			'beatCanceller':                StateValue(self, echoed = True,  query_command = 'BC',  set_format = 'BC{:01}'),
			'autoBeatCanceller':            StateValue(self, echoed = True,  query_command = 'BC',  set_format = 'BC{:01}'),
			'manualBeatCanceller':          StateValue(self, echoed = True,  query_command = 'BC',  set_method = self._set_manualBeatCanceller),
			'bandDown':                     StateValue(self, echoed = True,                         set_format = 'BD'),
			'manualBeatCancellerFrequency': StateValue(self, echoed = False, query_command = 'BP',  set_format = 'BP{:03d}'),
			'bandUp':                       StateValue(self, echoed = True,                         set_format = 'BU'),
			'mainBusy':                     StateValue(self, query_command = 'BY'),
			'subBusy':                      StateValue(self, query_command = 'BY'),
			'CWautoTune':                   StateValue(self, echoed = True,  query_command = 'CA',  set_format = 'CA{:01d}', validity_check = self._cwAutoTuneValid, range_check = self._cwAutoTuneRange),
			'carrierGain':                  StateValue(self, echoed = False, query_command = 'CG',  set_format = 'CG{:03d}'),
			# False turns it up, True turns it down (derp derp),
			'turnMultiChControlDown':       StateValue(self, echoed = True,                         set_format = 'CH{:01d}'),
			# Sets the current frequency to be the CALL frequency for the band
			'storeAsCallFrequency':         StateValue(self, echoed = True,                         set_format = 'CI'),
			'packetClusterTune':            StateValue(self, echoed = True,  query_command = 'CM',  set_format = 'CM{:01d}'),
			'CTCSStone':                    StateValue(self, echoed = True,  query_command = 'CN',  set_format = 'CN{:02d}'),
			'CTCSS':                        StateValue(self, echoed = True,  query_command = 'CT',  set_format = 'CT{:01d}'),
			'TXmain':                       StateValue(self, echoed = True,  query_command = 'DC',  set_method = self._set_TXmain),
			'controlMain':                  StateValue(self, echoed = True,  query_command = 'DC',  set_method = self._set_controlMain),
			'down':                         StateValue(self, echoed = True,                         set_format = 'DN'),
			'DCS':                          StateValue(self, echoed = True,  query_command = 'DQ',  set_format = 'DQ{:01d}'),
			'vfoAFrequency':                StateValue(self, echoed = True,  query_command = 'FA',  set_format = 'FA{:011d}', range_check = self._checkMainFrequencyValid),
			'vfoBFrequency':                StateValue(self, echoed = True,  query_command = 'FB',  set_format = 'FB{:011d}', range_check = self._checkMainFrequencyValid),
			'subReceiverFrequency':         StateValue(self, echoed = True,  query_command = 'FC',  set_format = 'FC{:011d}', range_check = self._checkSubFrequencyValid),
			'filterDisplayPattern':         StateValue(self, query_command = 'FD'),
			# NOTE: FR changes FT, but FT doesn't change FR **and** doesn't notify
			# that FT was changed.  This is handled in update_FR
			'RXtuningMode':                 StateValue(self, echoed = True,  query_command = 'FR',  set_format = 'FR{:01d}', validity_check = self._notInTransmitSet),
			'fineTuning':                   StateValue(self, echoed = True,  query_command = 'FS',  set_format = 'FS{:01d}'),
			'TXtuningMode':                 StateValue(self, echoed = True,  query_command = 'FT',  set_format = 'FT{:01d}', validity_check = self._notInTransmitSet),
			'filterWidth':                  StateValue(self, echoed = True,  query_command = 'FW',  set_format = 'FW{:04d}', validity_check = self._filterWidthValid),
			'filterWidth':                  StateValue(self, echoed = True,  query_command = 'FW',  set_format = 'FW{:04d}', validity_check = self._filterWidthValid),
			'AGCconstant':                  StateValue(self, echoed = True,  query_command = 'GT',  set_format = 'GT{:03d}'),
			'ID':                           StateValue(self, echoed = True,  query_command = 'ID',  works_powered_off = True,  read_only = True),
			'currentReceiverTransmitting':  StateValue(self, query_command = 'IF', set_method = self._set_mainTransmitting, range_check = self._currentTransmittingValid),
			'currentFrequency':             StateValue(self, query_command = 'IF'),
			'frequencyStep':                StateValue(self, query_command = 'IF'),
			'RIT_XITfrequency':             StateValue(self, query_command = 'IF'),
			'channelBank':                  StateValue(self, query_command = 'IF'),
			'split':                        StateValue(self, query_command = 'IF'),
			'shiftStatus':                  StateValue(self, query_command = 'IF'),
			'tuningMode':                   StateValue(self, query_command = 'IF'),
			'IFshift':                      StateValue(self, echoed = True,  query_command = 'IS',  set_format = 'IS {:04d}'),
			'keyerSpeed':                   StateValue(self, echoed = False, query_command = 'KS',  set_format = 'KS{:03d}'),
			'keyerBufferFull':              StateValue(self, query_command = 'KY'),
			'keyerBuffer':                  StateValue(self, echoed = True,                         set_format = 'KY {:24}'),
			'frequencyLock':                StateValue(self, echoed = True,  query_command = 'LK',  set_method = self._set_frequencyLock),
			'allLock':                      StateValue(self, echoed = True,  query_command = 'LK',  set_method = self._set_allLock),
			'rc2000Lock':                   StateValue(self, echoed = True,  query_command = 'LK',  set_method = self._set_rc2000Lock),
			'rigLock':                      StateValue(self, echoed = True,  query_command = 'LK',  set_method = self._set_rigLock),
			'recordingChannel':             StateValue(self, echoed = True,  query_command = 'LM',  set_format = 'LM{:01d}'),
			'autoLockTuning':               StateValue(self, echoed = True,  query_command = 'LT',  set_format = 'LT{:01d}'),
			'memoryChannel':                StateValue(self, echoed = True,  query_command = 'MC',  set_format = 'MC{:03d}'),
			'mode':                         StateValue(self, echoed = True,  query_command = 'MD',  set_format = 'MD{:01d}'),
			'menuAB':                       StateValue(self, echoed = True,  query_command = 'MF',  set_format = 'MF{:1}'),
			'microphoneGain':               StateValue(self, echoed = False, query_command = 'MG',  set_format = 'MG{:03d}'),
			'monitorLevel':                 StateValue(self, echoed = False, query_command = 'ML',  set_format = 'ML{:03d}'),
			# MO; fails, and I dont' see a way to check if Sky Command is ON
			#self.skyCommandMonitor =            StateValue(self, query_command = 'MO',  set_format = 'MO{:01d}')
			# TODO: Modernize MR (memory read)
			# TODO: Modernize MW (memory write)
			'memoryGroups':                 StateValue(self, echoed = False, query_command = 'MU',  set_method = self._set_memoryGroups, range_check = self._memoryGroupRange),
			'noiseBlanker':                 StateValue(self, echoed = True,  query_command = 'NB',  set_format = 'NB{:01d}', validity_check = self._noiseBlankerValid),
			'noiseBlankerLevel':            StateValue(self, echoed = False, query_command = 'NL',  set_format = 'NL{:03d}'),
			'noiseReduction':               StateValue(self, echoed = True,  query_command = 'NR',  set_format = 'NR{:01d}'),
			'noiseReduction1':              StateValue(self, echoed = True,  query_command = 'NR',  set_format = 'NR{:01d}'),
			'noiseReduction2':              StateValue(self, echoed = True,  query_command = 'NR',  set_method = self._set_noiseReduction2),
			'autoNotch':                    StateValue(self, echoed = True,  query_command = 'NT',  set_format = 'NT{:01d}'),
			'offsetFrequency':              StateValue(self, echoed = True,  query_command = 'OF',  set_format = 'OF{:09d}'),
			# TODO: OI appears to be IF for the non-active receiver... not sure if that's PTT or CTRL
			'offsetType':                   StateValue(self, echoed = True,  query_command = 'OS',  set_format = 'OS{:01d}'),
			'mainPreAmp':                   StateValue(self, echoed = True,  query_command = 'PA',  set_format = 'PA{:01d}'),
			'subPreAmp':                    StateValue(self, query_command = 'PA'),
			'playbackChannel':              StateValue(self, echoed = True,  query_command = 'PB',  set_format = 'PB{:01d}'),
			'outputPower':                  StateValue(self, echoed = False, query_command = 'PC',  set_format = 'PC{:03d}'),
			'storeAsProgrammableMemory':    StateValue(self, echoed = True,                         set_format = 'PI{:01d}'),
			'lastSpot':                     StateValue(self),
			'speechProcessorInputLevel':    StateValue(self, echoed = False, query_command = 'PL',  set_method = self._set_speechProcessorInputLevel),
			'speechProcessorOutputLevel':   StateValue(self, echoed = False, query_command = 'PL',  set_method = self._set_speechProcessorOutputLevel),
			'programmableMemoryChannel':    StateValue(self, echoed = True,  query_command = 'PM',  set_format = 'PM{:01d}'),
			'speechProcessor':              StateValue(self, echoed = True,  query_command = 'PR',  set_format = 'PR{:01d}'),
			'powerOn':                      StateValue(self, echoed = True,  query_command = 'PS',  set_format = 'PS{:01d}', works_powered_off = True),
			'DCScode':                      StateValue(self, echoed = True,  query_command = 'QC',  set_format = 'QC{:03d}'),
			'storeAsQuickMemory':           StateValue(self, echoed = True,                         set_format = 'QC'),
			'quickMemory':                  StateValue(self, echoed = True,  query_command = 'QR',  set_method = self._set_quickMemory),
			'quickMemoryChannel':           StateValue(self, echoed = True,  query_command = 'QR',  set_method = self._set_quickMemoryChannel),
			'attenuator':                   StateValue(self, echoed = True,  query_command = 'RA',  set_format = 'RA{:02d}'),
			'clearRIT':                     StateValue(self, echoed = True,                         set_format = 'RC'),
			'RITdown':                      StateValue(self, echoed = True,                         set_format = 'RD{:04d}', validity_check = self._RITupDownValid),
			'scanSpeed':                    StateValue(self, echoed = True,  query_command = 'RD',  validity_check = self._scanSpeedUpDownValid),
			'scanSpeedDown':                StateValue(self, echoed = True,                         set_format = 'RD{:04d}', validity_check = self._scanSpeedUpDownValid),
			'RFgain':                       StateValue(self, echoed = False, query_command = 'RG',  set_format = 'RG{:03d}'),
			'noiseReductionLevel':          StateValue(self, echoed = False, query_command = 'RL',  set_format = 'RL{:02d}', validity_check = self._noiseReductionLevelValid),
			'meterType':                    StateValue(self, echoed = True,  query_command = 'RM',  set_format = 'RM{:01d}', range_check = self._checkMeterValue),
			'meterValue':                   StateValue(self, query_command = 'RM'),
			'SWRmeter':                     StateValue(self, query_command = 'RM'),
			'compressionMeter':             StateValue(self, query_command = 'RM'),
			'ALCmeter':                     StateValue(self, query_command = 'RM'),
			'RIT':                          StateValue(self, echoed = True,  query_command = 'RT',  set_format = 'RT{:01d}'),
			'RITup':                        StateValue(self, echoed = True,                         set_format = 'RU{:04d}', validity_check = self._RITupDownValid),
			'scanSpeedUp':                  StateValue(self, echoed = True,                         set_format = 'RU{:04d}', validity_check = self._scanSpeedUpDownValid),
			'mainTransmitting':             StateValue(self, echoed = True,  query_method = self._update_mainTransmitting, set_method = self._set_mainTransmitting, range_check = self._mainTransmittingValid), # RX, TX
			'subTransmitting':              StateValue(self, echoed = True,  query_method = self._update_subTransmitting, set_method = self._set_subTransmitting, range_check = self._subTransmittingValid), # RX, TX
			# TODO: Setters for SA command
			'satelliteMode':                StateValue(self, query_command = 'SA'),
			'satelliteMemoryChannel':       StateValue(self, query_command = 'SA'),
			'satelliteMainUpSubDown':       StateValue(self, query_command = 'SA'),
			'satelliteControlMain':         StateValue(self, query_command = 'SA'),
			'satelliteTrace':               StateValue(self, query_command = 'SA'),
			'satelliteTraceReverse':        StateValue(self, query_command = 'SA'),
			'satelliteMultiKnobVFO':        StateValue(self, query_command = 'SA'),
			'satelliteChannelName':         StateValue(self, query_command = 'SA'),
			'subReceiver':                  StateValue(self, echoed = True,  query_command = 'SB',  set_format = 'SB{:01d}'),
			'scanMode':                     StateValue(self, echoed = True,  query_command = 'SB',  set_format = 'SB{:01d}'),
			'cwBreakInTimeDelay':           StateValue(self, echoed = True,  query_command = 'SD',  set_format = 'SD{:04d}'),
			'voiceLowPassCutoff':           StateValue(self, echoed = True,  query_command = 'SH',  set_format = 'SH{:02d}', validity_check = self._voiceCutoffValid),
			# TODO: SI - Satellite memory name
			'voiceHighPassCutoff':          StateValue(self, echoed = True,  query_command = 'SL',  set_format = 'SL{:02d}', validity_check = self._voiceCutoffValid),
			'mainSMeter':                   StateValue(self, query_command = 'SM0'),
			'subSMeter':                    StateValue(self, query_command = 'SM1'),
			'mainSMeterLevel':              StateValue(self, query_command = 'SM2'),
			'subSMeterLevel':               StateValue(self, query_command = 'SM3'),
			'mainSquelch':                  StateValue(self, echoed = False,  query_command = 'SQ0', set_format = 'SQ0{:03d}'),
			'subSquelch':                   StateValue(self, echoed = False,  query_command = 'SQ1', set_format = 'SQ1{:03d}'),
			# TODO?: SR1, SR2... reset transceiver
			# TODO: SS set/read Program Scan pause frequency
			'multiChFrequencySteps':        StateValue(self, echoed = True,  query_command = 'ST',  set_format = 'ST{:02d}'),
			# TODO: SU - program scan pause frequency
			'memoryToVFO':                  StateValue(self, echoed = True,                         set_format = 'SV', validity_check = self._inMemoryMode),
			'PCcontrolCommandMode':         StateValue(self, echoed = True,  query_command = 'TC',  set_format = 'TC {:01d}'),
			'sendDTMFmemoryData':           StateValue(self, echoed = True,                         set_format = 'TD {:02d}'),
			'tnc96kLED':                    StateValue(self, query_command = 'TI'),
			'tncSTALED':                    StateValue(self, query_command = 'TI'),
			'tncCONLED':                    StateValue(self, query_command = 'TI'),
			'subToneFrequency':             StateValue(self, echoed = False, query_command = 'TN',  set_format = 'TN{:02d}'),
			'toneFunction':                 StateValue(self, echoed = False, query_command = 'TO',  set_format = 'TO{:01d}'),
			'transmitSet':                  StateValue(self, echoed = True,  query_command = 'TS',  set_format = 'TS{:01d}', validity_check = self._check_notSimplex, range_check = self._check_transmitSet),
			# TODO: TS (simplex)
			'firmwareType':                 StateValue(self, query_command = 'TY'),
			# TODO: UL? (PLL Unlock)
			'up':                           StateValue(self, echoed = True,                         set_format = 'UP'),
			'VOXdelayTime':                 StateValue(self, echoed = False, query_command = 'VD',  set_format = 'VD{:04d}'),
			'VOXgain':                      StateValue(self, echoed = False, query_command = 'VG',  set_format = 'VG{:03d}'),
			'voice1':                       StateValue(self, echoed = True,                         set_format = 'VR0'),
			'voice2':                       StateValue(self, echoed = True,                         set_format = 'VR1'),
			'VOX':                          StateValue(self, echoed = False, query_command = 'VX',  set_format = 'VX{:01d}'),
			'XIT':                          StateValue(self, echoed = False, query_command = 'XT',  set_format = 'XT{:01d}'),
			'memoryVFOsplitEnabled':        StateValue(self, echoed = False, query_command = 'EX0060100',  set_format = 'EX0060100{:01d}'),
			'tunerOnInRX':                  StateValue(self, echoed = False, query_command = 'EX0270000',  set_format = 'EX0270000{:01d}'),
			'currentMainFrequency':         StateValue(self),
			'currentSubFrequency':          StateValue(self),
			'currentTXfrequency':           StateValue(self),
			'mainRXtuningMode':             StateValue(self, set_method = self._set_mainRXtuningMode, range_check = self._check_mainRXtuningMode),
			'mainTXtuningMode':             StateValue(self, set_method = self._set_mainTXtuningMode, range_check = self._check_mainTXtuningMode),
			'subTuningMode':                StateValue(self),
			'VFOAmode':                     StateValue(self, query_method = self._query_VFOAmode),
			'VFOBmode':                     StateValue(self, query_method = self._query_VFOBmode),
			'mainMode':                     StateValue(self, query_method = self._query_mainMode),
			'subMode':                      StateValue(self, query_method = self._query_subMode),
			'TXmode':                       StateValue(self),
		}
		# Now plug the names in...
		for a, p in self._state.items():
			if isinstance(p, StateValue):
				p.name = a
		self.memories = MemoryArray(self)
		self._fill_cache()
		if self.powerOn:
			self.autoInformation = 2

	def __getattr__(self, name):
		if name in self._state:
			return self._state[name].value
		raise AttributeError('No state named ' + name + ' found in Kenwood object')

	def __setattr__(self, name, value):
		if name[:1] != '_':
			if name in self._state:
				self._state[name].value = value
		super().__setattr__(name ,value)

	# TODO: No nice way to add memories[] callbacks.
	def add_callback(self, prop, cb):
		self._state[prop].add_callback(cb)

	def remove_callback(self, prop, cb):
		self._state[prop].remove_callback(cb)

	def __init__(self, port = "/dev/ttyU0", speed = 4800, stopbits = 2, verbose = False):
		self._init_done = False
		self._terminate = False
		self._writeQueue = queue.Queue(maxsize = 0)
		self._verbose = verbose
		self._killing_cache = False
		self._serial = serial.Serial(baudrate = speed, stopbits = stopbits, rtscts = False, timeout = 0.01, inter_byte_timeout = 0.5)
		self._serial.rts = True
		self._serial.port = port
		self._serial.open()
		self._error_count = 0
		self._last_hack = time.time()
		# We assume all rigs support the ID command (for no apparent reason)
		self._state = {'ID': StateValue(self, query_command = 'ID', works_powered_off = True)}
		self._command = dict()
		self._command = {
			b'ID': self._update_ID,
			b'?': self._update_Error,
			b'E': self._update_ComError,
			b'O': self._update_IncompleteError,
		}
		self._readThread = threading.Thread(target = self._readThread, name = "Read Thread")
		self._readThread.start()
		self._last_command = None
		self._last_power_state = None
		self._fill_cache_state = {}

		resp = self.ID
		initFunction = '_init_' + str(resp)
		if callable(getattr(self, initFunction, None)):
			getattr(self, initFunction, None)()
		else:
			raise Exception("Unsupported rig (%d)!" % (resp))
		self._init_done = True
		self._sync_lock = threading.Lock()

	def _fill_cache_cb(self, prop, *args):
		nxt = None
		while len(self._fill_cache_state['todo']) > 0:
			nxt = self._fill_cache_state['todo'].pop(0)
			if not nxt[0].valid():
				self._fill_cache_state['matched_count'] += 1
				nxt = None
				continue
			break
		if nxt is not None:
			nxt[0]._add_wait_callback(nxt[1])
			self._send_query(nxt[0])

		if prop is not None:
			self._fill_cache_state['matched_count'] += 1
			prop._remove_wait_callback(self._fill_cache_cb)
			if self._fill_cache_state['matched_count'] == self._fill_cache_state['target_count']:
				for cb in self._fill_cache_state['call_after']:
					cb()

	def _fill_cache(self):
		done = {}
		self._fill_cache_state['todo'] = []
		self._fill_cache_state['call_after'] = ()
		self._fill_cache_state['target_count'] = 0
		self._fill_cache_state['matched_count'] = 0
		# Perform queries in this order:
		# 1) Simple string queries without validators
		# 2) Simple string queries with validators
		# 3) Method queries
		for a, p in self._state.items():
			if isinstance(p, StateValue):
				if p._query_command is None:
					if p._query_method is not None:
						self._fill_cache_state['call_after'] += (p._query_method,)
				else:
					if not p._query_command in done:
						done[p._query_command] = True
						self._fill_cache_state['target_count'] += 1
						if p._validity_check is not None:
							self._fill_cache_state['todo'].append((p, self._fill_cache_cb,))
						else:
							self._fill_cache_state['todo'].insert(0, (p, self._fill_cache_cb,))
		self._fill_cache_cb(None, None)

	def _kill_cache(self):
		self._killing_cache = True
		for a, p in self._state.items():
			if isinstance(p, StateValue):
				if p._query_command in ('PS', 'ID'):
					continue
				p._cached = None
		self._killing_cache = False

	def __del__(self):
		self.terminate()

	def terminate(self):
		if hasattr(self, 'autoInformation'):
			self.autoInformation = 0
		if hasattr(self, '_terminate'):
			self._terminate = True
		if hasattr(self, 'readThread'):
			self._readThread.join()

	def _send_query(self, state):
		self._writeQueue.put({
			'msgType': 'query',
			'stateValue': state,
		})

	def _query(self, state):
		self._error_count = 0
		ev = threading.Event()
		cb = lambda x, y: ev.set()
		state._add_wait_callback(cb)
		while True:
			# WE can't be the ones to retry since the error handler does that!
			self._send_query(state)
			if ev.wait(5):
				break
			raise Exception("I've been here all day waiting for "+str(state.name))
		state._remove_wait_callback(cb)

	# This attenpts to synchronize the queue and the rig.
	# Unfortunately, the rig will process commands out of order, so
	# sending FB00007072000;ID; responds with ID019;FB00007072000;
	# (Unless you're already on the 70.720 of course)
	#
	# As a result, the guarantee you get from calling this is that
	# all commands have been sent to the rig, and the rig has started
	# processing them.  This does not guarantee that processing is
	# complete.  Worst case, a command will hit a transient failure
	# and retry much later since retries go to the back of the queue
	# 
	# Actually, that's not the worst case since the command that gets
	# retried is the *last* command that was sent, in the example
	# above, if the FB failed after the ID was sent, the ID would
	# be retried, and the VFOB frequency would never actually get
	# updated.
	#
	# It *may* be possible to serialize these by relying on the
	# echoed property and adding a query of the modified data after
	# each command, but that's getting pretty insane and would
	# impose a large performance penalty that I don't want to face.
	def sync(self):
		self._sync_lock.acquire()
		self._query(self.ID)
		self._sync_lock.release()

	def _set(self, state, value):
		self._writeQueue.put({
			'msgType': 'set',
			'stateValue': state,
			'value': value,
		})

	def _read(self):
		ret = b'';
		while not self._terminate:
			# Always read first if possible.
			if self._serial.rts:
				ret += self._serial.read_until(b';')
				if ret[-1:] == b';':
					if self._verbose:
						print("Read: "+str(ret), file=sys.stderr)
					return ret
				else:
					if not self._writeQueue.empty():
						self._serial.rts = False
			if not self._writeQueue.empty():
				if self._serial.cts:
					self._serial.rts = False
			if self._serial.cts:
				if not self._writeQueue.empty():
					wr = self._writeQueue.get()
					self._last_command = wr
					if wr['msgType'] == 'set':
						cmd = wr['stateValue'].set_string(wr['value'])
					elif wr['msgType'] == 'query':
						cmd = wr['stateValue'].query_string()
					else:
						raise Exception('Unhandled message type: '+str(wr['msgType']))
					if cmd is None:
						if wr['msgType'] == 'query':
							wr['stateValue']._cached = None
					else:
						if cmd != '':
							cmd = bytes(cmd + ';', 'ascii')
							if self._verbose:
								print('Writing ' + str(cmd), file=sys.stderr)
							self._serial.write(cmd)
							# Another power-related hack...
							if cmd == b'PS0;':
								return cmd
							if wr['msgType'] == 'set' and (not wr['stateValue']._echoed):
								cmd = wr['stateValue'].query_string()
								if cmd is not None:
									cmd = bytes(cmd + ';', 'ascii')
									self._serial.write(cmd)
							self.last_hack = time.time()
				if self._writeQueue.empty():
					self._serial.rts = True
			else:
				self._serial.rts = True
			# The final piece of the puzzle...
			# It looks like when the rig is powered off, it takes a byte being
			# sent to wake it up.  It then stays awake for some period of time
			# before going back to sleep.  That period of time appears to be
			# longer than a second, so we send a power state request at least
			# every second of idle time when the rig is powered off.
			#
			# This has the side benefit of letting us know if/when the power state
			# change occured (as long as we know when we turned the rig off, see PS0 above)
			if (not 'powerOn' in self._state) or self._state['powerOn']._cached == False:
				if time.time() - self._last_hack > 1:
					self._serial.write(b'PS;')
					self._last_hack = time.time()

	def _readThread(self):
		while not self._terminate:
			cmdline = self._read()
			if cmdline is not None:
				m = re.match(b"^.*?([\?A-Z]{1,2})([\x20-\x3a\x3c-\x7f]*?);$", cmdline)
				if m:
					cmd = m.group(1)
					args = m.group(2).decode('ascii')
					if cmd in self._command:
						self._command[cmd](args)
					else:
						if self._init_done:
							print('Unhandled command "%s" (args: "%s")' % (cmd, args), file=sys.stderr)
				else:
					print('Bad command line: "'+str(cmdline)+'"', file=sys.stderr)

	def _update_AC(self, args):
		split = parse('1d1d1d', args)
		self._state['tuner']._cached = bool(split[0]) or bool(split[1])
		self._state['tunerRX']._cached = bool(split[0])
		self._state['tunerTX']._cached = bool(split[1])
		self._state['tunerState']._cached = tunerState(split[2])

	def _update_AG(self, args):
		split = parse('1d3d', args)
		if split[0] == 0:
			self._state['mainAFgain']._cached = split[1]
		else:
			self._state['subAFgain']._cached = split[1]

	def _update_AI(self, args):
		split = parse('1d', args)
		self._state['autoInformation']._cached = AI(split[0])

	def _update_AL(self, args):
		split = parse('3d', args)
		self._state['autoNotchLevel']._cached = split[0]

	def _update_AM(self, args):
		split = parse('1d', args)
		self._state['autoMode']._cached = bool(split[0])

	# TODO: None here means 2m or 440 fixed antenna
	#       maybe something better would be good?
	def _update_AN(self, args):
		split = parse('1d', args)
		self._state['antennaConnector']._cached = None if split[0] == 0 else split[0]
		self._state['antenna1']._cached = (split[0] == 1) if split[0] != 0 else None
		self._state['antenna2']._cached = (split[0] == 2) if split[0] != 0 else None

	def _update_AR(self, args):
		split = parse('1d1d1d', args)
		aso = bool(split[1])
		if split[0] == 0:
			self._state['mainAutoSimplexOn']._cached = aso
			self._state['mainSimplexPossible']._cached = bool(split[2]) if aso else False
		else:
			self._state['subAutoSimplexOn']._cached = aso
			self._state['subSimplexPossible']._cached = bool(split[2]) if aso else False

	def _update_BC(self, args):
		split = parse('1d', args)
		self._state['beatCanceller']._cached = BeatCanceller(split[0])
		if split[0] == 0:
			self._state['autoBeatCanceller']._cached = False
			self._state['manualBeatCanceller']._cached = False
		elif split[0] == 1:
			self._state['autoBeatCanceller']._cached = True
			self._state['manualBeatCanceller']._cached = False
		elif split[0] == 2:
			self._state['autoBeatCanceller']._cached = False
			self._state['manualBeatCanceller']._cached = True

	def _update_BP(self, args):
		split = parse('3d', args)
		self._state['manualBeatCancellerFrequency']._cached = split[0]

	def _update_BY(self, args):
		split = parse('1d1d', args)
		self._state['mainBusy']._cached = bool(split[0])
		self._state['subBusy']._cached = bool(split[1])

	def _update_CA(self, args):
		split = parse('1d', args)
		self._state['CWautoTune']._cached = bool(split[0])

	def _update_CG(self, args):
		split = parse('3d', args)
		self._state['carrierGain']._cached = split[0]

	def _update_CM(self, args):
		split = parse('1d', args)
		self._state['packetClusterTune']._cached = bool(split[0])

	def _update_CN(self, args):
		split = parse('2d', args)
		self._state['CTCSStone']._cached = CTCSStone(split[0])

	def _update_CT(self, args):
		split = parse('1d', args)
		self._state['CTCSS']._cached = bool(split[0])

	def _update_DC(self, args):
		split = parse('1d1d', args)
		self._state['TXmain']._cached = not bool(split[0])
		self._state['controlMain']._cached = not bool(split[1])

	def _update_DQ(self, args):
		split = parse('1d', args)
		self._state['DCS']._cached = bool(split[0])

	def _update_EX(self, args):
		split = parse('3d2d1d1d0l', args)
		if split[0] == 27:
			self._state['tunerOnInRX']._cached = bool(int(split[4]))
		if split[0] == 6:
			self._state['memoryVFOsplitEnabled']._cached = bool(int(split[4]))
		else:
			print('Unhandled EX menu {:03d}'.format(split[0]), file=sys.stderr)

	def _update_FA(self, args):
		split = parse('11d', args)
		self._state['vfoAFrequency']._cached = split[0]
		if self._state['mainRXtuningMode']._cached == tuningMode.VFOA:
			self._state['currentMainFrequency']._cached = split[0]
			if self._state['controlMain']._cached == True:
				self._state['currentFrequency']._cached = split[0]
		if self._state['mainTXtuningMode']._cached == tuningMode.VFOA:
			if self._state['TXmain']._cached == True:
				self._state['currentTXfrequency']._cached = split[0]

	def _update_FB(self, args):
		split = parse('11d', args)
		self._state['vfoBFrequency']._cached = split[0]
		if self._state['mainRXtuningMode']._cached == tuningMode.VFOB:
			self._state['currentMainFrequency']._cached = split[0]
			if self._state['controlMain']._cached == True:
				self._state['currentFrequency']._cached = split[0]
		if self._state['mainTXtuningMode']._cached == tuningMode.VFOB:
			if self._state['TXmain']._cached == True:
				self._state['currentTXfrequency']._cached = split[0]

	def _update_FC(self, args):
		split = parse('11d', args)
		self._state['subReceiverFrequency']._cached = split[0]
		if not self._state['controlMain']._cached:
			if self._state['subTuningMode']._cached == tuningMode.VFOA:
				self._state['currentFrequency']._cached = split[0]
		if self._state['TXmain']._cached == False:
			self._state['currentTXfrequency']._cached = split[0]

	def _update_FD(self, args):
		split = parse('8x', args)
		self._state['filterDisplayPattern']._cached = bitarray.util.int2ba(split[0], 32)

	def _update_FW(self, args):
		split = parse('4d', args)
		self._state['filterWidth']._cached = split[0]

	# TODO: Toggle tuningMode when transmitting?  Check the IF command...
	# NOTE: FR changes FT, but FT doesn't change FR **and** doesn't notify
	# that FT was changed.
	def _update_FR(self, args):
		split = parse('1d', args)
		self._state['currentFrequency']._cached = None
		if self._state['controlMain']._cached == True:
			self._state['currentMainFrequency']._cached = None
		else:
			self._state['currentSubFrequency']._cached = None
		if self._state['TXtuningMode']._cached_value is not None:
			if self._state['TXtuningMode']._cached != tuningMode(split[0]):
				self._state['split']._cached = True
			else:
				self._state['split']._cached = False
		self._state['RXtuningMode']._cached = tuningMode(split[0])
		if self._state['controlMain']._cached == True:
			self._state['mainRXtuningMode']._cached = tuningMode(split[0])
		else:
			self._state['subTuningMode']._cached = tuningMode(split[0])
		self._send_query(self._state['TXmain'])
		self._send_query(self._state['TXtuningMode'])

	def _update_FS(self, args):
		split = parse('1d', args)
		self._state['fineTuning']._cached = bool(split[0])

	def _update_FT(self, args):
		split = parse('1d', args)
		self._state['currentFrequency']._cached = None
		self._state['currentTXfrequency']._cached = None
		if self._state['RXtuningMode']._cached_value is not None:
			if self._state['RXtuningMode']._cached != tuningMode(split[0]):
				self._state['split']._cached = True
			else:
				self._state['currentTXfrequency']._cached = self._state['currentMainFrequency']._cached
				self._state['split']._cached = False
		self._state['TXtuningMode']._cached = tuningMode(split[0])
		if self._state['TXmain']._cached == True:
			self._state['mainTXtuningMode']._cached = tuningMode(split[0])
		else:
			self._state['subTuningMode']._cached = tuningMode(split[0])
		if self._state['TXmain']._cached:
			# I assume that FR has already been updated. :(
			# It *looks* like this is always true.
			if self._state['TXtuningMode']._cached == tuningMode.CALL:
				self._state['TXmode']._cached = self._state['mainMode']._cached
			elif self._state['TXtuningMode']._cached == tuningMode.MEMORY:
				self._state['currentTXfrequency']._cached = self.memories.memories[self._state['memoryChannel']._cached]._cached['TXFrequency']
				# Glah!  We'll just assume this is the same for now... TODO
				self._state['TXmode']._cached = self._state['mainMode'].self.memories.memories[self._state['memoryChannel']._cached]._cached['TXMode']
			elif self._state['TXtuningMode']._cached == tuningMode.VFOA:
				self._state['currentTXfrequency']._cached = self._state['vfoAFrequency']._cached
				self._state['TXmode']._cached = self._state['VFOAmode']._cached
			elif self._state['TXtuningMode']._cached == tuningMode.VFOB:
				self._state['currentTXfrequency']._cached = self._state['vfoBFrequency']._cached
				self._state['TXmode']._cached = self._state['VFOBmode']._cached

	def _update_GT(self, args):
		if args == '   ':
			self._state['AGCconstant']._cached = None
		else:
			split = parse('3d', args)
			self._state['AGCconstant']._cached = split[0]

	def _update_ID(self, args):
		self._state['ID']._cached = parse('3d', args)[0]

	def _update_IF(self, args):
		# TODO: Synchronize these with the single-value options
		# NOTE: Combined P6 and P7 since they're effectively one number on the TS-2000
		#'00003810000' '    ' ' 00000' '0' '0' '101' '0' '1' '0' '0' '0' '0' '08' '0'
		#'00003810000' '    ' ' 00000' '0' '0' '101' '0' '1' '0' '0' '0' '0' '08' '0'
		#     3810000,     0,       1,  0,  1,    0,  1,  0,  0,  0,  0,  0,   8,  0
		split = parse('11d4d6d1d1d3d1d1d1d1d1d1d2d1d', args)

		if split[6]:
			self._state['currentTXfrequency']._cached = split[0]
		else:
			self._state['currentFrequency']._cached = split[0]
		if self._state['controlMain']._cached == True:
			if not split[6]:
				self._state['currentMainFrequency']._cached = split[0]
		else:
			self._state['currentSubFrequency']._cached = split[0]
		self._state['frequencyStep']._cached = split[1]
		self._state['RIT_XITfrequency']._cached = split[2]
		self._state['RIT']._cached = bool(split[3])
		self._state['XIT']._cached = bool(split[4])
		self._state['channelBank']._cached = split[5]
		self._state['currentReceiverTransmitting']._cached = bool(split[6])
		self._update_MD(str(split[7]))
		if split[6]:
			self._state['TXtuningMode']._cached = tuningMode(split[8])
			if self._state['controlMain']._cached:
				self._state['mainTXtuningMode']._cached = tuningMode(split[8])
			else:
				self._state['subTuningMode']._cached = tuningMode(split[8])
		else:
			self._state['RXtuningMode']._cached = tuningMode(split[8])
			self._state['tuningMode']._cached = tuningMode(split[8])
			if self._state['controlMain']._cached:
				self._state['mainRXtuningMode']._cached = tuningMode(split[8])
			else:
				self._state['subTuningMode']._cached = tuningMode(split[8])
		self._state['scanMode']._cached = scanMode(split[9])
		# TODO: Split is undocumented and full-duplex may be here?
		self._state['split']._cached = bool(split[10])
		# TODO: TONE/CTCSS/DCS squished together here in split[11]
		# TODO: Tone frequency
		self._state['shiftStatus']._cached = offset(split[13])
		# Fun hack... in CALL mode, MC300 is updated via IF...
		# We handle this special case by asserting that if we get IF
		# when in MC300, the MC has been updated
		if self._state['memoryChannel']._cached == 300:
			self.memories.memories[300]._cached_value = None
			self._state['memoryChannel']._cached_value = None
			self._state['memoryChannel']._cached = 300

	def _update_IS(self, args):
		split = parse('5d', args)
		self._state['IFshift']._cached = split[0]

	def _update_KS(self, args):
		split = parse('3d', args)
		self._state['keyerSpeed']._cached = split[0]

	def _update_KY(self, args):
		split = parse('1d', args)
		self._state['keyerBufferFull']._cached = bool(split[0])

	def _update_LK(self, args):
		split = parse('1d1d', args)
		self._state['rigLock']._cached = rigLock(split[0])
		if split[0] == 0:
			self._state['frequencyLock']._cached = False
			self._state['allLock']._cached = False
		elif split[0] == 1:
			self._state['frequencyLock']._cached = True
			self._state['allLock']._cached = False
		elif split[1] == 2:
			self._state['frequencyLock']._cached = True
			self._state['allLock']._cached = True
		self._state['rc2000Lock']._cached = bool(split[1])

	def _update_LM(self, args):
		# TODO: Maybe false for 0 and be an int?
		split = parse('1d', args)
		self._state['recordingChannel']._cached = recordingChannel(split[0])

	def _update_LT(self, args):
		split = parse('1d', args)
		self._state['autoLockTuning']._cached = bool(split[0])

	def _update_MC(self, args):
		split = parse('3d', args)
		# TODO:
		# Any time we get an MC300; it means we entered CALL mode
		# The calling frequency *may* be different than last time!
		if split[0] == 300:
			self.memories.memories[300]._cached_value = None
		self._state['memoryChannel']._cached = split[0]
		# This also invalidates the current frequency
		self._state['currentFrequency']._cached = None
		if self._state['controlMain']._cached:
			self._state['currentMainFrequency']._cached = None
		else:
			self._state['currentSubFrequency']._cached = None

	def _update_MD(self, args):
		split = parse('1d', args)
		self._state['mode']._cached = mode(split[0])
		if not self._state['mode']._cached in (mode.CW, mode.CW_REVERSED,):
			self._state['CWautoTune']._cached = None
		else:
			self._state['CWautoTune']._cached = False
		if self._state['controlMain']._cached == True:
			self._state['mainMode']._cached = mode(split[0])
			if self._state['mainRXtuningMode']._cached == tuningMode.VFOA:
				self._state['VFOAmode']._cached = mode(split[0])
			elif self._state['mainRXtuningMode']._cached == tuningMode.VFOB:
				self._state['VFOBmode']._cached = mode(split[0])
		else:
			self._state['subMode']._cached = mode(split[0])

	def _update_MF(self, args):
		split = parse('1d', args)
		if split[0] == 0:
			self._state['menuAB']._cached = 'A'
		elif split[0] == 1:
			self._state['menuAB']._cached = 'B'

	def _update_MG(self, args):
		split = parse('3d', args)
		self._state['microphoneGain']._cached = split[0]

	def _update_ML(self, args):
		split = parse('3d', args)
		self._state['monitorLevel']._cached = split[0]

	def _update_MO(self, args):
		split = parse('1d', args)
		self._state['skyCommandMonitor']._cached = bool(split[0])

	# TODO: We actually need to merge these because we need two reads
	# to get the RX/TX frequencies and modes
	def _update_MR(self, args):
		split = parse('1d3d11d1d1d1d2d2d3d1d1d9d2d1d0l', args)
		idx = 0
		newVal = copy.deepcopy(self.memories.memories[split[1]]._cached)
		if newVal is None:
			newVal = {}
		newVal['Channel'] = split[1]
		if split[1] < 290 or split[1] > 299:
			if split[0]:
				newVal['TXfrequency'] = split[2]
			else:
				newVal['Frequency'] = split[2]
			if split[0]:
				newVal['TXmode'] = mode(split[3])
			else:
				newVal['Mode'] = mode(split[3])
		else:
			if split[0]:
				newVal['EndFrequency'] = split[2]
			else:
				newVal['StartFrequency'] = split[2]
			newVal['Mode'] = mode(split[3])
		newVal['LockedOut'] = bool(split[4])
		newVal['ToneType'] = toneType(split[5])
		# TODO: Tone Number mapping?
		newVal['ToneNumber'] = CTCSStone(split[6])
		newVal['CTCSStoneNumber'] = CTCSStone(split[7])
		newVal['DCScode'] = DCScode(split[8])
		newVal['Reverse'] = bool(split[9])
		newVal['OffsetType'] = offset(split[10])
		newVal['OffsetFrequency'] = split[11]
		newVal['StepSize'] = split[12]
		newVal['MemoryGroup'] = split[13]
		newVal['MemoryName'] = split[14]
		self.memories.memories[split[1]]._cached = newVal

	def _update_MU(self, args):
		self._state['memoryGroups']._cached = bitarray.util.base2ba(2, args)

	def _update_NB(self, args):
		split = parse('1d', args)
		self._state['noiseBlanker']._cached = bool(split[0])

	def _update_NL(self, args):
		split = parse('3d', args)
		self._state['noiseBlankerLevel']._cached = split[0]

	def _update_NR(self, args):
		split = parse('1d', args)
		self._state['noiseReduction']._cached = noiseReduction(split[0])
		if split[0] == 0:
			self._state['noiseReduction1']._cached = False
			self._state['noiseReduction2']._cached = False
		elif split[0] == 1:
			self._state['noiseReduction1']._cached = True
			self._state['noiseReduction2']._cached = False
		else:
			self._state['noiseReduction1']._cached = False
			self._state['noiseReduction2']._cached = True

	def _update_NT(self, args):
		split = parse('1d', args)
		self._state['autoNotch']._cached = bool(split[0])

	def _update_OF(self, args):
		split = parse('9d', args)
		self._state['offsetFrequency']._cached = split[0]

	def _update_OS(self, args):
		split = parse('1d', args)
		self._state['offsetType']._cached = offset(split[0])

	def _update_PA(self, args):
		split = parse('1d1d', args)
		self._state['mainPreAmp']._cached = bool(split[0])
		self._state['subPreAmp']._cached = bool(split[1])

	def _update_PB(self, args):
		split = parse('1d', args)
		self._state['playbackChannel']._cached = recordingChannel(split[0])

	def _update_PC(self, args):
		split = parse('3d', args)
		self._state['outputPower']._cached = split[0]

	def _update_PK(self, args):
		split = parse('11d12l20l5l', args)
		spot = {
			frequency: split[0],
			callsign: split[1],
			comments: split[2],
			time: split[3]
		}
		self._state['lastSpot']._cached = spot

	def _update_PL(self, args):
		split = parse('3d3d', args)
		self._state['speechProcessorInputLevel']._cached = split[0]
		self._state['speechProcessorOutputLevel']._cached = split[1]

	def _update_PM(self, args):
		split = parse('1d', args)
		# TODO: Should this be False when it's off?
		self._state['programmableMemoryChannel']._cached = split[0]

	def _update_PR(self, args):
		split = parse('1d', args)
		self._state['speechProcessor']._cached = bool(split[0])

	def _update_PS(self, args):
		split = parse('1d', args)
		old = self._last_power_state
		self._state['powerOn']._cached = bool(split[0])
		self._last_power_state = bool(split[0])
		if split[0] and old == False:
			self._set(self.autoInformation, 2)
			self._fill_cache()
		elif (not split[0]) and old == True:
			self._kill_cache()

	def _update_QC(self, args):
		split = parse('3d', args)
		self._state['DCScode']._cached = DCScode(split[0])

	def _update_QR(self, args):
		split = parse('1d1d', args)
		self._state['quickMemory']._cached = bool(split[0])
		self._state['quickMemoryChannel']._cached = split[1]

	def _update_RA(self, args):
		split = parse('2d', args)
		self._state['attenuator']._cached = bool(split[0])

	# NOTE: Updates the same value as RU
	def _update_RD(self, args):
		split = parse('1d', args)
		self._state['scanSpeed']._cached = split[0]

	def _update_RG(self, args):
		split = parse('3d', args)
		self._state['RFgain']._cached = split[0]

	def _update_RL(self, args):
		split = parse('2d', args)
		self._state['noiseReductionLevel']._cached = split[0]

	def _update_RM(self, args):
		split = parse('1d4d', args)
		self._state['meterType']._cached = meter(split[0])
		self._state['meterValue']._cached = split[1]
		self._state['SWRmeter']._cached = split[1] if split[0] == 1 else 0
		self._state['compressionMeter']._cached = split[1] if split[0] == 2 else 0
		self._state['ALCmeter']._cached = split[1] if split[0] == 3 else 0

	# Note: Can only set RM2 when COMP is on

	def _update_RT(self, args):
		split = parse('1d', args)
		self._state['RIT']._cached = bool(split[0])

	# NOTE: Updates the same value as RD
	def _update_RU(self, args):
		split = parse('1d', args)
		self._state['scanSpeed']._cached = split[0]

	def _update_RX(self, args):
		split = parse('1d', args)
		if self._state['TXmain']._cached == True and split[0] == 0:
			self._state['currentReceiverTransmitting']._cached = False
		elif self._state['RXmain']._cached == True and split[0] == 1:
			self._state['currentReceiverTransmitting']._cached = False
		if split[0] == 0:
			self._state['mainTransmitting']._cached = False
		if split[0] == 1:
			self._state['subTransmitting']._cached = False

	def _update_SA(self, args):
		split = parse('1d1d1d1d1d1d1d8l', args)
		self._state['satelliteMode']._cached = bool(split[0])
		self._state['satelliteMemoryChannel']._cached = split[1]
		self._state['satelliteMainUpSubDown']._cached = not bool(split[2])
		self._state['satelliteControlMain']._cached = not bool(split[3])
		self._state['satelliteTrace']._cached = bool(split[4])
		self._state['satelliteTraceReverse']._cached = bool(split[5])
		self._state['satelliteMultiKnobVFO']._cached = not bool(split[6])
		self._state['satelliteChannelName']._cached = split[7]

	def _update_SB(self, args):
		split = parse('1d', args)
		self._state['subReceiver']._cached = bool(split[0])

	def _update_SC(self, args):
		split = parse('1d', args)
		self._state['scanMode']._cached = scanMode(split[0])

	def _update_SD(self, args):
		split = parse('4d', args)
		self._state['cwBreakInTimeDelay']._cached = split[0]

	def _update_SH(self, args):
		split = parse('2d', args)
		self._state['voiceLowPassCutoff']._cached = split[0]

	def _update_SL(self, args):
		split = parse('2d', args)
		self._state['voiceHighPassCutoff']._cached = split[0]

	def _update_SM(self, args):
		split = parse('1d4d', args)
		# TODO: Figure out what 2 and 3 actually are...
		if split[0] == 0:
			self._state['mainSMeter']._cached = split[1]
		if split[0] == 1:
			self._state['subSMeter']._cached = split[1]
		if split[0] == 2:
			print('Got SM2!', file=sys.stderr)
			self._state['mainSMeterLevel']._cached = split[1]
		if split[0] == 3:
			print('Got SM3!', file=sys.stderr)
			self._state['subSMeterLevel']._cached = split[1]

	def _update_SQ(self, args):
		split = parse('1d3d', args)
		if split[0] == 0:
			self._state['mainSquelch']._cached = split[1]
		elif split[0] == 1:
			self._state['subSquelch']._cached = split[1]

	def _update_ST(self, args):
		split = parse('2d', args)
		self._state['multiChFrequencySteps']._cached = split[0]

	def _update_TC(self, args):
		split = parse('1d1d', args)
		self._state['PCcontrolCommandMode']._cached = bool(split[1])

	def _update_TI(self, args):
		split = parse('1d1d1d', args)
		self._state['tnc96kLED']._cached = bool(split[0])
		self._state['tncSTALED']._cached = bool(split[1])
		self._state['tncCONLED']._cached = bool(split[2])

	def _update_TN(self, args):
		split = parse('2d', args)
		# TODO: Smart mapping thing?
		self._state['subToneFrequency']._cached = CTCSStone(split[0])

	def _update_TO(self, args):
		split = parse('1d', args)
		self._state['toneFunction']._cached = bool(split[0])

	def _update_TS(self, args):
		split = parse('1d', args)
		self._state['transmitSet']._cached = bool(split[0])

	def _update_TX(self, args):
		split = parse('1d', args)
		self._state['currentFrequency']._cached = None
		if self._state['TXmain']._cached == True and split[0] == 0:
			self._state['currentReceiverTransmitting']._cached = True
		elif self._state['RXmain']._cached == True and split[0] == 1:
			self._state['currentReceiverTransmitting']._cached = True
		else:
			print('TX triggered for wrong receiver!', file=sys.stderr)
		if split[0] == 0:
			self._state['mainTransmitting']._cached = True
		if split[0] == 1:
			self._state['subTransmitting']._cached = True

	def _update_TY(self, args):
		split = parse('2d1d', args)
		self._state['firmwareType']._cached = firmwareType(split[1])

	def _update_UL(self, args):
		split = parse('1d', args)
		if split[0] == 1:
			raise Exception('PLL Unlocked!')
		self._state['PLLunlock']._cached = bool(split[0])

	def _update_VD(self, args):
		split = parse('4d', args)
		self._state['VOXdelayTime']._cached = split[0]

	def _update_VG(self, args):
		split = parse('3d', args)
		self._state['VOXgain']._cached = split[0]

	def _update_VX(self, args):
		split = parse('1d', args)
		self._state['VOX']._cached = bool(split[0])

	def _update_XT(self, args):
		split = parse('1d', args)
		self._state['XIT']._cached = bool(split[0])

	def _update_Error(self, args):
		self._error_count += 1
		if self._error_count < 10:
			print('Resending: '+str(self._last_command), file=sys.stderr)
			self._writeQueue.put(self._last_command)
		else:
			raise Exception('Error count exceeded')

	def _update_ComError(self, args):
		self._error_count += 1
		if self._error_count < 10:
			print('Resending: '+str(self._last_command), file=sys.stderr)
			self._writeQueue.put(self._last_command)
		else:
			raise Exception('Error count exceeded')

	def _update_IncompleteError(self, args):
		self._error_count += 1
		if self._error_count < 10:
			print('Resending: '+str(self._last_command), file=sys.stderr)
			self._writeQueue.put(self._last_command)
		else:
			raise Exception('Error count exceeded')
