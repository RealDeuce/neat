import rig.kenwood_hf
from serial import Serial
from time import time
from queue import Queue
from sys import stderr
from threading import Event

# TODO: Do we need our own handler/callback here?

class KenwoodHFProtocol:
	def __init__(self, port = "/dev/ttyU0", speed = 4800, stopbits = 2, **kwargs):
		kwargs = {'verbose': False, **kwargs}
		self._verbose = kwargs.get('verbose')
		self._terminate = False
		self.writeQueue = Queue(maxsize = 0)
		self._last_hack = 0
		self.PS_works = None
		self.power_on = False
		self._last_command = None
		self._serial = Serial(baudrate = speed, stopbits = stopbits, rtscts = False, timeout = 0.01, inter_byte_timeout = 0.5)
		# Kenwood mostly uses RTR/CTS flow control, but with a
		# special exception for when the radio is powered off.
		# In this case, the radio does not wake when RTR is
		# asserted, but rather when RTR is asserted and data is
		# sent.  Because we need to be able to send data when
		# CTS is low, we can't use hardware RTS/CTS flow
		# control.
		self._serial.rts = True
		self._serial.port = port
		self._serial.open()
		self._serial.reset_output_buffer()
		self._serial.reset_input_buffer()
		self._write_buffer = b''
		self._event = None

	def terminate(self):
		self._terminate = True

	def _set_event(self):
		if self._event is not None:
			self._event.set()

	def read(self):
		ret = b'';
		while not self._terminate:
			# Always read first if possible.
			if self._serial.rts:
				ret += self._serial.read_until(b';')
				if ret[-1:] == b';':
					if self._verbose:
						print("Read: "+str(ret), file=stderr)
					ret = ret.replace(b'^[^A-Z]*', b'')
					self._set_event()
					return ret
				else:
					if self._event is None or self._event.is_set():
						if self._write_buffer != b'' or not self.writeQueue.empty():
							self._serial.rts = False
			if self._event is None or self._event.is_set():
				self._event = None
				if self._write_buffer != b'' or not self.writeQueue.empty():
					if self._serial.cts:
						self._serial.rts = False
				if self._serial.cts:
					if self._write_buffer != b'' or not self.writeQueue.empty():
						if self._write_buffer == b'':
							wr = self.writeQueue.get()
							self._last_command = wr
							if wr['msgType'] == 'set':
								newcmd = wr['stateValue']._set_string(wr['value'])
							elif wr['msgType'] == 'query':
								newcmd = wr['stateValue']._query_string()
							else:
								raise Exception('Unhandled message type: '+str(wr['msgType']))
							if newcmd is None:
								if wr['msgType'] == 'query':
									wr['stateValue']._cached = None
							else:
								if newcmd == '':
									wr['stateValue']._cached = wr['stateValue']._cached
								self._write_buffer = bytes(newcmd + ';', 'ascii')
								if wr['msgType'] == 'set' and (not wr['stateValue']._echoed):
									newcmd = wr['stateValue']._query_string()
									if newcmd is not None:
										self._write_buffer += bytes(newcmd + ';', 'ascii')
						if self._write_buffer != b'':
							fs = self._write_buffer.find(b';')
							if fs == None:
								raise Exception('Write buffer does not contain semi-colon')
							cmd = self._write_buffer[0:fs+1]
							self._write_buffer = self._write_buffer[fs+1:]
							if cmd != b'' and cmd != b';' and cmd != b'\x00;':
								wait_event = True
								if cmd[0] == 0:
									cmd = cmd[1:]
									wait_event = False
								if self._verbose:
									print('Writing ' + str(cmd), file=stderr)
								self._serial.write(cmd)
								if wait_event:
									self._event = Event()
								self._serial.rts = True
								# Another power-related hack...
								if cmd == b'PS0;':
									return cmd
								self.last_hack = time()
					if self._write_buffer == b'' or self.writeQueue.empty():
						self._serial.rts = True
				else:
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
			if (self.PS_works == None or self.PS_works == True) and not self.power_on:
				if time() - self._last_hack > 1:
					self._serial.write(b'PS;')
					self._last_hack = time()
