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

"""
All Kenwood HF radios that support computer interfacing via a serial
port seem to implement some form of this protocol.

This is originally written for a TS-2000, so the best method names will
reflect that.  If a particular model implements a command differently,
it will get a suboptimal name.
"""

from enum import IntEnum
from rig import Rig, StateValue
from bitarray.util import int2ba, base2ba
from copy import deepcopy
from re import match
from sys import stderr
from threading import Lock, Event, Thread
from queue import Queue
from rig.kenwood_hf.serial import KenwoodHFProtocol

'''
A basic overview of the concepts behind this

The kenwood.py module is an asynchronous rig control library, and it
maintains a cache of what it believes is the current state of the rig.
That state is populated when the Kenwood class is created, then
maintained via the Auto Information send by the rig in AI2 mode.

The Kenwood object contains a number of state properties, each one of
which can be read or set through the standard interface.  When one is
set the command to take that action is sent to the rig.  The state will
not be updated until the rig replies with the updated state message
which may be delayed, may actually be lost, and state changes may occur
in a different order than they were requested.  The front-end is
expected to deal with this.

Each state property can also have callbacks installed which are called
when the value of the state property changes.  This is how the front-end
is expected to know when a change takes place, rather than assuming it
took place as soon as the property was written.  Callbacks are called
from a different thread and should not query properties from that thread.
TODO: Fix this with a queue, it's not that hard and you're lazy.
If a callback is given a None value as the new value, that may just mean
that a state change invalidated the cached value and a new read of the
property will retreive it.  If reading the property returns None, that
indicates the property can not be obtained from the rig in the current
state, and is not applicable.

This allows the front-end to be more responsive, at the expense of a
consistent, known rig state.

There are a number of frequencies available:
mainRXsetFrequency    - "The" frequency of the main receiver.  This is what
                        the dial is set to, and does not include RIT if
                        enabled.
mainRXfrequency       - The frequency that is currently being received if
                        the rig is not transmitting, this DOES include RIT
mainTXsetFrequency    - "The" transmit frequency - either the same as
                        mainRXsetFrequency if not operating split, or the
                        set frequency of the "other VFO".  When operating
                        in FM mode, this also doesn't include the offset
mainTXoffsetFrequency - The mainRXsetFrequency with offset applied if
                        applicable.  Does not include XIT.
mainTXfrequency       - The frequency that will actually be transmitted on
                        takes into account XIT and offset
VFOAsetFrequency      - The "set" frequency for VFOA
VFOBsetFrequency      - The "set" frequency for VFOB
subSetFrequency       - The "set" frequency for the sub-receiver
                        This is always the RX frequency for the sub-recevier
                        as it doesn't support RIT
subTXoffsetFrequency  - This is the frequency the sub-receiver will transmit
                        on.  This takes into account offset
mainFrequency         - Equal to either mainRXfrequency or mainTXfrequency
                        depending on if the radio is transmitting or not.
subFrequency          - Equal to either subSetFrequency or
                        subTXoffsetFrequency depending on if the radio
                        is transmitting or not.
currentTXfrequency    - Set to either mainTXfrequency or subTXoffsetFrequency
currentRXfrequency    - Set to either mainRXfrequency or subSetFrequency
                        based on the current *TX* receiver

"Tuning Mode" is what I call the VFO selection type thing... there's a
few of these too:
mainRXtuningMode
mainTXtuningMode
subTuningMode

And the mode (ie: CW, USB, etc...)
mainRXmode
mainTXmode
subMode
currentRXmode
currentTXmode

The current* ones are intended to be generic across all backends, and
should be enough for things like loggers and wsjt-x that just want to
get or set the basic parameters and don't care how that happens.  If
you're hacking up a backend for that, just implementing the current*
stuff should get it functional.

currentTXfrequency    - Set to either mainTXfrequency or subTXoffsetFrequency
currentRXfrequency    - Set to either mainRXfrequency or subSetFrequency
                        based on the current *TX* receiver
currentRXtuningMode
currentTXtuningMode
currentRXmode
currentTXmode

'''

class tunerState(IntEnum):
	STOPPED = 0
	ACTIVE = 1
	FAILED = 2

class AI(IntEnum):
	OFF = 0
	OLD = 1
	EXTENDED = 2
	BOTH = 3

class BeatCanceller(IntEnum):
	OFF = 0
	AUTO = 1
	MANUAL = 2

class tuningMode(IntEnum):
	VFOA = 0
	VFOB = 1
	MEMORY = 2
	CALL = 3

class scanMode(IntEnum):
	OFF = 0
	ON = 1
	MHZ_SCAN = 2
	VISUAL_SCAN = 3
	TONE_SCAN = 4
	CTCSS_SCAN = 5
	DCS_SCAN = 6

class offset(IntEnum):
	NONE = 0
	POSITIVE = 1
	NEGATIVE = 2
	# -7.6MHz for 430 or -6MHz for 1.2GHz
	EURO_SPLIT = 3

class meter(IntEnum):
	UNSELECTED = 0
	SWR = 1
	COMPRESSION = 2
	ALC = 3

class firmwareType(IntEnum):
	OVERSEAS = 0
	JAP100W = 1
	JAP20W = 2

class toneType(IntEnum):
	OFF = 0
	TONE = 1
	CTCSS = 2
	DCS = 3

class CTCSStone(IntEnum):
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

class rigLock(IntEnum):
	OFF = 0
	F_LOCK = 1
	A_LOCK = 2

class recordingChannel(IntEnum):
	OFF = 0
	CH1 = 1
	CH2 = 2
	CH3 = 3

class noiseReduction(IntEnum):
	OFF = 0
	NR1 = 1
	NR2 = 2

class DCScode(IntEnum):
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

class KenwoodStateValue(StateValue):
	def __init__(self, rig, **kwargs):
		super().__init__(rig, **kwargs)
		self._depends_on = kwargs.get('depends_on')
		self._echoed = kwargs.get('echoed')
		self._query_command = kwargs.get('query_command')
		self._query_method = kwargs.get('query_method')
		self._range_check = kwargs.get('range_check')
		self._set_format = kwargs.get('set_format')
		self._set_method = kwargs.get('set_method')
		self._validity_check = kwargs.get('validity_check')
		self._works_powered_off = kwargs.get('works_powered_off')
		if self._depends_on is None:
			self._depends_on = ()
		if self._set_format is not None and self._set_method is not None:
			raise Exception('Only one of set_method or set_format may be specified')
		if  self._query_command is not None and self._query_method is not None:
			raise Exception('Only one of query_command or query_method may be specified')

	def _query_string(self):
		if not self._valid(True):
			self._cached = None
			return ''
		if self._query_method is not None:
			return self._query_method()
		elif self._query_command is not None:
			return self._query_command
		raise Exception('Attempt to query value "'+self.name+'" without a query command or method', file=stderr)

	def _do_range_check(self, value):
		if not self._valid(False):
			return False
		if self._range_check is not None:
			return self._range_check(value)
		return True

	def _set_string(self, value):
		if not self._do_range_check(value):
			return ''
		if value is None:
			raise Exception('Setting new value of None!')
		if self._set_format is not None:
			return self._set_format.format(value)
		elif self._set_method is not None:
			return self._set_method(value)
		print('Attempt to set value "'+self._name+'" without a set command or method', file=stderr)

	def _valid(self, can_query):
		for d in self._depends_on:
			if isinstance(d, StateValue):
				if StateValue._cached is None:
					if (not can_query) or (getattr(self._rig, 'value') == None):
						self._cached_value = None
						return
			else:
				if self._rig._state[d]._cached is None:
					if (not can_query) or (getattr(self._rig, d) == None):
						self._cached_value = None
						return
		if not self._works_powered_off:
			if not self._rig.powerOn:
				return False
		if self._validity_check is not None:
			if not self._validity_check():
				self._cached = None
				return False
		return True

	@property
	def value(self):
		if not self._valid(True):
			self._cached_value = None
			return None
		if self._cached is None and not self._rig._killing_cache:
			self._rig._query(self)
		# We just deepcopy it as an easy hack
		return deepcopy(self._cached)

	@value.setter
	def value(self, value):
		if isinstance(value, StateValue):
			raise Exception('Forgot to add ._cached!')
		if self._read_only:
			raise Exception('Attempt to set read-only property '+self.name+'!')
		self._rig._set(self, value)

class KenwoodNagleStateValue(KenwoodStateValue):
	def __init__(self, rig, **kwargs):
		super().__init__(rig, **kwargs)
		self._pending = None
		self._queued = None
		self.lock = Lock()

	@property
	def value(self):
		return super().value

	@value.setter
	def value(self, value):
		if isinstance(value, StateValue):
			raise Exception('Forgot to add ._cached!')
		if self._read_only:
			raise Exception('Attempt to set read-only property '+self.name+'!')
		self.lock.acquire()
		if self._pending is not None:
			self._pending['value'] = value
			self.lock.release()
			return
		if self._queued is not None:
			self._queued['value'] = value
			self.lock.release()
			return
		self._queued = {
			'msgType': 'set',
			'stateValue': self,
			'value': value,
		}
		self._serial.writeQueue.put(self._queued)
		self.lock.release()

	def set_string(self, value):
		self.lock.acquire()
		self._pending = self._queued
		self._queued = None
		if not self.range_check(value):
			self._pending = None
			self.lock.release()
			return None
		self.lock.release()
		if self._set_format is not None:
			return self._set_format.format(value)
		elif self._set_method is not None:
			return self._set_method(value)
		print('Attempt to set value "'+self.name+'" without a set command or method', file=stderr)

