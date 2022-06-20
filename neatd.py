import rig
import rig.kenwood_hf as kenwood_hf
import rigctld
import threading
import configparser
import json
import socket
import selectors
import sys

class NeatDCallback:
	def __init__(self, neatd_connection, prop, name, **kwargs):
		self._prop = prop
		self._name = name
		self._neatd_connection = neatd_connection
		try:
			self._prop.add_modify_callback(self.callback)
		except:
			print('1Exception ignored: ', sys.exc_info()[0])

	def __del__(self):
		try:
			self._prop.remove_modify_callback(self.callback)
		except:
			print('2Exception ignored: ', sys.exc_info()[0])

	def callback(self, value):
		try:
			self._neatd_connection.append(bytes('watched ' + self._name + '=' + json.dumps(value), 'ascii')+b'\n')
		except:
			print('3Exception ignored: ', sys.exc_info()[0])
			self._neatd_connection.append(b'watched ' + bytes(self._name, 'ascii') + b'=null\n')

class NeatDConnection:
	def __init__(self, neatd, conn):
		self._neatd = neatd
		self._conn = conn
		self.inbuf = b''
		self.outbuf = b''
		self.mask = selectors.EVENT_READ | selectors.EVENT_WRITE
		self._callbacks = {}

	# TODO: Clean up all watchers in close() and del...

	def _getsv(self, bname):
		try:
			bname = bname.decode('ascii')
		except:
			print('4Exception ignored: ', sys.exc_info()[0], str(bname))
			return None
		ob = bname.find('[')
		cb = bname.find(']')
		if ob != -1 and cb != -1:
			name = bname[0:ob]
			index = int(bname[ob+1:cb])
		else:
			name = bname
			index = None
		if index == None:
			if not name in self._neatd.rigobj._state:
				return None
			return self._neatd.rigobj._state[name]
		a = getattr(self._neatd.rigobj, name)
		if isinstance(a, list):
			if index == None:
				return a
			if len(a) > index:
				return getattr(a, name)[index]
		return None

	def handle(self, cmd):
		if self._neatd.verbose:
			print('NeatD command: '+str(cmd), file=sys.stderr)
		if cmd[0:4] == b'set ':
			cmd = cmd[4:]
			eq = cmd.find(b'=')
			if eq == -1:
				self.close()
			else:
				sv = self._getsv(cmd[0:eq])
				if sv is not None and not isinstance(sv, list):
					try:
						sv.value = json.loads(cmd[eq+1:].decode('ascii'))
					except:
						print('5Exception ignored: ', sys.exc_info()[0])
		elif cmd[0:4] == b'get ':
			cmd = cmd[4:]
			sv = self._getsv(cmd)
			if sv is not None:
				val = sv.value
			else:
				val = None
			try:
				if isinstance(val, list):
					cmd += bytest('[0:'+str(len(val))+']', 'ascii')
				self.append(cmd + bytes('=' + json.dumps(val), 'ascii') + b'\n')
			except:
				print('6Exception ignored: ', sys.exc_info()[0])
				self.append(cmd + b'=null\n')
		elif cmd[0:6] == b'watch ':
			cmd = cmd[6:]
			sv = self._getsv(cmd)
			if isinstance(sv, list):
				return
			if sv in self._callbacks:
				return
			try:
				self._callbacks[sv] = NeatDCallback(self, sv, cmd.decode('ascii'))
			except:
				print('7Exception ignored: ', sys.exc_info()[0])
		elif cmd[0:8] == b'unwatch ':
			cmd = cmd[8:]
			sv = self._getsv(cmd)
			if isinstance(sv, list):
				return
			if sv in self._callbacks:
				del self._callbacks[sv]
		elif cmd == b'list':
			self.append(b'list')
			for a, p in self._neatd.rigobj._state.items():
				if isinstance(p, rig.StateValue):
					self.append(b' ' + bytes(a, 'ascii'))
			for a, p in self._neatd.rigobj.__dict__.items():
				if a[0:1] != '_':
					if isinstance(p, list):
						self.append(b' ' + bytes(a+'['+str(len(getattr(self._neatd.rigobj, a)))+']', 'ascii'))
			self.append(b'\n')

	def append(self, buf):
		if buf is None:
			return
		self.outbuf += buf
		if (not self.mask & selectors.EVENT_WRITE) and self._conn.fileno() != -1:
			self.mask |= selectors.EVENT_WRITE
			self._neatd.sel.modify(self._conn, self.mask, data = self)

	def close(self):
		self._neatd.sel.unregister(self._conn)
		self._conn.close()

	def read(self):
		data = self._conn.recv(1500)
		if data:
			self.inbuf += data
			while b'\n' in self.inbuf:
				i = self.inbuf.find(b'\n')
				self.handle(self.inbuf[0:i])
				self.inbuf = self.inbuf[i+1:]
		else:
			self.close()

	def write(self):
		sent = self._conn.send(self.outbuf)
		if sent > 0:
			if self._neatd.verbose:
				print('NeatD response: '+str(self.outbuf[:sent]), file=sys.stderr)
			self.outbuf = self.outbuf[sent:]
		if len(self.outbuf) == 0:
			self.mask &= ~selectors.EVENT_WRITE
			self._neatd.sel.modify(self._conn, self.mask, data = self)

