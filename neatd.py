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
	def __init__(self, neatd_connection, prop, **kwargs):
		self._prop = prop
		print('Prop: '+str(prop))
		self._neatd_connection = neatd_connection
		try:
			self._neatd_connection._neatd.rigobj.add_callback(prop, self.callback)
		except:
			print('Exception ignored: ', sys.exc_info()[0])

	def __del__(self):
		try:
			self._neatd_connection._neatd.rigobj.remove_callback(self._prop, self.callback)
		except:
			print('Exception ignored: ', sys.exc_info()[0])

	def callback(self, value):
		try:
			self._neatd_connection.append(bytes('watched ' + self._prop + '=' + json.dumps(value), 'ascii')+b'\n')
		except:
			print('Exception ignored: ', sys.exc_info()[0])
			self._neatd_connection.append(b'watched ' + bytes(self._prop, 'ascii') + b'=null\n')

class NeatDConnection:
	def __init__(self, neatd, conn):
		self._neatd = neatd
		self._conn = conn
		self.inbuf = b''
		self.outbuf = b''
		self.mask = selectors.EVENT_READ | selectors.EVENT_WRITE
		self._callbacks = {}
	
	def handle(self, cmd):
		if self._neatd.verbose:
			print('NeatD command: '+str(cmd), file=sys.stderr)
		if cmd[0:4] == b'set ':
			cmd = cmd[4:]
			eq = cmd.find(b'=')
			if eq == -1:
				self.close()
			else:
				try:
					setattr(self._neatd.rigobj, cmd[0:eq].decode('ascii'), json.loads(cmd[eq+1:].decode('ascii')))
				except:
					print('Exception ignored: ', sys.exc_info()[0])
		elif cmd[0:4] == b'get ':
			cmd = cmd[4:]
			if hasattr(self._neatd.rigobj, cmd.decode('ascii')):
				val = getattr(self._neatd.rigobj, cmd.decode('ascii'))
			else:
				val = None
			try:
				#if cmd == b'memories':
				#	print('Val = '+str(list(val.__iter__())))
				#	self.append(cmd + bytes('=' + json.dumps(list(val.__iter__())), 'ascii') + b'\n')
				#else:
				self.append(cmd + bytes('=' + json.dumps(val), 'ascii') + b'\n')
			except:
				print('Exception ignored: ', sys.exc_info()[0])
				self.append(cmd + b'=null\n')
		elif cmd[0:6] == b'watch ':
			cmd = cmd[6:]
			if cmd in self._callbacks:
				return
			try:
				cmd = cmd.decode('ascii')
				self._callbacks[cmd] = NeatDCallback(self, cmd)
			except:
				print('Exception ignored: ', sys.exc_info()[0])
		elif cmd[0:8] == b'unwatch ':
			cmd = cmd[8:]
			if cmd in self._callbacks:
				del self._callbacks[cmd]
		elif cmd == b'list ':
			self.append(b'list ')
			for a, p in self._state.items():
				if isinstance(p, StateValue):
					self.append(b' ' + bytes(a, 'ascii'))

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
