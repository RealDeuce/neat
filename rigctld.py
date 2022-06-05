import enum
import kenwood
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
				'out_args':[]
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
				'handler': self._get_level
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
		# Hamlib braindead split mode.
		# In braindead split mode, set_vfo is not expected to change either the RX or TX VFO.
		# Instead, it just changes the current VFO that commands will be applied to.
		# When not in braindead mode though, it's expected to change both the RX and TX VFOs.
		# currVFO is always the "you know what I mean" VFO, even if you don't.
		self.bd_split = self._rigctld.rig.split.value
		self.currVFO = vfo.VFOA # Bah.
		if self._rigctld.rig.controlMain:
			if self._rigctld.rig.RXtuningMode == kenwood.tuningMode.VFOB:
				self.currVFO = vfo.VFOB
			else:
				self.currVFO = vfo.VFOA
		else:
			self.currVFO = vfo.VFOC
		self.rxVFO = self.currVFO

	def synchronize_vfo(self):
		if not self._rigctld.rig.controlMain.value:
			self.bd_split = False
			self.currVFO = vfo.VFOC
			self.rxVFO = vfo.VFOC
		elif self._rigctld.rig.split.value:
			self.bd_split = True
			rigRX = vfo.VFOA
			if self._rigctld.rig.RXtuningMode.value != kenwood.tuningMode.VFOA:
				rigRX = vfo.VFOB
			rigTX = vfo.VFOB
			if self._rigctld.rig.TXtuningMode.value != kenwood.tuningMode.VFOB:
				rigTX = vfo.VFOA
			self.currVFO = rigRX
			if self._rigctld.rig.transmitSet.value:
				tmpTX = rigTX
				rigTX = rigRX
				rigRX = tmpTX
			self.rxVFO = rigRX
		else:
			self.bd_split = False
			if self._rigctld.rig.RXtuningMode.value != kenwood.tuningMode.VFOB:
				self.rxVFO = vfo.VFOA
				self.currVFO = vfo.VFOA
			else:
				self.rxVFO = vfo.VFOB
				self.currVFO = vfo.VFOB

	def _chk_vfo(self, command):
		# Indicates that VFO parameters must be sent
		if self._vfo_mode is None:
			self._vfo_mode = True
		self.append(bytes("CHKVFO {:1d}\n".format(self._vfo_mode), 'ascii'))

	def _dump_state(self, command):
		# TODO: Flesh this out
		self.append(b"0\n")                   # Protocol version
		self.append(b"2\n")                   # Rig model (dummy)
		self.append(b"2\n")                   # ITU region (!)
		# RX info: lowest/highest freq, modes available, low power, high power, VFOs, antennas
		self.append(b"30000 60000000 0x1ff -1 -1 0x6c000003 0x03\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		self.append(b"142000000 151999999 0x1ff -1 -1 0xfc000007 0x00\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		self.append(b"420000000 449999999 0x1ff -1 -1 0xfc000007 0x00\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		# Terminated with all zeros
		self.append(b"0 0 0 0 0 0 0\n")
		# TX info (as above) we just lie and pretend we can TX everywhere.
		self.append(b"30000 60000000 0x1ff 5 100 0x7c000003 0x03\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		self.append(b"142000000 151999999 0x1ff 5 100 0xfc000007 0x00\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		self.append(b"420000000 449999999 0x1ff 5 50 0xfc000007 0x00\n") # Low limit, high limit, ?, ?, ? VFOs, ?
		self.append(b"0 0 0 0 0 0 0\n")
		self.append(b"0 0\n")                 # Tuning steps available, modes, steps (nobody cares, direct tune)
		self.append(b"0 0\n")                 # Filter sizes, mode, bandwidth (too many to list sanely)
		self.append(b"20000\n")               # Max RIT
		self.append(b"20000\n")               # Max XIT
		self.append(b"1000\n")                # Max IF shift (but the min is 400)
		self.append(b"0x1f\n")                # "announces"
		self.append(b"20\n")                  # Preamp settings (Not sure of this one...)
		self.append(b"12\n")                  # Attenuator settings (20dB if CN2 is removed)
		#self.append(b"0xe5fff7ff\n")          # has get func
		#self.append(b"0xe5fff7ff\n")          # has set func
		#self.append(b"0xfff7f97f\n")          # get levels
		#self.append(b"0x03f7f97f\n")          # set levels
		#self.append(b"0x4f\n")                # get param
		#self.append(b"0x4f\n")                # set param
		self.append(b"0\n")
		self.append(b"0\n")
		self.append(b"0x40000000\n")
		self.append(b"0\n")
		self.append(b"0\n")
		self.append(b"0\n")

	def _set_vfo(self, command):
		vfo = self.parse_vfo(command['argv'][0])
		if vfo is None:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))

		if self.bd_split:
			if not vfo in (vfo.VFOA, vfo.VFOB):
				self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			self.currVFO = vfo
			self._rigctld.rig.transmitSet.value = (vfo != self.rxVFO)
			self.append(bytes('RPRT 0\n', 'ascii'))
			return

		if vfo == vfo.VFOA:
			self._rigctld.rig.controlMain.value = True
			self._rigctld.rig.TXmain.value = True
			self._rigctld.rig.RXtuningMode.value = kenwood.tuningMode.VFOA
			self._rigctld.rig.TXtuningMode.value = kenwood.tuningMode.VFOA
		elif vfo == vfo.VFOB:
			self._rigctld.rig.controlMain.value = True
			self._rigctld.rig.TXmain.value = True
			self._rigctld.rig.RXtuningMode.value = kenwood.tuningMode.VFOB
			self._rigctld.rig.TXtuningMode.value = kenwood.tuningMode.VFOB
		elif vfo == vfo.VFOC:
			self._rigctld.rig.controlMain.value = False
			self._rigctld.rig.TXmain.value = False
			self._rigctld.rig.RXtuningMode.value = kenwood.tuningMode.VFOA
			self._rigctld.rig.TXtuningMode.value = kenwood.tuningMode.VFOA
		else:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		self.currVFO = vfo
		self.rxVFO = vfo
		self.append(bytes('RPRT 0\n', 'ascii'))

	def _get_vfo(self, command):
		if self.currVFO == vfo.VFOA:
			self.append(b'VFOA\n')
		elif self.currVFO == vfo.VFOB:
			self.append(b'VFOB\n')
		elif self.currVFO == vfo.VFOC:
			self.append(b'VFOC\n')
		else:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))

	def _get_freq(self, command):
		# wsjtx/hamlib does set/get/set so this needs to be uncached. :(
		rmode = self._rigctld.rig.RXtuningMode.value
		if command['vfo'] == vfo.VFOA:
			self.append(bytes(str(self._rigctld.rig.vfoAFrequency.value)+'\n', 'ascii'))
		elif command['vfo'] == vfo.VFOB:
			self.append(bytes(str(self._rigctld.rig.vfoBFrequency.value)+'\n', 'ascii'))
		elif command['vfo'] == vfo.VFOC:
			self.append(bytes(str(self._rigctld.rig.subReceiverFrequency.value)+'\n', 'ascii'))
		else:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))

	def _get_mode(self, command):
		if command['vfo'] == vfo.VFOA:
			mode = self._rigctld.rig.VFOAmode.value
		elif command['vfo'] == vfo.VFOB:
			mode = self._rigctld.rig.VFOBmode.value
		elif command['vfo'] == vfo.VFOC:
			mode = self._rigctld.rig.subMode.value
		else:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL, 'ascii')))
			return
		if mode is None:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINTERNAL), 'ascii'))
		self.send_mode(mode)

		# Now figure out the filter width (le sigh)
		# First, we need to figure out if we're on the main receiver.
		# if we're not, the filter is fixed (likely at 2800, but who cares?)
		if command['vfo'] == vfo.VFOC:
			self.append(bytes(str(2800) + '\n', 'ascii'))
		else:
			if mode in (kenwood.mode.CW, kenwood.mode.CW_REVERSED, kenwood.mode.FSK, kenwood.mode.FSK_REVERSED):
				self.append(bytes(str(self._rigctld.rig.filterWidth.value) + '\n', 'ascii'))
			elif mode in (kenwood.mode.FM, kenwood.mode.LSB, kenwood.mode.USB):
				highfreq = [1400, 1600, 1800, 2000, 2200, 2400, 2600, 2800, 3000, 3400, 4000, 5000][self._rigctld.rig.voiceLowPassCutoff.value]
				lowfreq = [10, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000][self._rigctld.rig.voiceHighPassCutoff.value]
				self.append(bytes(str(highfreq - lowfreq) + '\n', 'ascii'))
			elif mode == kenwood.mode.AM:
				highfreq = [2500, 3000, 4000, 5000][self._rigctld.rig.voiceLowPassCutoff.value]
				lowfreq = [10, 100, 200, 500][self._rigctld.rig.voiceHighPassCutoff.value]
				self.append(bytes(str(highfreq - lowfreq) + '\n', 'ascii'))

	def send_supported_modes(self):
		self.append(bytes('USB LSB CW CWR RTTY RTTYR AM FM\n', 'ascii'))

	def get_rig_mode(self, mode):
		ret = None
		if mode == 'USB':
			ret = kenwood.mode.USB
		if mode == 'LSB':
			ret = kenwood.mode.LSB
		if mode == 'CW':
			ret = kenwood.mode.CW
		if mode == 'CWR':
			ret = kenwood.mode.CW_REVERSED
		if mode == 'RTTY':
			ret = kenwood.mode.FSK
		if mode == 'RTTYR':
			ret = kenwood.mode.FSK_REVERSED
		if mode == 'AM':
			ret = kenwood.mode.AM
		if mode == 'FM':
			ret = kenwood.mode.FM
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
		self._rigctld.rig.mode.value = mode
		# TODO: Passband...
		self.append(bytes('RPRT 0\n', 'ascii'))

	def _get_level(self, command):
		if command['argv'][0] == 'STRENGTH':
			sm = self._rigctld.rig.mainSMeter.value
			tbl = [[0, -54], [3, -48], [6, -36], [9, -24], [12, -12], [15, 0], [20, 20], [25, 40], [30, 60]]
			for j in range(len(tbl)):
				if sm < tbl[j][0]:
					break
			if j == 0:
				val = 0
			else:
				if j >= len(tbl):
					val = tbl[len(tbl)-1][1]
				else:
					interp = ((tbl[j][0] - sm) * (tbl[j][1] - tbl[j-1][1])) / (tbl[j][0] - tbl[j-1][0])
					val = tbl[j][1] - interp
			self.append(bytes(str(int(val))+'\n', 'ascii'))
		elif command['argv'][0] == 'RAWSTR':
			self.append(bytes(str(self._rigctld.rig.mainSMeter.value)+'\n', 'ascii'))
		elif command['argv'][0] in ('PREAMP', 'ATT', 'VOX', 'AF', 'RF', 'SQL', 'IF', 'NR', 'CWPITCH', 'RFPOWER', 'MICGAIN', 'KEYSPD', 'NOTCHF', 'COMP', 'AGC', 'BKINDL', 'METER', 'VOXGAIN', 'ANTIVOX', 'SLOPE_LOW', 'SLOPE_HIGH', 'BKIN_DLYMS', 'SQLSTAT', 'SWR', 'ALC'):
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_ENIMPL), 'ascii'))
		else:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))

	def _quit(self, command):
		self._rigctld.sel.unregister(self._conn)
		self._conn.close()

	def _set_split_vfo(self, command):
		# TODO: For some reason, Hamlib loves to split a VFO with itself (ie: 'S VFOA 1 VFOA')
		#       Figure out what the hell it's thinking and deal with that.
		#       Untel then, we're just ignoring the VFO argument.
		txvfo = self.parse_vfo(command['argv'][1])
		if txvfo is None or txvfo == vfo.VFOC:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		if txvfo == vfo.VFOA:
			rxvfo = vfo.VFOB
		else:
			rxvfo = vfo.VFOA
		self._rigctld.rig.controlMain.value = True
		if command['argv'][0] == '0':
			self.currVFO = rxvfo
			self.rxVFO = rxvfo
			self._rigctld.rig.transmitSet.value = False
			if rxvfo == vfo.VFOA:
				self._rigctld.rig.RXtuningMode.value = kenwood.tuningMode.VFOA
				self._rigctld.rig.TXtuningMode.value = kenwood.tuningMode.VFOA
			elif rxvfo == vfo.VFOB:
				self._rigctld.rig.RXtuningMode.value = kenwood.tuningMode.VFOB
				self._rigctld.rig.TXtuningMode.value = kenwood.tuningMode.VFOB
		elif command['argv'][0] == '1':
			self.currVFO = rxvfo
			self.rxVFO = rxvfo
			self._rigctld.rig.transmitSet.value = False
			if rxvfo == vfo.VFOA:
				self._rigctld.rig.RXtuningMode.value = kenwood.tuningMode.VFOA
			elif rxvfo == vfo.VFOB:
				self._rigctld.rig.RXtuningMode.value = kenwood.tuningMode.VFOB
			if txvfo == vfo.VFOA:
				self._rigctld.rig.TXtuningMode.value = kenwood.tuningMode.VFOA
			elif txvfo == vfo.VFOB:
				self._rigctld.rig.TXtuningMode.value = kenwood.tuningMode.VFOB
		else:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		self.append(bytes('RPRT 0\n', 'ascii'))

	def _get_split_vfo(self, command):
		self.append(bytes('{:d}\n'.format(self.bd_split), 'ascii'))
		if self.bd_split:
			if self.rxVFO == vfo.VFOA:
				self.append(b"VFOB\n")
			elif self.rxVFO == vfo.VFOB:
				self.append(b"VFOA\n")
			elif self.rxVFO == vfo.VFOC:
				self.append(b"VFOC\n")
		else:
			if command['vfo'] == vfo.VFOA:
				self.append(b"VFOB\n")
			elif command['vfo'] == vfo.VFOB:
				self.append(b"VFOA\n")
			elif command['vfo'] == vfo.VFOC:
				self.append(b"VFOC\n")

	def _set_ptt(self, command):
		vfo = command['vfo']
		if vfo in (vfo.VFOA, vfo.VFOB) and self._rigctld.rig.TXmain.value:
			self._rigctld.rig.currentReceiverTransmitting.value = bool(int(command['argv'][0]))
		elif vfo == vfo.VFOC and (not self._rigctld.rig.TXmain.value):
			self._rigctld.rig.currentReceiverTransmitting.value = bool(int(command['argv'][0]))
		else:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		self.append(bytes('RPRT 0\n', 'ascii'))

	def _get_ptt(self, command):
		vfo = command['vfo']
		val = 0
		if vfo == vfo.VFOA and self._rigctld.rig.TXmain.value and self._rigctld.rig.TXtuningMode.value == kenwood.tuningMode.VFOA:
			if self._rigctld.rig.mainTransmitting.value:
				val = 1
		elif vfo == vfo.VFOB and self._rigctld.rig.TXmain.value and self._rigctld.rig.TXtuningMode.value == kenwood.tuningMode.VFOB:
			if self._rigctld.rig.mainTransmitting.value:
				val = 1
		elif vfo == vfo.VFOC and (not self._rigctld.rig.TXmain.value) and self._rigctld.rig.TXtuningMode.value == kenwood.tuningMode.VFOA:
			if self._rigctld.rig.subTransmitting.value:
				val = 1
		self.append(bytes('{:d}\n'.format(val), 'ascii'))

	def _set_freq(self, command):
		vfo = command['vfo']
		rprt = error.RIG_EINVAL
		# wsjtx (Hamlib?) sends this with six decimal places...
		freq = int(float(command['argv'][0]))
		if vfo == vfo.VFOA:
			self._rigctld.rig.vfoAFrequency.value = freq
			rprt = 0
		if vfo == vfo.VFOB:
			self._rigctld.rig.vfoBFrequency.value = freq
			rprt = 0
		if vfo == vfo.VFOC:
			self._rigctld.rig.subReceiverFrequency.value = freq
			rprt = 0
		self.append(bytes('RPRT {:d}\n'.format(rprt), 'ascii'))

	def _set_split_mode(self, command):
		# We ignore the VFO passed in and set the mode for both
		if not self.bd_split:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		mode = self.get_rig_mode(command['argv'][0])
		if mode is None:
			self.append(bytes('RPRT {:d}\n'.format(error.RIG_EINVAL), 'ascii'))
			return
		# Start with the not current one...
		oldts = self._rigctld.rig.transmitSet.value
		self._rigctld.rig.transmitSet.value = (not oldts)
		self._rigctld.rig.mode.value = mode
		self._rigctld.rig.transmitSet.value = (oldts)
		self._rigctld.rig.mode.value = mode
		self.append(bytes('RPRT 0\n', 'ascii'))

	'''
	We're just here to map a VFO to VFOA, B, or C
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
		elif rvfo == vfo.VFOA or rvfo == vfo.VFOB or rvfo == vfo.VFOC:
			return rvfo
		elif rvfo == vfo.VFO_MAIN:
			if self.bd_split:
				return self.rxVFO
			if self._rigctld.rig.mainRXtuningMode.value == kenwood.tuningMode.VFOA:
				return vfo.VFOA
			elif self._rigctld.rig.mainRXtuningMode.value == kenwood.tuningMode.VFOB:
				return vfo.VFOB
		elif rvfo == vfo.VFO_SUB:
			if self._rigctld.rig.subTuningMode.value == kenwood.tuningMode.VFOA:
				return vfo.VFOC
		elif rvfo == vfo.VFO_RX:
			return self.rxVFO
		elif rvfo == vfo.VFO_TX:
			if self.bd_split:
				if self.rxVFO == vfo.VFOA:
					return vfo.VFOB
				else:
					return vfo.VFOA
			else:
				return self.rxVFO
		return None

	def isCurrentVFO(self, rvfo):
		if rvfo == vfo.VFOA:
			if self._rigctld.rig.controlMain.value == True:
				if self._rigctld.rig.tuningMode.value == kenwood.tuningMode.VFOA:
					return True
		elif rvfo == vfo.VFOB:
			if self._rigctld.rig.controlMain.value == True:
				if self._rigctld.rig.tuningMode.value == kenwood.tuningMode.VFOB:
					return True
		elif rvfo == vfo.VFOC:
			if self._rigctld.rig.controlMain.value == False:
				if self._rigctld.rig.tuningMode.value == kenwood.tuningMode.VFOA:
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

	def parse_vfo(self, name):
		vfo_mapping = {
			'VFOA': vfo.VFOA,
			'VFOB': vfo.VFOB,
			'VFOC': vfo.VFOC,
			'currVFO': vfo.currVFO,
			'MEM': vfo.MEM,
			'VFO': vfo.VFO,
			'TX': vfo.VFO_TX,
			'RX': vfo.VFO_RX,
			'Main': vfo.VFO_MAIN,
			'Sub': vfo.VFO_SUB
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
			self.synchronize_vfo()
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
				self.append(bytes('RPRT {:d}'.format(error.RIG_ENIMPL), 'ascii'))
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
	def __init__(self, rig, address = 'localhost', port = 4532, verbose = False):
		self.rig = rig
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
