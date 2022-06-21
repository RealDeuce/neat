# Copyright (c) 2022 Stephen Hurd
# Copyright (c) 2022 Stephen Hurd
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
from rig import Rig, StateValue, mode
from bitarray.util import int2ba, base2ba
from copy import deepcopy
from re import match
from sys import stderr
from threading import Lock, Event, Thread, get_ident
from queue import Queue
from rig.kenwood_hf.serial import KenwoodHFProtocol

'''
A basic overview of the concepts behind this

The kenwood_hf.py module is an asynchronous rig control library, and it
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

class Direction(IntEnum):
	UP = 0
	DOWN = 1

# Indicates which sub-rigs this property should be included in
class InRig(IntEnum):
	BOTH = 0             # The state is shared between the two receivers
	MAIN = 1             # The state is only for the main receiver
	SUB = 2              # The state is only for the sub receiver
	NONE = 3             # The state is not in a receiver (ie: a list with a state for each)

# Indicates what state the control and tx rig selection needs to be
# in to set this value
class SetState(IntEnum):
	ANY = 0     # Can be set from any state
	CONTROL = 1 # Can only be set for the current control receiver
	TX = 2      # Can only be set for the current TX receiver
	TS = 3      # Must be the current TX receiver and TS mode must be enabled
	NOT_TS = 4  # Must be the current TX receiver and TS mode must not be enabled
	NONE = 5    # Can't be set

class QueryState(IntEnum):
	ANY = 0     # Can always be queried
	CONTROL = 1 # Can only be queried when control receiver is the receiver it's in
	TS = 2      # Can only be queried when TX and when TS is true
	NOT_TS = 3  # Must be the current TX receiver and TS mode must not be enabled
	NONE = 4    # Can't be queried

class KenwoodStateValue(StateValue):
	def __init__(self, rig, **kwargs):
		super().__init__(rig, **kwargs)
		self._echoed = kwargs.get('echoed', True)
		self._query_command = kwargs.get('query_command')
		self._query_method = kwargs.get('query_method')
		self._range_check = kwargs.get('range_check')
		self._set_format = kwargs.get('set_format')
		self._set_method = kwargs.get('set_method')
		self._validity_check = kwargs.get('validity_check')
		self._works_powered_off = kwargs.get('works_powered_off', False)
		self._works_sub_off = kwargs.get('works_sub_off', False)
		self._in_rig = kwargs.get('in_rig', InRig.BOTH)
		self._set_state = kwargs.get('set_state', SetState.ANY)
		self._query_state = kwargs.get('query_state', QueryState.ANY)
		if self._set_format is not None and self._set_method is not None:
			raise Exception('Only one of set_method or set_format may be specified')
		if self._query_command is not None and self._query_method is not None:
			raise Exception('Only one of query_command or query_method may be specified')

	def _get_query_prefix_suffix(self):
		# First, ensure control is set correctly
		prefix = ''
		suffix = ''
		if not 'control_main' in self._rig._state:
			return (prefix, suffix)
		if not 'tx_main' in self._rig._state:
			return (prefix, suffix)
		if self._rig._state['control_main']._cached is None:
			return (prefix, suffix)
		if self._rig._state['tx_main']._cached is None:
			return (prefix, suffix)
		need_ts = False
		need_control = False
		need_tx = False
		if self._query_state != QueryState.ANY:
			if (self._in_rig == InRig.MAIN) != self._rig._state['control_main']._cached:
				need_control = True
			if self._query_state in (QueryState.TS, QueryState.NOT_TS):
				if (self._in_rig == InRig.MAIN) != self._rig._state['tx_main']._cached:
					need_tx = True
				if self._rig._state['transmit_set']._cached is not None:
					if self._rig._transmit_set_valid():
						if self._rig._state['transmit_set']._cached != (self._query_state == QueryState.TS):
							need_ts = True
			otxm = self._rig._state['tx_main']._cached
			ocm = self._rig._state['control_main']._cached
			if need_control or need_tx:
				prefix += 'DC{:1d}{:1d};'.format(
					self._in_rig == InRig.SUB if need_tx else otxm,
					self._in_rig == InRig.SUB
				)
				suffix = ';DC{:1d}{:1d}'.format(not otxm, not ocm) + suffix
				if need_tx and (not need_control):
					suffix = ';DC{:1d}{:1d}'.format(not otxm, not ocm) + suffix
			# Next, set TS if needed
			if need_ts:
				prefix += 'TS1;'
				suffix = ';TS0' + suffix
		return (prefix, suffix)

	# TODO: This is just a copy of above with Query changed to Set
	def _get_set_prefix_suffix(self):
		# First, ensure control is set correctly
		prefix = ''
		suffix = ''
		if not self._echoed:
			prefix = prefix + '\x00'
		if not 'control_main' in self._rig._state:
			return (prefix, suffix)
		if not 'tx_main' in self._rig._state:
			return (prefix, suffix)
		if self._rig._state['control_main']._cached is None:
			return (prefix, suffix)
		if self._rig._state['tx_main']._cached is None:
			return (prefix, suffix)
		need_ts = False
		need_control = False
		need_tx = False
		if self._set_state != SetState.ANY:
			if (self._in_rig == InRig.MAIN) != self._rig._state['control_main']._cached:
				need_control = True
			if self._set_state in (SetState.TS, SetState.NOT_TS):
				if (self._in_rig == InRig.MAIN) != self._rig._state['tx_main']._cached:
					need_tx = True
				if self._rig._state['transmit_set']._cached is not None:
					if self._rig._transmit_set_valid():
						if self._rig._state['transmit_set']._cached != (self._set_state == SetState.TS):
							need_ts = True
			otxm = self._rig._state['tx_main']._cached
			ocm = self._rig._state['control_main']._cached
			if need_control or need_tx:
				prefix += 'DC{:1d}{:1d};'.format(
					self._in_rig == InRig.SUB if need_tx else otxm,
					self._in_rig == InRig.SUB
				)
				suffix = ';DC{:1d}{:1d}'.format(not otxm, not ocm) + suffix
				if need_tx and (not need_control):
					suffix = ';DC{:1d}{:1d}'.format(not otxm, not ocm) + suffix
			# Next, set TS if needed
			if need_ts:
				prefix += 'TS1;'
				suffix = ';TS0' + suffix
		return (prefix, suffix)

	def _query_string(self):
		if not self._valid(True):
			self._cached = None
			return ''
		prefix, suffix = self._get_query_prefix_suffix()
		if self._query_method is not None:
			qs = self._query_method()
			if qs != '':
				return prefix + qs + suffix
			return qs
		elif self._query_command is not None:
			if self.name is None:
				raise Exception('Unnamed state! '+self._query_command)
			return prefix + self._query_command + suffix
		print('Attempt to query value "'+self.name+'" without a query command or method', file=stderr)
		return None

	def _do_range_check(self, value):
		if self._set_state == SetState.NONE:
			return False
		if self._cached == value:
			return False
		if not self._works_powered_off:
			if not self._rig.power_on:
				return False
		if self._set_state == SetState.TX:
			if self._in_rig == InRig.MAIN and self._rig._state['tx_main']._cached == False:
				return False
			if self._in_rig == InRig.SUB and self._rig._state['tx_main']._cached == True:
				return False
		if self._in_rig == InRig.SUB and self._rig._state['sub_receiver']._cached == False and not self._works_sub_off:
			return False
		if self._range_check is not None:
			return self._range_check(value)
		return True

	def _set_string(self, value):
		if not self._do_range_check(value):
			return ''
		if value is None:
			raise Exception('Setting new value of None!')
		if isinstance(value, list) and None in value:
			raise Exception('Setting a list with None in '+self.name+', '+str(value))
			return ''
		prefix, suffix = self._get_set_prefix_suffix()
		if self._set_format is not None:
			return prefix + self._set_format.format(value) + suffix
		elif self._set_method is not None:
			ss = self._set_method(value)
			if ss is None:
				return ss
			return prefix + self._set_method(value) + suffix
		print('Attempt to set value "'+self.name+'" without a set command or method', file=stderr)

	def _valid(self, can_query):
		if self._query_state == QueryState.NONE:
			return False
		if hasattr(self, '_readThread') and get_ident() == self._readThread.ident:
			can_query = False
		if not self._works_powered_off:
			if not self._rig.power_on:
				return False
		if self._in_rig == InRig.SUB and self._rig._state['sub_receiver']._cached == False and not self._works_sub_off:
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

class KenwoodDerivedBoolValue(KenwoodStateValue):
	def __init__(self, rig, derived_from, true_value, **kwargs):
		super().__init__(rig, **kwargs)
		self._true_value = true_value
		self._false_value = kwargs.get('false_value')
		self._derived_from = derived_from
		self._derived_from.add_set_callback(self._set_callback)
		self._cached_value = self._derived_from._cached
		self._echoed = self._derived_from._echoed
		self._query_command = self._derived_from._query_command
		self._query_method = self._derived_from._query_method
		self._works_powered_off = self._derived_from._works_powered_off
		self._works_sub_off = self._derived_from._works_sub_off
		self._in_rig = self._derived_from._in_rig
		self._set_state = self._derived_from._set_state
		self._query_state = self._derived_from._query_state

	def _set_callback(self, prop, value):
		if value is None:
			self._cached = None
		elif value == self._true_value:
			self._cached = True
		else:
			self._cached = False

	@property
	def value(self):
		return super().value

	@value.setter
	def value(self, value):
		if value == True:
			self._derived_from.value = self._true_value
		elif value == False:
			if self._false_value is not None:
				self._derived_from.value = self._false_value

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
		self._rig._serial.writeQueue.put(self._queued)
		self.lock.release()

	def _set_string(self, value):
		self.lock.acquire()
		self._pending = self._queued
		self._queued = None
		if not self._range_check(value):
			self._pending = None
			self.lock.release()
			return None
		self.lock.release()
		prefix, suffix = self._get_set_prefix_suffix()
		if self._set_format is not None:
			return prefix + self._set_format.format(value) + suffix
		elif self._set_method is not None:
			ss = self._set_method(value)
			if ss is None:
				return ss
			return prefix + self._set_method(value) + suffix
		print('Attempt to set value "'+self.name+'" without a set command or method', file=stderr)

class KenwoodListStateValue(KenwoodStateValue):
	def __init__(self, rig, length, **kwargs):
		super().__init__(rig, **kwargs)
		self._queued = None
		self.length = length
		self.children = [None] * self.length
		self._cached_value = [None] * self.length
		self.lock = Lock()
		self.add_set_callback(self._update_children)

	def _update_children(self, prop, value):
		if self._cached_value is None:
			self._cached_value = [None] * self.length
		if value is None:
			value = [None] * self.length
		for i in range(self.length):
			if self.children[i] is not None:
				self.children[i]._cached = value[i]

	@property
	def _cached(self):
		if self._cached_value is None:
			self._cached_value = [None] * self.length
		return self._cached_value

	@_cached.setter
	def _cached(self, value):
		if self._cached_value is None:
			self._cached_value = [None] * self.length
		modified = False
		if isinstance(value, StateValue):
			raise Exception('Forgot to add .cached!')
		for i in range(self.length):
			nv = None if value is None else value[i]
			if self._cached_value[i] != nv:
				modified = True
				self._cached_value[i] = nv
				if self.children[i] is not None:
					self.children[i]._cached_value = nv
				if self.children[i] is not None:
					for cb in self.children[i]._modify_callbacks:
						cb(nv)
			if self.children[i] is not None:
				for cb in self.children[i]._set_callbacks:
					cb(self.children[i], nv)
		if modified:
			for cb in self._modify_callbacks:
				cb(value)
		for cb in self._set_callbacks:
			cb(self, value)

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
			lst = self._queued['value']
		else:
			lst = [None] * self.length
		# Merge values... anything that's not None in
		# the new value should be copied into the old one
		for v in range(len(lst)):
			if value[v] is not None:
				lst[v] = value[v]
			else:
				lst[v] = self._cached[v]
		if self._queued is not None:
			self.lock.release()
			return
		self._queued = {
			'msgType': 'set',
			'stateValue': self,
			'value': lst,
		}
		self._rig._serial.writeQueue.put(self._queued)
		self.lock.release()

	def _set_string(self, value):
		self.lock.acquire()
		self._queued = None
		if not self._do_range_check(value):
			self.lock.release()
			return None
		self.lock.release()
		prefix, suffix = self._get_set_prefix_suffix()
		if self._set_format is not None:
			for i in range(self.length):
				if value[i] is None and self._cached is not None:
					value[i] = self._cached[i]
			return prefix + self._set_format.format(value) + suffix
		elif self._set_method is not None:
			ss = self._set_method(value)
			if ss is None:
				return ss
			return prefix + self._set_method(value) + suffix
		print('Attempt to set value "'+self.name+'" without a set command or method', file=stderr)

class KenwoodSingleStateValue(KenwoodStateValue):
	def __init__(self, rig, parent, offset, **kwargs):
		super().__init__(rig, **kwargs)
		self._parent = parent
		self._offset = offset
		self._parent.children[self._offset] = self

	@property
	def value(self):
		plist = self._parent.value
		if plist is None:
			return None
		return plist[self._offset]

	@value.setter
	def value(self, value):
		if isinstance(value, StateValue):
			raise Exception('Forgot to add ._cached!')
		if self._read_only:
			raise Exception('Attempt to set read-only property '+self.name+'!')
		newval = [None] * self._parent.length
		newval[self._offset] = value
		self._parent.value = newval

class MemoryArray(list):
	def __init__(self, rig, **kwargs):
		self.memories = [None] * 301
		self._rig = rig
		for i in range(len(self.memories)):
			self.memories[i] = KenwoodStateValue(rig, 
				echoed = True,
				query_command = 'MR0{:03d};MR1{:03d}'.format(i, i),
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.NONE,
			)
			self.memories[i].name = 'Memory' + str(i)

	def __len__(self):
		return len(self.memories)

	def __getitem__(self, key):
		# TODO: Support slices...
		if isinstance(key, slice):
			raise IndexError('Sorry, no slicing support yet')
		return self.memories[key].value

	def __setitem__(self, key, value):
		self.memories[key].value = value

	def __iter__(self):
		for x in range(len(self.memories)):
			yield self.memories[x].value

class KenwoodHFSubRig(Rig):
	def __init__(self, **kwargs):
		self._state = {}
		self._terminate = False

	def add_property(self, name, state_value):
		self._state[name] = state_value

	def __getattr__(self, name):
		if name in self._state:
			if hasattr(self, '_readThread') and get_ident() == self._readThread.ident:
				return self._state[name]._cached
			return self._state[name].value
		return super().__getattr__(name)

	def __setattr__(self, name, value):
		if name[:1] != '_':
			if name in self._state:
				self._state[name].value = value
				return
		super().__setattr__(name ,value)

	def terminate(self):
		self._terminate = True

class KenwoodHF(Rig):
	# TODO: Get ranges for non-K types
	tx_ranges_k = { # Americas
		'160m': [   1800000,   1999999],
		'80m':  [   3500000,   3999999],
		'40m':  [   7000000,   7299999],
		'30m':  [  10100000,  10149999],
		'20m':  [  14000000,  14349999],
		'17m':  [  18068000,  18167999],
		'15m':  [  21000000,  21449999],
		'12m':  [  24890000,  24989999],
		'10m':  [  28000000,  29699999],
		'6m':   [  50000000,  53999999],
		'2m':   [ 144000000, 147999999],
		'70cm': [ 430000000, 449999999],
		'23cm': [1240000000,1299999999],
	}
	tx_ranges_e = { # Europe
		'160m': [   1810000,   1999999],
		'80m':  [   3500000,   3799999],
		'40m':  [   7000000,   7099999],
		'30m':  [  10100000,  10149999],
		'20m':  [  14000000,  14349999],
		'17m':  [  18068000,  18167999],
		'15m':  [  21000000,  21449999],
		'12m':  [  24890000,  24989999],
		'10m':  [  28000000,  29699999],
		'6m':   [  50000000,  51999999],
		'2m':   [ 144000000, 145999999],
		'70cm': [ 430000000, 439999999],
		'23cm': [1240000000,1299999999],
	}
	tx_ranges_e2 = { # Spain
		'160m': [   1830000,   1849999],
		'80m':  [   3500000,   3799999],
		'40m':  [   7000000,   7099999],
		'30m':  [  10100000,  10149999],
		'20m':  [  14000000,  14349999],
		'17m':  [  18068000,  18167999],
		'15m':  [  21000000,  21449999],
		'12m':  [  24890000,  24989999],
		'10m':  [  28000000,  29699999],
		'6m':   [  50000000,  50199999],
		'2m':   [ 144000000, 145999999],
		'70cm': [ 430000000, 439999999],
		'23cm': [1240000000,1299999999],
	}
	rx_ranges_k_main = {
		'HF':   [     30000,  60000000],
		'2m':   [ 142000000, 151999999],
		'70cm': [ 420000000, 449999999],
		'23cm': [1240000000,1299999999],
	}
	rx_ranges_e_main = {
		'HF':   [     30000,  60000000],
		'2m':   [ 144000000, 145999999],
		'70cm': [ 430000000, 439999999],
		'23cm': [1240000000,1299999999],
	}
	rx_ranges_e2_main = {
		'HF':   [     30000,  60000000],
		'2m':   [ 144000000, 145999999],
		'70cm': [ 430000000, 439999999],
		'23cm': [1240000000,1299999999],
	}
	rx_ranges_k_sub = {
		'2m':   [118000000, 173995000],
		'70cm': [220000000, 511995000],
	}
	rx_ranges_e_sub = {
		'2m':   [144000000, 145995000],
		'70cm': [430000000, 439995000],
	}
	rx_ranges_e2_sub = {
		'2m':   [144000000, 145995000],
		'70cm': [430000000, 439995000],
	}

	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self._terminate = False
		self._killing_cache = False
		self._filling_cache = False
		self._error_count = 0
		self._last_hack = 0
		self._last_power_state = None
		self._fill_cache_state = {}
		self._serial = KenwoodHFProtocol(**kwargs)
		# All supported rigs must support the ID command
		self._state = {
			'id': KenwoodStateValue(self, name = 'ID', query_command = 'ID', works_powered_off = True),
		}
		self._state['id'].name = 'ID'
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
		self.rigs = (self,)

		resp = None
		while resp is None:
			resp = self.id
		initFunction = '_init_' + str(resp)
		if callable(getattr(self, initFunction, None)):
			getattr(self, initFunction, None)()
		else:
			raise Exception("Unsupported rig (%d)!" % (resp))
		self._init_done = True
		self._sync_lock = Lock()

	def __getattr__(self, name):
		if name in self._state:
			if hasattr(self, '_readThread') and get_ident() == self._readThread.ident:
				return self._state[name]._cached
			return self._state[name].value
		return super().__getattr__(name)

	def __setattr__(self, name, value):
		if name[:1] != '_':
			if name in self._state:
				self._state[name].value = value
				return
		super().__setattr__(name ,value)

	def __del__(self):
		self.terminate()

	# Init methods for specific rig IDs go here
	def _init_19(self):
		# A list of all handlers for commands send by the rig
		self._command = {
			# Errors
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

		# Read/Write state values
		self._state = {
			# State objects
			# AC set fails when main TX frequency not in HF
			# AC set fails when Control not in main
			# AC set fails when control is sub
			# AC set with a state of 0 always toggles the
			# current TX state, and will toggle the RX state
			# if so configured in the menu.
			# AC001; is an error
			# Not available for sub receiver
			'tuner_list': KenwoodListStateValue(self,
				echoed = True,
				query_command = 'AC',
				#set_format = 'AC{0[0]:1d}{0[1]:1d}{0[2]:1d}',
				set_method = self._set_tuner_list,
				length = 3,
				range_check = self._tuner_list_range_check,
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.ANY
			),
			'main_audio_level': KenwoodStateValue(self,
				name = 'audio_level',
				echoed = False,
				query_command = 'AG0',
				set_format = 'AG0{:03d}',
				in_rig = InRig.MAIN,
				set_state = SetState.ANY,
				query_state = QueryState.ANY
			),
			'sub_audio_level': KenwoodStateValue(self,
				name = 'audio_level',
				echoed = False,
				query_command = 'AG1',
				set_format = 'AG1{:03d}',
				in_rig = InRig.SUB,
				set_state = SetState.ANY,
				query_state = QueryState.ANY
			),
			# TODO: Should this be read-only?
			'auto_information': KenwoodStateValue(self,
				echoed = False,
				query_command = 'AI',
				set_format = 'AI{:01d}',
				in_rig = InRig.BOTH,
				set_state = SetState.ANY,
				query_state = QueryState.ANY
			),
			'auto_notch_level': KenwoodStateValue(self,
				echoed = False,
				query_command = 'AL',
				set_format = 'AL{:03d}',
				in_rig = InRig.MAIN,
				set_state = SetState.ANY,
				query_state = QueryState.ANY,
			),
			'auto_mode': KenwoodStateValue(self,
				echoed = True,
				query_command = 'AM',
				set_format = 'AM{:01d}',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.ANY,
			),
			'antenna_connector': KenwoodStateValue(self,
				echoed = True,
				query_command = 'AN',
				set_format = 'AN{:01d}',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
				range_check = self._antenna_connector_range_check
			),
			# The AR set command returns an error even when
			# changing to the current state
			# 
			# Further, the AR command returns an error when
			# trying to set it on the non-control receiver.
			# So basically, you can only set it for the
			# control recevier, and then only to the
			# opposite value.  Query appears to always work
			# for both however.
			# 
			# You can't change the offset when AR is
			# enabled, and you can't set AR when OS is Simplex
			# 
			# TS-Set disables AR mode (and doesn't change TS)
			# 
			# Setting AR disables TS (and does change it)
			# 
			# Memories hold the TS status for OS != 0, if
			# a memory is recalled with TS = 1 and OS != 0,
			# AR is disabled
			'main_auto_simplex_check': KenwoodStateValue(self,
				name = 'auto_simplex_check',
				echoed = True,
				query_command = 'AR0',
				set_format = 'AR0{:01d}0',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.ANY,
				range_check = self._main_auto_simplex_check_range_check,
			),
			'main_simplex_possible': KenwoodStateValue(self,
				name = 'simplex_possible',
				echoed = True,
				query_command = 'AR0',
				in_rig = InRig.MAIN,
				set_state = SetState.NONE,
				query_state = QueryState.ANY,
			),
			'sub_auto_simplex_check': KenwoodStateValue(self,
				name = 'auto_simplex_check',
				echoed = True,
				query_command = 'AR1',
				set_format = 'AR1{:01d}0',
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.ANY,
				range_check = self._sub_auto_simplex_check_range_check,
			),
			'sub_simplex_possible': KenwoodStateValue(self,
				name = 'simplex_possible',
				echoed = True,
				query_command = 'AR1',
				in_rig = InRig.SUB,
				set_state = SetState.NONE,
				query_state = QueryState.ANY,
			),
			'beat_canceller': KenwoodStateValue(self,
				echoed = True,
				query_command = 'BC',
				set_format = 'BC{:01}',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.ANY,
				range_check = self._beat_canceller_range_check
			),
			'main_band_down': KenwoodStateValue(self,
				name = 'band_down',
				echoed = True,
				set_format = 'BD',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.NONE,
			),
			'sub_band_down': KenwoodStateValue(self,
				name = 'band_down',
				echoed = True,
				set_format = 'BD',
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.NONE,
			),
			'manual_beat_canceller_frequency': KenwoodStateValue(self,
				echoed = False,
				query_command = 'BP',
				set_format = 'BP{:03d}',
				in_rig= InRig.MAIN,
				set_state = SetState.ANY,
				query_state = QueryState.ANY,
			),
			'main_band_up': KenwoodStateValue(self,
				name = 'band_up',
				echoed = True,
				set_format = 'BU',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.NONE,
			),
			'sub_band_up': KenwoodStateValue(self,
				name = 'band_up',
				echoed = True,
				set_format = 'BU',
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.NONE,
			),
			'busy_list': KenwoodListStateValue(self, 2,
				query_command = 'BY',
				in_rig = InRig.NONE,
				set_state = SetState.NONE,
				query_state = QueryState.ANY,
			),
			# Only in CW mode, only when DSP filter
			# is less than 1.0 kHz
			'auto_zero_beat': KenwoodStateValue(self,
				echoed = True,
				query_command = 'CA',
				set_format = 'CA{:01d}',
				range_check = self._auto_zero_beat_range_check,
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.ANY
			),
			# AM, CW, or FSK
			'carrier_gain': KenwoodStateValue(self,
				echoed = False,
				query_command = 'CG',
				set_format = 'CG{:03d}',
				in_rig = InRig.BOTH,
				set_state = SetState.ANY,
				query_state = QueryState.ANY,
			),
			# False turns it up, True turns it down (derp derp),
			'main_turn_multi_ch_control': KenwoodStateValue(self,
				name = 'turn_multi_ch_control',
				echoed = True,
				set_format = 'CH{:01d}',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.NONE,
			),
			'sub_turn_multi_ch_control': KenwoodStateValue(self,
				name = 'turn_multi_ch_control',
				echoed = True,
				set_format = 'CH{:01d}',
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.NONE,
			),
			# Sets the current frequency to be the CALL frequency for the band
			'main_store_as_call_frequency': KenwoodStateValue(self,
				name = 'store_as_call_frequency',
				echoed = True,
				set_format = 'CI',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.NONE,
			),
			'sub_store_as_call_frequency': KenwoodStateValue(self,
				name = 'store_as_call_frequency',
				echoed = True,
				set_format = 'CI',
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.NONE,
			),
			# Only available when sub-receiver is on and
			# the main receiver is on VFOA or VFOB
			'packet_cluster_tune': KenwoodStateValue(self,
				echoed = True,
				query_command = 'CM',
				set_format = 'CM{:01d}',
				in_rig = InRig.MAIN,
				set_state = SetState.ANY,
				query_state = QueryState.ANY,
				range_check = self._packet_cluster_tune_range_check
			),
			'main_ctcss_tone': KenwoodStateValue(self,
				name = 'ctcss_tone',
				echoed = True,
				query_command = 'CN',
				set_format = 'CN{:02d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'sub_ctcss_tone': KenwoodStateValue(self,
				name = 'ctcss_tone',
				echoed = True,
				query_command = 'CN',
				set_format = 'CN{:02d}',
				in_rig = InRig.SUB,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'main_ctcss': KenwoodStateValue(self,
				name = 'ctcss',
				echoed = True,
				query_command = 'CT',
				set_format = 'CT{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'sub_ctcss': KenwoodStateValue(self,
				name = 'ctcss',
				echoed = True,
				query_command = 'CT',
				set_format = 'CT{:01d}',
				in_rig = InRig.SUB,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			# NOTE: If you change the TX, the control is 
			# always changed to match.
			'control_list': KenwoodListStateValue(self, 2,
				echoed = True,
				query_command = 'DC',
				set_format = 'DC{0[0]:1d}{0[1]:1d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'main_down': KenwoodStateValue(self,
				name = 'down',
				echoed = True,
				set_format = 'DN',
				in_rig = InRig.MAIN,
				query_state = QueryState.NONE,
				set_state = SetState.CONTROL,
			),
			'sub_down': KenwoodStateValue(self,
				name = 'down',
				echoed = True,
				set_format = 'DN',
				in_rig = InRig.SUB,
				query_state = QueryState.NONE,
				set_state = SetState.CONTROL,
			),
			'main_dcs': KenwoodStateValue(self,
				name = 'dcs',
				echoed = True,
				query_command = 'DQ',
				set_format = 'DQ{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'sub_dcs': KenwoodStateValue(self,
				name = 'dcs',
				echoed = True,
				query_command = 'DQ',
				set_format = 'DQ{:01d}',
				in_rig = InRig.SUB,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'vfoa_frequency': KenwoodStateValue(self,
				echoed = True,
				query_command = 'FA',
				set_format = 'FA{:011d}',
				range_check = self._checkMainFrequencyValid,
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'vfob_frequency': KenwoodStateValue(self,
				echoed = True,
				query_command = 'FB',
				set_format = 'FB{:011d}',
				range_check = self._checkMainFrequencyValid,
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'sub_vfo_frequency': KenwoodStateValue(self,
				name = 'vfo_frequency',
				echoed = True,
				query_command = 'FC',
				set_format = 'FC{:011d}',
				range_check = self._checkSubFrequencyValid,
				in_rig = InRig.SUB,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'filter_display_pattern': KenwoodStateValue(self,
				query_command = 'FD',
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.NONE,
			),
			# NOTE: FR changes FT, but FT doesn't change FR **and** doesn't notify
			# that FT was changed.  This is handled in update_FR
			'main_rx_tuning_mode': KenwoodStateValue(self,
				name = 'rx_tuning_mode',
				echoed = True,
				query_command = 'FR',
				set_format = 'FR{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.NOT_TS,
				set_state = SetState.NOT_TS,
				range_check = self._main_rx_tuning_mode_range_check
			),
			'sub_tuning_mode': KenwoodStateValue(self,
				name = 'rx_tuning_mode',
				echoed = True,
				query_command = 'FR',
				set_format = 'FR{:01d}',
				in_rig = InRig.SUB,
				query_state = QueryState.NOT_TS,
				set_state = SetState.NOT_TS,
				range_check = self._sub_rx_tuning_mode_range_check
			),

			'main_fine_tuning': KenwoodStateValue(self,
				name = 'fine_tuning',
				echoed = True,
				query_command = 'FS',
				set_format = 'FS{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'sub_fine_tuning': KenwoodStateValue(self,
				name = 'fine_tuning',
				echoed = True,
				query_command = 'FS',
				set_format = 'FS{:01d}',
				in_rig = InRig.SUB,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'main_tx_tuning_mode': KenwoodStateValue(self,
				name = 'tx_tuning_mode',
				echoed = True,
				query_command = 'FT',
				set_format = 'FT{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
				range_check = self._main_tx_tuning_mode_range_check
			),
			'filter_width': KenwoodStateValue(self,
				echoed = True,
				query_command = 'FW',
				set_format = 'FW{:04d}',
				validity_check = self._filter_width_valid,
				range_check = self._filter_width_range_check,
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'agc_constant': KenwoodStateValue(self,
				echoed = True,
				query_command = 'GT',
				set_format = 'GT{:03d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
				range_check = self._agc_constant_range_check
			),
			'id': KenwoodStateValue(self,
				echoed = True,
				query_command = 'ID',
				works_powered_off = True,
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.NONE,
				read_only = True,
			),
			'main_tx': KenwoodStateValue(self,
				name = 'tx',
				query_command = 'IF',
				set_method = self._set_tx,
				range_check = self._main_tx_range_check,
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.TX,
			),
			'sub_tx': KenwoodStateValue(self,
				name = 'tx',
				query_command = 'IF',
				set_method = self._set_tx,
				range_check = self._sub_tx_range_check,
				in_rig = InRig.SUB,
				query_state = QueryState.CONTROL,
				set_state = SetState.TX,
			),
			# Note that as long as sub isn't in scan mode,
			# we can set this when sub has control.
			'rit_xit_frequency': KenwoodNagleStateValue(self,
				echoed = True,
				query_command = 'IF',
				set_method = self._set_rit_xit_frequency,
				range_check = self._rit_xit_frequency_range_check,
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'split': KenwoodStateValue(self,
				query_command = 'IF',
				set_method = self._set_split,
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'if_shift': KenwoodStateValue(self,
				echoed = True,
				query_command = 'IS',
				set_format = 'IS {:04d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.CONTROL,
			),
			'keyer_speed': KenwoodStateValue(self,
				echoed = False,
				query_command = 'KS',
				set_format = 'KS{:03d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'keyer_buffer_full': KenwoodStateValue(self,
				query_command = 'KY',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.NONE,
			),
			'keyer_buffer': KenwoodStateValue(self,
				echoed = True,
				set_format = 'KY {:24}',
				in_rig = InRig.MAIN,
				query_state = QueryState.NONE,
				set_state = SetState.ANY,
			),
			'lock_list': KenwoodListStateValue(self, 2,
				echoed = True,
				query_command = 'LK',
				set_format = 'LK{0[0]:1d}{0[1]:1d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'recording_channel': KenwoodStateValue(self,
				echoed = True,
				query_command = 'LM',
				set_format = 'LM{:01d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'auto_lock_tuning': KenwoodStateValue(self,
				echoed = True,
				query_command = 'LT',
				set_format = 'LT{:01d}',
				range_check = self._auto_lock_tuning_range_check,
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.CONTROL,
			),
			# Memories hold the TS status for OS != 0, if
			# a memory is recalled with TS = 1 and OS != 0,
			# AR is disabled
			'main_memory_channel': KenwoodStateValue(self,
				name = 'memory_channel',
				echoed = True,
				query_command = 'MC',
				set_format = 'MC{:03d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'sub_memory_channel': KenwoodStateValue(self,
				name = 'memory_channel',
				echoed = True,
				query_command = 'MC',
				set_format = 'MC{:03d}',
				in_rig = InRig.SUB,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'main_rx_mode': KenwoodStateValue(self,
				name = 'rx_mode',
				echoed = True,
				query_command = 'MD',
				set_format = 'MD{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.NOT_TS,
				set_state = SetState.NOT_TS,
			),
			'main_tx_mode': KenwoodStateValue(self,
				name = 'tx_mode',
				echoed = True,
				query_command = 'MD',
				set_format = 'MD{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.TS,
				set_state = SetState.TS,
			),
			'sub_mode': KenwoodStateValue(self,
				name = 'mode',
				echoed = True,
				query_command = 'MD',
				set_format = 'MD{:01d}',
				in_rig = InRig.SUB,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
				range_check = self._sub_mode_range_check
			),
			'menu_ab': KenwoodStateValue(self,
				echoed = True,
				query_command = 'MF',
				set_format = 'MF{:1}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'microphone_gain': KenwoodStateValue(self,
				echoed = False,
				query_command = 'MG',
				set_format = 'MG{:03d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'monitor_level': KenwoodStateValue(self,
				echoed = False,
				query_command = 'ML',
				set_format = 'ML{:03d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			# MO; fails, and I dont' see a way to check if Sky Command is ON
			#self.skyCommandMonitor =            KenwoodStateValue(self, query_command = 'MO',  set_format = 'MO{:01d}')
			# TODO: Modernize MW (memory write)
			'memory_groups': KenwoodListStateValue(self, 10,
				echoed = False,
				query_command = 'MU',
				set_command = 'MU{0[0]:1d}{0[1]:1d}{0[2]:1d}{0[3]:1d}{0[4]:1d}{0[5]:1d}{0[6]:1d}{0[7]:1d}{0[8]:1d}{0[9]:1d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'noise_blanker': KenwoodStateValue(self,
				echoed = True,
				query_command = 'NB',
				set_format = 'NB{:01d}',
				validity_check = self._noise_blanker_valid,
				range_check = self._noise_blanker_range_check,
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.CONTROL,
			),
			'noise_blanker_level': KenwoodStateValue(self,
				echoed = False,
				query_command = 'NL',
				set_format = 'NL{:03d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.CONTROL,
			),
			'main_noise_reduction': KenwoodStateValue(self,
				name = 'noise_reduction',
				echoed = True,
				query_command = 'NR',
				set_format = 'NR{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
				range_check = self._main_noise_reduction_range_check,
			),
			'sub_noise_reduction': KenwoodStateValue(self,
				name = 'noise_reduction',
				echoed = True,
				query_command = 'NR',
				set_format = 'NR{:01d}',
				in_rig = InRig.SUB,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
				range_check = self._sub_noise_reduction_range_check
			),
			# It appears that writing NT1 *toggles* auto-notch... *sigh*
			'auto_notch': KenwoodStateValue(self,
				echoed = True,
				query_command = 'NT',
				set_format = 'NT{:01d}',
				range_check = self._auto_notch_range_check,
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.ANY,
			),
			'main_offset_frequency': KenwoodStateValue(self,
				name = 'offset_frequency',
				echoed = True,
				query_command = 'OF',
				set_format = 'OF{:09d}',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
			),
			'sub_offset_frequency': KenwoodStateValue(self,
				name = 'offset_frequency',
				echoed = True,
				query_command = 'OF',
				set_format = 'OF{:09d}',
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
			),
			# TODO: OI appears to be IF for the non-active receiver... that's CTRL
			# If AR is enabled, you cant change OS
			'main_offset_type': KenwoodStateValue(self,
				name = 'offset_type',
				echoed = True,
				query_command = 'OS',
				set_format = 'OS{:01d}',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
				range_check = self._main_offset_type_range_check,
			),
			'sub_offset_type': KenwoodStateValue(self,
				name = 'offset_type',
				echoed = True,
				query_command = 'OS',
				set_format = 'OS{:01d}',
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
				range_check = self._sub_offset_type_range_check,
			),
			# Note that this is basically per-band, not per-receiver...
			'main_preamp': KenwoodStateValue(self,
				name = 'preamp',
				echoed = True,
				query_command = 'PA',
				set_format = 'PA{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.CONTROL,
			),
			'sub_preamp': KenwoodStateValue(self,
				name = 'preamp',
				echoed = True,
				query_command = 'PA',
				set_format = 'PA{:01d}',
				in_rig = InRig.SUB,
				query_state = QueryState.ANY,
				set_state = SetState.CONTROL,
				range_check = self._sub_preamp_range_check,
			),
			'playback_channel': KenwoodStateValue(self,
				echoed = True,
				query_command = 'PB',
				set_format = 'PB{:01d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'main_output_power': KenwoodStateValue(self,
				name = 'output_power',
				echoed = False,
				query_command = 'PC',
				set_format = 'PC{:03d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'sub_output_power': KenwoodStateValue(self,
				name = 'output_power',
				echoed = False,
				query_command = 'PC',
				set_format = 'PC{:03d}',
				in_rig = InRig.SUB,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'store_as_programmable_memory': KenwoodStateValue(self,
				echoed = True,
				set_format = 'PI{:01d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.NONE,
				set_state = SetState.ANY,
			),
			'last_spot': KenwoodStateValue(self,
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.NONE,
				query_command = 'PK',
			),
			'speech_processor_level_list': KenwoodListStateValue(self, 2,
				echoed = False,
				query_command = 'PL',
				set_format = 'PL{0[0]:03d}{0[1]:03d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'programmable_memory_channel': KenwoodStateValue(self,
				echoed = True,
				query_command = 'PM',
				set_format = 'PM{:01d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'speech_processor': KenwoodStateValue(self,
				echoed = True,
				query_command = 'PR',
				set_format = 'PR{:01d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'power_on': KenwoodStateValue(self,
				echoed = True,
				query_command = 'PS',
				set_format = 'PS{:01d}',
				works_powered_off = True,
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'main_dcs_code': KenwoodStateValue(self,
				name = 'dcs_code',
				echoed = True,
				query_command = 'QC',
				set_format = 'QC{:03d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'sub_dcs_code': KenwoodStateValue(self,
				name = 'dcs_code',
				echoed = True,
				query_command = 'QC',
				set_format = 'QC{:03d}',
				in_rig = InRig.SUB,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'store_as_quick_memory': KenwoodStateValue(self,
				echoed = True,
				set_format = 'QI',
				in_rig = InRig.BOTH,
				query_state = QueryState.NONE,
				set_state = SetState.ANY,
			),
			'quick_memory_list': KenwoodListStateValue(self, 2,
				echoed = True,
				query_command = 'QR',
				set_format = 'QR{0[0]:01d}{0[1]:01d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'main_attenuator': KenwoodStateValue(self,
				name = 'attenuator',
				echoed = True,
				query_command = 'RA',
				set_format = 'RA{:02d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'sub_attenuator': KenwoodStateValue(self,
				name = 'attenuator',
				echoed = True,
				query_command = 'RA',
				set_format = 'RA{:02d}',
				in_rig = InRig.SUB,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'clear_rit': KenwoodStateValue(self,
				echoed = True,
				set_format = 'RC',
				range_check = self._clear_rit_range_check,
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.NONE,
			),
			# Technically, can be used in sub mode as long
			# as it's not scanning...
			'rit_down': KenwoodStateValue(self,
				echoed = True,
				set_format = 'RD{:05d}',
				range_check = self._rit_up_down_range_check,
				in_rig = InRig.MAIN,
				query_state = QueryState.NONE,
				set_state = SetState.CONTROL,
			),
			'scan_speed': KenwoodStateValue(self,
				echoed = True,
				query_command = 'RD',
				validity_check = self._scan_speed_up_down_valid,
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.NONE,
			),
			'scan_speed_down': KenwoodStateValue(self,
				echoed = True,
				set_format = 'RD{:05d}',
				range_check = self._scan_speed_up_down_range_check,
				in_rig = InRig.MAIN,
				query_state = QueryState.NONE,
				set_state = SetState.CONTROL,
			),
			'rf_gain': KenwoodStateValue(self,
				echoed = False,
				query_command = 'RG',
				set_format = 'RG{:03d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'noise_reduction_level': KenwoodStateValue(self,
				echoed = False,
				query_command = 'RL',
				set_format = 'RL{:02d}',
				validity_check = self._noise_reduction_level_valid,
				range_check = self._noise_reduction_level_range_check,
				in_rig = InRig.MAIN,
				query_state = QueryState.CONTROL,
				set_state = SetState.CONTROL,
			),
			'meter_type': KenwoodStateValue(self,
				echoed = True,
				query_command = 'RM',
				set_format = 'RM{:01d}',
				range_check = self._meter_value_range_check,
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'meter_value': KenwoodStateValue(self,
				query_command = 'RM',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.NONE,
			),
			'swr_meter': KenwoodStateValue(self,
				query_command = 'RM',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.NONE,
			),
			'compression_meter': KenwoodStateValue(self,
				query_command = 'RM',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.NONE,
			),
			'alc_meter': KenwoodStateValue(self,
				query_command = 'RM',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.NONE,
			),
			'rit': KenwoodStateValue(self,
				echoed = True,
				query_command = 'RT',
				set_format = 'RT{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.CONTROL,
			),
			'rit_up': KenwoodStateValue(self,
				echoed = True,
				set_format = 'RU{:05d}',
				range_check = self._rit_up_down_range_check,
				in_rig = InRig.MAIN,
				query_state = QueryState.NONE,
				set_state = SetState.CONTROL,
			),
			'scan_speed_up': KenwoodStateValue(self,
				echoed = True,
				set_format = 'RU{:05d}',
				range_check = self._scan_speed_up_down_range_check,
				in_rig = InRig.MAIN,
				query_state = QueryState.NONE,
				set_state = SetState.CONTROL,
			),
			'satellite_mode_list': KenwoodListStateValue(self, 8,
				echoed = True,
				query_command = 'SA',
				set_format = 'SA{0[0]:01d}{0[1]:01d}{0[2]:01d}{0[3]:01d}{0[4]:01d}{0[5]:01d}{0[6]:01d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'sub_receiver': KenwoodStateValue(self,
				name = 'power_on',
				echoed = True,
				query_command = 'SB',
				set_format = 'SB{:01d}',
				in_rig = InRig.SUB,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
				works_sub_off = True,
			),
			'main_scan_mode': KenwoodStateValue(self,
				name = 'scan_mode',
				echoed = True,
				query_command = 'SC',
				set_format = 'SC{:01d}',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
			),
			'sub_scan_mode': KenwoodStateValue(self,
				name = 'scan_mode',
				echoed = True,
				query_command = 'SC',
				set_format = 'SC{:01d}',
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
			),
			'cw_break_in_time_delay': KenwoodStateValue(self,
				echoed = True,
				query_command = 'SD',
				set_format = 'SD{:04d}',
				in_rig = InRig.MAIN,
				set_state = SetState.ANY,
				query_state = QueryState.ANY,
			),
			'voice_low_pass_cutoff': KenwoodStateValue(self,
				echoed = True,
				query_command = 'SH',
				set_format = 'SH{:02d}',
				validity_check = self._voice_cutoff_valid,
				range_check = self._voice_low_pass_cutoff_range_check,
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
			),
			# TODO: SI - Satellite memory name
			'voice_high_pass_cutoff': KenwoodStateValue(self,
				echoed = True,
				query_command = 'SL',
				set_format = 'SL{:02d}',
				validity_check = self._voice_cutoff_valid,
				range_check = self._voice_high_pass_cutoff_range_check,
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
			),
			'main_s_meter': KenwoodStateValue(self,
				name = 's_meter',
				query_command = 'SM0',
				in_rig = InRig.MAIN,
				set_state = SetState.NONE,
				query_state = QueryState.ANY,
			),
			'sub_s_meter': KenwoodStateValue(self,
				name = 's_meter',
				query_command = 'SM1',
				in_rig = InRig.SUB,
				set_state = SetState.NONE,
				query_state = QueryState.ANY,
			),
			'main_s_meter_level': KenwoodStateValue(self,
				name = 's_meter_level',
				query_command = 'SM2',
				in_rig = InRig.MAIN,
				set_state = SetState.NONE,
				query_state = QueryState.ANY,
			),
			'sub_s_meter_level': KenwoodStateValue(self,
				name = 's_meter_level',
				query_command = 'SM3',
				in_rig = InRig.SUB,
				set_state = SetState.NONE,
				query_state = QueryState.ANY,
			),
			'main_squelch': KenwoodStateValue(self,
				name = 'squelch',
				echoed = False,
				query_command = 'SQ0',
				set_format = 'SQ0{:03d}',
				in_rig = InRig.MAIN,
				set_state = SetState.ANY,
				query_state = QueryState.ANY,
			),
			'sub_squelch': KenwoodStateValue(self,
				name = 'squelch',
				echoed = False,
				query_command = 'SQ1',
				set_format = 'SQ1{:03d}',
				in_rig = InRig.SUB,
				set_state = SetState.ANY,
				query_state = QueryState.ANY,
			),
			# TODO?: SR1, SR2... reset transceiver
			# TODO: SS set/read Program Scan pause frequency
			# Not valid in memory or call mode...
			'main_multi_ch_frequency_steps': KenwoodStateValue(self,
				name = 'multi_ch_frequency_steps',
				echoed = True,
				query_command = 'ST',
				set_format = 'ST{:02d}',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
				validity_check = self._main_multi_ch_frequency_steps_valid,
				range_check = self._main_multi_ch_frequency_steps_range_check,
			),
			'sub_multi_ch_frequency_steps': KenwoodStateValue(self,
				name = 'multi_ch_frequency_steps',
				echoed = True,
				query_command = 'ST',
				set_format = 'ST{:02d}',
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
				validity_check = self._sub_multi_ch_frequency_steps_valid,
				range_check = self._sub_multi_ch_frequency_steps_range_check,
			),
			# TODO: SU - program scan pause frequency
			'main_memory_to_vfo': KenwoodStateValue(self,
				name = 'memory_to_vfo',
				echoed = True,
				set_format = 'SV',
				range_check = self._main_memory_to_vfo_range_check,
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.NONE,
			),
			'sub_memory_to_vfo': KenwoodStateValue(self,
				name = 'memory_to_vfo',
				echoed = True,
				set_format = 'SV',
				range_check = self._sub_memory_to_vfo_range_check,
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.NONE,
			),
			'pc_control_command_mode': KenwoodStateValue(self,
				echoed = True,
				query_command = 'TC',
				set_format = 'TC {:01d}',
				in_rig = InRig.BOTH,
				set_state = SetState.ANY,
				query_state = QueryState.ANY,
			),
			'main_send_dtmf_memory_data': KenwoodStateValue(self,
				name = 'send_dtmf_memory_data',
				echoed = True,
				set_format = 'TD{:02d}',
				in_rig = InRig.MAIN,
				set_state = SetState.TX,
				query_state = QueryState.NONE,
			),
			'sub_send_dtmf_memory_data': KenwoodStateValue(self,
				name = 'send_dtmf_memory_data',
				echoed = True,
				set_format = 'TD{:02d}',
				in_rig = InRig.SUB,
				set_state = SetState.TX,
				query_state = QueryState.NONE,
			),
			'tnc_led_list': KenwoodListStateValue(self, 3,
				query_command = 'TI',
				in_rig = InRig.BOTH,
				set_state = SetState.NONE,
				query_state = QueryState.ANY,
			),
			'main_subtone_frequency': KenwoodStateValue(self,
				name = 'subtone_frequency',
				echoed = False,
				query_command = 'TN',
				set_format = 'TN{:02d}',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
			),
			'sub_subtone_frequency': KenwoodStateValue(self,
				name = 'subtone_frequency',
				echoed = False,
				query_command = 'TN',
				set_format = 'TN{:02d}',
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
			),
			'main_tone_function': KenwoodStateValue(self,
				name = 'tone_function',
				echoed = False,
				query_command = 'TO',
				set_format = 'TO{:01d}',
				in_rig = InRig.MAIN,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
			),
			'sub_tone_function': KenwoodStateValue(self,
				name = 'tone_function',
				echoed = False,
				query_command = 'TO',
				set_format = 'TO{:01d}',
				in_rig = InRig.SUB,
				set_state = SetState.CONTROL,
				query_state = QueryState.CONTROL,
			),
			# If AR is enabled, TS[01] just disables AR and
			# does not change TS
			# If OS != 0, TS0 does nothing, and TS1 toggles
			# the TS state
			'transmit_set': KenwoodStateValue(self,
				echoed = True,
				query_command = 'TS',
				set_method = self._set_transmit_set,
				validity_check = self._transmit_set_valid,
				range_check = self._check_transmitSet,
				in_rig = InRig.MAIN,
				set_state = SetState.NOT_TS,
				query_state = QueryState.CONTROL,
			),
			'firmware_type': KenwoodStateValue(self,
				query_command = 'TY',
				in_rig = InRig.BOTH,
				set_state = SetState.NONE,
				query_state = QueryState.ANY,
			),
			# TODO: UL? (PLL Unlock)
			'main_up': KenwoodStateValue(self,
				name = 'up',
				echoed = True,
				set_format = 'UP',
				in_rig = InRig.MAIN,
				query_state = QueryState.NONE,
				set_state = SetState.CONTROL,
			),
			'sub_up': KenwoodStateValue(self,
				name = 'up',
				echoed = True,
				set_format = 'UP',
				in_rig = InRig.SUB,
				query_state = QueryState.NONE,
				set_state = SetState.CONTROL,
			),
			'vox_delay_time': KenwoodStateValue(self,
				echoed = False,
				query_command = 'VD',
				set_format = 'VD{:04d}',
				in_rig = InRig.BOTH,
				set_state = SetState.ANY,
				query_state = QueryState.ANY,
			),
			'vox_gain': KenwoodStateValue(self,
				echoed = False,
				query_command = 'VG',
				set_format = 'VG{:03d}',
				in_rig = InRig.BOTH,
				set_state = SetState.ANY,
				query_state = QueryState.ANY,
			),
			'voice1': KenwoodStateValue(self,
				echoed = True,
				set_format = 'VR0',
				in_rig = InRig.BOTH,
				set_state = SetState.ANY,
				query_state = QueryState.NONE,
			),
			'voice2': KenwoodStateValue(self,
				echoed = True,
				set_format = 'VR1',
				in_rig = InRig.BOTH,
				set_state = SetState.ANY,
				query_state = QueryState.NONE,
			),
			'vox': KenwoodStateValue(self,
				echoed = False,
				query_command = 'VX',
				set_format = 'VX{:01d}',
				in_rig = InRig.BOTH,
				set_state = SetState.ANY,
				query_state = QueryState.ANY,
			),
			'xit': KenwoodStateValue(self,
				echoed = False,
				query_command = 'XT',
				set_format = 'XT{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.CONTROL,
			),
			'beep_output_level': KenwoodStateValue(self,
				echoed = False,
				query_command = 'EX0120000',
				set_format = 'EX0120000{:01d}',
				in_rig = InRig.BOTH,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'memory_vfo_split_enabled': KenwoodStateValue(self,
				echoed = False,
				query_command = 'EX0060100',
				set_format = 'EX0060100{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'tuner_on_in_rx': KenwoodStateValue(self,
				echoed = False,
				query_command = 'EX0270000',
				set_format = 'EX0270000{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'packet_filter': KenwoodStateValue(self,
				echoed = False,
				query_command = 'EX0500100',
				set_format = 'EX0500100{:01d}',
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			# Synthetic states
			'main_rx_frequency': KenwoodStateValue(self,
				name = 'rx_frequency',
				echoed = True,
				query_method = self._main_rx_frequency_query,
				set_method = self._set_main_rx_frequency,
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'main_tx_frequency': KenwoodStateValue(self,
				name = 'tx_frequency',
				echoed = True,
				query_method = self._main_tx_frequency_query,
				set_method = self._set_main_tx_frequency,
				in_rig = InRig.MAIN,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
			'sub_frequency': KenwoodStateValue(self,
				name = 'frequency',
				echoed = True,
				query_method = self._sub_frequency_query,
				set_method = self._set_sub_frequency,
				in_rig = InRig.SUB,
				query_state = QueryState.ANY,
				set_state = SetState.ANY,
			),
		}
		# Parts of ListStates
		self._state['tuner_rx'] = KenwoodSingleStateValue(self, self._state['tuner_list'], 0,
			echoed = True,
			in_rig = InRig.MAIN,
			query_state = QueryState.ANY,
			set_state = SetState.CONTROL,
		)
		self._state['tuner_tx'] = KenwoodSingleStateValue(self, self._state['tuner_list'], 1,
			echoed = True,
			in_rig = InRig.MAIN,
			query_state = QueryState.ANY,
			set_state = SetState.CONTROL,
		)
		self._state['tuner_state'] = KenwoodSingleStateValue(self, self._state['tuner_list'], 2,
			echoed = True,
			in_rig = InRig.MAIN,
			query_state = QueryState.ANY,
			set_state = SetState.TX,
		)
		self._state['rig_lock'] = KenwoodSingleStateValue(self, self._state['lock_list'], 0,
			echoed = True,
			in_rig = InRig.MAIN,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['rc2000_lock'] = KenwoodSingleStateValue(self, self._state['lock_list'], 1,
			echoed = True,
			in_rig = InRig.MAIN,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['speech_processor_input_level'] = KenwoodSingleStateValue(self, self._state['speech_processor_level_list'], 0,
			echoed = True,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['speech_processor_output_level'] = KenwoodSingleStateValue(self, self._state['speech_processor_level_list'], 1,
			echoed = True,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['quick_memory'] = KenwoodSingleStateValue(self, self._state['quick_memory_list'], 0,
			echoed = True,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['quick_memory_channel'] = KenwoodSingleStateValue(self, self._state['quick_memory_list'], 1,
			echoed = True,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['main_busy'] = KenwoodSingleStateValue(self, self._state['busy_list'], 0,
			in_rig = InRig.MAIN,
			set_state = SetState.NONE,
			query_state = QueryState.ANY,
			name = 'busy'
		)
		self._state['sub_busy'] = KenwoodSingleStateValue(self, self._state['busy_list'], 1,
			in_rig = InRig.SUB,
			set_state = SetState.NONE,
			query_state = QueryState.ANY,
			name = 'busy'
		)
		self._state['tx_main'] = KenwoodSingleStateValue(self, self._state['control_list'], 0,
			in_rig = InRig.BOTH,
			set_state = SetState.ANY,
			query_state = QueryState.ANY,
		)
		self._state['control_main'] = KenwoodSingleStateValue(self, self._state['control_list'], 1,
			in_rig = InRig.BOTH,
			set_state = SetState.ANY,
			query_state = QueryState.ANY,
		)
		self._state['satellite_mode'] = KenwoodSingleStateValue(self, self._state['satellite_mode_list'], 0,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['satellite_channel'] = KenwoodSingleStateValue(self, self._state['satellite_mode_list'], 1,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['satellite_main_up_sub_down'] = KenwoodSingleStateValue(self, self._state['satellite_mode_list'], 2,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['satellite_control_main'] = KenwoodSingleStateValue(self, self._state['satellite_mode_list'], 3,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['satellite_trace'] = KenwoodSingleStateValue(self, self._state['satellite_mode_list'], 4,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['satellite_trace_reverse'] = KenwoodSingleStateValue(self, self._state['satellite_mode_list'], 5,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['satellite_multi_knob_vfo'] = KenwoodSingleStateValue(self, self._state['satellite_mode_list'], 6,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['satellite_channel_name'] = KenwoodSingleStateValue(self, self._state['satellite_mode_list'], 7,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['tnc_96k_led'] = KenwoodSingleStateValue(self, self._state['tnc_led_list'], 0,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['tnc_sta_led'] = KenwoodSingleStateValue(self, self._state['tnc_led_list'], 1,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)
		self._state['tnc_con_led'] = KenwoodSingleStateValue(self, self._state['tnc_led_list'], 2,
			in_rig = InRig.BOTH,
			query_state = QueryState.ANY,
			set_state = SetState.ANY,
		)

		# Derived bools
		self._state['antenna1'] = KenwoodDerivedBoolValue(self, self._state['antenna_connector'], 1)
		self._state['antenna2'] = KenwoodDerivedBoolValue(self, self._state['antenna_connector'], 2)
		self._state['auto_beat_canceller'] = KenwoodDerivedBoolValue(self, self._state['beat_canceller'], BeatCanceller.AUTO, false_value = BeatCanceller.OFF)
		self._state['manual_beat_canceller'] = KenwoodDerivedBoolValue(self, self._state['beat_canceller'], BeatCanceller.MANUAL, false_value = BeatCanceller.OFF)
		self._state['main_rx_vfoa'] = KenwoodDerivedBoolValue(self,
			self._state['main_rx_tuning_mode'],
			tuningMode.VFOA,
			name = 'rx_vfoa',
		)
		self._state['main_rx_vfob'] = KenwoodDerivedBoolValue(self,
			self._state['main_rx_tuning_mode'],
			tuningMode.VFOB,
			name = 'rx_vfob',
		)
		self._state['main_rx_memory'] = KenwoodDerivedBoolValue(self,
			self._state['main_rx_tuning_mode'],
			tuningMode.MEMORY,
			name = 'rx_memory',
		)
		self._state['main_rx_call'] = KenwoodDerivedBoolValue(self,
			self._state['main_rx_tuning_mode'],
			tuningMode.CALL,
			name = 'rx_call',
		)
		self._state['main_tx_vfoa'] = KenwoodDerivedBoolValue(self,
			self._state['main_tx_tuning_mode'],
			tuningMode.VFOA,
			name = 'tx_vfoa',
		)
		self._state['main_tx_vfob'] = KenwoodDerivedBoolValue(self,
			self._state['main_tx_tuning_mode'],
			tuningMode.VFOB,
			name = 'tx_vfob',
		)
		self._state['main_tx_memory'] = KenwoodDerivedBoolValue(self,
			self._state['main_tx_tuning_mode'],
			tuningMode.MEMORY,
			name = 'tx_memory',
		)
		self._state['main_tx_call'] = KenwoodDerivedBoolValue(self,
			self._state['main_tx_tuning_mode'],
			tuningMode.CALL,
			name = 'tx_call',
		)
		self._state['sub_vfo'] = KenwoodDerivedBoolValue(self,
			self._state['sub_tuning_mode'],
			tuningMode.VFOA,
			name = 'vfo',
		)
		self._state['sub_memory'] = KenwoodDerivedBoolValue(self,
			self._state['sub_tuning_mode'],
			tuningMode.MEMORY,
			name = 'memory',
		)
		self._state['sub_call'] = KenwoodDerivedBoolValue(self,
			self._state['sub_tuning_mode'],
			tuningMode.CALL,
			name = 'call',
		)
		self._state['lock_frequency'] = KenwoodDerivedBoolValue(self, self._state['rig_lock'], rigLock.F_LOCK)
		self._state['lock_rig'] = KenwoodDerivedBoolValue(self, self._state['rig_lock'], rigLock.A_LOCK)
		self._state['lock_rc2000'] = KenwoodDerivedBoolValue(self, self._state['rig_lock'], True)
		self._state['main_noise_reduction1'] = KenwoodDerivedBoolValue(self,
			self._state['main_noise_reduction'],
			1,
			false_value = 0,
			name = 'noise_reduction1',
		)
		self._state['main_noise_reduction2'] = KenwoodDerivedBoolValue(self,
			self._state['main_noise_reduction'],
			2,
			false_value = 0,
			name = 'noise_reduction2',
		)
		self._state['sub_noise_reduction1'] = KenwoodDerivedBoolValue(self,
			self._state['sub_noise_reduction'],
			1,
			false_value = 0,
			name = 'noise_reduction1',
		)
		self._state['start_tune'] = KenwoodDerivedBoolValue(self, self._state['tuner_state'], tunerState.ACTIVE, false_value = tunerState.STOPPED)

		# Now plug the names in...
		for a, p in self._state.items():
			if isinstance(p, StateValue):
				if p.name is None:
					p.name = a

		# Now build the two sub-receivers as Rig instances
		main = KenwoodHFSubRig()
		sub = KenwoodHFSubRig()
		for a, p in self._state.items():
			if isinstance(p, StateValue):
				if p.name[0:5] == 'main_':
					raise Exception('Property '+a+' name starts with "main_"')
				if p.name[0:4] == 'sub_':
					raise Exception('Property '+a+' name starts with "sub_"')
				if p._in_rig == InRig.BOTH:
					if p.name in main._state:
						raise Exception('Duplicate main name '+p.name+' ('+a+')')
					if p.name in sub._state:
						raise Exception('Duplicate sub name '+p.name+' ('+a+')')
					main.add_property(p.name, p)
					sub.add_property(p.name, p)
				elif p._in_rig == InRig.MAIN:
					if p.name in main._state:
						raise Exception('Duplicate main name '+p.name+' ('+a+')')
					main.add_property(p.name, p)
				elif p._in_rig == InRig.SUB:
					if p.name in sub._state:
						raise Exception('Duplicate sub name '+p.name+' ('+a+')')
					sub.add_property(p.name, p)

		# Aliases for standard rig interface
		self._state['rx_frequency'] = self._state['main_rx_frequency']
		self._state['tx_frequency'] = self._state['main_tx_frequency']
		self._state['rx_mode'] = self._state['main_rx_mode']
		self._state['tx_mode'] = self._state['main_tx_mode']
		self._state['tx'] = self._state['main_tx']
		sub._state['rx_frequency'] = sub._state['frequency']
		sub._state['tx_frequency'] = sub._state['frequency']
		sub._state['rx_mode'] = sub._state['mode']
		sub._state['tx_mode'] = sub._state['mode']
		sub.add_property('split', KenwoodStateValue(self,
			name='split',
			in_rig = InRig.SUB,
			query_state = QueryState.NONE,
			set_state = SetState.NONE,
		))

		# And place the memories in both...
		self.memories = MemoryArray(self)
		main.memories = self.memories
		sub.memories = self.memories
		self.rigs = (main, sub)

		if self.power_on:
			if self.auto_information != 2:
				self.auto_information = 2
		self._fill_cache()

	def _readThread(self):
		while not self._terminate:
			cmdline = self._serial.read()
			if cmdline is not None:
				m = match(b"^.*?([\?A-Z]{1,2})([\x20-\x3a\x3c-\x7f\xff]*?);$", cmdline)
				if m:
					if self._aliveWait is not None:
						self._aliveWait.set()
					cmd = m.group(1)
					# \xff is in PK command...
					args = m.group(2).replace(b'\xff', b' ').decode('ascii')
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
		if get_ident() == self._readThread.ident:
			raise Exception('_query from readThread')
		if self._filling_cache:
			self._fill_cache_wait()
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

	def _set(self, state, value):
		if value is None:
			raise Exception('Attempt to set '+state.name+' to None')
		self._serial.writeQueue.put({
			'msgType': 'set',
			'stateValue': state,
			'value': value,
		})

	def terminate(self):
		if hasattr(self, 'auto_information'):
			self.auto_information = 0
		if hasattr(self, '_terminate'):
			self._terminate = True
		if hasattr(self, 'rigs'):
			if hasattr(self.rigs[0], '_terminate'):
				self.rigs[0]._terminate = True
			if hasattr(self.rigs[1], '_terminate'):
				self.rigs[1]._terminate = True
		self._serial.terminate()
		if hasattr(self, 'readThread'):
			self._readThread.join()

	def _fill_cache_wait(self):
		self._fill_cache_state['event'].wait()
		self._filling_cache = False

	def _fill_cache_beep_cb(self, prop, *args):
		self._fill_cache_state['event'].set()
		self._state['beep_output_level'].remove_set_callback(self._fill_cache_beep_cb)

	def _fill_cache_cb(self, prop, *args):
		nxt = None
		if prop is not None:
			prop.remove_set_callback(self._fill_cache_cb)
		while len(self._fill_cache_state['todo']) > 0:
			nxt = self._fill_cache_state['todo'].pop(0)
			if not nxt[0]._valid(False):
				self._fill_cache_state['matched_count'] += 1
				nxt = None
				continue
			if nxt[0]._cached is not None and not isinstance(nxt[0], KenwoodListStateValue):
				self._fill_cache_state['matched_count'] += 1
				nxt = None
				continue
			break
		if nxt is not None:
			nxt[0].add_set_callback(nxt[1])
			self._send_query(nxt[0])

		if prop is not None:
			if prop.name == 'beep_output_level':
				self._fill_cache_state['beep'] = prop._cached
				self._set(prop, 0)
			self._fill_cache_state['matched_count'] += 1
			if self._fill_cache_state['matched_count'] == self._fill_cache_state['target_count']:
				for cb in self._fill_cache_state['call_after']:
					cb[0]()
				if self._fill_cache_state['beep'] is not None:
					self._state['beep_output_level'].add_set_callback(self._fill_cache_beep_cb)
					self._set(self._state['beep_output_level'], self._fill_cache_state['beep'])
				else:
					self._fill_cache_state['event'].set()

	def _fill_cache(self):
		if self._state['power_on']._cached == False:
			return
		if self._filling_cache:
			return
		self._filling_cache = True
		done = {}
		self._fill_cache_state['todo'] = []
		self._fill_cache_state['call_after'] = ()
		self._fill_cache_state['target_count'] = 0
		self._fill_cache_state['matched_count'] = 0
		self._fill_cache_state['event'] = Event()
		self._fill_cache_state['beep'] = None
		# Perform queries in this order:
		# 0) FA, FB, FC
		# 1) Simple string queries without validators
		# 2) Simple string queries with validators
		# 3) Method queries
		for a, p in self._state.items():
			if isinstance(p, StateValue):
				if p._query_command is None:
					if p._query_method is not None:
						self._fill_cache_state['call_after'] += ((p._query_method,a),)
				else:
					if not p._query_command in done:
						done[p._query_command] = True
						self._fill_cache_state['target_count'] += 1
						if p._validity_check is not None:
							self._fill_cache_state['todo'].append((p, self._fill_cache_cb,a))
						else:
							self._fill_cache_state['todo'].insert(0, (p, self._fill_cache_cb,a))
		# We need control_main, main_rx_tuning_mode, and main_tx_tuning_mode first
		self._fill_cache_state['target_count'] += 5
		self._fill_cache_state['todo'].insert(0, (self._state['main_tx_tuning_mode'], self._fill_cache_cb,'main_tx_tuning_mode'))
		self._fill_cache_state['todo'].insert(0, (self._state['main_rx_tuning_mode'], self._fill_cache_cb,'main_rx_tuning_mode'))
		self._fill_cache_state['todo'].insert(0, (self._state['transmit_set'], self._fill_cache_cb,'transmit_set'))
		self._fill_cache_state['todo'].insert(0, (self._state['control_list'], self._fill_cache_cb,'control_list'))
		self._fill_cache_state['todo'].insert(0, (self._state['beep_output_level'], self._fill_cache_cb,'beep_output_level'))
		self._fill_cache_cb(None, None)
		if get_ident() != self._readThread.ident:
			self._fill_cache_wait()
		# TODO: switch to other receiver to get mode/frequency

	def _kill_cache(self):
		self._killing_cache = True
		for a, p in self._state.items():
			if isinstance(p, StateValue):
				if p._query_command in ('PS', 'ID'):
					continue
				p._cached = None
		self._killing_cache = False

	# Query methods return a string to send to the rig
	def _main_rx_frequency_query(self):
		if self._state['main_rx_tuning_mode']._cached == tuningMode.VFOA:
			self._state['main_rx_frequency']._cached = self._state['vfoa_frequency']._cached
		elif self._state['main_rx_tuning_mode']._cached == tuningMode.VFOB:
			self._state['main_rx_frequency']._cached = self._state['vfob_frequency']._cached
		elif self._state['main_rx_tuning_mode']._cached == tuningMode.MEMORY:
			if self._state['main_memory_channel']._cached is not None:
				if self.memories.memories[self._state['main_memory_channel']._cached]._cached is not None:
					self._state['main_rx_frequency']._cached = self.memories.memories[self._state['main_memory_channel']._cached]._cached['Frequency']
		elif self._state['main_rx_tuning_mode']._cached == tuningMode.CALL:
			if self.memories.memories[300]._cached is not None:
				self._state['main_rx_frequency']._cached = self.memories.memories[300]._cached['Frequency']
		return ''

	def _main_tx_frequency_query(self):
		if self._state['main_tx_tuning_mode']._cached == tuningMode.VFOA:
			self._state['main_tx_frequency']._cached = self._state['vfoa_frequency']._cached
		elif self._state['main_tx_tuning_mode']._cached == tuningMode.VFOB:
			self._state['main_tx_frequency']._cached = self._state['vfob_frequency']._cached
		elif self._state['main_tx_tuning_mode']._cached == tuningMode.MEMORY:
			if self._state['main_memory_channel']._cached is not None:
				if self.memories.memories[self._state['main_memory_channel']._cached]._cached is not None:
					self._state['main_tx_frequency']._cached = self.memories.memories[self._state['main_memory_channel']._cached]._cached['Frequency']
		elif self._state['main_tx_tuning_mode']._cached == tuningMode.CALL:
			if self.memories.memories[300]._cached is not None:
				self._state['main_tx_frequency']._cached = self.memories.memories[300]._cached['Frequency']
		return ''

	def _sub_frequency_query(self):
		if self._state['sub_tuning_mode']._cached == tuningMode.VFOA:
			self._state['sub_frequency']._cached = self._state['sub_vfo_frequency']._cached
		elif self._state['sub_tuning_mode']._cached == tuningMode.VFOB:
			self._state['sub_frequency']._cached = self._state['sub_vfo_frequency']._cached
		elif self._state['sub_tuning_mode']._cached == tuningMode.MEMORY:
			if self._state['sub_memory_channel']._cached is not None:
				if self.memories.memories[self._state['sub_memory_channel']._cached]._cached is not None:
					self._state['sub_frequency']._cached = self.memories.memories[self._state['sub_memory_channel']._cached]._cached['Frequency']
				else:
					self._state['sub_frequency']._cached = None
		elif self._state['sub_tuning_mode']._cached == tuningMode.CALL:
			if self.memories.memories[300]._cached is not None:
				self._state['sub_frequency']._cached = self.memories.memories[300]._cached['Frequency']
			else:
				self._state['sub_frequency']._cached = None
		return ''

	# Range check methods return True or False
	def _tuner_list_range_check(self, value):
		# Fail if we're trying to set it to the current value
		# Unless we're changing the tuning state and it's
		# currently enabled
		#
		# Unfortunately, for an external tuner, we can only turn
		# the tuner on when we're also starting tuning...
		if value[1] == self._state['tuner_list']._cached[1]:
			# If we're setting anything except TX enabled,
			# TX enabled must be set as well
			if value[2] != tunerState.ACTIVE:
				if value[1] == False:
					if value[0] or value[2]:
						return False
				if value[2] == self._state['tuner_list']._cached[2]:
					return False
		# Fail if main TX is VHF+
		# With exernal tuners, this should be over 30MHz... :(
		if self._state['main_tx_frequency']._cached > 60000000:
			return False
		# Tuner will not respond to commands with TX outside of band
		if self._check_frequency(self._state['main_tx_frequency']._cached, self.tx_ranges_k) is None:
			return False
		return True

	def _antenna_connector_range_check(self, value):
		# For VHF+, we can't set it.
		if self._state['main_tx_frequency']._cached > 60000000:
			return False
		# For HF, it must be 1 or 2
		if value < 1 or value > 2:
			return False
		return True

	def _main_auto_simplex_check_range_check(self, value):
		if value == self._state['main_auto_simplex_check']._cached:
			return False
		if self._state['main_offset_type']._cached == offset.NONE:
			return False
		return True

	def _sub_auto_simplex_check_range_check(self, value):
		if value == self._state['sub_auto_simplex_check']._cached:
			return False
		if self._state['sub_offset_type']._cached == offset.NONE:
			return False
		return True

	def _beat_canceller_range_check(self, value):
		# Auto beat cancel can only be enabled on some modes
		if value == BeatCanceller.AUTO and (not self._state['main_rx_mode']._cached in (mode.USB, mode.LSB, mode.AM)):
			return False
		return True

	def _auto_zero_beat_range_check(self, value):
		# Only in CW and only when filter is < 1kHz wide
		if self._state['main_rx_mode']._cached not in (mode.CW, mode.CW_REVERSED):
			return False
		if self._state['filter_width']._cached >= 1000:
			return False
		return True

	def _packet_cluster_tune_range_check(self, value):
		# Only when sub is enabled and main is VFOA and/or VFOB
		if self._state['sub_receiver']._cached == False:
			return False
		if self._state['main_rx_tuning_mode']._cached not in (tuningMode.VFOA, tuningMode.VFOB):
			return False
		if self._state['main_tx_tuning_mode']._cached not in (tuningMode.VFOA, tuningMode.VFOB):
			return False
		return True

	def _agc_constant_range_check(self, value):
		if self._state['main_rx_mode']._cached == mode.FM:
			return False
		return True

	def _main_tx_range_check(self, value):
		if value:
			if self._state['sub_tx']._cached:
				return False
		return True

	def _sub_tx_range_check(self, value):
		if value:
			if self._state['main_tx']._cached:
				return False
		return True

	def _rit_xit_frequency_range_check(self, value):
		if value == self._state['rit_xit_frequency']._cached:
			return False
		if self._state['main_scan_mode']._cached != scanMode.OFF:
			return False
		return True

	def _auto_lock_tuning_range_check(self, value):
		if self._state['main_rx_frequency']._cached >= 1200000000:
			if self._state['main_rx_mode']._cached == mode.FM:
				return True
		return false

	def _main_noise_reduction_range_check(self, value):
		if value == noiseReduction.OFF:
			return True
		if value == noiseReduction.NR2:
			if not self._state['main_rx_mode']._cached in (mode.AM, mode.CW, mode.CW_REVERSED, mode.FSK, mode.FSK_REVERSED, mode.LSB, mode.USB):
				return False
		return True

	def _sub_noise_reduction_range_check(self, value):
		if value == noiseReduction.OFF:
			return True
		if value == noiseReduction.NR2:
			return False
		return True

	def _auto_notch_range_check(self, value):
		if self._state['main_rx_mode']._cached not in (mode.USB, mode.LSB):
			return False
		return True

	def _main_offset_type_range_check(self, value):
		if self._state['main_rx_mode']._cached != mode.FM:
			return False
		if self._state['main_auto_simplex_check']._cached:
			return False
		return True

	def _sub_offset_type_range_check(self, value):
		if self._state['sub_mode']._cached != mode.FM:
			return False
		if self._state['sub_auto_simplex_check']._cached:
			return False
		return True

	def _clear_rit_range_check(self, value):
		return self._state['rit']._cached or self._state['xit']._cached

	def _meter_value_range_check(self, value):
		if meter(value) == meter.COMPRESSION and not self._state['speech_processor']._cached:
			return False
		if meter(value) == meter.SWR:
			if not self._state['tx_main']._cached:
				return False
			if self._state['main_tx_frequency']._cached > 60000000:
				return False
		return True

	def _main_tx_tuning_mode_range_check(self, value):
		if value == self._state['main_tx_tuning_mode']._cached:
			return False
		return True

	def _main_rx_tuning_mode_range_check(self, value):
		if value == self._state['main_rx_tuning_mode']._cached:
			if self._state['main_rx_tuning_mode']._cached == self._state['main_tx_tuning_mode']._cached:
				return False
		return True

	def _sub_rx_tuning_mode_range_check(self, value):
		if value == self._state['sub_tuning_mode']._cached:
			return False
		return True

	def _sub_mode_range_check(self, value):
		return value in (mode.AM, mode.FM)

	def _sub_preamp_range_check(self, value):
		if value == False:
			return True
		sf = self._state['sub_frequency']._cached
		if sf >= 118000000 and sf <= 135999999:
			return False
		if sf >= 155000000 and sf <= 173999999:
			return False
		if sf >= 220000000 and sf <= 229999999:
			return False

	def _rit_up_down_range_check(self, value):
		return self._state['main_scan_mode']._cached == scanMode.OFF

	def _scan_speed_up_down_range_check(self, value):
		return self._state['main_scan_mode']._cached != scanMode.OFF

	def _filter_width_range_check(self, value):
		if self._state['main_rx_mode']._cached in (mode.AM, mode.FM):
			if value < 0 or value > 1:
				return False
		elif self._state['main_rx_mode']._cached in (mode.FSK, mode.FSK_REVERSED):
			if value not in (250, 500, 1000, 1500):
				return False
		elif self._state['main_rx_mode']._cached in (mode.CW, mode.CW_REVERSED):
			if value not in (50, 80, 100, 150, 200, 300, 400, 500, 600, 1000, 2000):
				return False
		else:
			return False
		# Don't query filter width when tuning
		if self._state['start_tune']._cached:
			return False
		return True

	def _noise_blanker_range_check(self, value):
		if self._state['main_rx_mode']._cached == mode.FM:
			return False
		elif value < 0 or value > 1:
			return False
		return True

	def _voice_low_pass_cutoff_range_check(self, value):
		if self._state['main_rx_mode']._cached in (mode.FM, mode.LSB, mode.USB):
			if self._state['packet_filter']._cached:
				if value < 0 or value > 3:
					return False
			elif value < 0 or value > 11:
				return False
		elif self._state['main_rx_mode']._cached in (mode.AM,):
			if value < 0 or value > 3:
				return False
		else:
			return False
		return True

	def _voice_high_pass_cutoff_range_check(self, value):
		if self._state['main_rx_mode']._cached in (mode.FM, mode.LSB, mode.USB):
			if self._state['packet_filter']._cached:
				if value < 0 or value > 1:
					return False
			elif value < 0 or value > 11:
				return False
		elif self._state['main_rx_mode']._cached in (mode.AM,):
			if value < 0 or value > 3:
				return False
		else:
			return False
		return True

	def _main_multi_ch_frequency_steps_range_check(self, value):
		if self._state['main_rx_tuning_mode'] in (tuningMode.CALL, tuningMode.MEMORY):
			return False
		elif self._state['main_rx_mode']._cached in (mode.USB, mode.LSB, mode.CW, mode.CW_REVERSED, mode.FSK, mode.FSK_REVERSED):
			if value < 0 or value > 3:
				return False
		elif self._state['main_rx_mode']._cached in (mode.AM, mode.FM):
			if value < 0 or value > 9:
				return False
		else:
			return False
		return True

	def _sub_multi_ch_frequency_steps_range_check(self, value):
		if self._state['sub_tuning_mode'] in (tuningMode.CALL, tuningMode.MEMORY):
			return False
		elif self._state['sub_mode']._cached in (mode.USB, mode.LSB, mode.CW, mode.CW_REVERSED, mode.FSK, mode.FSK_REVERSED):
			if value < 0 or value > 3:
				return False
		elif self._state['sub_mode']._cached in (mode.AM, mode.FM):
			if value < 0 or value > 9:
				return False
		else:
			return False
		return True

	def _main_memory_to_vfo_range_check(self, value):
		return self._state['main_rx_tuning_mode']._cached == tuningMode.MEMORY

	def _sub_memory_to_vfo_range_check(self, value):
		return self._state['sub_tuning_mode']._cached == tuningMode.MEMORY

	def _noise_reduction_level_range_check(self, value):
		if self._state['main_noise_reduction']._cached == noiseReduction.OFF:
			return False
		if value < 0 or value > 9:
			return False
		return True

	# Set methods return a string to send to the rig
	def _set_tx(self, value):
		if value:
			return 'TX'
		else:
			return 'RX'

	def _set_rit_xit_frequency(self, value):
		diff = int(value - self._state['rit_xit_frequency']._cached)
		if diff < 0:
			return 'RD{:05d}'.format(int(abs(diff)))
		else:
			return 'RU{:05d}'.format(int(diff))

	def _set_split(self, value):
		ret = ''
		vfo = self._state['main_rx_tuning_mode']._cached
		if not vfo in (tuningMode.VFOA, tuningMode.VFOB):
			ret += self._state['main_rx_tuning_mode']._set_string(tuningMode.VFOA)
			vfo = tuningMode.VFOA
		if value:
			if vfo == tuningMode.VFOA:
				ret += self._state['main_tx_tuning_mode']._set_string(tuningMode.VFOB)
			else:
				ret += self._state['main_tx_tuning_mode']._set_string(tuningMode.VFOA)
		else:
			if vfo == tuningMode.VFOB:
				ret += self._state['main_tx_tuning_mode']._set_string(tuningMode.VFOA)
			else:
				ret += self._state['main_tx_tuning_mode']._set_string(tuningMode.VFOB)
		ret += ';FR;FT;FA;FB'
		return ret

	def _set_main_rx_frequency(self, value):
		if self._state['main_rx_tuning_mode']._cached == tuningMode.VFOA:
			return self._state['vfoa_frequency']._set_string(value)
		elif self._state['main_rx_tuning_mode']._cached == tuningMode.VFOB:
			return self._state['vfob_frequency']._set_string(value)
		return ''

	def _set_main_tx_frequency(self, value):
		if self._state['main_tx_tuning_mode']._cached == tuningMode.VFOA:
			return self._state['vfoa_frequency']._set_string(value)
		elif self._state['main_tx_tuning_mode']._cached == tuningMode.VFOB:
			return self._state['vfob_frequency']._set_string(value)
		return ''

	def _set_sub_frequency(self, value):
		if self._state['sub_tuning_mode']._cached == tuningMode.VFOA:
			return self._state['sub_vfo_frequency']._set_string(value)
		elif self._state['sub_tuning_mode']._cached == tuningMode.VFOB:
			return self._state['sub_vfo_frequency']._set_string(value)
		return ''

	def _set_transmit_set(self, value):
		if value == self._state['transmit_set']._cached:
			return ''
		if self._transmit_set_valid():
			return 'TS{:1d}'.format(value)
		self._state['transmit_set']._cached = self._state['transmit_set']._cached

	def _set_tuner_list(self, value):
		if value[2] == tunerState.ACTIVE:
			value[1] = True
		return 'AC{0[0]:1d}{0[1]:1d}{0[2]:1d}'.format(value)

	# Update methods return a string to send to the rig
	# Validity check methods return True or False
	def _noise_reduction_level_valid(self):
		return self._state['main_noise_reduction']._cached != noiseReduction.OFF

	def _noise_blanker_valid(self):
		return self._state['main_rx_mode']._cached != mode.FM

	def _voice_cutoff_valid(self):
		return self._state['main_rx_mode']._cached in (mode.AM, mode.FM, mode.LSB, mode.USB)

	def _main_multi_ch_frequency_steps_valid(self):
		if self._state['main_rx_tuning_mode'] in (tuningMode.CALL, tuningMode.MEMORY):
			return False
		return True

	def _sub_multi_ch_frequency_steps_valid(self):
		if self._state['sub_tuning_mode'] in (tuningMode.CALL, tuningMode.MEMORY):
			return False
		return True

	def _filter_width_valid(self):
		if self._state['main_rx_mode']._cached in (mode.LSB, mode.USB,):
			return False
		# Don't query filter width when tuning
		if self._state['start_tune']._cached:
			return False
		return True

	def _check_frequency(self, value, band_list):
		for b in band_list:
			if value >= band_list[b][0] and value <= band_list[b][1]:
				return b
		return None

	def _checkMainFrequencyValid(self, value):
		return self._check_frequency(value, self.rx_ranges_k_main) is not None

	def _checkSubFrequencyValid(self, value):
		return self._check_frequency(value, self.rx_ranges_k_sub) is not None

	def _check_transmitSet(self, value):
		if not value:
			return True
		if self._state['split']._cached:
			return True
		return False

	def _transmit_set_valid(self):
		# TODO: This is sketchy and here to avoid issues with transmitSet
		if self._state['main_tx_tuning_mode']._cached is None or self._state['main_rx_tuning_mode']._cached is None:
			return False
		if self._state['main_tx_tuning_mode']._cached != self._state['main_rx_tuning_mode']._cached:
			return True
		return False

	def _scan_speed_up_down_valid(self):
		return self._scan_speed_up_down_range_check(None)

	def _update_AC(self, args):
		split = self.parse('1d1d1d', args)
		self._state['tuner_list']._cached = [bool(split[0]), bool(split[1]), tunerState(split[2])]

	def _update_AG(self, args):
		split = self.parse('1d3d', args)
		if split[0] == 0:
			self._state['main_audio_level']._cached = split[1]
		else:
			self._state['sub_audio_level']._cached = split[1]

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
		if self._state['control_main']._cached:
			self._state['antenna_connector']._cached = None if split[0] == 0 else split[0]

	def _update_AR(self, args):
		split = self.parse('1d1d1d', args)
		aso = bool(split[1])
		if split[0] == 0:
			self._state['main_auto_simplex_check']._cached = aso
			self._state['main_simplex_possible']._cached = bool(split[2]) if aso else False
		else:
			self._state['sub_auto_simplex_check']._cached = aso
			self._state['sub_simplex_possible']._cached = bool(split[2]) if aso else False

	def _update_BC(self, args):
		split = self.parse('1d', args)
		self._state['beat_canceller']._cached = BeatCanceller(split[0])

	def _update_BP(self, args):
		split = self.parse('3d', args)
		self._state['manual_beat_canceller_frequency']._cached = split[0]

	def _update_BY(self, args):
		split = self.parse('1d1d', args)
		self._state['busy_list']._cached = [bool(split[0]), bool(split[1])]

	def _update_CA(self, args):
		split = self.parse('1d', args)
		self._state['auto_zero_beat']._cached = bool(split[0])

	def _update_CG(self, args):
		split = self.parse('3d', args)
		self._state['carrier_gain']._cached = split[0]

	def _update_CM(self, args):
		split = self.parse('1d', args)
		self._state['packet_cluster_tune']._cached = bool(split[0])

	def _update_CN(self, args):
		split = self.parse('2d', args)
		if self._state['control_main']._cached:
			self._state['main_ctcss_tone']._cached = CTCSStone(split[0])
		else:
			self._state['sub_ctcss_tone']._cached = CTCSStone(split[0])

	def _update_CT(self, args):
		split = self.parse('1d', args)
		if self._state['control_main']._cached:
			self._state['main_ctcss']._cached = bool(split[0])
		else:
			self._state['sub_ctcss']._cached = bool(split[0])

	def _update_DC(self, args):
		split = self.parse('1d1d', args)
		self._state['control_list']._cached = [not bool(split[0]), not bool(split[1])]

	def _update_DQ(self, args):
		split = self.parse('1d', args)
		if self._state['control_main']._cached:
			self._state['main_dcs']._cached = bool(split[0])
		else:
			self._state['sub_dcs']._cached = bool(split[0])

	def _update_EX(self, args):
		split = self.parse('3d2d1d1d0l', args)
		if split[0] == 27:
			self._state['tuner_on_in_rx']._cached = bool(int(split[4]))
		elif split[0] == 12:
			self._state['beep_output_level']._cached = int(split[4])
		elif split[0] == 6:
			self._state['memory_vfo_split_enabled']._cached = bool(int(split[4]))
		elif split[0] == 50 and split[1] == 1:
			self._state['packet_filter']._cached = bool(int(split[4]))
		else:
			print('Unhandled EX menu {:03d}'.format(split[0]), file=stderr)

	def _update_FA(self, args):
		split = self.parse('11d', args)
		self._state['vfoa_frequency']._cached = split[0]
		self._main_rx_frequency_query()
		self._main_tx_frequency_query()

	def _update_FB(self, args):
		split = self.parse('11d', args)
		self._state['vfob_frequency']._cached = split[0]
		self._main_rx_frequency_query()
		self._main_tx_frequency_query()

	def _update_FC(self, args):
		split = self.parse('11d', args)
		self._state['sub_vfo_frequency']._cached = split[0]
		self._sub_frequency_query()

	def _update_FD(self, args):
		split = self.parse('8x', args)
		self._state['filter_display_pattern']._cached = int2ba(split[0], 32)

	# TODO: Toggle tuningMode when transmitting?  Check the IF command...
	# NOTE: FR changes FT **and** doesn't notify that FT was changed.
	#       FT doesn't change FR unless the sub receiver is the TX
	def _update_FR(self, args):
		split = self.parse('1d', args)
		tuning_mode = tuningMode(split[0])
		if self._state['control_main']._cached:
			self._state['main_rx_tuning_mode']._cached = tuning_mode
			self._state['main_tx_tuning_mode']._cached = tuning_mode
			self._main_rx_frequency_query()
			self._main_tx_frequency_query()
		else:
			self._state['sub_tuning_mode']._cached = tuning_mode
			self._sub_frequency_query()

	def _update_FS(self, args):
		split = self.parse('1d', args)
		if self._state['control_main']._cached:
			self._state['main_fine_tuning']._cached = bool(split[0])
		else:
			self._state['sub_fine_tuning']._cached = bool(split[0])

	def _update_FT(self, args):
		split = self.parse('1d', args)
		tuning_mode = tuningMode(split[0])
		if self._state['control_main']._cached:
			self._state['main_tx_tuning_mode']._cached = tuning_mode
			self._main_tx_frequency_query()
		else:
			self._state['sub_tuning_mode']._cached = tuning_mode
			self._sub_frequency_query()

	def _update_FW(self, args):
		split = self.parse('4d', args)
		self._state['filter_width']._cached = split[0]

	def _update_GT(self, args):
		if args == '   ':
			self._state['agc_constant']._cached = None
		else:
			split = self.parse('3d', args)
			self._state['agc_constant']._cached = split[0]

	def _update_ID(self, args):
		self._state['id']._cached = self.parse('3d', args)[0]

	def _update_IF(self, args):
		# TODO: Synchronize these with the single-value options
		# NOTE: This is the control receiver, not the TX one even if we're transmitting
		# NOTE: Combined P6 and P7 since they're effectively one number on the TS-2000
		#'00003810000' '    ' ' 00000' '0' '0' '101' '0' '1' '0' '0' '0' '0' '08' '0'
		#'00003810000' '    ' ' 00000' '0' '0' '101' '0' '1' '0' '0' '0' '0' '08' '0'
		#     3810000,     0,       1,  0,  1,    0,  1,  0,  0,  0,  0,  0,   8,  0
		split = self.parse('11d4d6d1d1d3d1d1d1d1d1d1d2d1d', args)

		# [0]  Frequency*
		# [1]  Step size
		# [2]  RIT/XIT
		# [3]  RIT
		# [4]  XIT
		# [5]  Channel
		# [6]  TX
		# [7]  Mode
		# [8]  Tuning Mode
		# [9]  Scanning
		# [10] Split
		# [11] Tone mode
		# [12] Tone
		# [13] Shift type
		if self._state['control_main']._cached:
			self._state['rit_xit_frequency'].lock.acquire()
			if self._state['rit_xit_frequency']._pending is not None:
				if self._state['rit_xit_frequency']._pending['value'] is not None:
					self._state['rit_xit_frequency']._queued = self._state['rit_xit_frequency']._pending
					self._set(self._state['rit_xit_frequency'], self._state['rit_xit_frequency']._queued['value'])
				self._state['rit_xit_frequency']._pending = None
			self._state['rit_xit_frequency'].lock.release()
			# This is not the enum from ST (sigh)
			#if split[1] is not None:
			#	self._state['main_multi_ch_frequency_steps']._cached = split[1]
			self._state['rit_xit_frequency']._cached = split[2]
			self._state['rit']._cached = bool(split[3])
			self._state['xit']._cached = bool(split[4])
			self._state['main_memory_channel']._cached = split[5]
			self._state['main_tx']._cached = bool(split[6])
			if self._state['main_tx']._cached:
				self._state['main_tx_mode']._cached = mode(split[7])
				self._state['main_tx_tuning_mode']._cached = tuningMode(split[8])
			else:
				self._state['main_rx_mode']._cached = mode(split[7])
				self._state['main_rx_tuning_mode']._cached = tuningMode(split[8])
			self._state['main_scan_mode']._cached = scanMode(split[9])
			self._state['split']._cached = bool(split[10])
			self._state['main_tone_function']._cached = toneType(split[11])
			self._state['main_subtone_frequency']._cached = CTCSStone(split[12])
			self._state['main_offset_type']._cached = offset(split[13])
			# Fun hack... in CALL mode, MC300 is updated via IF...
			# We handle this special case by asserting that if we get IF
			# when in MC300, the MC has been updated
			# TODO: Also fun, the main and sub memory 300 is different
			if self._state['main_memory_channel']._cached == 300:
				self.memories.memories[300]._cached_value = None
				self._state['main_memory_channel']._cached_value = None
				self._state['main_memory_channel']._cached = 300
		else:
			# This is not the enum from ST (sigh)
			#if split[1] is not None:
			#	self._state['sub_multi_ch_frequency_steps']._cached = split[1]
			self._state['sub_memory_channel']._cached = split[5]
			self._state['sub_tx']._cached = bool(split[6])
			self._state['sub_mode']._cached = mode(split[7])
			self._state['sub_tuning_mode']._cached = tuningMode(split[8])
			self._state['sub_scan_mode']._cached = scanMode(split[9])
			self._state['sub_tone_function']._cached = toneType(split[11])
			self._state['sub_subtone_frequency']._cached = CTCSStone(split[12])
			self._state['sub_offset_type']._cached = offset(split[13])
			# Fun hack... in CALL mode, MC300 is updated via IF...
			# We handle this special case by asserting that if we get IF
			# when in MC300, the MC has been updated
			if self._state['sub_memory_channel']._cached == 300:
				self.memories.memories[300]._cached_value = None
				self._state['sub_memory_channel']._cached_value = None
				self._state['sub_memory_channel']._cached = 300

	def _update_IS(self, args):
		split = self.parse('5d', args)
		self._state['if_shift']._cached = split[0]

	def _update_KS(self, args):
		split = self.parse('3d', args)
		self._state['keyer_speed']._cached = split[0]

	def _update_KY(self, args):
		split = self.parse('1d', args)
		self._state['keyer_buffer_full']._cached = bool(split[0])

	def _update_LK(self, args):
		split = self.parse('1d1d', args)
		self._state['lock_list']._cached = [rigLock(split[0]), bool(split[1])]

	def _update_LM(self, args):
		# TODO: Maybe false for 0 and be an int?
		split = self.parse('1d', args)
		self._state['recording_channel']._cached = recordingChannel(split[0])

	def _update_LT(self, args):
		split = self.parse('1d', args)
		self._state['auto_lock_tuning']._cached = bool(split[0])

	def _update_MC(self, args):
		split = self.parse('3d', args)
		if self._state['control_main']._cached:
			self._state['main_memory_channel']._cached = split[0]
			self._main_rx_frequency_query()
			self._main_tx_frequency_query()
		else:
			self._state['sub_memory_channel']._cached = split[0]
			self._sub_frequency_query()
		# Any time we get an MC300; it means we entered CALL mode
		# The calling frequency *may* be different than last time!
		if split[0] == 300:
			self.memories.memories[300]._cached_value = None
			self._send_query(self.memories.memories[300])

	def _update_MD(self, args):
		split = self.parse('1d', args)
		if self._state['control_main']._cached:
			if self._state['transmit_set']._cached:
				self._state['main_tx_mode']._cached = mode(split[0])
			else:
				if self._state['main_tx_tuning_mode']._cached == self._state['main_rx_tuning_mode']._cached:
					self._state['main_tx_mode']._cached = mode(split[0])
				self._state['main_rx_mode']._cached = mode(split[0])
		else:
			self._state['sub_mode']._cached = mode(split[0])

	def _update_MF(self, args):
		split = self.parse('1d', args)
		if split[0] == 0:
			self._state['menu_ab']._cached = 'A'
		elif split[0] == 1:
			self._state['menu_ab']._cached = 'B'

	def _update_MG(self, args):
		split = self.parse('3d', args)
		self._state['microphone_gain']._cached = split[0]

	def _update_ML(self, args):
		split = self.parse('3d', args)
		self._state['monitor_level']._cached = split[0]

	def _update_MO(self, args):
		split = self.parse('1d', args)
		self._state['skyCommandMonitor']._cached = bool(split[0])

	def _update_MR(self, args):
		split = self.parse('1d3d11d1d1d1d2d2d3d1d1d9d2d1d0l', args)
		idx = 0
		newVal = deepcopy(self.memories.memories[split[1]]._cached)
		if newVal is None:
			newVal = {}
		if split[3] != 0:
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
			newVal['ToneNumber'] = CTCSStone(split[6])
			newVal['CTCSStoneNumber'] = CTCSStone(split[7])
			newVal['dcs_code'] = DCScode(split[8])
			newVal['Reverse'] = bool(split[9])
			newVal['OffsetType'] = offset(split[10])
			newVal['OffsetFrequency'] = split[11]
			newVal['StepSize'] = split[12]
			newVal['MemoryGroup'] = split[13]
			newVal['MemoryName'] = split[14]
		self.memories.memories[split[1]]._cached = newVal
		if split[1] == 300:
			self._main_rx_frequency_query()
			self._main_tx_frequency_query()
			self._sub_frequency_query()

	def _update_MU(self, args):
		self._state['memory_groups']._cached = base2ba(2, args)

	def _update_NB(self, args):
		split = self.parse('1d', args)
		self._state['noise_blanker']._cached = bool(split[0])

	def _update_NL(self, args):
		split = self.parse('3d', args)
		self._state['noise_blanker_level']._cached = split[0]

	def _update_NR(self, args):
		split = self.parse('1d', args)
		if self._state['control_main']._cached:
			self._state['main_noise_reduction']._cached = noiseReduction(split[0])
			self._send_query(self._state['noise_reduction_level'])
		else:
			self._state['sub_noise_reduction']._cached = noiseReduction(split[0])

	def _update_NT(self, args):
		split = self.parse('1d', args)
		self._state['auto_notch']._cached = bool(split[0])

	def _update_OF(self, args):
		split = self.parse('9d', args)
		if self._state['control_main']._cached:
			self._state['main_offset_frequency']._cached = split[0]
		else:
			self._state['sub_offset_frequency']._cached = split[0]

	def _update_OS(self, args):
		split = self.parse('1d', args)
		if self._state['control_main']._cached:
			self._state['main_offset_type']._cached = offset(split[0])
		else:
			self._state['sub_offset_type']._cached = offset(split[0])

	def _update_PA(self, args):
		split = self.parse('1d1d', args)
		self._state['main_preamp']._cached = bool(split[0])
		self._state['sub_preamp']._cached = bool(split[1])

	def _update_PB(self, args):
		split = self.parse('1d', args)
		self._state['playback_channel']._cached = recordingChannel(split[0])

	def _update_PC(self, args):
		split = self.parse('3d', args)
		if self._state['control_main']._cached:
			self._state['main_output_power']._cached = split[0]
		else:
			self._state['sub_output_power']._cached = split[0]

	def _update_PK(self, args):
		split = self.parse('11d12l20l5l', args)
		spot = {
			'frequency': split[0],
			'callsign': split[1],
			'comments': split[2],
			'time': split[3]
		}
		self._state['last_spot']._cached = spot

	def _update_PL(self, args):
		split = self.parse('3d3d', args)
		self._state['speech_processor_level_list']._cached = [split[0], split[1]]

	def _update_PM(self, args):
		split = self.parse('1d', args)
		# TODO: Should this be False when it's off?
		self._state['programmable_memory_channel']._cached = split[0]

	def _update_PR(self, args):
		split = self.parse('1d', args)
		self._state['speech_processor']._cached = bool(split[0])

	def _update_PS(self, args):
		self._serial.PS_works = True
		split = self.parse('1d', args)
		old = self._last_power_state
		self._state['power_on']._cached = bool(split[0])
		self._serial.power_on = self._state['power_on']._cached
		self._last_power_state = bool(split[0])
		if split[0] and old == False:
			self._set(self._state['auto_information'], 2)
			self._fill_cache()
		elif (not split[0]) and old == True:
			self._kill_cache()

	def _update_QC(self, args):
		split = self.parse('3d', args)
		if self._state['control_main']._cached:
			self._state['main_dcs_code']._cached = DCScode(split[0])
		else:
			self._state['sub_dcs_code']._cached = DCScode(split[0])

	def _update_QR(self, args):
		split = self.parse('1d1d', args)
		self._state['quick_memory_list']._cached = [bool(split[0]), split[1]]

	def _update_RA(self, args):
		split = self.parse('2d', args)
		if self._state['control_main']._cached:
			self._state['main_attenuator']._cached = bool(split[0])
		else:
			self._state['sub_attenuator']._cached = bool(split[0])

	# NOTE: Updates the same value as RU
	def _update_RD(self, args):
		split = self.parse('1d', args)
		self._state['scan_speed']._cached = split[0]

	def _update_RG(self, args):
		split = self.parse('3d', args)
		self._state['rf_gain']._cached = split[0]

	def _update_RL(self, args):
		split = self.parse('2d', args)
		self._state['noise_reduction_level']._cached = split[0]

	def _update_RM(self, args):
		split = self.parse('1d4d', args)
		self._state['meter_type']._cached = meter(split[0])
		self._state['meter_value']._cached = split[1]
		self._state['swr_meter']._cached = split[1] if split[0] == 1 else 0
		self._state['compression_meter']._cached = split[1] if split[0] == 2 else 0
		self._state['alc_meter']._cached = split[1] if split[0] == 3 else 0

	# Note: Can only set RM2 when COMP is on

	def _update_RT(self, args):
		split = self.parse('1d', args)
		self._state['rit']._cached = bool(split[0])

	# NOTE: Updates the same value as RD
	def _update_RU(self, args):
		split = self.parse('1d', args)
		self._state['scan_speed']._cached = split[0]

	def _update_RX(self, args):
		split = self.parse('1d', args)
		if self._state['tx_main']._cached == True and split[0] == 0:
			self._state['tx']._cached = False
		elif self._state['tx_main']._cached == False and split[0] == 1:
			self._state['tx']._cached = False
		if split[0] == 0:
			self._state['main_tx']._cached = False
		if split[0] == 1:
			self._state['sub_tx']._cached = False

	def _update_SA(self, args):
		split = self.parse('1d1d1d1d1d1d1d8l', args)
		self._state['satellite_mode_list']._cached = [bool(split[0]), split[1], not bool(split[2]), not bool(split[3]), bool(split[4]), bool(split[5]), not bool(split[6]), split[7]]

	def _update_SB(self, args):
		split = self.parse('1d', args)
		self._state['sub_receiver']._cached = bool(split[0])
		if self._state['sub_receiver']._cached:
			self._fill_cache()

	def _update_SC(self, args):
		split = self.parse('1d', args)
		if self._state['control_main']._cached:
			self._state['main_scan_mode']._cached = scanMode(split[0])
		else:
			self._state['sub_scan_mode']._cached = scanMode(split[0])

	def _update_SD(self, args):
		split = self.parse('4d', args)
		self._state['cw_break_in_time_delay']._cached = split[0]

	def _update_SH(self, args):
		split = self.parse('2d', args)
		self._state['voice_low_pass_cutoff']._cached = split[0]

	def _update_SL(self, args):
		split = self.parse('2d', args)
		self._state['voice_high_pass_cutoff']._cached = split[0]

	def _update_SM(self, args):
		split = self.parse('1d4d', args)
		# TODO: Figure out what 2 and 3 actually are...
		if split[0] == 0:
			self._state['main_s_meter']._cached = split[1]
		if split[0] == 1:
			self._state['sub_s_meter']._cached = split[1]
		if split[0] == 2:
			print('Got SM2!', file=stderr)
			self._state['main_s_meter_level']._cached = split[1]
		if split[0] == 3:
			print('Got SM3!', file=stderr)
			self._state['sub_s_meter_level']._cached = split[1]

	def _update_SQ(self, args):
		split = self.parse('1d3d', args)
		if split[0] == 0:
			self._state['main_squelch']._cached = split[1]
		elif split[0] == 1:
			self._state['sub_squelch']._cached = split[1]

	def _update_ST(self, args):
		split = self.parse('2d', args)
		if self._state['control_main']._cached:
			self._state['main_multi_ch_frequency_steps']._cached = split[0]
		else:
			self._state['sub_multi_ch_frequency_steps']._cached = split[0]

	def _update_TC(self, args):
		split = self.parse('1d1d', args)
		self._state['pc_control_command_mode']._cached = bool(split[1])

	def _update_TI(self, args):
		split = self.parse('1d1d1d', args)
		self._state['tnc_led_list']._cached = [bool(split[0]), bool(split[1]), bool(split[2])]

	def _update_TN(self, args):
		split = self.parse('2d', args)
		# TODO: Smart mapping thing?
		if self._state['control_main']._cached:
			self._state['main_subtone_frequency']._cached = CTCSStone(split[0])
		else:
			self._state['sub_subtone_frequency']._cached = CTCSStone(split[0])

	def _update_TO(self, args):
		split = self.parse('1d', args)
		if self._state['control_main']._cached:
			self._state['main_tone_function']._cached = bool(split[0])
		else:
			self._state['sub_tone_function']._cached = bool(split[0])

	def _update_TS(self, args):
		split = self.parse('1d', args)
		self._state['transmit_set']._cached = bool(split[0])

	def _update_TX(self, args):
		split = self.parse('1d', args)
		if self._state['tx_main']._cached == True and split[0] == 0:
			self._state['tx']._cached = True
		elif self._state['tx_main']._cached == False and split[0] == 1:
			self._state['tx']._cached = True
		else:
			print('TX triggered for wrong receiver!', file=stderr)
		if split[0] == 0:
			self._state['main_tx']._cached = True
		if split[0] == 1:
			self._state['sub_tx']._cached = True

	def _update_TY(self, args):
		split = self.parse('2d1d', args)
		self._state['firmware_type']._cached = firmwareType(split[1])

	def _update_UL(self, args):
		split = self.parse('1d', args)
		if split[0] == 1:
			raise Exception('PLL Unlocked!')
		self._state['PLLunlock']._cached = bool(split[0])

	def _update_VD(self, args):
		split = self.parse('4d', args)
		self._state['vox_delay_time']._cached = split[0]

	def _update_VG(self, args):
		split = self.parse('3d', args)
		self._state['vox_gain']._cached = split[0]

	def _update_VX(self, args):
		split = self.parse('1d', args)
		self._state['vox']._cached = bool(split[0])

	def _update_XT(self, args):
		split = self.parse('1d', args)
		self._state['xit']._cached = bool(split[0])

	def _update_Error(self, args):
		self._error_count += 1
		if self._serial._last_command is None:
			self._serial.PS_works = False
		if self._error_count < 10:
			if self._serial._last_command is not None:
				print('Resending: '+str(self._serial._last_command), file=stderr)
				self._serial.writeQueue.put(self._serial._last_command)
		else:
			raise Exception('Error count exceeded')

	def _update_ComError(self, args):
		self._error_count += 1
		if self._serial._last_command is None:
			self._serial.PS_works = False
		if self._error_count < 10:
			if self._serial._last_command is not None:
				print('Resending: '+str(self._serial._last_command), file=stderr)
				self._serial.writeQueue.put(self._serial._last_command)
		else:
			raise Exception('Error count exceeded')

	def _update_IncompleteError(self, args):
		self._error_count += 1
		if self._serial._last_command is None:
			self._serial.PS_works = False
		if self._error_count < 10:
			if self._serial._last_command is not None:
				print('Resending: '+str(self._serial._last_command), file=stderr)
				self._serial.writeQueue.put(self._serial._last_command)
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
