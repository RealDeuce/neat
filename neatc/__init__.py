import rig
import json
import selectors
import socket
import threading
from copy import deepcopy

class NeatCStateValue(rig.StateValue):
	def __init__(self, neatcc, name, **kwargs):
		super().__init__(neatcc._neatc, **kwargs)
		self._name = name
		self._neatcc = neatcc
		self._neatcc.append(b'watch '+bytes(self._name, 'ascii')+b'\n')
		self._neatcc.append(b'get '+bytes(self._name, 'ascii')+b'\n')

	@property
	def value(self):
		return deepcopy(self._cached)

	@value.setter
	def value(self, value):
		if isinstance(value, rig.StateValue):
			raise Exception('Forgot to add ._cached!')
		self._neatcc.append(b'set '+bytes(self._name + '=' + json.dumps(value), 'ascii')+b'\n')

	def __del__(self):
		self._neatcc.append(b'unwatch '+bytes(self._name, 'ascii')+b'\n')
		try:
			super().__del__()
		except AttributeError:
			pass

class NeatCConnection:
	def __init__(self, neatc, sel, sel_lock, conn, **kwargs):
		self._neatc = neatc
		self._conn = conn
		self._sel = sel
		self._sel_lock = sel_lock
		self._inbuf = b''
		self._outbuf = b''
		self.mask = selectors.EVENT_READ | selectors.EVENT_WRITE
		conn.setblocking(False)
		self._sel_lock.acquire()
		self._sel.register(self._conn, self.mask, data = self)
		self._sel_lock.release()
		self.append(b'list\n')

	def handle(self, cmd):
		if self._neatc._verbose:
			print('Received command "'+cmd.decode('ascii')+'"', file = sys.stderr)
		if cmd[0:8] == b'watched ':
			cmd = cmd[8:]
			eq = cmd.find(b'=')
			ob = cmd.find(b'[')
			if ob > eq:
				ob = -1
			cb = cmd.find(b']')
			if cb > eq:
				cb = -1
			if (ob == -1) != (cb == -1) or cb < ob:
				raise Exception('Invalid list index '+str(cmd))
			if ob == -1:
				self._neatc._state[cmd[0:eq].decode('ascii')]._cached = json.loads(cmd[eq+1:].decode('ascii'))
			else:
				self._neatc._state[cmd[0:ob].decode('ascii')][int(cmd[ob+1:cb].decode('ascii'))]._cached = json.loads(cmd[eq+1:].decode('ascii'))
		elif cmd[0:5] == b'list ':
			cmd = cmd[5:]
			while len(cmd) > 0:
				sp = cmd.find(b' ')
				if sp == -1:
					name = cmd[0:].decode('ascii')
					cmd = b''
				else:
					name = cmd[0:sp].decode('ascii')
					cmd = cmd[sp+1:]
				if name[-1:] == ']':
					ob = name.find('[')
					length = int(name[ob+1:-1])
					self._neatc._state[name[:ob]] = [None] * length
					for i in range(length):
						self._neatc._state[name[:ob]][i] = NeatCStateValue(self, name[:ob] + '['+str(i)+']')
				else:
					self._neatc._state[name] = NeatCStateValue(self, name)
			if self._neatc._list_event is not None:
				self._neatc._list_event.set()
		else:
			eq = cmd.find(b'=')
			ob = cmd.find(b'[')
			if ob > eq:
				ob = -1
			cb = cmd.find(b']')
			if cb > eq:
				cb = -1
			if (ob == -1) != (cb == -1) or cb < ob:
				raise Exception('Invalid list index '+str(cmd))
			if ob == -1:
				self._neatc._state[cmd[0:eq].decode('ascii')]._cached = json.loads(cmd[eq+1:].decode('ascii'))
			else:
				self._neatc._state[cmd[0:ob].decode('ascii')][int(cmd[ob+1:cb].decode('ascii'))]._cached = json.loads(cmd[eq+1:].decode('ascii'))
				
	def append(self, buf):
		if buf is None:
			return
		self._outbuf += buf
		if (not self.mask & selectors.EVENT_WRITE) and self._conn.fileno() != -1:
			self.mask |= selectors.EVENT_WRITE
			self._sel_lock.acquire()
			self._neatc._sel.modify(self._conn, self.mask, data = self)
			self._sel_lock.release()

	def close(self):
		self._sel_lock.acquire()
		self._neatc._sel.unregister(self._conn)
		self._sel_lock.release()
		self._conn.close()
		self._neatc._terminate = True
		self._conn = None

	def read(self):
		data = self._conn.recv(1500)
		if data:
			self._inbuf += data
			while b'\n' in self._inbuf:
				i = self._inbuf.find(b'\n')
				self.handle(self._inbuf[0:i])
				self._inbuf = self._inbuf[i+1:]
		else:
			self.close()

	def write(self):
		sent = self._conn.send(self._outbuf)
		if sent > 0:
			if self._neatc._verbose:
				print('Sent command: '+str(self._outbuf[:sent]), file=sys.stderr)
			self._outbuf = self._outbuf[sent:]
		if len(self._outbuf) == 0:
			if (self.mask & selectors.EVENT_WRITE) and self._conn.fileno() != -1:
				self.mask &= ~selectors.EVENT_WRITE
				self._sel_lock.acquire()
				self._neatc._sel.modify(self._conn, self.mask, data = self)
				self._sel_lock.release()

class NeatC(rig.Rig):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self._terminate = False
		self._verbose = kwargs.get('verbose', False)
		self._address = kwargs.get('address', 'localhost')
		self._port = kwargs.get('port', 3532)
		self._conn = None
		self._list_event = threading.Event()
		self._sel = selectors.DefaultSelector()
		self._sel_lock = threading.Lock()
		self._neatc_thread = threading.Thread(target = self.neatc_thread, name = 'neatc')
		self._neatc_thread.start()
		self._list_event.wait()
		self._list_event = None

	def terminate(self):
		self._terminate = True
		self._neatc_thread.join()

	def neatc_thread(self):
		sock = socket.create_connection((self._address, self._port))
		self._conn = NeatCConnection(self, self._sel, self._sel_lock, sock)
		while not self._terminate:
			#self._sel_lock.acquire()
			events = self._sel.select(0.1)
			#self._sel_lock.release()
			for key, mask in events:
				if isinstance(key.data, NeatCConnection):
					if mask & selectors.EVENT_WRITE:
						key.data.write()
					if mask & selectors.EVENT_READ:
						key.data.read()
				else:
					print(str(key.data)+" isn't a NeatCConnection", file = sys.stderr)