class NeatD:
	def accept(self, sock):
		conn, addr = sock.accept()
		conn.setblocking(False)
		rconn = NeatDConnection(self, conn)
		self.sel.register(conn, rconn.mask, data = rconn)

	def __init__(self, **kwargs):
		config = configparser.ConfigParser()
		config.read_dict({'SerialPort': {
				'device': '/dev/ttyU0',
				'speed': 57600,
				'stopBits': 1,
			},
			'Neat': {
				'verbose': 0,
				'rigctld': 1,
				'rigctld_address': 'localhost',
				'rigctld_port': 4532,
				'neatd_address': 'localhost',
				'neatd_port': 4531,
			}
		})
		config.read('neat.ini')
		self.verbose = config.getboolean('Neat', 'verbose')
		self.rigobj = kenwood_hf.KenwoodHF(port = config['SerialPort']['device'], speed = config.getint('SerialPort', 'speed'), stopbits = config.getint('SerialPort', 'stopBits'), verbose = config.getboolean('Neat', 'verbose'))
		if config.getboolean('Neat', 'rigctld'):
			rigctl_main = rigctld.rigctld(self.rigobj.rigs[0], address = config['Neat']['rigctld_address'], port = config.getint('Neat', 'rigctld_port'), verbose = config.getboolean('Neat', 'verbose'))
			rigctldThread_main = threading.Thread(target = rigctl_main.rigctldThread, name = 'rigctld')
			rigctldThread_main.start()
			rigctl_sub = rigctld.rigctld(self.rigobj.rigs[0], address = config['Neat']['rigctld_address'], port = config.getint('Neat', 'rigctld_port') + 1, verbose = config.getboolean('Neat', 'verbose'))
			rigctldThread_sub = threading.Thread(target = rigctl_sub.rigctldThread, name = 'rigctld')
			rigctldThread_sub.start()
		
		sock = socket.socket()
		sock.bind((config['Neat']['neatd_address'], config.getint('Neat', 'neatd_port')))
		sock.listen(100)
		sock.setblocking(False)
		self.sel = selectors.DefaultSelector()
		self.sel.register(sock, selectors.EVENT_READ)
		while not self.rigobj._terminate:
			events = self.sel.select(0.1)
			for key, mask in events:
				if isinstance(key.data, NeatDConnection):
					if mask & selectors.EVENT_WRITE:
						key.data.write()
					if mask & selectors.EVENT_READ:
						key.data.read()
				else:
					self.accept(key.fileobj)

if __name__ == '__main__':
	blah = NeatD()