class KenwoodListStateValue(KenwoodStateValue):
	def __init__(self, rig, length, **kwargs):
		super().__init__(rig, **kwargs)
		self._queued = None
		self.length = length
		self.children = [None] * self.length
		self.lock = Lock()
		self.add_set_callback(self._update_children)

	def _update_children(self, value):
		for i in range(self.length):
			self.children[i]._cached = value[i]

	@property
	def value(self):
		return super().value

	@value.setter
	def value(self, value):
		if isinstance(value, StateValue):
			raise Exception('Forgot to add ._cached!')
		if self._read_only:
			raise Exception('Attempt to set read-only property '+self.name+'!')
		if self.length != len(value):
			raise Exception('Incorrect length for '+self.name+', got '+str(len(value))+', expected '+str(self.length))
		self.lock.acquire()
		if self._queued is not None:
			# Merge values... anything that's not None in
			# the new value should be copied into the old one
			for v in range(len(value)):
				if value[v] is not None:
					self._queued['value'][v] = value[v]
			self.lock.release()
			return
		self._queued = {
			'msgType': 'set',
			'stateValue': self,
			'value': value,
		}
		self._serial.writeQueue.put(self._queued)
		self.lock.release()

	def set_string(self, value):
		self.lock.acquire()
		self._queued = None
		if not self.range_check(value):
			self.lock.release()
			return None
		self.lock.release()
		if self._set_format is not None:
			for i in range(self.length):
				if value[i] is None and self._cached is not None:
					value[i] = self._cached[i]
			return self._set_format.format(value)
		elif self._set_method is not None:
			return self._set_method(value)
		print('Attempt to set value "'+self.name+'" without a set command or method', file=stderr)

class KenwoodSingleStateValue(KenwoodStateValue):
	def __init__(self, parent, offset, **kwargs):
		super().__init__(**kwargs)
		self._depends_on = self._depends_on + (self,)
		self._parent = parent
		self._offset = offset
		self._parent.children[self._offset] = self

	@property
	def value(self):
		return super().value[self._offset]

	@value.setter
	def value(self, value):
		if isinstance(value, StateValue):
			raise Exception('Forgot to add ._cached!')
		if self._read_only:
			raise Exception('Attempt to set read-only property '+self.name+'!')
		newval = [None] * self.parent.length
		newval[self._offset] = value
		self._parent.value = newval

class MemoryArray:
	def __init__(self, rig, **kwargs):
		self.memories = [None] * 301
		self._rig = rig
		for i in range(len(self.memories)):
			self.memories[i] = KenwoodStateValue(rig, query_command = 'MR0{:03d};MR1{:03d}'.format(i, i))
			self.name = 'Memory' + str(i+1)

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

