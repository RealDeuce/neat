from abc import ABC

class mode(enum.IntEnum):
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
			return self._state[name].value
		elif name in (split, rx_frequency, tx_frequency, rx_mode, tx_mode, tx)
			raise NotImplementedError('Rig types require ' + name)
		raise AttributeError('No state named ' + name + ' found in Kenwood object')

	def __setattr__(self, name, value):
		if name[:1] != '_':
			if name in self._state:
				self._state[name].value = value
			elif name in (split, rx_frequency, tx_frequency, rx_mode, tx_mode, tx)
				raise NotImplementedError('Rig types require ' + name)
		super().__setattr__(name ,value)

	def __del__(self):
		self.terminate()

	@abstractmethod
	def terminate(self):
		raise NotImplementedError('Rig types require terminate')

	def add_callback(self, prop, cb):
		self._state[prop].add_modify_callback(cb)

	def remove_callback(self, prop, cb):
		self._state[prop].remove_modify_callback(cb)

"""
This class implements the caching layer.

Backends should read/write the ._cached property to check/set the cached
value.  A set to _cached triggers all applicable registered callbacks.

Frontends should read/write the property itself and not deal with this
class at all.
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
			raise Exception('Forgot to add ._cached!')
		if self._cached_value != value:
			self._cached_value = value
			for cb in self._callbacks:
				cb(value)
		for cb in self._wait_callbacks:
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
		self._callbacks += (cb,)

	def add_set_callback(self, cb):
		self._wait_callbacks += (cb,)

	def remove_modify_callback(self, cb):
		self._callbacks = tuple(filter(lambda x: x == cb, self._callbacks))

	def remove_set_callback(self, cb):
		self._wait_callbacks = tuple(filter(lambda x: x is cb, self._wait_callbacks))
