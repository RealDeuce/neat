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
		self._set_format = kwargs.get('set_format')
		self._set_method = kwargs.get('set_method')
		if self._set_format is not None and self._set_method is not None:
			raise Exception('Only one of set_method or set_format may be specified')
		self._validity_check = kwargs.get('validity_check')
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
		if self._validity_check is not None and not self._validity_check():
			self.cached = None
			return None
		if self._cached is None:
			if self._query_method is not None:
				self._query_method()
			elif self._query_command is not None:
				self._rig._query(self)
			else:
				raise Exception('Attempt to set value without a setter')
		return self._cached

	@value.setter
	def value(self, value):
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
		self._write('MU{:01d}{:01d}{:01d}{:01d}{:01d}{:01d}{:01d}{:01d}{:01d}{:01d}'.format(value[0], value[1], value[2], value[3], value[4], value[5], value[6], value[7], value[8], value[9]))

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

	def _voiceCutoffValid(self):
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
		self.command[b'CN'] = {'update': self.__update_CN}
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
		# TODO: OI appears to be IF for the non-active receiver... not sure if that's PTT or CTRL
		self.command[b'PA'] = {'update': self.__update_PA}
		self.command[b'PB'] = {'update': self.__update_PB}
		self.command[b'PC'] = {'update': self.__update_PC}
		self.command[b'PK'] = {'update': self.__update_PK}
		self.command[b'PL'] = {'update': self.__update_PL}
		self.command[b'PM'] = {'update': self.__update_PM}
		self.command[b'PR'] = {'update': self.__update_PR}
		self.command[b'PS'] = {'update': self.__update_PS}
		self.command[b'QC'] = {'update': self.__update_QC}
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
		self.command[b'ST'] = {'update': self.__update_ST}
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
		self.antennaConnector =             StateValue(self, query_command = 'AN',  set_format = 'AN{:01d}')
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
		self.CWautoTune =                   StateValue(self, query_command = 'CA',  set_format = 'CA{:01d}')
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
		self.vfoAFrequency =                StateValue(self, query_command = 'FA',  set_format = 'FA{:011d}')
		self.vfoBFrequency =                StateValue(self, query_command = 'FB',  set_format = 'FB{:011d}')
		self.subReceiverFrequency =         StateValue(self, query_command = 'FC',  set_format = 'FC{:011d}')
		self.filterDisplayPattern =         StateValue(self, query_command = 'FD')
		self.RXtuningMode =                 StateValue(self, query_command = 'FR',  set_format = 'FR{:01d}')
		self.fineTuning =                   StateValue(self, query_command = 'FS',  set_format = 'FS{:01d}')
		self.TXtuningMode =                 StateValue(self, query_command = 'FT',  set_format = 'FT{:01d}')
		self.filterWidth =                  StateValue(self, query_command = 'FW',  set_format = 'FW{:04d}')
		self.AGCconstant =                  StateValue(self, query_command = 'GT',  set_format = 'GT{:03d}')
		self.ID =                           StateValue(self, query_command = 'ID')
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
		self.memoryGroups =                 StateValue(self, query_command = 'MU',  set_method = self._set_memoryGroups)
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
		self.speechProcessorInputLevel =    StateValue(self, query_command = 'PL',  set_method = self._set_speechProcessorInputLevel)
		self.speechProcessorOutputLevel =   StateValue(self, query_command = 'PL',  set_method = self._set_speechProcessorOutputLevel)
		self.programmableMemoryChannel =    StateValue(self, query_command = 'PM',  set_format = 'PM{:01d}')
		self.speechProcessor =              StateValue(self, query_command = 'PR',  set_format = 'PR{:01d}')
		self.powerOn =                      StateValue(self, query_command = 'PS',  set_format = 'PS{:01d}')
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
		self.meterType =                    StateValue(self, query_command = 'RM',  set_format = 'RM{:01d}')
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

		# Initialization
		self.autoInformation.value = 2

	def __init__(self, port = "/dev/ttyU0", speed = 4800, stopbits = 2):
		self.init_done = False
		self.__terminate = False
		self.serial = serial.Serial(port = port, baudrate = speed, stopbits = stopbits, rtscts = True, timeout = 0.1, inter_byte_timeout = 0.5)
		self.error_count = 0
		# We assume all rigs support the ID command (for no apparent reason)
		self.ID = StateValue(self, query_command = 'ID')
		self.command = dict()
		self.command[b'ID'] = {'update': self.__update_ID}
		self.readThread = threading.Thread(target = self.__readThread, name = "Read Thread")
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
		self.__write(b'AI0;')
		self.__terminate = True
		self.readThread.join()

	def terminate(self):
		self.__write(b'AI0;')
		self.__terminate = True
		self.readThread.join()

	def _query(self, state):
		self.error_count = 0
		ev = threading.Event()
		cb = lambda x: ev.set()
		state._add_wait_callback(cb)
		self._write(state._query_command)
		ev.wait()
		state._remove_wait_callback(cb)

	def _write(self, cmd):
		self.last_command = bytes(cmd + ';', 'ascii')
		print("Writing: "+str(self.last_command))
		self.serial.write(self.last_command)

	def __write(self, barr):
		self.last_command = barr
		print("Writing: '"+str(barr)+"'")
		self.serial.write(barr)

	def __read(self):
		ret = b'';
		while not self.__terminate:
			ret += self.serial.read_until(b';')
			if ret[-1:] == b';':
				print("Read: '"+str(ret)+"'")
				return ret

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
							self.command[cmd]['update'](args)
					else:
						if self.init_done:
							print('Unhandled command "%s" (args: "%s")' % (cmd, args), file=sys.stderr)
				else:
					print('Bad command line: "'+str(cmdline)+'"', file=sys.stderr)

	'''
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
	'''

	def __updated(self, name, value):
		getattr(self, name)._cached = value
		return ()

	def __update_AC(self, args):
		split = parse('1d1d1d', args)
		ret = ()
		self.tuner._cached = bool(split[0]) or bool(split[1])
		ret += self.__updated('tuner', (bool(split[0]) or bool(split[1])))
		ret += self.__updated('tunerRX', bool(split[0]))
		ret += self.__updated('tunerTX', bool(split[1]))
		ret += self.__updated('tunerState', tunerState(split[2]))
		return ret

	def __update_AG(self, args):
		split = parse('1d3d', args)
		ret = ()
		if split[0] == 0:
			ret += self.__updated('mainAFgain', split[1]);
		else:
			ret += self.__updated('subAFgain', split[1])
		return ret

	def __update_AI(self, args):
		split = parse('1d', args)
		return self.__updated('autoInformation', AI(split[0]))

	def __update_AL(self, args):
		split = parse('3d', args)
		return self.__updated('autoNotchLevel', split[0])

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

	def __update_BP(self, args):
		split = parse('3d', args)
		return self.__updated('manualBeatCancellerFrequency', split[0])

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

	def __update_CN(self, args):
		split = parse('2d', args)
		return self.__updated('CTCSStone', CTCSStone(split[0]))

	def __update_CT(self, args):
		split = parse('1d', args)
		return self.__updated('CTCSS', bool(split[0]))

	def __update_DC(self, args):
		split = parse('1d1d', args)
		ret = ()
		ret += self.__updated('TXmain', not bool(split[0]))
		ret += self.__updated('controlMain', not bool(split[1]))
		return ret;

	def __update_DQ(self, args):
		split = parse('1d', args)
		return self.__updated('DCS', bool(split[0]))

	def __update_EX(self, args):
		split = parse('3d2d1d1d0l', args)
		ret = ()
		if split[0] == 27:
			ret += self.__updated('tunerOnInRX', bool(int(split[4])))
		else:
			print('Unhandled EX menu {:03d}'.format(split[0]), file=sys.stderr)
		return ret

	def __update_FA(self, args):
		split = parse('11d', args)
		return self.__updated('vfoAFrequency', split[0])

	def __update_FB(self, args):
		split = parse('11d', args)
		return self.__updated('vfoBFrequency', split[0])

	def __update_FC(self, args):
		split = parse('11d', args)
		return self.__updated('subReceiverFrequency', split[0])

	def __update_FD(self, args):
		split = parse('8x', args)
		return self.__updated('filterDisplayPattern', bitarray.util.int2ba(split[0], 32))

	def __update_FW(self, args):
		split = parse('4d', args)
		return self.__updated('filterWidth', split[0])

	def __update_FR(self, args):
		split = parse('1d', args)
		return self.__updated('RXtuningMode', tuningMode(split[0]))

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
		if self.memoryChannel._cached == 300:
			self.memories[300]._cached_value = None
			self.memoryChannel._cached_value = None
			self.memoryChannel._cached = 300
			ret += ('memoryChannel',)
		return ret;

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
		ret += self.__updated('rigLock', rigLock(self[0]))
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
		# TODO: Maybe false for 0 and be an int?
		split = parse('1d', args)
		return self.__updated('recordingChannel', recordingChannel(split[0]))

	def __update_LT(self, args):
		split = parse('1d', args)
		return self.__updated('autoLockTuning', bool(split[0]))

	def __update_MC(self, args):
		split = parse('3d', args)
		# Any time we get an MC300; it means we entered CALL mode
		# The calling frequency *may* be different than last time!
		if split[0] == 300:
			self.memories[300]._cached_value = None
		return self.__updated('memoryChannel', split[0])

	def __update_MD(self, args):
		split = parse('1d', args)
		return self.__updated('mode', mode(split[0]))

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

	# TODO: We actually need to merge these because the TX and RX memory is completely different
	def __update_MR(self, args):
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
		return ('Memory{:03d}'.format(split[1]),)

	def __update_MU(self, args):
		return self.__updated('memoryGroups', bitarray.bitarray(args))

	def __update_NB(self, args):
		split = parse('1d', args)
		return self.__updated('noiseBlanker', bool(split[0]))

	def __update_NL(self, args):
		split = parse('3d', args)
		return self.__updated('noiseBlankerLevel', split[0])

	def __update_NR(self, args):
		split = parse('1d', args)
		ret = ()
		ret += self.__updated('noiseReduction', noiseReduction(split[0]))
		if split[0] == 0:
			ret += self.__updated('noiseReduction1', False)
			ret += self.__updated('noiseReduction2', False)
		elif split[0] == 1:
			ret += self.__updated('noiseReduction1', True)
			ret += self.__updated('noiseReduction2', False)
		else:
			ret += self.__updated('noiseReduction1', False)
			ret += self.__updated('noiseReduction2', True)
		return ret

	def __update_NT(self, args):
		split = parse('1d', args)
		return self.__updated('autoNotch', bool(split[0]))

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

	def __update_PB(self, args):
		split = parse('1d', args)
		return self.__updated('playbackChannel', recordingChannel(split[0]))

	def __update_PC(self, args):
		split = parse('3d', args)
		return self.__updated('outputPower', split[0])

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
		# TODO: Should this be False when it's off?
		return self.__updated('programmableMemoryChannel', split[0])

	def __update_PR(self, args):
		split = parse('1d', args)
		return self.__updated('speechProcessor', bool(split[0]))

	def __update_PS(self, args):
		split = parse('1d', args)
		return self.__updated('powerOn', bool(split[0]))

	def __update_QC(self, args):
		split = parse('3d', args)
		return self.__updated('DCScode', DCScode(split[0]))

	def __update_QR(self, args):
		split = parse('1d1d', args)
		ret = ()
		ret += self.__updated('quickMemory', bool(split[0]))
		ret += self.__updated('quickMemoryChannel', split[1])
		return ret

	def __update_RA(self, args):
		split = parse('2d', args)
		return self.__updated('attenuator', bool(split[0]))

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

	def __update_SL(self, args):
		split = parse('2d', args)
		return self.__updated('voiceHighPassCutoff', split[0])

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

	def __update_ST(self, args):
		split = parse('2d', args)
		return self.__updated('multiChFrequencySteps', split[0])

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
		return self.__updated('subToneFrequency', CTCSStone(split[0]))

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

