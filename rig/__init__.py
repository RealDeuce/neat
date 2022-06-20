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

from abc import ABC, abstractmethod
from enum import IntEnum

class mode(IntEnum):
	LSB = 1
	USB = 2
	CW  = 3
	FM  = 4
	AM  = 5
	FSK = 6
	CW_REVERSED = 7
	FSK_REVERSED = 9

"""
This is the generic interface for each rig.  The following
are all expected to be overridden

- split
	If True, rx_* and tx_* are independent values. Setting one will
	not set the other.  The backend is responsible for enforcing (or
	emulating) this behaviour.

	If False, rx_* and tx_* will always have the same value. 
	Setting either will always set both.

	If None, split is not supported

	When split is changed from False to True, rx_* and tx_* values
	will be the same as each other.  When split is changed from True
	to False, if the radio is currently transmitting, it will be
	taken out of transmit if possible, and the tx_* values set to
	the rx_* values

- rx_frequency
	The current receive frequency in Hz.  This frequency includes
	the RIT	offset if set, and indicates the frequency the carrier
	of the received signal would be on (if it had one)

	For FSK mode, this is the MARK frequency.

- tx_frequency
	The current transmit frequency in Hz.  This frequency includes
	the XIT offset if set, any transmit offset, and anything  else
	that affects the output signal.  In short, this frequency is
	that of the carrier that is transmitted if the current mode has
	one.

	For FSK mode, this is the MARK frequency.

- rx_mode
	This is the mode the receiver is operating in.

- tx_mode
	This is the mode the transmitter is operating in.

- tx
	When set to True, the radio begins transmitting, when set to
	False, it stops transmitting.

- add_callback(self, prop, cb):
	self._state[prop].add_callback(cb)

- remove_callback(self, prop, cb):
	self._state[prop].remove_callback(cb)

- terminate()

"""

class Rig(ABC):
	def __init__(self, **kwargs):
		kwargs = {'verbose': False, **kwargs}
		self._verbose = kwargs.get('verbose')
		self._state = {}

	def __getattr__(self, name):
		if name in self._state:
			if isinstance(self._state[name], list):
				return self._state[name]
			return self._state[name].value
		elif name in ('split', 'rx_frequency', 'tx_frequency', 'rx_mode', 'tx_mode', 'tx'):
			raise NotImplementedError('Rig types require ' + name)
		raise AttributeError('No state named ' + name + ' found in Rig object')

	def __setattr__(self, name, value):
		if name[:1] != '_':
			if name in self._state:
				self._state[name].value = value
			elif name in ('split', 'rx_frequency', 'tx_frequency', 'rx_mode', 'tx_mode', 'tx'):
				raise NotImplementedError('Rig types require ' + name)
		super().__setattr__(name ,value)

	def __del__(self):
		self.terminate()

	@abstractmethod
	def terminate(self):
		raise NotImplementedError('Rig types require terminate')

	def add_callback(self, prop, callback):
		if isinstance(self._state[prop], list):
			raise Exception('Unable to add callback for entire list')
		ob = prop.find('[')
		cb = prop.find(']')
		if (ob == -1) != (cb == -1) or cb < ob:
			raise Exception('Invalid list indexing')
		if ob == -1:
			print('Prop: '+prop)
			self._state[prop].add_modify_callback(callback)
			return
		self._state[prop[:ob]][int(prop[ob+1:cb])].add_modify_callback(callback)

	def remove_callback(self, prop, callback):
		if isinstance(self._state[prop], list):
			raise Exception('Unable to add callback for entire list')
		ob = prop.find('[')
		cb = prop.find(']')
		if (ob == -1) != (cb == -1) or cb < ob:
			raise Exception('Invalid list indexing')
		if ob == -1:
			self._state[prop].remove_modify_callback(callback)
			return
		self._state[prop[:ob]][int(prop[ob+1:cb])].remove_modify_callback(callback)

"""
This class implements the caching layer.

Backends should read/write the .cached property to check/set the cached
value.  A set to cached triggers all applicable registered callbacks.

Frontends should read/write the property itself and not deal with this
class at all.

The set callbacks are intended for use by backends.
"""
class StateValue(ABC):
	def __init__(self, rig, **kwargs):
		self.name = kwargs.get('name')
		self._read_only = kwargs.get('read_only')
		self._rig = rig
		self._cached_value = None
		self._modify_callbacks = ()
		self._set_callbacks = ()

	@property
	def _cached(self):
		return self._cached_value

	@_cached.setter
	def _cached(self, value):
		if isinstance(value, StateValue):
			raise Exception('Forgot to add .cached!')
		if self._cached_value != value:
			self._cached_value = value
			for cb in self._modify_callbacks:
				cb(value)
		for cb in self._set_callbacks:
			cb(self, value)

	@property
	@abstractmethod
	def value(self):
		raise NotImplementedError('value getter not defined')

	@value.setter
	@abstractmethod
	def value(self, value):
		raise NotImplementedError('value setter not defined')

	def add_modify_callback(self, cb):
		if not callable(cb):
			raise Exception('Adding uncallable modify callback: '+str(cb))
		self._modify_callbacks += (cb,)

	def add_set_callback(self, cb):
		if not callable(cb):
			raise Exception('Adding uncallable set callback: '+str(cb))
		self._set_callbacks += (cb,)

	def remove_modify_callback(self, cb):
		self._modify_callbacks = tuple(filter(lambda x: x != cb, self._modify_callbacks))

	def remove_set_callback(self, cb):
		self._set_callbacks = tuple(filter(lambda x: x != cb, self._set_callbacks))
