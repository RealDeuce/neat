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
import re
import serial
import sys
import time
import threading
import enum

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
			cb(value)

	@property
	def value(self):
		if self._works_powered_off != True and not self._rig.powerOn.value:
			self._cached = None
			return None
		if self._validity_check is not None and not self._validity_check():
			self._cached = None
			return None
		if self._cached is None:
			if self._query_method is not None:
				self._query_method()
			elif self._query_command is not None:
				self._rig._query(self)
			else:
				raise Exception('Attempt to set value without a setter')
		# We just deepcopy it as an easy hack
		return copy.deepcopy(self._cached)

	@value.setter
	def value(self, value):
		if self._works_powered_off != True and not self._rig.powerOn.value:
			self._cached = None
			return None
		if self._range_check is not None and not self._range_check(value):
			return
		if self._validity_check is not None and not self._validity_check():
			return
		if self._set_format is not None:
			self._rig._write(self._set_format.format(value))
		else:
			self._set_method(value)

	@property
	def uncached_value(self):
		self._cached_value = None
		return self.value

	def valid(self):
		if self._validity_check is not None:
			return self._validity_check()
		return True

	def range_check(self, value):
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
		self._wait_callbacks = tuple(filter(lambda x: x == cb, self._wait_callbacks))

class Kenwood:
	def _update_mainTransmitting(self):
		self.mainTransmitting._cached = self.TXmain.value and self.currentReceiverTransmitting.value

	def _update_subTransmitting(self):
		self.subTransmitting._cached = (not self.TXmain.value) and self.currentReceiverTransmitting.value

	def _noiseBlankerValid(self):
		return self.mode.value != mode.FM

	def _set_manualBeatCanceller(self, value):
		self._write('BC{:01d}'.format(BeatCanceller.MANUAL if value else BeatCanceller.OFF))

	def _set_frequencyLock(self, value):
		rc = self.rc2000Lock.uncached_value
		self._write('LK{:01d}{:01d}'.format(value, rc))

	def _set_allLock(self, value):
		rc = self.rc2000Lock.uncached_value
		self._write('LK{:01d}{:01d}'.format(2 if value else 0, rc))

	def _set_rigLock(self, value):
		rc = self.rc2000Lock.uncached_value
		self._write('LK{:01d}{:01d}'.format(value, rc))

	def _set_rc2000Lock(self, value):
		fa = self.rigLock.uncached_value
		self._write('LK{:01d}{:01d}'.format(fa, value))

	def _set_memoryGroups(self, value):
		self._write('MU{:1d}{:1d}{:1d}{:1d}{:1d}{:1d}{:1d}{:1d}{:1d}{:1d}'.format(value[0], value[1], value[2], value[3], value[4], value[5], value[6], value[7], value[8], value[9]))
		self._write('MU')

	def _set_noiseReduction2(self, value):
		self._write('NR{:01d}'.format(noiseReduction.NR2 if value else noiseReduction.OFF))

	def _set_speechProcessorInputLevel(self, value):
		ol = self.speechProcessorOutputLevel.uncached_value
		self._write('PL{:03d}{:03d}'.format(value, ol))

	def _set_speechProcessorOutputLevel(self, value):
		ol = self.speechProcessorInputLevel.uncached_value
		self._write('PL{:03d}{:03d}'.format(ol, value))

	def _set_quickMemory(self, value):
		qm = self.quickMemoryChannel.uncached_value
		self._write('QR{:01d}{:01d}'.format(value, qm))

	def _set_quickMemoryChannel(self, value):
		qm = self.quickMemory.uncached_value
		self._write('QR{:01d}{:01d}'.format(qm, value))

	def _RITupDownValid(self):
		return self.scanMode.value == scanMode.OFF

	def _scanSpeedUpDownValid(self):
		return self.scanMode.value != scanMode.OFF

	def _noiseReductionLevelValid(self):
		return self.noiseReduction.value != noiseReduction.OFF

	def _mainReceiverOnly(self):
		return self.controlMain.value

	def _voiceCutoffValid(self):
		if not self.controlMain.value:
			return False
		return self.mode.value in (mode.AM, mode.FM, mode.LSB, mode.USB)

	def _inMemoryMode(self):
		return self.tuningMode.value == tuningMode.MEMORY

	def _set_mainTransmitting(self, value):
		if value:
			self._write('TX0')
		else:
			self._write('RX0')

	def _set_subTransmitting(self, value):
		if value:
			self._write('TX1')
		else:
			self._write('RX1')

	def _checkMeterValue(self, value):
		if meter(value) == meter.COMPRESSION and not self.speechProcessor.value:
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
		if self.currentFrequency.value <= 60000000 and (value == 1 or value == 2):
			return True
		return False

	def _antenna1Valid(self):
		return self._antennaRangeCheck(1)

	def _antenna2Valid(self):
		return self._antennaRangeCheck(2)

	def _setAntenna1(self, value):
		self._write('AN' + '1' if value else '2')

	def _setAntenna2(self, value):
		self._write('AN' + '2' if value else '1')

	def _cwAutoTuneRange(self, value):
		if not self.mode.value in (mode.CW, mode.CW_REVERSED, ):
			return False
		if value:
			return True
		if self.CWautoTune:
			return True
		return False

	def _cwAutoTuneValid(self):
		if self.mode.value in (mode.CW, mode.CW_REVERSED, ):
			return True
		return False

	def _memoryGroupRange(self, value):
		if not 1 in value:
			return False
		return True

	def init_19(self):
		# Errors
		self.command = {
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
			# TODO: TS - Weird docs
			b'TX': self._update_TX,
			b'TY': self._update_TY,
			b'UL': self._update_UL,
			b'VD': self._update_VD,
			b'VG': self._update_VG,
			b'VX': self._update_VX,
			b'XT': self._update_XT,
		}

		# State objects
		self.tuner =                        StateValue(self, query_command = 'AC',  set_format = 'AC1{:1d}0')
		self.tunerRX =                      StateValue(self, query_command = 'AC')
		self.tunerTX =                      StateValue(self, query_command = 'AC')
		self.tunerState =                   StateValue(self, query_command = 'AC',  set_format = 'AC11{:1d}')
		self.mainAFgain =                   StateValue(self, query_command = 'AG0', set_format = 'AG0{:03d}')
		self.subAFgain =                    StateValue(self, query_command = 'AG1', set_format = 'AG1{:03d}')
		self.autoInformation =              StateValue(self, query_command = 'AI',  set_format = 'AI{:01d}')
		self.autoNotchLevel =               StateValue(self, query_command = 'AL',  set_format = 'AL{:03d}')
		self.autoMode =                     StateValue(self, query_command = 'AM',  set_format = 'AM{:01d}')
		self.antennaConnector =             StateValue(self, query_command = 'AN',  set_format = 'AN{:01d}', range_check = self._antennaRangeCheck)
		self.antenna1 =                     StateValue(self, query_command = 'AN',  set_method = self._setAntenna1, validity_check = self._antenna1Valid)
		self.antenna2 =                     StateValue(self, query_command = 'AN',  set_method = self._setAntenna2, validity_check = self._antenna2Valid)
		self.mainAutoSimplexOn =            StateValue(self, query_command = 'AR0', set_format = 'AR0{:01d}1')
		self.mainSimplexPossible =          StateValue(self, query_command = 'AR0')
		self.subAutoSimplexOn =             StateValue(self, query_command = 'AR1', set_format = 'AR1{:01d}1')
		self.subSimplexPossible =           StateValue(self, query_command = 'AR1')
		self.beatCanceller =                StateValue(self, query_command = 'BC',  set_format = 'BC{:01}')
		self.autoBeatCanceller =            StateValue(self, query_command = 'BC',  set_format = 'BC{:01}')
		self.manualBeatCanceller =          StateValue(self, query_command = 'BC',  set_method = self._set_manualBeatCanceller)
		self.bandDown =                     StateValue(self,                        set_format = 'BD')
		self.manualBeatCancellerFrequency = StateValue(self, query_command = 'BP',  set_format = 'BP{:03d}')
		self.bandUp =                       StateValue(self,                        set_format = 'BU')
		self.mainBusy =                     StateValue(self, query_command = 'BY')
		self.subBusy =                      StateValue(self, query_command = 'BY')
		self.CWautoTune =                   StateValue(self, query_command = 'CA',  set_format = 'CA{:01d}', validity_check = self._cwAutoTuneValid, range_check = self._cwAutoTuneRange)
		self.carrierGain =                  StateValue(self, query_command = 'CG',  set_format = 'CG{:03d}')
		# False turns it up, True turns it down (derp derp)
		self.turnMultiChControlDown =       StateValue(self,                        set_format = 'CH{:01d}')
		# Sets the current frequency to be the CALL frequency for the band
		self.storeAsCallFrequency =         StateValue(self,                        set_format = 'CI')
		self.packetClusterTune =            StateValue(self, query_command = 'CM',  set_format = 'CM{:01d}')
		self.CTCSStone =                    StateValue(self, query_command = 'CN',  set_format = 'CN{:02d}')
		self.CTCSS =                        StateValue(self, query_command = 'CT',  set_format = 'CT{:01d}')
		self.TXmain =                       StateValue(self, query_command = 'DC')
		self.controlMain =                  StateValue(self, query_command = 'DC')
		self.down =                         StateValue(self,                        set_format = 'DN')
		self.DCS =                          StateValue(self, query_command = 'DQ',  set_format = 'DQ{:01d}')
		self.vfoAFrequency =                StateValue(self, query_command = 'FA',  set_format = 'FA{:011d}', range_check = self._checkMainFrequencyValid)
		self.vfoBFrequency =                StateValue(self, query_command = 'FB',  set_format = 'FB{:011d}', range_check = self._checkMainFrequencyValid)
		self.subReceiverFrequency =         StateValue(self, query_command = 'FC',  set_format = 'FC{:011d}', range_check = self._checkSubFrequencyValid)
		self.filterDisplayPattern =         StateValue(self, query_command = 'FD')
		self.RXtuningMode =                 StateValue(self, query_command = 'FR',  set_format = 'FR{:01d}')
		self.fineTuning =                   StateValue(self, query_command = 'FS',  set_format = 'FS{:01d}')
		self.TXtuningMode =                 StateValue(self, query_command = 'FT',  set_format = 'FT{:01d}')
		self.split =                        StateValue(self)
		self.filterWidth =                  StateValue(self, query_command = 'FW',  set_format = 'FW{:04d}', validity_check = self._mainReceiverOnly)
		self.AGCconstant =                  StateValue(self, query_command = 'GT',  set_format = 'GT{:03d}')
		self.ID =                           StateValue(self, query_command = 'ID',  works_powered_off = True)
		self.currentReceiverTransmitting =  StateValue(self, query_command = 'IF')
		self.currentFrequency =             StateValue(self, query_command = 'IF')
		self.frequencyStep =                StateValue(self, query_command = 'IF')
		self.RIT_XITfrequency =             StateValue(self, query_command = 'IF')
		self.channelBank =                  StateValue(self, query_command = 'IF')
		self.splitMode =                    StateValue(self, query_command = 'IF')
		self.shiftStatus =                  StateValue(self, query_command = 'IF')
		self.tuningMode =                   StateValue(self, query_command = 'IF')
		self.IFshift =                      StateValue(self, query_command = 'IS',  set_format = 'IS {:04d}')
		self.keyerSpeed =                   StateValue(self, query_command = 'KS',  set_format = 'KS{:03d}')
		self.keyerBufferFull =              StateValue(self, query_command = 'KY')
		self.keyerBuffer =                  StateValue(self,                        set_format = 'KY {:24}')
		self.frequencyLock =                StateValue(self, query_command = 'LK',  set_method = self._set_frequencyLock)
		self.allLock =                      StateValue(self, query_command = 'LK',  set_method = self._set_allLock)
		self.rc2000Lock =                   StateValue(self, query_command = 'LK',  set_method = self._set_rc2000Lock)
		self.rigLock =                      StateValue(self, query_command = 'LK',  set_method = self._set_rigLock)
		self.recordingChannel =             StateValue(self, query_command = 'LM',  set_format = 'LM{:01d}')
		self.autoLockTuning =               StateValue(self, query_command = 'LT',  set_format = 'LT{:01d}')
		self.memoryChannel =                StateValue(self, query_command = 'MC',  set_format = 'MC{:03d}')
		self.mode =                         StateValue(self, query_command = 'MD',  set_format = 'MD{:01d}')
		self.menuAB =                       StateValue(self, query_command = 'MF',  set_format = 'MF{:1}')
		self.microphoneGain =               StateValue(self, query_command = 'MG',  set_format = 'MG{:03d}')
		self.monitorLevel =                 StateValue(self, query_command = 'ML',  set_format = 'ML{:03d}')
		self.skyCommandMonitor =            StateValue(self, query_command = 'MO',  set_format = 'MO{:01d}')
		# TODO: Modernize MR (memory read)
		# TODO: Modernize MW (memory write)
		self.memoryGroups =                 StateValue(self, query_command = 'MU',  set_method = self._set_memoryGroups, range_check = self._memoryGroupRange)
		self.noiseBlanker =                 StateValue(self, query_command = 'NB',  set_format = 'NB{:01d}', validity_check = self._noiseBlankerValid)
		self.noiseBlankerLevel =            StateValue(self, query_command = 'NL',  set_format = 'NL{:03d}')
		self.noiseReduction =               StateValue(self, query_command = 'NR',  set_format = 'NR{:01d}')
		self.noiseReduction1 =              StateValue(self, query_command = 'NR',  set_format = 'NR{:01d}')
		self.noiseReduction2 =              StateValue(self, query_command = 'NR',  set_method = self._set_noiseReduction2)
		self.autoNotch =                    StateValue(self, query_command = 'NT',  set_format = 'NT{:01d}')
		self.offsetFrequency =              StateValue(self, query_command = 'OF',  set_format = 'OF{:09d}')
		# TODO: OI appears to be IF for the non-active receiver... not sure if that's PTT or CTRL
		self.offsetType =                   StateValue(self, query_command = 'OS',  set_format = 'OS{:01d}')
		self.mainPreAmp =                   StateValue(self, query_command = 'PA',  set_format = 'PA{:01d}')
		self.subPreAmp =                    StateValue(self, query_command = 'PA')
		self.playbackChannel =              StateValue(self, query_command = 'PB',  set_format = 'PB{:01d}')
		self.outputPower =                  StateValue(self, query_command = 'PC',  set_format = 'PC{:03d}')
		self.storeAsProgrammableMemory =    StateValue(self,                        set_format = 'PI{:01d}')
		self.lastSpot =                     StateValue(self)
		self.speechProcessorInputLevel =    StateValue(self, query_command = 'PL',  set_method = self._set_speechProcessorInputLevel)
		self.speechProcessorOutputLevel =   StateValue(self, query_command = 'PL',  set_method = self._set_speechProcessorOutputLevel)
		self.programmableMemoryChannel =    StateValue(self, query_command = 'PM',  set_format = 'PM{:01d}')
		self.speechProcessor =              StateValue(self, query_command = 'PR',  set_format = 'PR{:01d}')
		self.powerOn =                      StateValue(self, query_command = 'PS',  set_format = 'PS{:01d}', works_powered_off = True)
		self.DCScode =                      StateValue(self, query_command = 'QC',  set_format = 'QC{:03d}')
		self.storeAsQuickMemory =           StateValue(self,                        set_format = 'QC')
		self.quickMemory =                  StateValue(self, query_command = 'QR',  set_method = self._set_quickMemory)
		self.quickMemoryChannel =           StateValue(self, query_command = 'QR',  set_method = self._set_quickMemoryChannel)
		self.attenuator =                   StateValue(self, query_command = 'RA',  set_format = 'RA{:02d}')
		self.clearRIT =                     StateValue(self,                        set_format = 'RC')
		self.RITdown =                      StateValue(self,                        set_format = 'RD{:04d}', validity_check = self._RITupDownValid)
		self.scanSpeed =                    StateValue(self, query_command = 'RD',  validity_check = self._scanSpeedUpDownValid)
		self.scanSpeedDown =                StateValue(self,                        set_format = 'RD{:04d}', validity_check = self._scanSpeedUpDownValid)
		self.RFgain =                       StateValue(self, query_command = 'RG',  set_format = 'RG{:03d}')
		self.noiseReductionLevel =          StateValue(self, query_command = 'RL',  set_format = 'RL{:02d}', validity_check = self._noiseReductionLevelValid)
		self.meterType =                    StateValue(self, query_command = 'RM',  set_format = 'RM{:01d}', range_check = self._checkMeterValue)
		self.meterValue =                   StateValue(self, query_command = 'RM')
		self.SWRmeter =                     StateValue(self, query_command = 'RM')
		self.compressionMeter =             StateValue(self, query_command = 'RM')
		self.ALCmeter =                     StateValue(self, query_command = 'RM')
		self.RIT =                          StateValue(self, query_command = 'RT',  set_format = 'RT{:01d}')
		self.RITup =                        StateValue(self,                        set_format = 'RU{:04d}', validity_check = self._RITupDownValid)
		self.scanSpeedUp =                  StateValue(self,                        set_format = 'RU{:04d}', validity_check = self._scanSpeedUpDownValid)
		self.mainTransmitting =             StateValue(self, query_method = self._update_mainTransmitting, set_method = self._set_mainTransmitting) # RX, TX
		self.subTransmitting =              StateValue(self, query_method = self._update_subTransmitting, set_method = self._set_subTransmitting) # RX, TX
		# TODO: Setters for SA command
		self.satelliteMode =                StateValue(self, query_command = 'SA')
		self.satelliteMemoryChannel =       StateValue(self, query_command = 'SA')
		self.satelliteMainUpSubDown =       StateValue(self, query_command = 'SA')
		self.satelliteControlMain =         StateValue(self, query_command = 'SA')
		self.satelliteTrace =               StateValue(self, query_command = 'SA')
		self.satelliteTraceReverse =        StateValue(self, query_command = 'SA')
		self.satelliteMultiKnobVFO =        StateValue(self, query_command = 'SA')
		self.satelliteChannelName =         StateValue(self, query_command = 'SA')
		self.subReceiver =                  StateValue(self, query_command = 'SB',  set_format = 'SB{:01d}')
		self.scanMode =                     StateValue(self, query_command = 'SB',  set_format = 'SB{:01d}')
		self.cwBreakInTimeDelay =           StateValue(self, query_command = 'SD',  set_format = 'SD{:04d}')
		self.voiceLowPassCutoff =           StateValue(self, query_command = 'SH',  set_format = 'SH{:02d}', validity_check = self._voiceCutoffValid)
		# TODO: SI - Satellite memory name
		self.voiceHighPassCutoff =          StateValue(self, query_command = 'SL',  set_format = 'SL{:02d}', validity_check = self._voiceCutoffValid)
		self.mainSMeter =                   StateValue(self, query_command = 'SM0')
		self.subSMeter =                    StateValue(self, query_command = 'SM1')
		self.mainSMeterLevel =              StateValue(self, query_command = 'SM2')
		self.subSMeterLevel =               StateValue(self, query_command = 'SM3')
		self.mainSquelch =                  StateValue(self, query_command = 'SQ0', set_format = 'SQ0{:03d}')
		self.subSquelch =                   StateValue(self, query_command = 'SQ1', set_format = 'SQ1{:03d}')
		# TODO?: SR1, SR2... reset transceiver
		# TODO: SS set/read Program Scan pause frequency
		self.multiChFrequencySteps =        StateValue(self, query_command = 'ST',  set_format = 'ST{:02d}')
		# TODO: SU - program scan pause frequency
		self.memoryToVFO =                  StateValue(self,                        set_format = 'SV', validity_check = self._inMemoryMode)
		self.PCcontrolCommandMode =         StateValue(self, query_command = 'TC',  set_format = 'TC {:01d}')
		self.sendDTMFmemoryData =           StateValue(self,                        set_format = 'TD {:02d}')
		self.tnc96kLED =                    StateValue(self, query_command = 'TI')
		self.tncSTALED =                    StateValue(self, query_command = 'TI')
		self.tncCONLED =                    StateValue(self, query_command = 'TI')
		self.subToneFrequency =             StateValue(self, query_command = 'TN',  set_format = 'TN{:02d}')
		self.toneFunction =                 StateValue(self, query_command = 'TO',  set_format = 'TO{:01d}')
		# TODO: TS
		self.firmwareType =                 StateValue(self, query_command = 'TY')
		# TODO: UL? (PLL Unlock)
		self.up =                           StateValue(self,                        set_format = 'UP')
		self.VOXdelayTime =                 StateValue(self, query_command = 'VD',  set_format = 'VD{:04d}')
		self.VOXgain =                      StateValue(self, query_command = 'VG',  set_format = 'VG{:03d}')
		self.voice1 =                       StateValue(self,                        set_format = 'VR0')
		self.voice2 =                       StateValue(self,                        set_format = 'VR1')
		self.VOX =                          StateValue(self, query_command = 'VX',  set_format = 'VX{:01d}')
		self.XIT =                          StateValue(self, query_command = 'XT',  set_format = 'XT{:01d}')
		self.tunerOnInRX =                  StateValue(self, query_command = 'EX0270000',  set_format = 'EX0270000{:01d}')

		# Memories
		self.memories = [None] * 301
		for i in range(len(self.memories)):
			self.memories[i] = StateValue(self, query_command = 'MR0{:03d}'.format(i))


		# Populate values used in parser callbacks:
		if self.powerOn.value:
			# Initialization
			self.autoInformation.value = 2
			self._write(self.controlMain._query_command)
			self._write(self.RXtuningMode._query_command)     # used for split
			self._write(self.TXtuningMode._query_command)     # used for split
			self._write(self.TXmain._query_command)
			self._write(self.currentReceiverTransmitting._query_command)

	def __init__(self, port = "/dev/ttyU0", speed = 4800, stopbits = 2):
		self.init_done = False
		self._terminate = False
		self.serial = serial.Serial(port = port, baudrate = speed, stopbits = stopbits, rtscts = True, timeout = 0.1, inter_byte_timeout = 0.5)
		self.error_count = 0
		# We assume all rigs support the ID command (for no apparent reason)
		self.ID = StateValue(self, query_command = 'ID', works_powered_off = True)
		self.command = dict()
		self.command = {b'ID': self._update_ID}
		self.readThread = threading.Thread(target = self._readThread, name = "Read Thread")
		self.readThread.start()
		self.last_command = None
		resp = self.ID.value
		initFunction = 'init_' + str(resp)
		if callable(getattr(self, initFunction, None)):
			getattr(self, initFunction, None)()
		else:
			raise Exception("Unsupported rig (%d)!" % (resp))
		self.init_done = True

	def __del__(self):
		self._write('AI0')
		self._terminate = True
		self.readThread.join()

	def terminate(self):
		self._write('AI0')
		self._terminate = True
		self.readThread.join()

	def _query(self, state):
		if threading.get_ident() == self.readThread.ident:
			raise Exception('_query() called from read thread')
		self.error_count = 0
		ev = threading.Event()
		cb = lambda x: ev.set()
		state._add_wait_callback(cb)
		self._write(state._query_command)
		ev.wait()
		state._remove_wait_callback(cb)

	def _write(self, cmd):
		self.last_command = cmd
		wr = bytes(self.last_command + ';', 'ascii')
		#print("Write: "+str(wr))
		self.serial.write(wr)

	def _read(self):
		ret = b'';
		while not self._terminate:
			ret += self.serial.read_until(b';')
			if ret[-1:] == b';':
				#print("Read: '"+str(ret)+"'")
				return ret

	def _readThread(self):
		while not self._terminate:
			cmdline = self._read()
			if cmdline is not None:
				re.sub(b'[\x00-\x1f\x7f-\xff]', b'', cmdline)
				m = re.match(b"^([?A-Z]{1,2})([\x00-\x3a\x3c-\x7f]*);$", cmdline)
				if m:
					cmd = m.group(1)
					args = m.group(2).decode('ascii')
					if cmd in self.command:
						self.command[cmd](args)
					else:
						if self.init_done:
							print('Unhandled command "%s" (args: "%s")' % (cmd, args), file=sys.stderr)
				else:
					print('Bad command line: "'+str(cmdline)+'"', file=sys.stderr)

	def _update_AC(self, args):
		split = parse('1d1d1d', args)
		self.tuner._cached = bool(split[0]) or bool(split[1])
		self.tunerRX._cached = bool(split[0])
		self.tunerTX._cached = bool(split[1])
		self.tunerState._cached = tunerState(split[2])

	def _update_AG(self, args):
		split = parse('1d3d', args)
		if split[0] == 0:
			self.mainAFgain._cached = split[1]
		else:
			self.subAFgain._cached = split[1]

	def _update_AI(self, args):
		split = parse('1d', args)
		self.autoInformation._cached = AI(split[0])

	def _update_AL(self, args):
		split = parse('3d', args)
		self.autoNotchLevel._cached = split[0]

	def _update_AM(self, args):
		split = parse('1d', args)
		self.autoMode._cached = bool(split[0])

	# TODO: None here means 2m or 440 fixed antenna
	#       maybe something better would be good?
	def _update_AN(self, args):
		split = parse('1d', args)
		self.antennaConnector._cached = None if split[0] == 0 else split[0]
		self.antenna1._cached = (split[0] == 1) if split[0] != 0 else None
		self.antenna2._cached = (split[0] == 2) if split[0] != 0 else None

	def _update_AR(self, args):
		split = parse('1d1d1d', args)
		aso = bool(split[1])
		if split[0] == 0:
			self.mainAutoSimplexOn._cached = aso
			self.mainSimplexPossible._cached = bool(split[2]) if aso else False
		else:
			self.subAutoSimplexOn._cached = aso
			self.subSimplexPossible._cached = bool(split[2]) if aso else False

	def _update_BC(self, args):
		split = parse('1d', args)
		self.beatCanceller._cached = BeatCanceller(split[0])
		if split[0] == 0:
			self.autoBeatCanceller._cached = False
			self.manualBeatCanceller._cached = False
		elif split[0] == 1:
			self.autoBeatCanceller._cached = True
			self.manualBeatCanceller._cached = False
		elif split[0] == 2:
			self.autoBeatCanceller._cached = False
			self.manualBeatCanceller._cached = True

	def _update_BP(self, args):
		split = parse('3d', args)
		self.manualBeatCancellerFrequency._cached = split[0]

	def _update_BY(self, args):
		split = parse('1d1d', args)
		self.mainBusy._cached = bool(split[0])
		self.subBusy._cached = bool(split[1])

	def _update_CA(self, args):
		split = parse('1d', args)
		self.CWautoTune._cached = bool(split[0])

	def _update_CG(self, args):
		split = parse('3d', args)
		self.carrierGain._cached = split[0]

	def _update_CM(self, args):
		split = parse('1d', args)
		self.packetClusterTune._cached = bool(split[0])

	def _update_CN(self, args):
		split = parse('2d', args)
		self.CTCSStone._cached = CTCSStone(split[0])

	def _update_CT(self, args):
		split = parse('1d', args)
		self.CTCSS._cached = bool(split[0])

	def _update_DC(self, args):
		split = parse('1d1d', args)
		self.TXmain._cached = not bool(split[0])
		self.controlMain._cached = not bool(split[1])

	def _update_DQ(self, args):
		split = parse('1d', args)
		self.DCS._cached = bool(split[0])

	def _update_EX(self, args):
		split = parse('3d2d1d1d0l', args)
		if split[0] == 27:
			self.tunerOnInRX._cached = bool(int(split[4]))
		else:
			print('Unhandled EX menu {:03d}'.format(split[0]), file=sys.stderr)

	def _update_FA(self, args):
		split = parse('11d', args)
		if self.tuningMode == tuningMode.VFOA:
			self.currentFrequency._cached = split[0]
		self.vfoAFrequency._cached = split[0]

	def _update_FB(self, args):
		split = parse('11d', args)
		if self.tuningMode == tuningMode.VFOB:
			self.currentFrequency._cached = split[0]
		self.vfoBFrequency._cached = split[0]

	def _update_FC(self, args):
		split = parse('11d', args)
		if not self.controlMain:
			if not self.subTransmitting:
				self.currentFrequency._cached = split[0]
		elif not self.TXmain:
			if self.subTransmitting:
				self.currentFrequency._cached = split[0]
		self.subReceiverFrequency._cached = split[0]

	def _update_FD(self, args):
		split = parse('8x', args)
		self.filterDisplayPattern._cached = bitarray.util.int2ba(split[0], 32)

	def _update_FW(self, args):
		split = parse('4d', args)
		self.filterWidth._cached = split[0]

	def _update_FR(self, args):
		split = parse('1d', args)
		self.currentFrequency._cached = None
		if self.TXtuningMode._cached_value is not None:
			if self.TXtuningMode != tuningMode(split[0]):
				self.split._cached = True
		if not self.mainTransmitting:
			self.tuningMode._cached = tuningMode(split[0])
		self.RXtuningMode._cached = tuningMode(split[0])

	def _update_FS(self, args):
		split = parse('1d', args)
		self.fineTuning._cached = bool(split[0])

	def _update_FT(self, args):
		split = parse('1d', args)
		self.currentFrequency._cached = None
		if self.RXtuningMode._cached_value is not None:
			if self.RXtuningMode != tuningMode(split[0]):
				self.split._cached = True
		if self.mainTransmitting:
			self.tuningMode._cached = tuningMode(split[0])
		self.TXtuningMode._cached = tuningMode(split[0])

	def _update_GT(self, args):
		if args == '   ':
			self.AGCconstant._cached = None
		else:
			split = parse('3d', args)
			self.AGCconstant._cached = split[0]

	def _update_ID(self, args):
		self.ID._cached = parse('3d', args)[0]

	def _update_IF(self, args):
		# TODO: Synchronize these with the single-value options
		# NOTE: Combined P6 and P7 since they're effectively one number on the TS-2000
		#'00003810000' '    ' ' 00000' '0' '0' '101' '0' '1' '0' '0' '0' '0' '08' '0'
		#'00003810000' '    ' ' 00000' '0' '0' '101' '0' '1' '0' '0' '0' '0' '08' '0'
		#     3810000,     0,       1,  0,  1,    0,  1,  0,  0,  0,  0,  0,   8,  0
		split = parse('11d4d6d1d1d3d1d1d1d1d1d1d2d1d', args)
		self.currentFrequency._cached = split[0]
		self.frequencyStep._cached = split[1]
		self.RIT_XITfrequency._cached = split[2]
		self.RIT._cached = bool(split[3])
		self.XIT._cached = bool(split[4])
		self.channelBank._cached = split[5]
		self.currentReceiverTransmitting._cached = bool(split[6])
		self._update_MD(str(split[7]))
		self.tuningMode._cached = tuningMode(split[8])
		self.scanMode._cached = scanMode(split[9])
		# TODO: Split is undocumented and full-duplex may be here?
		self.splitMode._cached = bool(split[10])
		# TODO: TONE/CTCSS/DCS squished together here in split[11]
		# TODO: Tone frequency
		self.shiftStatus._cached = offset(split[13])
		# Fun hack... in CALL mode, MC300 is updated via IF...
		# We handle this special case by asserting that if we get IF
		# when in MC300, the MC has been updated
		if self.memoryChannel._cached == 300:
			self.memories[300]._cached_value = None
			self.memoryChannel._cached_value = None
			self.memoryChannel._cached = 300
			ret += ('memoryChannel',)

	def _update_IS(self, args):
		split = parse('5d', args)
		self.IFshift._cached = split[0]

	def _update_KS(self, args):
		split = parse('3d', args)
		self.keyerSpeed._cached = split[0]

	def _update_KY(self, args):
		split = parse('1d', args)
		self.keyerBufferFull._cached = bool(split[0])

	def _update_LK(self, args):
		split = parse('1d1d', args)
		self.rigLock._cached = rigLock(self[0])
		if split[0] == 0:
			self.frequencyLock._cached = False
			self.allLock._cached = False
		elif split[0] == 1:
			self.frequencyLock._cached = True
			self.allLock._cached = False
		elif split[1] == 2:
			self.frequencyLock._cached = True
			self.allLock._cached = True
		self.rc2000Lock._cached = bool(split[1])

	def _update_LM(self, args):
		# TODO: Maybe false for 0 and be an int?
		split = parse('1d', args)
		self.recordingChannel._cached = recordingChannel(split[0])

	def _update_LT(self, args):
		split = parse('1d', args)
		self.autoLockTuning._cached = bool(split[0])

	def _update_MC(self, args):
		split = parse('3d', args)
		# Any time we get an MC300; it means we entered CALL mode
		# The calling frequency *may* be different than last time!
		if split[0] == 300:
			self.memories[300]._cached_value = None
		self.memoryChannel._cached = split[0]

	def _update_MD(self, args):
		split = parse('1d', args)
		self.mode._cached = mode(split[0])
		if not self.mode._cached in (mode.CW, mode.CW_REVERSED,):
			self.CWautoTune._cached = None
		else:
			self.CWautoTune._cached = False

	def _update_MF(self, args):
		split = parse('1d', args)
		if split[0] == 0:
			self.menuAB._cached = 'A'
		elif split[0] == 1:
			self.menuAB._cached = 'B'

	def _update_MG(self, args):
		split = parse('3d', args)
		self.microphoneGain._cached = split[0]

	def _update_ML(self, args):
		split = parse('3d', args)
		self.monitorLevel._cached = split[0]

	def _update_MO(self, args):
		split = parse('1d', args)
		self.skyCommandMonitor._cached = bool(split[0])

	# TODO: We actually need to merge these because the TX and RX memory is completely different
	def _update_MR(self, args):
		split = parse('1d3d11d1d1d1d2d2d3d1d1d9d2d1d0l', args)
		newVal = {
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
			newVal['TX'] = bool(split[0])
		else:
			newVal['Start'] = not bool(split[0])
		self.memories[split[1]]._cached = newVal

	def _update_MU(self, args):
		self.memoryGroups._cached = bitarray.util.base2ba(2, args)

	def _update_NB(self, args):
		split = parse('1d', args)
		self.noiseBlanker._cached = bool(split[0])

	def _update_NL(self, args):
		split = parse('3d', args)
		self.noiseBlankerLevel._cached = split[0]

	def _update_NR(self, args):
		split = parse('1d', args)
		self.noiseReduction._cached = noiseReduction(split[0])
		if split[0] == 0:
			self.noiseReduction1._cached = False
			self.noiseReduction2._cached = False
		elif split[0] == 1:
			self.noiseReduction1._cached = True
			self.noiseReduction2._cached = False
		else:
			self.noiseReduction1._cached = False
			self.noiseReduction2._cached = True

	def _update_NT(self, args):
		split = parse('1d', args)
		self.autoNotch._cached = bool(split[0])

	def _update_OF(self, args):
		split = parse('9d', args)
		self.offsetFrequency._cached = split[0]

	def _update_OS(self, args):
		split = parse('1d', args)
		self.offsetType._cached = offset(split[0])

	def _update_PA(self, args):
		split = parse('1d1d', args)
		self.mainPreAmp._cached = bool(split[0])
		self.subPreAmp._cached = bool(split[1])

	def _update_PB(self, args):
		split = parse('1d', args)
		self.playbackChannel._cached = recordingChannel(split[0])

	def _update_PC(self, args):
		split = parse('3d', args)
		self.outputPower._cached = split[0]

	def _update_PK(self, args):
		split = parse('11d12l20l5l', args)
		spot = {
			frequency: split[0],
			callsign: split[1],
			comments: split[2],
			time: split[3]
		}
		self.lastSpot.value = spot

	def _update_PL(self, args):
		split = parse('3d3d', args)
		self.speechProcessorInputLevel._cached = split[0]
		self.speechProcessorOutputLevel._cached = split[1]

	def _update_PM(self, args):
		split = parse('1d', args)
		# TODO: Should this be False when it's off?
		self.programmableMemoryChannel._cached = split[0]

	def _update_PR(self, args):
		split = parse('1d', args)
		self.speechProcessor._cached = bool(split[0])

	def _update_PS(self, args):
		split = parse('1d', args)
		self.powerOn._cached = bool(split[0])
		if split[0]:
			self._write(self.autoInformation._set_format.format(2))
			self._write(self.controlMain._query_command)
			self._write(self.RXtuningMode._query_command)     # used for split
			self._write(self.TXtuningMode._query_command)     # used for split
			self._write(self.TXmain._query_command)
			self._write(self.currentReceiverTransmitting._query_command)

	def _update_QC(self, args):
		split = parse('3d', args)
		self.DCScode._cached = DCScode(split[0])

	def _update_QR(self, args):
		split = parse('1d1d', args)
		self.quickMemory._cached = bool(split[0])
		self.quickMemoryChannel._cached = split[1]

	def _update_RA(self, args):
		split = parse('2d', args)
		self.attenuator._cached = bool(split[0])

	# NOTE: Updates the same value as RU
	def _update_RD(self, args):
		split = parse('1d', args)
		self.scanSpeed._cached = split[0]

	def _update_RG(self, args):
		split = parse('3d', args)
		self.RFgain._cached = split[0]

	def _update_RL(self, args):
		split = parse('2d', args)
		self.noiseReductionLevel._cached = split[0]

	def _update_RM(self, args):
		split = parse('1d4d', args)
		self.meterType._cached = meter(split[0])
		self.meterValue._cached = split[1]
		self.SWRmeter._cached = split[1] if split[0] == 1 else 0
		self.compressionMeter._cached = split[1] if split[0] == 2 else 0
		self.ALCmeter._cached = split[1] if split[0] == 3 else 0

	# Note: Can only set RM2 when COMP is on

	def _update_RT(self, args):
		split = parse('1d', args)
		self.RIT._cached = bool(split[0])

	# NOTE: Updates the same value as RD
	def _update_RU(self, args):
		split = parse('1d', args)
		self.scanSpeed._cached = split[0]

	def _update_RX(self, args):
		split = parse('1d', args)
		if split[0] == 0:
			self.mainTransmitting._cached = False
		if split[0] == 1:
			self.subTransmitting._cached = False

	def _update_SA(self, args):
		split = parse('1d1d1d1d1d1d1d8l', args)
		self.satelliteMode._cached = bool(split[0])
		self.satelliteMemoryChannel._cached = split[1]
		self.satelliteMainUpSubDown._cached = not bool(split[2])
		self.satelliteControlMain._cached = not bool(split[3])
		self.satelliteTrace._cached = bool(split[4])
		self.satelliteTraceReverse._cached = bool(split[5])
		self.satelliteMultiKnobVFO._cached = not bool(split[6])
		self.satelliteChannelName._cached = split[7]

	def _update_SB(self, args):
		split = parse('1d', args)
		self.subReceiver._cached = bool(split[0])

	def _update_SC(self, args):
		split = parse('1d', args)
		self.scanMode._cached = scanMode(split[0])

	def _update_SD(self, args):
		split = parse('4d', args)
		self.cwBreakInTimeDelay._cached = split[0]

	def _update_SH(self, args):
		split = parse('2d', args)
		self.voiceLowPassCutoff._cached = split[0]

	def _update_SL(self, args):
		split = parse('2d', args)
		self.voiceHighPassCutoff._cached = split[0]

	def _update_SM(self, args):
		split = parse('1d4d', args)
		# TODO: Figure out what 2 and 3 actually are...
		if split[0] == 0:
			self.mainSMeter._cached = split[1]
		if split[0] == 1:
			self.subSMeter._cached = split[1]
		if split[0] == 2:
			print('Got SM2!', file=sys.stderr)
			self.mainSMeterLevel._cached = split[1]
		if split[0] == 3:
			print('Got SM3!', file=sys.stderr)
			self.subSMeterLevel._cached = split[1]

	def _update_SQ(self, args):
		split = parse('1d3d', args)
		if split[0] == 0:
			self.mainSquelch._cached = split[1]
		elif split[0] == 1:
			self.subSquelch._cached = split[1]

	def _update_ST(self, args):
		split = parse('2d', args)
		self.multiChFrequencySteps._cached = split[0]

	def _update_TC(self, args):
		split = parse('1d1d', args)
		self.PCcontrolCommandMode._cached = bool(split[1])

	def _update_TI(self, args):
		split = parse('1d1d1d', args)
		self.tnc96kLED._cached = bool(split[0])
		self.tncSTALED._cached = bool(split[1])
		self.tncCONLED._cached = bool(split[2])

	def _update_TN(self, args):
		split = parse('2d', args)
		# TODO: Smart mapping thing?
		self.subToneFrequency._cached = CTCSStone(split[0])

	def _update_TO(self, args):
		split = parse('1d', args)
		self.toneFunction._cached = bool(split[0])

	def _update_TX(self, args):
		split = parse('1d', args)
		self.currentFrequency._cached = None
		if split[0] == 0:
			self.mainTransmitting._cached = True
		if split[0] == 1:
			self.subTransmitting._cached = True

	def _update_TY(self, args):
		split = parse('3d', args)
		self.firmwareType._cached = firmwareType(split[0])

	def _update_UL(self, args):
		split = parse('1d', args)
		if split[0] == 1:
			raise Exception('PLL Unlocked!')
		self.PLLunlock._cached = bool(split[0])

	def _update_VD(self, args):
		split = parse('4d', args)
		self.VOXdelayTime._cached = split[0]

	def _update_VG(self, args):
		split = parse('3d', args)
		self.VOXgain._cached = split[0]

	def _update_VX(self, args):
		split = parse('1d', args)
		self.VOX._cached = bool(split[0])

	def _update_XT(self, args):
		split = parse('1d', args)
		self.XIT._cached = bool(split[0])

	def _update_Error(self, args):
		self.error_count += 1
		if self.error_count < 10:
			self._write(self.last_command)
		else:
			raise Exception('Error count exceeded')

	def _update_ComError(self, args):
		self.error_count += 1
		if self.error_count < 10:
			self._write(self.last_command)
		else:
			raise Exception('Error count exceeded')

	def _update_IncompleteError(self, args):
		self.error_count += 1
		if self.error_count < 10:
			self._write(self.last_command)
		else:
			raise Exception('Error count exceeded')

