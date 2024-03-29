import enum
import rig
import selectors
import socket
import sys

class error(enum.IntEnum):
	RIG_OK = 0
	RIG_EINVAL = -1        # invalid parameter
	RIG_ECONF = -2         # invalid configuration (serial,..)
	RIG_ENOMEM = -3        # memory shortage
	RIG_ENIMPL = -4        # function not implemented, but will be
	RIG_ETIMEOUT = -5      # communication timed out
	RIG_EIO = -6           # IO error, including open failed
	RIG_EINTERNAL = -7     # Internal Hamlib error, huh!
	RIG_EPROTO = -8        # Protocol error
	RIG_ERJCTED = -9       # Command rejected by the rig
	RIG_ETRUNC = -10       # Command performed, but arg truncated
	RIG_ENAVAIL = -11      # function not available
	RIG_ENTARGET = -12     # VFO not targetable
	RIG_BUSERROR = -13     # Error talking on the bus
	RIG_BUSBUSY = -14      # Collision on the bus
	RIG_EARG = -15         # NULL RIG handle or any invalid pointer parameter in get arg
	RIG_EVFO = -16         # Invalid VFO
	RIG_EDOM = -17         # Argument out of domain of func

class vfo(enum.Enum):
	# "Real" VFOs
	VFO_NONE = 0
	VFOA = 1	    # Main VFOA
	VFOB = 2            # Main VFOB
	VFOC = 4            # Sub VFO

	currVFO = (1 << 29)              # Mapped to one of the others (current "tunable channel"/VFO)
	MEM = (1 << 28)                  # Memory mode on current control receiver
	VFO = (1 << 27)                  # (last or any) VFO mode
	VFO_TX = ((1 << 27) | (1 << 29)) # VFO that will be used if you TX
	VFO_RX = (1 << 29)               # Same as currVFO for whatever that's worth, good thing there's two names for it!
	VFO_MAIN = (1 << 26)             # VFOA or VFOB
	VFO_SUB = (1 << 25)              # VFOC

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
		# General format:
		# <cmd> [VFO] ARG1 ARG2 ARG3
		# Some commands don't take a VFO argument
		# VFO argument is optional, if not specified, uses current
		# Each command has a fixed number of arguments
		# Some commands take an extra line (TODO: unclear on placement, newline before args, or after? looks like before: \send_morse HIHI OM\nARG1")
		# Up to three lines of output, one piece of information per line
		# Except dump_state which is special
		self.commands = {
			b'*': {
				'long': "reset",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Reset"],
				'out_args':[]
			},
			b'1': {
				'long': "dump_caps",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':[],
				'out_args':[]
			},
			b'2': {
				'long': "power2mW",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':["Power [0.0..1.0]", "Frequency", "Mode"],
				'out_args':["Power mW"]
			},
			b'3': {
				'long': "dump_conf",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':[],
				'out_args':[]
			},
			b'4': {
				'long': "mW2power",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':["Power mW", "Frequency", "Mode"],
				'out_args':["Power [0.0..1.0]"]
			},
			b'A': {
				'long': "set_trn",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':["Transceive"],
				'out_args':[]
			},
			b'a': {
				'long': "get_trn",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["Transceive"]
			},
			b'B': {
				'long': "set_bank",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Bank"],
				'out_args':[]
			},
			b'b': {
				'long': "send_morse",
				'noVFO': False,
				'fullLineCommand': True,
				'in_args':["Morse"],
				'out_args':[]
			},
			b'C': {
				'long': "set_ctcss_tone",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["CTCSS Tone"],
				'out_args':[]
			},
			b'c': {
				'long': "get_ctcss_tone",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["CTCSS Tone"]
			},
			b'D': {
				'long': "set_dcs_code",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["DCS Code"],
				'out_args':[]
			},
			b'd': {
				'long': "get_dcs_code",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["DCS Code"]
			},
			b'E': {
				'long': "set_mem",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Memory#"],
				'out_args':[]
			},
			b'e': {
				'long': "get_mem",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["Memory#"]
			},
			b'F': {
				'long': "set_freq",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Frequency"],
				'out_args':[],
				'handler': self._set_freq
			},
			b'f': {
				'long': "get_freq",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':[],
				'out_args':["Frequency"],
				'handler': self._get_freq
			},
			b'G': {
				'long': "vfo_op",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Mem/VFO Op"],
				'out_args':[],
				'handler': self._vfo_op
			},
			b'g': {
				'long': "scan",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Scan Fct", "Scan Channel"],
				'out_args':[]
			},
			b'H': {
				'long': "set_channel",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':["Channel"],
				'out_args':[]
			},
			b'h': {
				'long': "get_channel",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':["Channel"],
				'out_args':[]
			},
			b'I': {
				'long': "set_split_freq",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["TX Frequency"],
				'out_args':[]
			},
			b'i': {
				'long': "get_split_freq",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["TX Frequency"]
			},
			b'J': {
				'long': "set_rit",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["RIT"],
				'out_args':[]
			},
			b'j': {
				'long': "get_rit",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["RIT"]
			},
			b'L': {
				'long': "set_level",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Level", "Level Value"],
				'out_args':[]
			},
			b'l': {
				'long': "get_level",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Level"],
				'out_args':["Level Value"],
			},
			b'M': {
				'long': "set_mode",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Mode", "Passband"],
				'out_args':[],
				'handler': self._set_mode
			},
			b'm': {
				'long': "get_mode",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["Mode", "Passband"],
				'handler': self._get_mode
			},
			b'N': {
				'long': "set_ts",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Tuning Step"],
				'out_args':[]
			},
			b'n': {
				'long': "get_ts",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["Tuning Step"]
			},
			b'O': {
				'long': "set_rptr_offs",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Rptr Offset"],
				'out_args':[]
			},
			b'o': {
				'long': "get_rptr_offs",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["Rptr Offset"]
			},
			b'P': {
				'long': "set_parm",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':["Parm", "Parm Value"],
				'out_args':[]
			},
			b'p': {
				'long': "get_parm",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':["Parm"],
				'out_args':["Parm Value"]
			},
			b'q': {
				'long': "q",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':[],
				'out_args':[],
				'handler': self._quit
			},
			b'R': {
				'long': "set_rptr_shift",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Rptr Shift"],
				'out_args':[]
			},
			b'r': {
				'long': "get_rptr_shift",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["Rptr Shift"]
			},
			b'S': {
				'long': "set_split_vfo",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Split", "TX VFO"],
				'out_args':[],
				'handler': self._set_split_vfo
			},
			b's': {
				'long': "get_split_vfo",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["Split", "TX VFO"],
				'handler': self._get_split_vfo
			},
			b'T': {
				'long': "set_ptt",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["PTT"],
				'out_args':[],
				'handler': self._set_ptt
			},
			b't': {
				'long': "get_ptt",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["PTT"],
				'handler': self._get_ptt
			},
			b'U': {
				'long': "set_func",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Func" "Func Status"],
				'out_args':[]
			},
			b'u': {
				'long': "get_func",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Func"],
				'out_args':["Func Status"]
			},
			b'V': {
				'long': "set_vfo",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':["VFO"],
				'out_args':[],
				'handler': self._set_vfo
			},
			b'v': {
				'long': "get_vfo",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["VFO"],
				'handler':self._get_vfo
			},
			b'w': {
				'long': "send_cmd",
				'noVFO': True,
				'fullLineCommand': True,
				'in_args':["Cmd"],
				'out_args':["Reply"]
			},
			b'X': {
				'long': "set_split_mode",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["TX Mode", "TX Passband"],
				'out_args':[],
				'handler': self._set_split_mode
			},
			b'x': {
				'long': "get_split_mode",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["TX Mode", "TX Passband"]
			},
			b'Y': {
				'long': "set_ant",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Antenna"],
				'out_args':[]
			},
			b'y': {
				'long': "get_ant",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["Antenna"]
			},
			b'Z': {
				'long': "set_xit",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["XIT"],
				'out_args':[]
			},
			b'z': {
				'long': "get_xit",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["XIT"]
			},
			b'_': {
				'long': "get_info",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["Info"]
			},
			b'\x87': {
				'long': "set_powerstat",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':["Power Status"],
				'out_args':[]
			},
			b'\x88': {
				'long': "get_powerstat",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["Power Status"]
			},
			b'\x89': {
				'long': "send_dtmf",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["Digits"],
				'out_args':[]
			},
			b'\x8a': {
				'long': "recv_dtmf",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["Digits"]
			},
			b'\x8b': {
				'long': "get_dcd",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["DCD"]
			},
			b'\x8f': {
				'long': "dump_state",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':[],
				'out_args':[],
				'handler':self._dump_state
			},
			# rigctld only--check for VFO mode
			b'\xf0': {
				'long': "chk_vfo",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':[],
				'out_args':[],
				'handler': self._chk_vfo
			},
			# rigctld only--halt the daemon
			b'\xf1': {
				'long': "halt",
				'noVFO': True,
				'fullLineCommand': False,
				'in_args':[],
				'out_args':[]
			},
			b'\x90': {
				'long': "set_ctcss_sql",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["CTCSS Sql"],
				'out_args':[]
			},
			b'\x91': {
				'long': "get_ctcss_sql",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["CTCSS Sql"]
			},
			b'\x92': {
				'long': "set_dcs_sql",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args':["DCS Sql"],
				'out_args':[]
			},
			b'\x93': {
				'long': "get_dcs_sql",
				'noVFO': False,
				'fullLineCommand': False,
				'in_args': [],
				'out_args':["DCS Sql"]
			},
		}
		self._rigctld = rigctld
		self._conn = conn
		self._vfo_mode = None
		self.inbuf = b''
		self.outbuf = b''
		self.mask = selectors.EVENT_READ | selectors.EVENT_WRITE
		self.currVFO = vfo.VFOA # Bah.
		self.rxVFO = self.currVFO
		self.txVFO = self.currVFO

	def _vfo_op(self, command):
		if command['argv'][0] == '?':
			self.send_supported_vfo_ops()
			return
		if command['argv'][0] == 'TUNE':
			self._rigctld.rig.tuner_tx = 1
			self._rigctld.rig.tuner_list = [0, 1, 1]
			self.append(b'RPRT 0\n')
			return
		self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))

	def _chk_vfo(self, command):
		# Indicates that VFO parameters must be sent
		if self._vfo_mode is None:
			self._vfo_mode = True
		self.append(bytes("CHKVFO {:1d}\n".format(self._vfo_mode), 'ascii'))

	def _dump_state(self, command):
		# TODO: Flesh this out
		self.append(b"1\n")                   # Protocol version
		self.append(b"2\n")                   # Rig model (dummy)
		self.append(b"0\n")                   # ITU region (!)
		# RX info: lowest/highest freq, modes available, low power, high power, VFOs, antennas
		#self.append(b"30000 60000000 0x1ff -1 -1 0x6c000003 0x03\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		#self.append(b"142000000 151999999 0x1ff -1 -1 0xfc000007 0x00\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		#self.append(b"420000000 449999999 0x1ff -1 -1 0xfc000007 0x00\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		self.append(b"-1 -1 0x1ff -1 -1 0x03 0\n")
		# Terminated with all zeros
		self.append(b"0 0 0 0 0 0 0\n")
		# TX info (as above) we just lie and pretend we can TX everywhere.
		#self.append(b"30000 60000000 0x1ff 5 100 0x7c000003 0x03\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		#self.append(b"142000000 151999999 0x1ff 5 100 0xfc000007 0x00\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		#self.append(b"420000000 449999999 0x1ff 5 50 0xfc000007 0x00\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		self.append(b"-1 -1 0x1ff 1 100 0x03 0\n")
		self.append(b"0 0 0 0 0 0 0\n")
		self.append(b"0 0\n")                 # Tuning steps available, modes, steps (nobody cares, direct tune)
		self.append(b"0 0\n")                 # Filter sizes, mode, bandwidth (too many to list sanely)
		self.append(b"0\n")               # Max RIT
		self.append(b"0\n")               # Max XIT
		self.append(b"0\n")                # Max IF shift (but the min is 400)
		self.append(b"0\n")                # "announces"
		self.append(b"0\n")                  # Preamp settings (Not sure of this one...)
		self.append(b"0\n")                  # Attenuator settings (20dB if CN2 is removed)
		#self.append(b"0xe5fff7ff\n")          # has get func
		#self.append(b"0xe5fff7ff\n")          # has set func
		#self.append(b"0xfff7f97f\n")          # get levels
		#self.append(b"0x03f7f97f\n")          # set levels
		#self.append(b"0x4f\n")                # get param
		#self.append(b"0x4f\n")                # set param
		self.append(b"0\n")
		self.append(b"0\n")
		self.append(b"0\n")
		self.append(b"0\n")
		self.append(b"0\n")
		self.append(b"0\n")
		self.append(b"vfo_ops=0x800\n")
		self.append(b'done\n')

	def _set_vfo(self, command):
		vfo = self.parse_vfo(command['argv'][0])
		if vfo is None:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))

		if not vfo in (vfo.VFOA, vfo.VFOB):
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		self.currVFO = vfo
		if not self._rigctld.rig.split:
			self.rxVFO = vfo
		self.append(bytes('RPRT 0\n', 'ascii'))

	def _get_vfo(self, command):
		if self.currVFO == vfo.VFOA:
			self.append(b'VFOA\n')
		elif self.currVFO == vfo.VFOB:
			self.append(b'VFOB\n')
		else:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))

	def _get_freq(self, command):
		if command['vfo'] == self.rxVFO:
			self.append(bytes(str(self._rigctld.rig.rx_frequency)+'\n', 'ascii'))
		else:
			self.append(bytes(str(self._rigctld.rig.tx_frequency)+'\n', 'ascii'))

	def _get_mode(self, command):
		if command['vfo'] == self.rxVFO:
			mode = self._rigctld.rig.rx_mode
		else:
			mode = self._rigctld.rig.tx_mode
		self.send_mode(mode)
		self.append(bytes(str(2800) + '\n', 'ascii'))

	def send_supported_modes(self):
		self.append(bytes('USB LSB CW CWR RTTY RTTYR AM FM\n', 'ascii'))

	def send_supported_vfo_ops(self):
		self.append(bytes('TUNE\n', 'ascii'))

	def get_rig_mode(self, mode):
		ret = None
		if mode == 'USB':
			ret = rig.mode.USB
		if mode == 'LSB':
			ret = rig.mode.LSB
		if mode == 'CW':
			ret = rig.mode.CW
		if mode == 'CWR':
			ret = rig.mode.CW_REVERSED
		if mode == 'RTTY':
			ret = rig.mode.FSK
		if mode == 'RTTYR':
			ret = rig.mode.FSK_REVERSED
		if mode == 'AM':
			ret = rig.mode.AM
		if mode == 'FM':
			ret = rig.mode.FM
		return ret

	def _set_mode(self, command):
		vfo = command['vfo']
		if command['argv'][0] == '?':
			self.send_supported_modes()
			return
		if not self.isCurrentVFO(vfo):
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		mode = self.get_rig_mode(command['argv'][0])
		if mode is None:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		self._rigctld.rig.mode = mode
		# TODO: Passband...
		self.append(bytes('RPRT 0\n', 'ascii'))

	def _quit(self, command):
		self._rigctld.sel.unregister(self._conn)
		self._conn.close()

	def _set_split_vfo(self, command):
		# TODO: For some reason, Hamlib loves to split a VFO with itself (ie: 'S VFOA 1 VFOA')
		#       Figure out what the hell it's thinking and deal with that.
		#       Until then, we're just ignoring the VFO argument.
		txvfo = self.parse_vfo(command['argv'][1])
		if txvfo is None:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		if txvfo == vfo.VFOA:
			rxvfo = vfo.VFOB
		else:
			rxvfo = vfo.VFOA
		if command['argv'][0] == '0':
			self._rigctld.rig.split = False
			self.currVFO = rxvfo
			self.rxVFO = rxvfo
			self.txVFO = rxvfo
			self._rigctld.rig.split = False
		elif command['argv'][0] == '1':
			self._rigctld.rig.split = True
			self.currVFO = rxvfo
			self.rxVFO = rxvfo
			self.txVFO = txvfo
			self._rigctld.rig.split = True
		else:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		self.append(bytes('RPRT 0\n', 'ascii'))

	def _get_split_vfo(self, command):
		self.append(bytes('{:d}\n'.format(self._rigctld.rig.split), 'ascii'))
		if self.rxVFO == vfo.VFOA:
			self.append(b"VFOA\n")
		else:
			self.append(b"VFOB\n")

	def _set_ptt(self, command):
		vfo = command['vfo']
		if vfo in (vfo.VFOA, vfo.VFOB):
			self._rigctld.rig.tx = bool(int(command['argv'][0]))
		else:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		self.append(bytes('RPRT 0\n', 'ascii'))

	def _get_ptt(self, command):
		self.append(bytes('{:d}\n'.format(self._rigctld.rig.tx), 'ascii'))

	def _set_freq(self, command):
		vfo = command['vfo']
		# wsjtx (Hamlib?) sends this with six decimal places...
		freq = int(float(command['argv'][0]))
		if vfo == self.rxVFO:
			self._rigctld.rig.rx_frequency = freq
		else:
			self._rigctld.rig.tx_frequency = freq
		# If we return an error here, WSJT-X fails
		self.append(bytes('RPRT 0\n', 'ascii'))

	def _set_split_mode(self, command):
		# We ignore the VFO passed in and set the mode for both
		if not self._rigctld.rig.split:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		mode = self.get_rig_mode(command['argv'][0])
		if mode is None:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		self._rigctld.rig.rx_mode = mode
		self._rigctld.rig.tx_mode = mode
		self.append(bytes('RPRT 0\n', 'ascii'))

	'''
	We're just here to map a VFO to VFOA, or VFOB
	If that's not possible, return None
	This should be used by all the set functions
	'''
	def grokVFO(self, rvfo):
		# Deal with braindead split mode... currVFO is the last chosen VFO which may be TX or RX
		# The ever-amazing 'VFO' VFO of course could be anything... we'll pretend it's currVFO
		# to preserve our sanity.
		if rvfo == vfo.VFO:
			return self.rxVFO
		if rvfo == vfo.currVFO:
			return self.currVFO
		elif rvfo == vfo.VFOA or rvfo == vfo.VFOB:
			return rvfo
		elif rvfo == vfo.VFO_MAIN:
			return self.rxVFO
		elif rvfo == vfo.VFO_RX:
			return self.rxVFO
		elif rvfo == vfo.VFO_TX:
			return self.txVFO
		return None

	def isCurrentVFO(self, rvfo):
		if rvfo == self.currVFO:
			return True
		return False

	def shorten(self, cmd):
		if b'\\' in cmd:
			for lng, sht in self.long2short.items():
				cmd = cmd.replace(lng, sht)
		return cmd

	def get_arg(self, cmd, offset):
		if cmd[offset:offset+1] == b' ':
			while cmd[offset:offset+1] == b' ' and cmd[offset:offset+1] != b'':
				offset += 1
			start = offset
			while cmd[offset:offset+1] != b' ' and cmd[offset:offset+1] != b'':
				offset += 1
			end = offset
			if start != end:
				return (cmd[start:end], offset)
		return None, offset

	def send_mode(self, mode):
		if mode == rig.mode.AM:
			self.append(b'AM\n')
		elif mode == rig.mode.FM:
			self.append(b'FM\n')
		elif mode == rig.mode.USB:
			self.append(b'USB\n')
		elif mode == rig.mode.LSB:
			self.append(b'LSB\n')
		elif mode == rig.mode.CW:
			self.append(b'CW\n')
		elif mode == rig.mode.CW_REVERSED:
			self.append(b'CWR\n')
		elif mode == rig.mode.FSK:
			self.append(b'RTTY\n')
		elif mode == rig.mode.FSK_REVERSED:
			self.append(b'RTTYR\n')
		else:
			self.append(b'\n')

	def parse_vfo(self, name):
		vfo_mapping = {
			'VFOA': vfo.VFOA,
			'VFOB': vfo.VFOB,
			'currVFO': vfo.currVFO,
			'VFO': vfo.VFO,
			'TX': vfo.VFO_TX,
			'RX': vfo.VFO_RX,
			'Main': vfo.VFO_MAIN,
		}
		if name in vfo_mapping:
			return self.grokVFO(vfo_mapping[name])
		return None

	def parse_command_line(self, cmd):
		ret = {}
		offset = 0
		while cmd[offset:offset+1] == b' ':
			offset += 1
		if not cmd[offset:offset+1] in self.commands:
			return {
				'error': error.RIG_EPROTO,
				'message': 'No such command'
			}
		command = self.commands[cmd[offset:offset+1]]
		ret['cmd'] = command
		offset += 1

		cmdVFO = self.grokVFO(vfo.currVFO)
		if command['noVFO'] != True:
			# This guesses the remote features...
			# If it sends a VFO after a command, we assume it supports
			# VFO mode, and we enable it and require it after that.
			# If not, we assume the opposite.
			#
			# If we get a chk_vfo command, we assume it is supported.
			if self._vfo_mode is None or self._vfo_mode == True:
				maybeVFO, vfo_offset = self.get_arg(cmd, offset)
				if maybeVFO is not None:
					chkVFO = self.parse_vfo(maybeVFO.decode('ascii'))
					if chkVFO is not None:
						offset = vfo_offset
						cmdVFO = chkVFO
				else:
					if self._vfo_mode is None:
						self._vfo_mode = False
					else:
						return {
							'error': error.RIG_EINVAL,
							'message': 'No VFO specified'
						}

		ret['vfo'] = cmdVFO

		ret['argv'] = []
		if command['fullLineCommand']:
			if cmd[offset:offset+1] != b' ':
				return {
					'error': error.RIG_EINVAL,
					'message': 'Missing full line ' + command['in_args'][0] + ' argument.'
				}
			ret['argv'].append(cmd[offset:].decode('ascii'))
		else:
			for a in range(len(command['in_args'])):
				arg, offset = self.get_arg(cmd, offset)
				if arg is None:
					return {
						'error': error.RIG_EINVAL,
						'message': 'Missing ' + command['in_args'][0] + ' argument.'
					}
				ret['argv'].append(arg.decode('ascii'))
		ret['endoffset'] = offset
		return ret

	def handle(self, cmd):
		cmd = self.shorten(cmd)
		while len(cmd):
			if self._rigctld.verbose:
				print('Raw command: '+str(cmd), file=sys.stderr)
			command = self.parse_command_line(cmd)
			if 'error' in command:
				self.append(bytes('RPRT {:d}\n'.format(command['error']), 'ascii'))
				print('ERROR: ' + command['message'], file=sys.stderr)
				return
			if self._rigctld.verbose:
				print('Parsed command: ' + command['cmd']['long'], end='', file=sys.stderr)
				if not command['cmd']['noVFO']:
					print(' '+str(command['vfo']), end='', file=sys.stderr)
				for i in range(len(command['cmd']['in_args'])):
					print(' ' + command['cmd']['in_args'][i]+'='+command['argv'][i], end='', file=sys.stderr)
				print('', file=sys.stderr)
			if 'handler' not in command['cmd']:
				self.append(bytes('RPRT {:d}\n'.format(error.RIG_ENIMPL), 'ascii'))
				print('ERROR: ' + command['cmd']['long'] + ' command not implemented', file=sys.stderr)
				return
			cmd = cmd[command['endoffset']:]
			command['cmd']['handler'](command)

	def append(self, buf):
		if buf is None:
			return
		self.outbuf += buf
		if (not self.mask & selectors.EVENT_WRITE) and self._conn.fileno() != -1:
			self.mask |= selectors.EVENT_WRITE
			self._rigctld.sel.modify(self._conn, self.mask, data = self)

	def read(self):
		data = self._conn.recv(1500)
		if data:
			self.inbuf += data
			while b'\n' in self.inbuf:
				i = self.inbuf.find(b'\n')
				self.handle(self.inbuf[0:i])
				self.inbuf = self.inbuf[i+1:]
		else:
			self._rigctld.sel.unregister(self._conn)
			self._conn.close()

	def write(self):
		sent = self._conn.send(self.outbuf)
		if sent > 0:
			if self._rigctld.verbose:
				print('Sent response: '+str(self.outbuf[:sent]), file=sys.stderr)
			self.outbuf = self.outbuf[sent:]
		if len(self.outbuf) == 0:
			self.mask &= ~selectors.EVENT_WRITE
			self._rigctld.sel.modify(self._conn, self.mask, data = self)

class rigctld:
	def __init__(self, rigobj, address = 'localhost', port = 4532, verbose = False):
		self.rig = rigobj
		self.verbose = verbose
		self.sel = selectors.DefaultSelector()
		self._address = address
		self._port = port

	def accept(self, sock):
		conn, addr = sock.accept()
		conn.setblocking(False)
		rconn = rigctld_connection(self, conn)
		self.sel.register(conn, rconn.mask, data = rconn)

	def rigctldThread(self):
		sock = socket.socket()
		sock.bind((self._address, self._port))
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