class KenwoodHF(Rig):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self._terminate = False
		self._killing_cache = False
		self._error_count = 0
		self._last_hack = 0
		# TODO: The error handling repeats whatever the last command was, not the failing command
		#       Short of only having one outstanding command at a time though, I'm not sure what
		#       we can actually do about that.
		self._last_command = None
		self._last_power_state = None
		self._fill_cache_state = {}
		self._serial = KenwoodHFProtocol(**kwargs)
		# All supported rigs must support the ID command
		self._state = {
			'ID': KenwoodStateValue(self, name = 'ID', query_command = 'ID', works_powered_off = True),
		}
		self._state['ID'].name = 'ID'
		self._command = {
			b'ID': self._update_ID,
			b'?': self._update_Error,
			b'E': self._update_ComError,
			b'O': self._update_IncompleteError,
		}
		self._aliveWait = Event()
		self._readThread = Thread(target = self._readThread, name = "Read Thread")
		self._readThread.start()
		self._aliveWait.wait()
		self._aliveWait = None

		resp = None
		while resp is None:
			resp = self.ID
		initFunction = '_init_' + str(resp)
		if callable(getattr(self, initFunction, None)):
			getattr(self, initFunction, None)()
		else:
			raise Exception("Unsupported rig (%d)!" % (resp))
		self._init_done = True
		self._sync_lock = Lock()

	def __getattr__(self, name):
		if name in self._state:
			return self._state[name].value
		return super().__getattr__(name)

	def __setattr__(self, name, value):
		if name[:1] != '_':
			if name in self._state:
				self._state[name].value = value
		super().__setattr__(name ,value)

	def __del__(self):
		self.terminate()

	# Init methods for specific rig IDs go here
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
			# AC set fails when not in HF
			# AC set fails when control is sub
			# Not available for sub receiver
			'tuner_list': KenwoodListStateValue(self,
				echoed = True,
				query_command = 'AC',
				set_format = 'AC{:1d}{:1d}{:1d}',
				length = 3
			),
			'main_af_gain': KenwoodStateValue(self,
				echoed = False,
				query_command = 'AG0',
				set_format = 'AG0{:03d}'
			),
			'sub_af_gain': KenwoodStateValue(self,
				echoed = False,
				query_command = 'AG1',
				set_format = 'AG1{:03d}'
			),
			'auto_information': KenwoodStateValue(self,
				echoed = True,
				query_command = 'AI',
				set_format = 'AI{:01d}'
			),
			'auto_notch_level': KenwoodStateValue(self,
				echoed = False,
				query_command = 'AL',
				set_format = 'AL{:03d}'
			),
			'auto_mode': KenwoodStateValue(self,
				echoed = True,
				query_command = 'AM',
				set_format = 'AM{:01d}'
			),
			'antenna_connector': KenwoodStateValue(self,
				echoed = True,
				query_command = 'AN',
				set_format = 'AN{:01d}',
				range_check = self._antennaRangeCheck
			),
			'antenna1': KenwoodStateValue(self,
				echoed = True,
				query_command = 'AN',
				set_method = self._setAntenna1,
				validity_check = self._antenna1Valid,
				depends_on=('mainFrequency',)
			),
			'antenna2': KenwoodStateValue(self,
				echoed = True,
				query_command = 'AN',
				set_method = self._setAntenna2,
				validity_check = self._antenna2Valid,
				depends_on=('mainFrequency',)
			),
			# The AR set command returns an error even when
			# changing to the current state, and doesn't
			# send a response.
			#
			# Further, the AR command returns an error when
			# trying to set it on the non-control receiver.
			# So basically, you can only set it for the
			# control recevier, and then only to the
			# opposite value.  Query appears to always work
			# for both however.
			'main_auto_simplex_on': KenwoodStateValue(self,
				echoed = True,
				query_command = 'AR0',
				set_format = 'AR0{:01d}1'
			),
			'main_simplex_possible': KenwoodStateValue(self,
				echoed = True,
				query_command = 'AR0'
			),
			'sub_auto_simplex_on': KenwoodStateValue(self,
				echoed = True,
				query_command = 'AR1',
				set_format = 'AR1{:01d}1'
			),
			'sub_simplex_possible': KenwoodStateValue(self,
				echoed = True,
				query_command = 'AR1'
			),
			'beat_canceller': KenwoodStateValue(self,
				echoed = True,
				query_command = 'BC',
				set_format = 'BC{:01}'
			),
			'auto_beat_canceller': KenwoodStateValue(self,
				echoed = True,
				query_command = 'BC',
				set_format = 'BC{:01}'
			),
			'manual_beat_canceller': KenwoodStateValue(self,
				echoed = True,
				query_command = 'BC',
				set_method = self._set_manualBeatCanceller
			),
			'band_down': KenwoodStateValue(self,
				echoed = True,
				set_format = 'BD'
			),
			'manual_beat_canceller_frequency': KenwoodStateValue(self,
				echoed = False,
				query_command = 'BP',
				set_format = 'BP{:03d}'
			),
			'band_up': KenwoodStateValue(self,
				echoed = True,
				set_format = 'BU'
			),
			'mainBusy': KenwoodStateValue(self, query_command = 'BY'),
			'subBusy': KenwoodStateValue(self, query_command = 'BY'),
			'CWautoTune': KenwoodStateValue(self,
				echoed = True,
				query_command = 'CA',
				set_format = 'CA{:01d}',
				validity_check = self._cwAutoTuneValid,
				range_check = self._cwAutoTuneRange,
				depends_on = ('mode',)
			),
			'carrierGain': KenwoodStateValue(self,
				echoed = False,
				query_command = 'CG',
				set_format = 'CG{:03d}'
			),
			# False turns it up, True turns it down (derp derp),
			'turnMultiChControlDown': KenwoodStateValue(self,
				echoed = True,
				set_format = 'CH{:01d}'
			),
			# Sets the current frequency to be the CALL frequency for the band
			'storeAsCallFrequency': KenwoodStateValue(self,
				echoed = True,
				set_format = 'CI'
			),
			'packetClusterTune': KenwoodStateValue(self,
				echoed = True,
				query_command = 'CM',
				set_format = 'CM{:01d}'
			),
			'CTCSStone': KenwoodStateValue(self,
				echoed = True,
				query_command = 'CN',
				set_format = 'CN{:02d}'
			),
			'CTCSS': KenwoodStateValue(self,
				echoed = True,
				query_command = 'CT',
				set_format = 'CT{:01d}'
			),
			'TXmain': KenwoodStateValue(self,
				echoed = True,
				query_command = 'DC',
				set_method = self._set_TXmain
			),
			'controlMain': KenwoodStateValue(self,
				echoed = True,
				query_command = 'DC',
				set_method = self._set_controlMain
			),
			'down': KenwoodStateValue(self,
				echoed = True,
				set_format = 'DN'
			),
			'DCS': KenwoodStateValue(self,
				echoed = True,
				query_command = 'DQ',
				set_format = 'DQ{:01d}'
			),
			'VFOAsetFrequency': KenwoodStateValue(self,
				echoed = True,
				query_command = 'FA',
				set_format = 'FA{:011d}',
				range_check = self._checkMainFrequencyValid,
				depends_on = ('mainTXmode', 'mainTransmitting', 'RIT', 'XIT', 'TXmain',)
			),
			'VFOBsetFrequency': KenwoodStateValue(self,
				echoed = True,
				query_command = 'FB',
				set_format = 'FB{:011d}',
				range_check = self._checkMainFrequencyValid,
				depends_on = ('mainTXmode', 'mainTransmitting', 'RIT', 'XIT', 'TXmain',)
			),
			'subSetFrequency': KenwoodStateValue(self,
				echoed = True,
				query_command = 'FC',
				set_format = 'FC{:011d}',
				range_check = self._checkSubFrequencyValid,
				depends_on = ('subMode', 'subTransmitting', 'TXmain',)
			),
			'filterDisplayPattern': KenwoodStateValue(self, query_command = 'FD'),
			# NOTE: FR changes FT, but FT doesn't change FR **and** doesn't notify
			# that FT was changed.  This is handled in update_FR
			'currentRXtuningMode':          KenwoodStateValue(self,
				echoed = True,
				query_command = 'FR',
				set_format = 'FR{:01d}',
				validity_check = self._notInTransmitSet,
				depends_on = ('controlMain', 'TXmain','transmitSet',)
			),
			'fineTuning': KenwoodStateValue(self,
				echoed = True,
				query_command = 'FS',
				set_format = 'FS{:01d}'
			),
			'currentTXtuningMode': KenwoodStateValue(self,
				echoed = True,
				query_command = 'FT',
				set_format = 'FT{:01d}',
				validity_check = self._notInTransmitSet,
				depends_on = ('controlMain', 'mainRXtuningMode', 'TXmain','transmitSet',)
			),
			'filterWidth': KenwoodStateValue(self,
				echoed = True,
				query_command = 'FW',
				set_format = 'FW{:04d}',
				validity_check = self._filterWidthValid,
				depends_on = ('controlMain','mode',)
			),
			'AGCconstant': KenwoodStateValue(self,
				echoed = True,
				query_command = 'GT',
				set_format = 'GT{:03d}'
			),
			'ID': KenwoodStateValue(self,
				echoed = True,
				query_command = 'ID',
				works_powered_off = True,
				read_only = True
			),
			'currentReceiverTransmitting': KenwoodStateValue(self,
				query_command = 'IF',
				set_method = self._set_mainTransmitting,
				range_check = self._currentTransmittingValid,
				depends_on = ('TXmain', 'controlMain',)
			),
			'RIT_XITfrequency': KenwoodNagleStateValue(self,
				echoed = True,
				query_command = 'IF',
				set_method = self._set_RIT_XITfrequency,
				range_check = self._check_RIT_XITfrequency,
				depends_on = ('TXmain', 'controlMain',)
			),
			'split': KenwoodStateValue(self,
				query_command = 'IF',
				depends_on=('mainTXtuningMode', 'mainRXtuningMode', 'TXmain', 'controlMain',)
			),
			'IFshift': KenwoodStateValue(self,
				echoed = True,
				query_command = 'IS',
				set_format = 'IS {:04d}'
			),
			'keyerSpeed': KenwoodStateValue(self,
				echoed = False,
				query_command = 'KS',
				set_format = 'KS{:03d}'
			),
			'keyerBufferFull': KenwoodStateValue(self, query_command = 'KY'),
			'keyerBuffer': KenwoodStateValue(self,
				echoed = True,
				set_format = 'KY {:24}'
			),
			'frequencyLock': KenwoodStateValue(self,
				echoed = True,
				query_command = 'LK',
				set_method = self._set_frequencyLock
			),
			'allLock': KenwoodStateValue(self,
				echoed = True,
				query_command = 'LK',
				set_method = self._set_allLock
			),
			'rc2000Lock': KenwoodStateValue(self,
				echoed = True,
				query_command = 'LK',
				set_method = self._set_rc2000Lock
			),
			'rigLock': KenwoodStateValue(self,
				echoed = True,
				query_command = 'LK',
				set_method = self._set_rigLock
			),
			'recordingChannel': KenwoodStateValue(self,
				echoed = True,
				query_command = 'LM',
				set_format = 'LM{:01d}'
			),
			'autoLockTuning': KenwoodStateValue(self,
				echoed = True,
				query_command = 'LT',
				set_format = 'LT{:01d}'
			),
			'memoryChannel': KenwoodStateValue(self,
				echoed = True,
				query_command = 'MC',
				set_format = 'MC{:03d}',
				depends_on = ('controlMain',)
			),
			'mode': KenwoodStateValue(self,
				echoed = True,
				query_command = 'MD',
				set_format = 'MD{:01d}',
				depends_on = ('controlMain', 'transmitSet', 'mainTXtuningMode', 'mainRXtuningMode', 'TXmain',)
			),
			'menuAB': KenwoodStateValue(self,
				echoed = True,
				query_command = 'MF',
				set_format = 'MF{:1}'
			),
			'microphoneGain': KenwoodStateValue(self,
				echoed = False,
				query_command = 'MG',
				set_format = 'MG{:03d}'
			),
			'monitorLevel': KenwoodStateValue(self,
				echoed = False,
				query_command = 'ML',
				set_format = 'ML{:03d}'
			),
			# MO; fails, and I dont' see a way to check if Sky Command is ON
			#self.skyCommandMonitor =            KenwoodStateValue(self, query_command = 'MO',  set_format = 'MO{:01d}')
			# TODO: Modernize MR (memory read)
			# TODO: Modernize MW (memory write)
			'memoryGroups': KenwoodStateValue(self,
				echoed = False,
				query_command = 'MU',
				set_method = self._set_memoryGroups,
				range_check = self._memoryGroupRange
			),
			'noiseBlanker': KenwoodStateValue(self,
				echoed = True,
				query_command = 'NB',
				set_format = 'NB{:01d}',
				validity_check = self._noiseBlankerValid,
				depends_on = ('mode',)
			),
			'noiseBlankerLevel': KenwoodStateValue(self,
				echoed = False,
				query_command = 'NL',
				set_format = 'NL{:03d}'
			),
			'noiseReduction': KenwoodStateValue(self,
				echoed = True,
				query_command = 'NR',
				set_format = 'NR{:01d}'
			),
			'noiseReduction1': KenwoodStateValue(self,
				echoed = True,
				query_command = 'NR',
				set_format = 'NR{:01d}'
			),
			'noiseReduction2': KenwoodStateValue(self,
				echoed = True,
				query_command = 'NR',
				set_method = self._set_noiseReduction2
			),
			'autoNotch': KenwoodStateValue(self,
				echoed = True,
				query_command = 'NT',
				set_format = 'NT{:01d}'
			),
			'offsetFrequency': KenwoodStateValue(self,
				echoed = True,
				query_command = 'OF',
				set_format = 'OF{:09d}',
				depends_on = ('controlMain',)
			),
			# TODO: OI appears to be IF for the non-active receiver... not sure if that's PTT or CTRL
			'offsetType': KenwoodStateValue(self,
				echoed = True,
				query_command = 'OS',
				set_format = 'OS{:01d}',
				depends_on = ('controlMain',)
			),
			'mainPreAmp': KenwoodStateValue(self,
				echoed = True,
				query_command = 'PA',
				set_format = 'PA{:01d}'
			),
			'subPreAmp': KenwoodStateValue(self, query_command = 'PA'),
			'playbackChannel': KenwoodStateValue(self,
				echoed = True,
				query_command = 'PB',
				set_format = 'PB{:01d}'
			),
			'outputPower': KenwoodStateValue(self,
				echoed = False,
				query_command = 'PC',
				set_format = 'PC{:03d}'
			),
			'storeAsProgrammableMemory': KenwoodStateValue(self,
				echoed = True,
				set_format = 'PI{:01d}'
			),
			'lastSpot': KenwoodStateValue(self),
			'speechProcessorInputLevel': KenwoodStateValue(self,
				echoed = False,
				query_command = 'PL',
				set_method = self._set_speechProcessorInputLevel
			),
			'speechProcessorOutputLevel': KenwoodStateValue(self,
				echoed = False,
				query_command = 'PL',
				set_method = self._set_speechProcessorOutputLevel
			),
			'programmableMemoryChannel': KenwoodStateValue(self,
				echoed = True,
				query_command = 'PM',
				set_format = 'PM{:01d}'
			),
			'speechProcessor': KenwoodStateValue(self,
				echoed = True,
				query_command = 'PR',
				set_format = 'PR{:01d}'
			),
			'powerOn': KenwoodStateValue(self,
				echoed = True,
				query_command = 'PS',
				set_format = 'PS{:01d}',
				works_powered_off = True
			),
			'DCScode': KenwoodStateValue(self,
				echoed = True,
				query_command = 'QC',
				set_format = 'QC{:03d}'
			),
			'storeAsQuickMemory': KenwoodStateValue(self,
				echoed = True,
				set_format = 'QC'
			),
			'quickMemory': KenwoodStateValue(self,
				echoed = True,
				query_command = 'QR',
				set_method = self._set_quickMemory
			),
			'quickMemoryChannel': KenwoodStateValue(self,
				echoed = True,
				query_command = 'QR',
				set_method = self._set_quickMemoryChannel
			),
			'attenuator': KenwoodStateValue(self,
				echoed = True,
				query_command = 'RA',
				set_format = 'RA{:02d}'
			),
			'clearRIT': KenwoodStateValue(self,
				echoed = True,
				set_format = 'RC',
				validity_check = self._can_clearRIT,
				depends_on = ('RIT', 'XIT','scanMode',)
			),
			'RITdown': KenwoodStateValue(self,
				echoed = True,
				set_format = 'RD{:05d}',
				validity_check = self._RITupDownValid,
				depends_on = ('scanMode',)
			),
			'scanSpeed': KenwoodStateValue(self,
				echoed = True,
				query_command = 'RD',
				validity_check = self._scanSpeedUpDownValid,
				depends_on = ('scanMode',)
			),
			'scanSpeedDown': KenwoodStateValue(self,
				echoed = True,
				set_format = 'RD{:05d}',
				validity_check = self._scanSpeedUpDownValid,
				depends_on = ('scanMode',)
			),
			'RFgain': KenwoodStateValue(self,
				echoed = False,
				query_command = 'RG',
				set_format = 'RG{:03d}'
			),
			'noiseReductionLevel': KenwoodStateValue(self,
				echoed = False,
				query_command = 'RL',
				set_format = 'RL{:02d}',
				validity_check = self._noiseReductionLevelValid,
				depends_on = ('noiseReduction',)
			),
			'meterType': KenwoodStateValue(self,
				echoed = True,
				query_command = 'RM',
				set_format = 'RM{:01d}',
				range_check = self._checkMeterValue,
				depends_on = ('speechProcessor',)
			),
			'meterValue': KenwoodStateValue(self, query_command = 'RM'),
			'SWRmeter': KenwoodStateValue(self, query_command = 'RM'),
			'compressionMeter': KenwoodStateValue(self, query_command = 'RM'),
			'ALCmeter': KenwoodStateValue(self, query_command = 'RM'),
			'RIT': KenwoodStateValue(self,
				echoed = True,
				query_command = 'RT',
				set_format = 'RT{:01d}'
			),
			'RITup': KenwoodStateValue(self,
				echoed = True,
				set_format = 'RU{:05d}',
				validity_check = self._RITupDownValid,
				depends_on = ('scanMode',)
			),
			'scanSpeedUp': KenwoodStateValue(self,
				echoed = True,
				set_format = 'RU{:05d}',
				validity_check = self._scanSpeedUpDownValid,
				depends_on = ('scanMode',)
			),
			'mainTransmitting': KenwoodStateValue(self,
				echoed = True,
				query_method = self._update_mainTransmitting,
				set_method = self._set_mainTransmitting,
				range_check = self._mainTransmittingValid,
				depends_on = ('TXmain', 'currentReceiverTransmitting',)
			), # RX, TX
			'subTransmitting': KenwoodStateValue(self,
				echoed = True,
				query_method = self._update_subTransmitting,
				set_method = self._set_subTransmitting,
				range_check = self._subTransmittingValid,
				depends_on = ('TXmain', 'currentReceiverTransmitting',)
			), # RX, TX
			# TODO: Setters for SA command
			'satelliteMode': KenwoodStateValue(self, query_command = 'SA'),
			'satelliteMemoryChannel': KenwoodStateValue(self, query_command = 'SA'),
			'satelliteMainUpSubDown': KenwoodStateValue(self, query_command = 'SA'),
			'satelliteControlMain': KenwoodStateValue(self, query_command = 'SA'),
			'satelliteTrace': KenwoodStateValue(self, query_command = 'SA'),
			'satelliteTraceReverse': KenwoodStateValue(self, query_command = 'SA'),
			'satelliteMultiKnobVFO': KenwoodStateValue(self, query_command = 'SA'),
			'satelliteChannelName': KenwoodStateValue(self, query_command = 'SA'),
			'subReceiver': KenwoodStateValue(self,
				echoed = True,
				query_command = 'SB',
				set_format = 'SB{:01d}'
			),
			'scanMode': KenwoodStateValue(self,
				echoed = True,
				query_command = 'SB',
				set_format = 'SB{:01d}'
			),
			'cwBreakInTimeDelay': KenwoodStateValue(self,
				echoed = True,
				query_command = 'SD',
				set_format = 'SD{:04d}'
			),
			'voiceLowPassCutoff': KenwoodStateValue(self,
				echoed = True,
				query_command = 'SH',
				set_format = 'SH{:02d}',
				validity_check = self._voiceCutoffValid,
				depends_on = ('controlMain', 'mode',)
			),
			# TODO: SI - Satellite memory name
			'voiceHighPassCutoff': KenwoodStateValue(self,
				echoed = True,
				query_command = 'SL',
				set_format = 'SL{:02d}',
				validity_check = self._voiceCutoffValid,
				depends_on = ('controlMain', 'mode',)
			),
			'mainSMeter': KenwoodStateValue(self, query_command = 'SM0'),
			'subSMeter': KenwoodStateValue(self, query_command = 'SM1'),
			'mainSMeterLevel': KenwoodStateValue(self, query_command = 'SM2'),
			'subSMeterLevel': KenwoodStateValue(self, query_command = 'SM3'),
			'mainSquelch': KenwoodStateValue(self,
				echoed = False,
				query_command = 'SQ0',
				set_format = 'SQ0{:03d}'
			),
			'subSquelch': KenwoodStateValue(self,
				echoed = False,
				query_command = 'SQ1',
				set_format = 'SQ1{:03d}'
			),
			# TODO?: SR1, SR2... reset transceiver
			# TODO: SS set/read Program Scan pause frequency
			'multiChFrequencySteps': KenwoodStateValue(self,
				echoed = True,
				query_command = 'ST',
				set_format = 'ST{:02d}'
			),
			# TODO: SU - program scan pause frequency
			'memoryToVFO': KenwoodStateValue(self,
				echoed = True,
				set_format = 'SV',
				validity_check = self._inMemoryMode,
				depends_on = ('controlMain', 'mainRXtuningMode',)
			),
			'PCcontrolCommandMode': KenwoodStateValue(self,
				echoed = True,
				query_command = 'TC',
				set_format = 'TC {:01d}'
			),
			'sendDTMFmemoryData': KenwoodStateValue(self,
				echoed = True,
				set_format = 'TD {:02d}'
			),
			'tnc96kLED': KenwoodStateValue(self, query_command = 'TI'),
			'tncSTALED': KenwoodStateValue(self, query_command = 'TI'),
			'tncCONLED': KenwoodStateValue(self, query_command = 'TI'),
			'subToneFrequency': KenwoodStateValue(self,
				echoed = False,
				query_command = 'TN',
				set_format = 'TN{:02d}'
			),
			'toneFunction': KenwoodStateValue(self,
				echoed = False,
				query_command = 'TO',
				set_format = 'TO{:01d}'
			),
			'transmitSet': KenwoodStateValue(self,
				echoed = True,
				query_command = 'TS',
				set_format = 'TS{:01d}',
				validity_check = self._check_notSimplex,
				range_check = self._check_transmitSet
			),
			# TODO: TS (simplex)
			'firmwareType': KenwoodStateValue(self, query_command = 'TY'),
			# TODO: UL? (PLL Unlock)
			'up': KenwoodStateValue(self,
				echoed = True,
				set_format = 'UP'
			),
			'VOXdelayTime': KenwoodStateValue(self,
				echoed = False,
				query_command = 'VD',
				set_format = 'VD{:04d}'
			),
			'VOXgain': KenwoodStateValue(self,
				echoed = False,
				query_command = 'VG',
				set_format = 'VG{:03d}'
			),
			'voice1': KenwoodStateValue(self,
				echoed = True,
				set_format = 'VR0'
			),
			'voice2': KenwoodStateValue(self,
				echoed = True,
				set_format = 'VR1'
			),
			'VOX': KenwoodStateValue(self,
				echoed = False,
				query_command = 'VX',
				set_format = 'VX{:01d}'
			),
			'XIT': KenwoodStateValue(self,
				echoed = False,
				query_command = 'XT',
				set_format = 'XT{:01d}'
			),
			'memoryVFOsplitEnabled': KenwoodStateValue(self,
				echoed = False,
				query_command = 'EX0060100',
				set_format = 'EX0060100{:01d}'
			),
			'tunerOnInRX': KenwoodStateValue(self,
				echoed = False,
				query_command = 'EX0270000',
				set_format = 'EX0270000{:01d}'
			),
			'mainRXsetFrequency': KenwoodStateValue(self),
			'mainRXfrequency': KenwoodStateValue(self),
			'mainTXsetFrequency': KenwoodStateValue(self),
			'mainTXoffsetFrequency': KenwoodStateValue(self),
			'mainTXfrequency': KenwoodStateValue(self),
			'subTXoffsetFrequency': KenwoodStateValue(self),
			'mainFrequency': KenwoodStateValue(self),
			'subFrequency': KenwoodStateValue(self),
			'currentTXfrequency': KenwoodStateValue(self),
			'currentRXfrequency': KenwoodStateValue(self),
			'mainRXtuningMode': KenwoodStateValue(self,
				set_method = self._set_mainRXtuningMode,
				range_check = self._check_mainRXtuningMode
			),
			'mainTXtuningMode': KenwoodStateValue(self,
				set_method = self._set_mainTXtuningMode,
				range_check = self._check_mainTXtuningMode
			),
			'subTuningMode': KenwoodStateValue(self),
			'mainRXmode': KenwoodStateValue(self),
			'mainTXmode': KenwoodStateValue(self),
			'subMode': KenwoodStateValue(self, query_method = self._query_subMode),
			'currentTXmode': KenwoodStateValue(self),
			'currentRXmode': KenwoodStateValue(self),
			'mainMemoryChannel': KenwoodStateValue(self),
			'subMemoryChannel': KenwoodStateValue(self),
		}
		# Parts if ListStates
		self._state['tunerRX'] = KenwoodSingleStateValue(self, self._state['tuner_list'],
			echoed = True,
			offset = 0,
		)
		self._state['tunerTX'] = KenwoodSingleStateValue(self, self._state['tuner_list'],
			echoed = True,
			offset = 1,
		)
		self._state['tunerState'] = KenwoodSingleStateValue(self, self._state['tuner_list'],
			echoed = True,
			offset = 0,
		)

		# TODO: This is a hack to fill the cache...
		#self._state['mainFrequency']._cached_value = 0
		#self._state['mainTransmitting']._cached_value = False
		# Now plug the names in...
		for a, p in self._state.items():
			if isinstance(p, StateValue):
				p.name = a
		if self.powerOn:
			self.auto_information = 2
		self.memories = MemoryArray(self)
		self._fill_cache()

	def _readThread(self):
		while not self._terminate:
			cmdline = self._serial.read()
			if cmdline is not None:
				m = match(b"^.*?([\?A-Z]{1,2})([\x20-\x3a\x3c-\x7f]*?);$", cmdline)
				if m:
					if self._aliveWait is not None:
						self._aliveWait.set()
					cmd = m.group(1)
					args = m.group(2).decode('ascii')
					if cmd in self._command:
						self._command[cmd](args)
					else:
						if cmd == b'PS':
							self._serial.PS_works = True
						else:
							print('Unhandled command "%s" (args: "%s")' % (cmd, args), file=stderr)
				else:
					print('Bad command line: "'+str(cmdline)+'"', file=stderr)

	def _send_query(self, state):
		self._serial.writeQueue.put({
			'msgType': 'query',
			'stateValue': state,
		})

	def _query(self, state):
		self._error_count = 0
		ev = Event()
		cb = lambda x, y: ev.set()
		state.add_set_callback(cb)
		while True:
			# WE can't be the ones to retry since the error handler does that!
			self._send_query(state)
			if ev.wait(1):
				break
			raise Exception("I've been here all day waiting for "+str(state.name))
		state.remove_set_callback(cb)

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
		if value is None:
			raise Exception('Attempt to set '+state.name+' to None')
		self._serial.writeQueue.put({
			'msgType': 'set',
			'stateValue': state,
			'value': value,
		})

	def add_callback(self, prop, cb):
		self._state[prop].add_callback(cb)

	def remove_callback(self, prop, cb):
		self._state[prop].remove_callback(cb)

	def terminate(self):
		if hasattr(self, 'auto_information'):
			self.auto_information = 0
		if hasattr(self, '_terminate'):
			self._terminate = True
		self._serial.terminate()
		if hasattr(self, 'readThread'):
			self._readThread.join()

	def _fill_cache_cb(self, prop, *args):
		nxt = None
		while len(self._fill_cache_state['todo']) > 0:
			nxt = self._fill_cache_state['todo'].pop(0)
			if not nxt[0]._valid(False):
				self._fill_cache_state['matched_count'] += 1
				nxt = None
				continue
			break
		if nxt is not None:
			nxt[0].add_set_callback(nxt[1])
			self._send_query(nxt[0])

		if prop is not None:
			self._fill_cache_state['matched_count'] += 1
			prop.remove_set_callback(self._fill_cache_cb)
			if self._fill_cache_state['matched_count'] == self._fill_cache_state['target_count']:
				for cb in self._fill_cache_state['call_after']:
					cb()
				self._fill_cache_state['event'].set()

	def _fill_cache(self):
		if self._state['powerOn']._cached == False:
			return
		done = {}
		self._fill_cache_state['todo'] = []
		self._fill_cache_state['call_after'] = ()
		self._fill_cache_state['target_count'] = 0
		self._fill_cache_state['matched_count'] = 0
		self._fill_cache_state['event'] = Event()
		# Perform queries in this order:
		# 0) FA, FB, FC
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
		print('Waiting...')
		self._fill_cache_state['event'].wait()
		# TODO: if on main, toggle TF-SET to get TX mode/frequency
		ocm = self._state['controlMain']._cached
		if not ocm:
			self._set(self._state['controlMain'], True)
			self._send_query(self._state['currentRXtuningMode'])
			self._send_query(self._state['currentTXtuningMode'])
			oldts = self._state['transmitSet']._cached
			if oldts is None:
				oldts = False
			self._set(self._state['transmitSet'], not oldts)
			self._send_query(self._state['currentRXtuningMode'])
			self._send_query(self._state['currentTXtuningMode'])
			self._set(self._state['transmitSet'], oldts)
			self._set(self._state['controlMain'], False)
			self._set(self._state['controlMain'], False)
		else:
			oldts = self._state['transmitSet']._cached
			if oldts is None:
				oldts = False
			self._set(self._state['transmitSet'], not oldts)
			self._send_query(self._state['currentRXtuningMode'])
			self._send_query(self._state['currentTXtuningMode'])
			self._set(self._state['transmitSet'], oldts)
			self._set(self._state['controlMain'], False)
			self._send_query(self._state['currentRXtuningMode'])
			self._set(self._state['controlMain'], True)
		# TODO: switch to other receiver to get mode/frequency

	def _kill_cache(self):
		self._killing_cache = True
		for a, p in self._state.items():
			if isinstance(p, StateValue):
				if p._query_command in ('PS', 'ID'):
					continue
				p._cached = None
		self._killing_cache = False

	# Range check methods return True or False
	
	# Set methods return a string to send to the rig
	def _set_manualBeatCanceller(self, value):
		return 'BC{:01d}'.format(BeatCanceller.MANUAL if value else BeatCanceller.OFF)

	# TODO: Multi-value items should use a list as the state value
	#       Then, the set method should interpret "None" as no
	#       change.  They also don't need to ensure they wait for
	#       a query to complete.
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

	# Update methods return a string to send to the rig
	def _update_mainTransmitting(self):
		self._state['mainTransmitting']._cached = self._state['TXmain']._cached and self._state['currentReceiverTransmitting']._cached
		return ''

	def _update_subTransmitting(self):
		self._state['subTransmitting']._cached = (not self._state['TXmain']._cached) and self._state['currentReceiverTransmitting']._cached
		return ''

	
	# Validity check methods return True or False
	def _noiseBlankerValid(self):
		if self._state['mode']._cached is None:
			return False
		return self._state['mode']._cached != mode.FM

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



	
	def _voiceCutoffValid(self):
		if not self._state['controlMain']._cached:
			return False
		return self._state['mode']._cached in (mode.AM, mode.FM, mode.LSB, mode.USB)

	def _inMemoryMode(self):
		return self._state['controlMain']._cached and self._state['mainRXtuningMode']._cached == tuningMode.MEMORY

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
		if self._state['mainFrequency']._cached <= 60000000 and (value == 1 or value == 2):
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
		if cm == self._state['controlMain']._cached and (m is None or m == self._state['currentRXtuningMode']._cached):
			sv._cached = self._state['mode']._cached
			return
		old_cm = None
		if not self._state['controlMain']._cached == cm:
			old_cm = self._state['controlMain']._cached
			self._set(self._state['controlMain'], cm)
		old_tm = None
		if m is not None:
			if not self._state['currentRXtuningMode']._cached == m:
				old_tm = self._state['currentRXtuningMode']._cached
				self._set(self._state['currentRXtuningMode'], m)
		if old_tm is not None:
			self._set(self._state['currentRXtuningMode'], old_tm)
		if old_cm is not None:
			self._set(self._state['controlMain'], old_cm)

	def _query_VFOAmode(self):
		self._query_VFOmode(True, tuningMode.VFOA, self._state['VFOAmode'])

	def _query_VFOBmode(self):
		self._query_VFOmode(True, tuningMode.VFOB, self._state['VFOBmode'])

	def _query_subMode(self):
		self._query_VFOmode(False, tuningMode.VFOA, self._state['subMode'])

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
		if self._state['split']._cached:
			return True
		return False

	def _never(self):
		return False

	def _check_notSimplex(self):
		# TODO: This is sketchy and here to avoid issues with transmitSet
		if self._state['offsetFrequency']._cached is None:
			return True
		if self._state['offsetType']._cached:
			return True
		if self._state['offsetFrequency']._cached == 0:
			return True
		if self._state['offsetType']._cached == offset.NONE:
			return True
		return False

	def _set_mainRXtuningMode(self, value):
		return 'FR{:01d}'.format(int(value))

	def _set_mainTXtuningMode(self, value):
		return 'FT{:01d}'.format(int(value))

	def _check_mainRXtuningMode(self, value):
		if self._state['controlMain']._cached is None:
			return True
		if not self._state['controlMain']._cached:
			return False
		return True

	def _check_mainTXtuningMode(self, value):
		if not self._state['controlMain']._cached:
			return False
		if value == tuningMode.CALL:
			return self._state['mainRXtuningMode']._cached == tuningMode.CALL
		elif self._state['mainTXtuningMode']._cached == tuningMode.CALL:
			return False
		return True

	def _notInTransmitSet(self):
		if self._state['transmitSet']._cached is None:
			return True
		return self._state['transmitSet']._cached == False

	def _check_RIT_XITfrequency(self, value):
		if value == self._state['RIT_XITfrequency']._cached:
			return False
		return not self._scanSpeedUpDownValid()

	def _set_RIT_XITfrequency(self, value):
		diff = int(value - self._state['RIT_XITfrequency']._cached)
		if diff < 0:
			return 'RD{:05d}'.format(int(abs(diff)))
		else:
			return 'RU{:05d}'.format(int(diff))

	def _can_clearRIT(self):
		return self._state['RIT']._cached or self._state['XIT']._cached

	def _update_AC(self, args):
		split = self.parse('1d1d1d', args)
		self._state['tuner_list'] = [bool(split[0]), bool(split[1]), tunerState(split[2])]

	def _update_AG(self, args):
		split = self.parse('1d3d', args)
		if split[0] == 0:
			self._state['main_af_gain']._cached = split[1]
		else:
			self._state['sub_af_gain']._cached = split[1]

	def _update_AI(self, args):
		split = self.parse('1d', args)
		self._state['auto_information']._cached = AI(split[0])

	def _update_AL(self, args):
		split = self.parse('3d', args)
		self._state['auto_notch_level']._cached = split[0]

	def _update_AM(self, args):
		split = self.parse('1d', args)
		self._state['auto_mode']._cached = bool(split[0])

	# TODO: None here means 2m or 440 fixed antenna
	#       maybe something better would be good?
	def _update_AN(self, args):
		split = self.parse('1d', args)
		self._state['antenna_connector']._cached = None if split[0] == 0 else split[0]
		self._state['antenna1']._cached = (split[0] == 1) if split[0] != 0 else None
		self._state['antenna2']._cached = (split[0] == 2) if split[0] != 0 else None

	def _update_AR(self, args):
		split = self.parse('1d1d1d', args)
		aso = bool(split[1])
		if split[0] == 0:
			self._state['main_auto_simplex_on']._cached = aso
			self._state['main_simplex_possible']._cached = bool(split[2]) if aso else False
		else:
			self._state['sub_auto_simplex_on']._cached = aso
			self._state['sub_simplex_possible']._cached = bool(split[2]) if aso else False

	def _update_BC(self, args):
		split = self.parse('1d', args)
		self._state['beat_canceller']._cached = BeatCanceller(split[0])
		if split[0] == 0:
			self._state['auto_beat_canceller']._cached = False
			self._state['manual_beat_canceller']._cached = False
		elif split[0] == 1:
			self._state['auto_beat_canceller']._cached = True
			self._state['manual_beat_canceller']._cached = False
		elif split[0] == 2:
			self._state['auto_beat_canceller']._cached = False
			self._state['manual_beat_canceller']._cached = True

	def _update_BP(self, args):
		split = self.parse('3d', args)
		self._state['manual_beat_canceller_frequency']._cached = split[0]

	def _update_BY(self, args):
		split = self.parse('1d1d', args)
		self._state['mainBusy']._cached = bool(split[0])
		self._state['subBusy']._cached = bool(split[1])

	def _update_CA(self, args):
		split = self.parse('1d', args)
		self._state['CWautoTune']._cached = bool(split[0])

	def _update_CG(self, args):
		split = self.parse('3d', args)
		self._state['carrierGain']._cached = split[0]

	def _update_CM(self, args):
		split = self.parse('1d', args)
		self._state['packetClusterTune']._cached = bool(split[0])

	def _update_CN(self, args):
		split = self.parse('2d', args)
		self._state['CTCSStone']._cached = CTCSStone(split[0])

	def _update_CT(self, args):
		split = self.parse('1d', args)
		self._state['CTCSS']._cached = bool(split[0])

	def _update_DC(self, args):
		split = self.parse('1d1d', args)
		self._state['TXmain']._cached = not bool(split[0])
		self._state['controlMain']._cached = not bool(split[1])

	def _update_DQ(self, args):
		split = self.parse('1d', args)
		self._state['DCS']._cached = bool(split[0])

	def _update_EX(self, args):
		split = self.parse('3d2d1d1d0l', args)
		if split[0] == 27:
			self._state['tunerOnInRX']._cached = bool(int(split[4]))
		elif split[0] == 6:
			self._state['memoryVFOsplitEnabled']._cached = bool(int(split[4]))
		else:
			print('Unhandled EX menu {:03d}'.format(split[0]), file=stderr)

	def _apply_offset(self, freq):
		if freq is None:
			return
		if self._state['offsetType']._cached is not None:
			if self._state['offsetType']._cached == offset.NEGATIVE:
				if self._state['offsetFrequency']._cached is not None:
					freq = freq - self._state['offsetFrequency']._cached
			elif self._state['offsetType']._cached == offset.POSITIVE:
				if self._state['offsetFrequency']._cached is not None:
					freq = freq + self._state['offsetFrequency']._cached
			elif self._state['offsetType']._cached == offset.NONE:
				pass
			elif self._state['offsetType']._cached == offset.EURO_SPLIT:
				if freq > 200000000 and freq < 600000000:
					freq -= 7600000
				elif freq > 1200000000 and freq < 1400000000:
					freq -= 6000000
		return freq

	def _apply_RIT(self, freq):
		if freq is None:
			return
		if self._state['RIT']._cached:
			freq += self._state['RIT_XITfrequency']._cached
		return freq

	def _apply_XIT(self, freq):
		if freq is None:
			return
		if self._state['XIT']._cached:
			freq += self._state['RIT_XITfrequency']._cached
		return freq

	def _set_mainRXfrequencies(self, freq):
		if freq is None:
			return
		self._state['mainRXsetFrequency']._cached = freq
		self._state['mainRXfrequency']._cached = self._apply_RIT(freq)
		if not self._state['mainTransmitting']._cached:
			self._state['mainFrequency']._cached = self._state['mainRXfrequency']._cached
		if self._state['TXmain']._cached:
			self._state['currentRXfrequency']._cached = self._state['mainRXfrequency']._cached

	def _set_mainTXfrequencies(self, freq):
		if freq is None:
			return
		self._state['mainTXsetFrequency']._cached = freq
		if self._state['mainTXmode']._cached == mode.FM and (not self._state['split']._cached):
			self._state['mainTXoffsetFrequency']._cached = self._apply_offset(freq)
		else:
			self._state['mainTXoffsetFrequency']._cached = freq
		self._state['mainTXfrequency']._cached = self._apply_XIT(self._state['mainTXoffsetFrequency']._cached)
		if self._state['mainTransmitting']._cached:
			self._state['mainFrequency']._cached = self._state['mainTXfrequency']._cached
		if self._state['TXmain']._cached:
			self._state['currentTXfrequency']._cached = self._state['mainTXfrequency']._cached

	def _updateMainFrequency(self, args, tuning_mode):
		split = self.parse('11d', args)
		if tuning_mode == tuningMode.VFOA:
			self._state['VFOAsetFrequency']._cached = split[0]
		elif tuning_mode == tuningMode.VFOB:
			self._state['VFOBsetFrequency']._cached = split[0]
		else:
			raise Exception('Unspecified tuning mode ' + str(tuning_mode))
		if self._state['mainRXtuningMode']._cached == tuning_mode:
			self._set_mainRXfrequencies(split[0])
		if self._state['mainTXtuningMode']._cached == tuning_mode:
			self._set_mainTXfrequencies(split[0])

	def _update_FA(self, args):
		self._updateMainFrequency(args, tuningMode.VFOA)

	def _update_FB(self, args):
		self._updateMainFrequency(args, tuningMode.VFOB)

	def _set_subFrequencies(self, freq):
		if freq is None:
			return
		self._state['subSetFrequency']._cached = freq
		if self._state['subMode']._cached == mode.FM:
			self._state['subTXoffsetFrequency']._cached = self._apply_offset(freq)
		else:
			self._state['subTXoffsetFrequency']._cached = freq
		if self._state['subTransmitting']._cached:
			self._state['subFrequency']._cached = self._state['subTXoffsetFrequency']._cached
			self._state['subFrequency']._cached = self._state['subTXoffsetFrequency']._cached
		else:
			self._state['subFrequency']._cached = self._state['subSetFrequency']._cached
		if not self._state['TXmain']._cached:
			self._state['currentTXfrequency']._cached = self._state['subTXoffsetFrequency']._cached
			self._state['currentRXfrequency']._cached = self._state['subSetFrequency']._cached

	def _update_FC(self, args):
		split = self.parse('11d', args)
		self._set_subFrequencies(split[0])

	def _update_FD(self, args):
		split = self.parse('8x', args)
		self._state['filterDisplayPattern']._cached = int2ba(split[0], 32)

	# TODO: Toggle tuningMode when transmitting?  Check the IF command...
	# NOTE: FR changes FT **and** doesn't notify that FT was changed.
	#       FT doesn't change FR unless the sub receiver is the TX
	def _update_FR(self, args):
		split = self.parse('1d', args)
		tuning_mode = tuningMode(split[0])
		# TODO: The mode is also unknown at this time...
		if self._state['controlMain']._cached == True:
			# TODO: This gets fixed by the IF command
			# TODO: We likely know all this already, 
			# TODO: We need to invalidate this, but we don't.
			#if not self._state['mainTransmitting']._cached:
			#	self._state['mainFrequency']._cached = None
			self._state['mainRXsetFrequency']._cached = None
			self._state['mainRXfrequency']._cached = None
			if self._state['TXmain']._cached:
				self._state['currentRXfrequency']._cached = None
			self._state['split']._cached = False
			self._state['mainRXtuningMode']._cached = tuning_mode
			self._state['currentRXtuningMode']._cached = tuning_mode
		else:
			# Handled in _update_FT()
			pass
		self._update_FT(args)

	def _update_FS(self, args):
		split = self.parse('1d', args)
		self._state['fineTuning']._cached = bool(split[0])

	def _update_FT(self, args):
		split = self.parse('1d', args)
		tuning_mode = tuningMode(split[0])
		if self._state['controlMain']._cached:
			# TODO: We need to invalidate this, but we don't.
			#if self._state['mainTransmitting']._cached:
			#	self._state['mainFrequency']._cached = None
			self._state['mainTXsetFrequency']._cached = None
			self._state['mainTXoffsetFrequency']._cached = None
			self._state['mainTXfrequency']._cached = None
			self._state['currentTXtuningMode']._cached = tuning_mode
			if self._state['mainRXtuningMode']._cached != tuning_mode:
				self._state['split']._cached = True
			else:
				self._state['split']._cached = False
			self._state['mainTXtuningMode']._cached = tuning_mode
			self._state['currentTXtuningMode']._cached = tuning_mode
		else:
			self._state['subFrequency']._cached = None
			self._state['subSetFrequency']._cached = None
			self._state['subTXoffsetFrequency']._cached = None
			self._state['currentRXfrequency']._cached = None
			if not self._state['TXmain']._cached:
				self._state['currentRXfrequency']._cached = None
			self._state['subTuningMode']._cached = tuning_mode
			self._state['currentTXtuningMode']._cached = tuning_mode
			self._state['currentRXtuningMode']._cached = tuning_mode
		self._send_query(self._state['split'])

	def _update_FW(self, args):
		split = self.parse('4d', args)
		self._state['filterWidth']._cached = split[0]

	def _update_GT(self, args):
		if args == '   ':
			self._state['AGCconstant']._cached = None
		else:
			split = self.parse('3d', args)
			self._state['AGCconstant']._cached = split[0]

	def _update_ID(self, args):
		self._state['ID']._cached = self.parse('3d', args)[0]

	def _update_IF(self, args):
		# TODO: Synchronize these with the single-value options
		# NOTE: This is the control receiver, not the TX one even if we're transmitting
		# NOTE: Combined P6 and P7 since they're effectively one number on the TS-2000
		#'00003810000' '    ' ' 00000' '0' '0' '101' '0' '1' '0' '0' '0' '0' '08' '0'
		#'00003810000' '    ' ' 00000' '0' '0' '101' '0' '1' '0' '0' '0' '0' '08' '0'
		#     3810000,     0,       1,  0,  1,    0,  1,  0,  0,  0,  0,  0,   8,  0
		split = self.parse('11d4d6d1d1d3d1d1d1d1d1d1d2d1d', args)

		# We need to parse RIT/XIT/Offset before the frequency
		self._state['RIT_XITfrequency'].lock.acquire()
		if self._state['RIT_XITfrequency']._pending is not None:
			if self._state['RIT_XITfrequency']._pending['value'] is not None:
				self._state['RIT_XITfrequency']._queued = self._state['RIT_XITfrequency']._pending
				self._set(self._state['RIT_XITfrequency'], self._state['RIT_XITfrequency']._queued['value'])
			self._state['RIT_XITfrequency']._pending = None
		self._state['RIT_XITfrequency'].lock.release()
		self._state['RIT_XITfrequency']._cached = split[2]
		self._state['RIT']._cached = bool(split[3])
		self._state['XIT']._cached = bool(split[4])
		self._state['offsetType']._cached = offset(split[13])
		if self._state['TXmain']._cached == self._state['controlMain']._cached:
			if split[6]: # TX - may not be the current transmitter
				self._state['currentTXfrequency']._cached = split[0]
				if self._state['controlMain']._cached:
					self._set_mainTXfrequencies(split[0])
				else:
					self._set_subFrequencies(split[0])
			else:
				self._state['currentRXfrequency']._cached = split[0]
		self._state['multiChFrequencySteps']._cached = split[1]
		self._state['memoryChannel']._cached = split[5]
		self._state['currentReceiverTransmitting']._cached = bool(split[6])
		self._update_MD(str(split[7]))
		if self._state['TXmain']._cached == self._state['controlMain']._cached:
			if split[6]:
				self._state['currentTXtuningMode']._cached = tuningMode(split[8])
				if self._state['controlMain']._cached:
					self._state['mainTXtuningMode']._cached = tuningMode(split[8])
				else:
					self._state['subTuningMode']._cached = tuningMode(split[8])
			else:
				self._state['currentRXtuningMode']._cached = tuningMode(split[8])
				if self._state['controlMain']._cached:
					self._state['mainRXtuningMode']._cached = tuningMode(split[8])
				else:
					self._state['subTuningMode']._cached = tuningMode(split[8])
		self._state['scanMode']._cached = scanMode(split[9])
		# TODO: Split is undocumented and full-duplex may be here?
		self._state['split']._cached = bool(split[10])
		# TODO: TONE/CTCSS/DCS squished together here in split[11]
		# TODO: Tone frequency
		self._state['subToneFrequency']._cached = CTCSStone(split[12])
		# Fun hack... in CALL mode, MC300 is updated via IF...
		# We handle this special case by asserting that if we get IF
		# when in MC300, the MC has been updated
		if self._state['memoryChannel']._cached == 300:
			self.memories.memories[300]._cached_value = None
			self._state['memoryChannel']._cached_value = None
			self._state['memoryChannel']._cached = 300

	def _update_IS(self, args):
		split = self.parse('5d', args)
		self._state['IFshift']._cached = split[0]

	def _update_KS(self, args):
		split = self.parse('3d', args)
		self._state['keyerSpeed']._cached = split[0]

	def _update_KY(self, args):
		split = self.parse('1d', args)
		self._state['keyerBufferFull']._cached = bool(split[0])

	def _update_LK(self, args):
		split = self.parse('1d1d', args)
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
		split = self.parse('1d', args)
		self._state['recordingChannel']._cached = recordingChannel(split[0])

	def _update_LT(self, args):
		split = self.parse('1d', args)
		self._state['autoLockTuning']._cached = bool(split[0])

	def _update_MC(self, args):
		split = self.parse('3d', args)
		# TODO:
		# Any time we get an MC300; it means we entered CALL mode
		# The calling frequency *may* be different than last time!
		if split[0] == 300:
			self.memories.memories[300]._cached_value = None
		self._state['memoryChannel']._cached = split[0]
		if self._state['controlMain']._cached:
			self._state['mainMemoryChannel']._cached = split[0]
		else:
			self._state['subMemoryChannel']._cached = split[0]
		# This also invalidates the current frequency
		if self._state['controlMain']._cached:
			if self.memories.memories[split[0]]._cached is None:
				self._state['currentRXfrequency']._cached = None
				self._state['currentTXfrequency']._cached = None
				self._state['mainRXsetFrequency']._cached = None
				self._state['mainRXfrequency']._cached = None
				self._state['mainTXsetFrequency']._cached = None
				self._state['mainTXoffsetFrequency']._cached = None
				self._state['mainTXfrequency']._cached = None
				# TODO: We need to invalidate this, but we don't.
				#self._state['mainFrequency']._cached = None
			else:
				mem = self.memories.memories[split[0]]._cached
				print('mem = '+str(mem))
				self._state['offsetFrequency']._cached = mem['OffsetFrequency']
				self._state['offsetType']._cached = mem['OffsetType']
				self._state['mainRXsetFrequency']._cached = mem['Frequency']
				self._state['mainRXfrequency']._cached = self._apply_RIT(mem['Frequency'])
				self._state['mainFrequency']._cached = self._state['mainRXfrequency']._cached
				self._state['mainTXsetFrequency']._cached = mem['TXfrequency']
				self._state['mainTXoffsetFrequency']._cached = self._apply_offset(mem['TXfrequency'])
				self._state['mainTXfrequency']._cached = self._apply_RIT(self._state['mainTXoffsetFrequency']._cached)
				self._state['currentRXfrequency']._cached = self._state['mainRXfrequency']._cached
				self._state['currentTXfrequency']._cached = self._state['mainTXfrequency']._cached
		else:
			if self.memories.memories[split[0]]._cached is None:
				self._state['currentRXfrequency']._cached = None
				self._state['currentTXfrequency']._cached = None
				self._state['subSetFrequency']._cached = None
				self._state['subTXoffsetFrequency']._cached = None
				self._state['subFrequency']._cached = None
			else:
				mem = self.memories.memories[split[0]]._cached
				self._state['offsetFrequency']._cached = mem['OffsetFrequency']
				self._state['offsetType']._cached = mem['OffsetType']
				self._state['subSetFrequency']._cached = mem['Frequency']
				self._state['subFrequency']._cached = mem['Frequency']
				self._state['subTXoffsetFrequency']._cached = self._apply_offset(mem['TXfrequency'])
				self._state['currentRXfrequency']._cached = self._state['subSetFrequency']._cached
				self._state['currentTXfrequency']._cached = self._state['subTXoffsetFrequency']._cached

	def _update_MD(self, args):
		split = self.parse('1d', args)
		self._state['mode']._cached = mode(split[0])
		if not self._state['mode']._cached in (mode.CW, mode.CW_REVERSED,):
			self._state['CWautoTune']._cached = None
		else:
			self._state['CWautoTune']._cached = False
		if self._state['controlMain']._cached == True:
			if self._notInTransmitSet():
				self._state['mainRXmode']._cached = mode(split[0])
				if self._state['mainTXtuningMode']._cached == self._state['mainRXtuningMode']._cached:
					self._state['mainTXmode']._cached = mode(split[0])
			else:
				self._state['mainTXmode']._cached = mode(split[0])
			if self._state['TXmain']._cached:
				self._state['currentTXmode']._cached = self._state['mainTXmode']._cached
				self._state['currentRXmode']._cached = self._state['mainRXmode']._cached
		else:
			self._state['subMode']._cached = mode(split[0])
			if not self._state['TXmain']._cached:
				self._state['currentTXmode']._cached = self._state['subMode']._cached
				self._state['currentRXmode']._cached = self._state['subMode']._cached

	def _update_MF(self, args):
		split = self.parse('1d', args)
		if split[0] == 0:
			self._state['menuAB']._cached = 'A'
		elif split[0] == 1:
			self._state['menuAB']._cached = 'B'

	def _update_MG(self, args):
		split = self.parse('3d', args)
		self._state['microphoneGain']._cached = split[0]

	def _update_ML(self, args):
		split = self.parse('3d', args)
		self._state['monitorLevel']._cached = split[0]

	def _update_MO(self, args):
		split = self.parse('1d', args)
		self._state['skyCommandMonitor']._cached = bool(split[0])

	def _update_MR(self, args):
		split = self.parse('1d3d11d1d1d1d2d2d3d1d1d9d2d1d0l', args)
		idx = 0
		newVal = deepcopy(self.memories.memories[split[1]]._cached)
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
		if newVal['Channel'] == self._state['mainMemoryChannel']._cached:
			if self._state['mainRXtuningMode']._cached == tuningMode.MEMORY and 'Frequency' in newVal:
				self._set_mainRXfrequencies(newVal['Frequency'])
			if self._state['mainTXtuningMode']._cached == tuningMode.MEMORY and 'TXfrequency' in newVal:
				self._set_mainTXfrequencies(newVal['TXfrequency'])
		else:
			if self._state['subTuningMode']._cached == tuningMode.MEMORY and 'Frequency' in newVal:
				self._set_subFrequencies(newVal['Frequency'])
			elif self._state['subTuningMode']._cached == tuningMode.MEMORY and 'TXfrequency' in newVal:
				self._set_subFrequencies(newVal['TXfrequency'])
		self.memories.memories[split[1]]._cached = newVal

	def _update_MU(self, args):
		self._state['memoryGroups']._cached = base2ba(2, args)

	def _update_NB(self, args):
		split = self.parse('1d', args)
		self._state['noiseBlanker']._cached = bool(split[0])

	def _update_NL(self, args):
		split = self.parse('3d', args)
		self._state['noiseBlankerLevel']._cached = split[0]

	def _update_NR(self, args):
		split = self.parse('1d', args)
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
		split = self.parse('1d', args)
		self._state['autoNotch']._cached = bool(split[0])

	def _update_OF(self, args):
		split = self.parse('9d', args)
		self._state['offsetFrequency']._cached = split[0]
		if self._state['controlMain']._cached:
			self._set_mainTXfrequencies(self._state['mainTXsetFrequency']._cached)
		else:
			self._set_subFrequencies(self._state['subSetFrequency']._cached)

	def _update_OS(self, args):
		split = self.parse('1d', args)
		self._state['offsetType']._cached = offset(split[0])
		if self._state['controlMain']._cached:
			self._set_mainTXfrequencies(self._state['mainTXsetFrequency']._cached)
		else:
			self._set_subFrequencies(self._state['subSetFrequency']._cached)

	def _update_PA(self, args):
		split = self.parse('1d1d', args)
		self._state['mainPreAmp']._cached = bool(split[0])
		self._state['subPreAmp']._cached = bool(split[1])

	def _update_PB(self, args):
		split = self.parse('1d', args)
		self._state['playbackChannel']._cached = recordingChannel(split[0])

	def _update_PC(self, args):
		split = self.parse('3d', args)
		self._state['outputPower']._cached = split[0]

	def _update_PK(self, args):
		split = self.parse('11d12l20l5l', args)
		spot = {
			frequency: split[0],
			callsign: split[1],
			comments: split[2],
			time: split[3]
		}
		self._state['lastSpot']._cached = spot

	def _update_PL(self, args):
		split = self.parse('3d3d', args)
		self._state['speechProcessorInputLevel']._cached = split[0]
		self._state['speechProcessorOutputLevel']._cached = split[1]

	def _update_PM(self, args):
		split = self.parse('1d', args)
		# TODO: Should this be False when it's off?
		self._state['programmableMemoryChannel']._cached = split[0]

	def _update_PR(self, args):
		split = self.parse('1d', args)
		self._state['speechProcessor']._cached = bool(split[0])

	def _update_PS(self, args):
		self._serial.PS_works = True
		split = self.parse('1d', args)
		old = self._last_power_state
		self._state['powerOn']._cached = bool(split[0])
		self._last_power_state = bool(split[0])
		if split[0] and old == False:
			self._set(self._state['auto_information'], 2)
			print('Filling')
			self._fill_cache()
			print('Done')
		elif (not split[0]) and old == True:
			self._kill_cache()

	def _update_QC(self, args):
		split = self.parse('3d', args)
		self._state['DCScode']._cached = DCScode(split[0])

	def _update_QR(self, args):
		split = self.parse('1d1d', args)
		self._state['quickMemory']._cached = bool(split[0])
		self._state['quickMemoryChannel']._cached = split[1]

	def _update_RA(self, args):
		split = self.parse('2d', args)
		self._state['attenuator']._cached = bool(split[0])

	# NOTE: Updates the same value as RU
	def _update_RD(self, args):
		split = self.parse('1d', args)
		self._state['scanSpeed']._cached = split[0]

	def _update_RG(self, args):
		split = self.parse('3d', args)
		self._state['RFgain']._cached = split[0]

	def _update_RL(self, args):
		split = self.parse('2d', args)
		self._state['noiseReductionLevel']._cached = split[0]

	def _update_RM(self, args):
		split = self.parse('1d4d', args)
		self._state['meterType']._cached = meter(split[0])
		self._state['meterValue']._cached = split[1]
		self._state['SWRmeter']._cached = split[1] if split[0] == 1 else 0
		self._state['compressionMeter']._cached = split[1] if split[0] == 2 else 0
		self._state['ALCmeter']._cached = split[1] if split[0] == 3 else 0

	# Note: Can only set RM2 when COMP is on

	def _update_RT(self, args):
		split = self.parse('1d', args)
		self._state['RIT']._cached = bool(split[0])
		self._set_mainTXfrequencies(self._state['mainTXsetFrequency']._cached)

	# NOTE: Updates the same value as RD
	def _update_RU(self, args):
		split = self.parse('1d', args)
		self._state['scanSpeed']._cached = split[0]

	def _update_RX(self, args):
		split = self.parse('1d', args)
		if self._state['TXmain']._cached == True and split[0] == 0:
			self._state['currentReceiverTransmitting']._cached = False
		elif self._state['TXmain']._cached == False and split[0] == 1:
			self._state['currentReceiverTransmitting']._cached = False
		if split[0] == 0:
			self._state['mainTransmitting']._cached = False
		if split[0] == 1:
			self._state['subTransmitting']._cached = False

	def _update_SA(self, args):
		split = self.parse('1d1d1d1d1d1d1d8l', args)
		self._state['satelliteMode']._cached = bool(split[0])
		self._state['satelliteMemoryChannel']._cached = split[1]
		self._state['satelliteMainUpSubDown']._cached = not bool(split[2])
		self._state['satelliteControlMain']._cached = not bool(split[3])
		self._state['satelliteTrace']._cached = bool(split[4])
		self._state['satelliteTraceReverse']._cached = bool(split[5])
		self._state['satelliteMultiKnobVFO']._cached = not bool(split[6])
		self._state['satelliteChannelName']._cached = split[7]

	def _update_SB(self, args):
		split = self.parse('1d', args)
		self._state['subReceiver']._cached = bool(split[0])

	def _update_SC(self, args):
		split = self.parse('1d', args)
		self._state['scanMode']._cached = scanMode(split[0])

	def _update_SD(self, args):
		split = self.parse('4d', args)
		self._state['cwBreakInTimeDelay']._cached = split[0]

	def _update_SH(self, args):
		split = self.parse('2d', args)
		self._state['voiceLowPassCutoff']._cached = split[0]

	def _update_SL(self, args):
		split = self.parse('2d', args)
		self._state['voiceHighPassCutoff']._cached = split[0]

	def _update_SM(self, args):
		split = self.parse('1d4d', args)
		# TODO: Figure out what 2 and 3 actually are...
		if split[0] == 0:
			self._state['mainSMeter']._cached = split[1]
		if split[0] == 1:
			self._state['subSMeter']._cached = split[1]
		if split[0] == 2:
			print('Got SM2!', file=stderr)
			self._state['mainSMeterLevel']._cached = split[1]
		if split[0] == 3:
			print('Got SM3!', file=stderr)
			self._state['subSMeterLevel']._cached = split[1]

	def _update_SQ(self, args):
		split = self.parse('1d3d', args)
		if split[0] == 0:
			self._state['mainSquelch']._cached = split[1]
		elif split[0] == 1:
			self._state['subSquelch']._cached = split[1]

	def _update_ST(self, args):
		split = self.parse('2d', args)
		self._state['multiChFrequencySteps']._cached = split[0]

	def _update_TC(self, args):
		split = self.parse('1d1d', args)
		self._state['PCcontrolCommandMode']._cached = bool(split[1])

	def _update_TI(self, args):
		split = self.parse('1d1d1d', args)
		self._state['tnc96kLED']._cached = bool(split[0])
		self._state['tncSTALED']._cached = bool(split[1])
		self._state['tncCONLED']._cached = bool(split[2])

	def _update_TN(self, args):
		split = self.parse('2d', args)
		# TODO: Smart mapping thing?
		self._state['subToneFrequency']._cached = CTCSStone(split[0])

	def _update_TO(self, args):
		split = self.parse('1d', args)
		self._state['toneFunction']._cached = bool(split[0])

	def _update_TS(self, args):
		split = self.parse('1d', args)
		self._state['transmitSet']._cached = bool(split[0])

	def _update_TX(self, args):
		split = self.parse('1d', args)
		if self._state['TXmain']._cached == True and split[0] == 0:
			self._state['currentReceiverTransmitting']._cached = True
		elif self._state['TXmain']._cached == False and split[0] == 1:
			self._state['currentReceiverTransmitting']._cached = True
		else:
			print('TX triggered for wrong receiver!', file=stderr)
		if split[0] == 0:
			self._state['mainTransmitting']._cached = True
		if split[0] == 1:
			self._state['subTransmitting']._cached = True

	def _update_TY(self, args):
		split = self.parse('2d1d', args)
		self._state['firmwareType']._cached = firmwareType(split[1])

	def _update_UL(self, args):
		split = self.parse('1d', args)
		if split[0] == 1:
			raise Exception('PLL Unlocked!')
		self._state['PLLunlock']._cached = bool(split[0])

	def _update_VD(self, args):
		split = self.parse('4d', args)
		self._state['VOXdelayTime']._cached = split[0]

	def _update_VG(self, args):
		split = self.parse('3d', args)
		self._state['VOXgain']._cached = split[0]

	def _update_VX(self, args):
		split = self.parse('1d', args)
		self._state['VOX']._cached = bool(split[0])

	def _update_XT(self, args):
		split = self.parse('1d', args)
		self._state['XIT']._cached = bool(split[0])
		self._set_mainTXfrequencies(self._state['mainTXsetFrequency']._cached)

	def _update_Error(self, args):
		self._error_count += 1
		if self._last_command is None:
			self._serial.PS_works = False
		if self._error_count < 10:
			print('Resending: '+str(self._last_command), file=stderr)
			self._serial.writeQueue.put(self._last_command)
		else:
			raise Exception('Error count exceeded')

	def _update_ComError(self, args):
		self._error_count += 1
		if self._last_command is None:
			self._serial.PS_works = False
		if self._error_count < 10:
			print('Resending: '+str(self._last_command), file=stderr)
			self._serial.writeQueue.put(self._last_command)
		else:
			raise Exception('Error count exceeded')

	def _update_IncompleteError(self, args):
		self._error_count += 1
		if self._last_command is None:
			self._serial.PS_works = False
		if self._error_count < 10:
			print('Resending: '+str(self._last_command), file=stderr)
			self._serial.writeQueue.put(self._last_command)
		else:
			raise Exception('Error count exceeded')

	def parse(self, fmt, args):
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
