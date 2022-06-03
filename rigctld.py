import kenwood
import selectors
import socket

class rigctld_connection:
	long2short = {
		b"\\set_split_freq": b'I',
		b"\\get_split_freq": b'i',
		b"\\set_split_mode": b'X',
		b"\\get_split_mode": b'x',
		b"\\set_rptr_shift": b'R',
		b"\\get_rptr_shift": b'r',
		b"\\set_ctcss_tone": b'C',
		b"\\get_ctcss_tone": b'c',
		b"\\set_rptr_offs": b'O',
		b"\\get_rptr_offs": b'o',
		b"\\set_split_vfo": b'S',
		b"\\get_split_vfo": b's',
		b"\\set_ctcss_sql": b'\x90',
		b"\\get_ctcss_sql": b'\x91',
		b"\\set_powerstat": b'\x87',
		b"\\get_powerstat": b'\x88',
		b"\\set_dcs_code": b'D',
		b"\\get_dcs_code": b'd',
		b"\\set_dcs_sql": b'\x92',
		b"\\get_dcs_sql": b'\x93',
		b"\\set_channel": b'H',
		b"\\get_channel": b'h',
		b"\\send_morse": b'b',
		b"\\dump_state": b'\x8f',
		b"\\set_level": b'L',
		b"\\get_level": b'l',
		b"\\send_dtmf": b'\x89',
		b"\\recv_dtmf": b'\x8a',
		b"\\dump_caps": b'1',
		b"\\dump_conf": b'3',
		b"\\set_freq": b'F',
		b"\\get_freq": b'f',
		b"\\set_mode": b'M',
		b"\\get_mode": b'm',
		b"\\set_func": b'U',
		b"\\get_func": b'u',
		b"\\set_parm": b'P',
		b"\\get_parm": b'p',
		b"\\set_bank": b'B',
		b"\\get_info": b'_',
		b"\\send_cmd": b'w',
		b"\\power2mW": b'2',
		b"\\mW2power": b'4',
		b"\\set_trn": b'A',
		b"\\get_trn": b'a',
		b"\\set_rit": b'J',
		b"\\get_rit": b'j',
		b"\\set_xit": b'Z',
		b"\\get_xit": b'z',
		b"\\set_ant": b'Y',
		b"\\get_ant": b'y',
		b"\\get_dcd": b'\x8b',
		b"\\chk_vfo": b'\xf0',
		b"\\set_vfo": b'V',
		b"\\get_vfo": b'v',
		b"\\set_ptt": b'T',
		b"\\get_ptt": b't',
		b"\\set_mem": b'E',
		b"\\get_mem": b'e',
		b"\\set_ts": b'N',
		b"\\get_ts": b'n',
		b"\\vfo_op": b'G',
		b"\\reset": b'*',
		b"\\scan": b'g',
		b"\\halt": b'\xf1',
	}

	def __init__(self, rigctld, conn):
		self._rigctld = rigctld
		self._conn = conn
		self.inbuf = b''
		self.outbuf = b''
		self.mask = selectors.EVENT_READ | selectors.EVENT_WRITE

	def shorten(self, cmd):
		if b'\\' in cmd:
			for lng, sht in self.long2short.items():
				cmd = cmd.replace(lng, sht)
		return cmd

	def send_vfo(self):
		val = self._rigctld.rig.tuningMode.value
		if val == kenwood.tuningMode.VFOA:
			self.append(b"VFOA\n")
		elif val == kenwood.tuningMode.VFOB:
			self.append(b"VFOB\n")
		else:
			self.append(b"MEM\n")

	def get_arg(self, cmd, offset):
		if cmd[offset:offset+1] == b' ':
			while cmd[offset:offset+1] == b' ' and cmd[offset:offset+1] != b'':
				offset += 1
			start = offset
			while cmd[offset:offset+1] != b' ' and cmd[offset:offset+1] != b'':
				offset += 1
			end = offset
			if start != end:
				return (cmd[start:end], offset - 1)
		return None, offset - 1

	def get_vfo(self, cmd):
		if cmd == b'VFOA':
			return kenwood.tuningMode.VFOA
		elif cmd == b'VFOB':
			return kenwood.tuningMode.VFOB
		elif cmd == b'MEM':
			return kenwood.tuningMode.MEMORY
		return None

	def get_freq(self, vfo):
		if vfo == kenwood.tuningMode.VFOA:
			return self._rigctld.rig.vfoAFrequency.value
		elif vfo == kenwood.tuningMode.VFOB:
			return self._rigctld.rig.vfoBFrequency.value
		else:
			return self._rigctld.rig.currentFrequency.value

	def send_mode(self):
		mode = self._rigctld.rig.mode.value
		if mode == kenwood.mode.AM:
			self.append(b'AM\n')
		elif mode == kenwood.mode.FM:
			self.append(b'FM\n')
		elif mode == kenwood.mode.USB:
			self.append(b'USB\n')
		elif mode == kenwood.mode.LSB:
			self.append(b'LSB\n')
		elif mode == kenwood.mode.CW:
			self.append(b'CW\n')
		elif mode == kenwood.mode.CW_REVERSED:
			self.append(b'CWR\n')
		elif mode == kenwood.mode.FSK:
			self.append(b'RTTY\n')
		elif mode == kenwood.mode.FSK_REVERSED:
			self.append(b'RTTYR\n')
		else:
			self.append(b'\n')
		self.append(b'2400\n')

	def handle(self, cmd):
		cmd = self.shorten(cmd)
		i = 0
		while i < len(cmd):
			ch = cmd[i:i+1]
			if ch == b'\xf0':
				self.append(b"CHKVFO 0\n")
			elif ch == b'\x8f':
				self.append(b"0\n")                   # Protocol version
				self.append(b"2\n")                   # Rig model (dummy)
				self.append(b"2\n")                   # ITU region (!)
				# RX info: lowest/highest freq, modes available, low power, high power, VFOs, antennas
				# i = 0x10000003                      # VFO_MEM, VFO_A, VFO_B
				self.append(b"30000 60000000 0x1ff -1 -1 0x10000003 0x01\n") # Low limit, high limit, ?, ?, ? VFOs, ?
				# Terminated with all zeros
				self.append(b"0 0 0 0 0 0 0\n")
				# TX info (as above)
				self.append(b"30000 60000000 0x1ff 0 100 0x10000003 0x01\n") # Low limit, high limit, ?, ?, ? VFOs, ?
				self.append(b"0 0 0 0 0 0 0\n")
				self.append(b"0 0\n")                 # Tuning steps available, modes, steps
				self.append(b"0 0\n")                 # Filter sizes, mode, bandwidth
				self.append(b"0\n")                   # Max RIT
				self.append(b"0\n")                   # Max XIT
				self.append(b"0\n")                   # Max IF shift
				self.append(b"0\n")                   # "announces"
				self.append(b"\n")                    # Preamp settings
				self.append(b"\n")                    # Attenuator settings
				self.append(b"0x0\n")                 # has get func
				self.append(b"0x0\n")                 # has set func
				self.append(b"0x40000000\n")          # get s-meter level
				self.append(b"0x0\n")                 # set level
				self.append(b"0x0\n")                 # get param
				self.append(b"0x0\n")                 # set param
			elif ch == b'v':
				self.send_vfo()
			elif ch == b'f':
				arg, i = self.get_arg(cmd, i + 1)
				vfo = self.get_vfo(arg)
				self.append(bytes(str(self.get_freq(vfo))+'\n', 'ascii'))
			elif ch == b'm':
				arg1, i = self.get_arg(cmd, i + 1)
				self.send_mode()
			elif ch == b'l':
				arg1, i = self.get_arg(cmd, i + 1)
				arg2, i = self.get_arg(cmd, i + 1)
				sm = self._rigctld.rig.mainSMeter.value
				tbl = [[0, -54], [3, -48], [6, -36], [9, -24], [12, -12], [15, 0], [20, 20], [25, 40], [30, 60]]
				for j in range(len(tbl)):
					if sm < tbl[j][0]:
						break
				if j == 0:
					return tbl[0][1]
				if j >= len(tbl):
					return tbl[len(tbl)-1][1]
				interp = ((tbl[j][0] - sm) * (tbl[j][1] - tbl[j-1][1])) / (tbl[j][0] - tbl[j-1][0])
				val = tbl[j][1] - interp
				self.append(bytes(str(int(val))+'\n', 'ascii'))
			elif ch == b'\n':
				pass
			elif ch == b'q':
				self._rigctld.sel.unregister(self._conn)
				self._conn.close()
			elif ch == b's':
				arg, i = self.get_arg(cmd, i + 1)
				self.append(b'0\n')
				self.send_vfo()
			else:
				print('Unimplemented command: '+ch.decode('ascii')+' in '+str(cmd))
				self.append(b"RPRT -1\n")
			i += 1

	def append(self, buf):
		if buf is None:
			return
		self.outbuf += buf
		if not self.mask & selectors.EVENT_WRITE and self._conn.fileno() != -1:
			self.mask |= selectors.EVENT_WRITE
			self._rigctld.sel.modify(self._conn, self.mask, data = self)

	def read(self):
		data = self._conn.recv(1500)
		if data:
			self.inbuf += data
			while b'\n' in self.inbuf:
				i = self.inbuf.find(b'\n')
				self.handle(self.inbuf[0:i+1])
				self.inbuf = self.inbuf[i+1:]
		else:
			self._rigctld.sel.unregister(self._conn)
			self._conn.close()

	def write(self):
		sent = self._conn.send(self.outbuf)
		if sent > 0:
			self.outbuf = self.outbuf[sent:]
		if len(self.outbuf) == 0:
			self.mask &= ~selectors.EVENT_WRITE
			self._rigctld.sel.modify(self._conn, self.mask, data = self)

class rigctld:
	def __init__(self, rig):
		self.rig = rig
		self.sel = selectors.DefaultSelector()

	def accept(self, sock):
		conn, addr = sock.accept()
		conn.setblocking(False)
		rconn = rigctld_connection(self, conn)
		self.sel.register(conn, rconn.mask, data = rconn)

	def rigctldThread(self):
		sock = socket.socket()
		sock.bind(('localhost', 4532))
		sock.listen(100)
		sock.setblocking(False)
		self.sel.register(sock, selectors.EVENT_READ)
		while not self.rig._terminate:
			events = self.sel.select(0.1)
			for key, mask in events:
				if isinstance(key.data, rigctld_connection):
					if mask & selectors.EVENT_WRITE:
						key.data.write()
					if mask & selectors.EVENT_READ:
						key.data.read()
				else:
					self.accept(key.fileobj)
