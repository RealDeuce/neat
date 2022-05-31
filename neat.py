# Copyright (c) 2022 Stephen Hurd
# Developers:
# Stephen Hurd (K6BSD/VE5BSD) <shurd@sasktel.net>
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

import kenwood
import math
import re
import time
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle
from kivy.properties import BooleanProperty, BoundedNumericProperty, ColorProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.checkbox import CheckBox
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
import kivy.utils
from gardengauge import Gauge

rig = kenwood.Kenwood("/dev/ttyU0", 57600, 1)
vfoa = int(kenwood.tuningMode.VFOA)
vfob = int(kenwood.tuningMode.VFOB)
mem = int(kenwood.tuningMode.MEMORY)
call = int(kenwood.tuningMode.CALL)
ids = None

class Neat(FloatLayout):
	def control(self, **kwargs):
		for k in kwargs.keys():
			rig.setState(k, kwargs[k])

class Smeter(Gauge):
	rig_state = StringProperty()

	def __init__(self, **kwargs):
		# Gauge variables
		self.file_gauge = 'gardengauge/smeter.png'
		self.unit = 6
		self.peak_hold = 0.5
		self.size_gauge = 128
		self.size_text = 20
		# Local variables
		self.all_updates = dict()
		self.timed_event = None
		self.lastval = 0
		self.lastinc = 0
		self.pos = (10, 10)
		super(Smeter, self).__init__(**kwargs)
		self.value = rig.queryState('mainSMeter')
		rig.callback['mainSMeter'] = self.update
		self._turn()

	def target(self):
		# Eliminate values older than peak_hold
		now = time.time()
		cutoff = now - self.peak_hold
		for t in list(self.all_updates):
			if t < cutoff:
				del self.all_updates[t]
		# Find highest value
		sz = len(self.all_updates)
		if sz < 1:
			return (now, self.lastval)
		byval = dict(sorted(self.all_updates.items(), key = lambda x:x[1]))
		return (list(byval.keys())[sz - 1], list(byval.values())[sz - 1])

	def schedule(self):
		highval = self.target()
		if self.timed_event is not None:
			self.timed_event.cancel()
		if highval[1] != self.value:
			self.timed_event = Clock.schedule_once(lambda *t: self.tick(), 0.01)
		else:
			self.timed_event = Clock.schedule_once(lambda *t: self.tick(), (self.peak_hold - (time.time() - highval[0])))

	def tick(self):
		self.timed_event = None
		highval = self.target()
		if self.value != highval[1]:
			if highval[1] > self.value:
				inc = 3
				if self.lastinc > 0:
					inc = self.lastinc * 1.1
				newval = self.value + inc
				self.lastinc = inc
				if highval[1] < newval:
					newval = highval[1]
			else:
				inc = -0.02
				if self.lastinc < 0:
					inc = self.lastinc * 1.1
				newval = self.value + inc
				self.lastinc = inc
				if highval[1] > newval:
					newval = highval[1]
			self.value = newval
		else:
			self.lastinc = 0
		self.schedule()

	def update(self, value):
		if self._img_gauge != 'gardengauge/SWR.png':
			self.all_updates = {}
			self.lastval = value
		else:
			self._progress.value = value * 10 / 3
			now = time.time()
			self.lastval = value
			if now in self.all_updates:
				if value < self.all_updates[now]:
					return
			self.all_updates[now] = value
		self.schedule()

	def _turn(self, *args):
		'''
		Turn needle, 1 degree = 1 unit, 0 degree point start on 50 value.
		'''
		self._needle.center_x = self._gauge.center_x
		self._needle.center_y = self._gauge.center_y
		self._needle.rotation = (15 * self.unit) - (self.value * self.unit)
		if self._img_gauge != 'gardengauge/smeter.png':
			self._glab.text = ''
		else:
			if self.value < 16:
				self._glab.text = "S[b]{0:.0f}[/b]".format(self.value*9/15)
			else:
				self._glab.text = "+[b]{0:.0f}[/b]".format((self.value-15)*60/15)

class SWRmeter(Gauge):
	def __init__(self, **kwargs):
		# Gauge variables
		self.file_gauge = 'gardengauge/SWR.png'
		self.unit = 6
		self.size_gauge = 128
		self.size_text = 0
		# Local variables
		self.all_updates = dict()
		self.timed_event = None
		self.lastval = 0
		self.lastinc = 0
		self.pos = (10, 10)
		super(SWRmeter, self).__init__(**kwargs)
		self.value = 0
		rig.callback['SWRmeter'] = self.update
		self._turn()

	def target(self):
		return self.lastval

	def schedule(self):
		highval = self.target()
		if self.timed_event is not None:
			self.timed_event.cancel()
		if highval != self.value:
			self.timed_event = Clock.schedule_once(lambda *t: self.tick(), 0.01)

	def tick(self):
		self.timed_event = None
		highval = self.target()
		if self.value != highval:
			if highval > self.value:
				inc = 3
				if self.lastinc > 0:
					inc = self.lastinc * 1.1
				newval = self.value + inc
				self.lastinc = inc
				if highval < newval:
					newval = highval
			else:
				inc = -0.02
				if self.lastinc < 0:
					inc = self.lastinc * 1.1
				newval = self.value + inc
				self.lastinc = inc
				if highval > newval:
					newval = highval
			self.value = newval
		else:
			self.lastinc = 0
		self.schedule()

	def update(self, value):
		self.lastval = value
		self.schedule()

	def _turn(self, *args):
		'''
		Turn needle, 1 degree = 1 unit, 0 degree point start on 50 value.
		'''
		self._needle.center_x = self._gauge.center_x
		self._needle.center_y = self._gauge.center_y
		self._needle.rotation = (15 * self.unit) - (self.value * self.unit)
		if self.value < 16:
			self._glab.text = "S[b]{0:.0f}[/b]".format(self.value*9/15)
		else:
			self._glab.text = "+[b]{0:.0f}[/b]".format((self.value-15)*60/15)

class COMPmeter(Gauge):
	def __init__(self, **kwargs):
		# Gauge variables
		self.file_gauge = 'gardengauge/comp.png'
		self.unit = 6
		self.size_gauge = 128
		self.size_text = 0
		# Local variables
		self.all_updates = dict()
		self.timed_event = None
		self.lastval = 0
		self.lastinc = 0
		self.pos = (10, 10)
		super(COMPmeter, self).__init__(**kwargs)
		self.value = 0
		rig.callback['SWRmeter'] = self.update
		self._turn()

	def target(self):
		return self.lastval

	def schedule(self):
		highval = self.target()
		if self.timed_event is not None:
			self.timed_event.cancel()
		if highval != self.value:
			self.timed_event = Clock.schedule_once(lambda *t: self.tick(), 0.01)

	def tick(self):
		self.timed_event = None
		highval = self.target()
		if self.value != highval:
			if highval > self.value:
				inc = 3
				if self.lastinc > 0:
					inc = self.lastinc * 1.1
				newval = self.value + inc
				self.lastinc = inc
				if highval < newval:
					newval = highval
			else:
				inc = -0.02
				if self.lastinc < 0:
					inc = self.lastinc * 1.1
				newval = self.value + inc
				self.lastinc = inc
				if highval > newval:
					newval = highval
			self.value = newval
		else:
			self.lastinc = 0
		self.schedule()

	def update(self, value):
		self.lastval = value
		self.schedule()

	def _turn(self, *args):
		'''
		Turn needle, 1 degree = 1 unit, 0 degree point start on 50 value.
		'''
		self._needle.center_x = self._gauge.center_x
		self._needle.center_y = self._gauge.center_y
		self._needle.rotation = (15 * self.unit) - (self.value * self.unit)
		if self.value < 11:
			self._glab.text = "{0:.0f}dB".format(self.value*9/15)
		else:
			self._glab.text = "[color=#F00]{0:.0f}[/color]dB".format((self.value-15)*60/15)
class ALCmeter(Gauge):
	rig_state = StringProperty()

	def __init__(self, **kwargs):
		# Gauge variables
		self.file_gauge = 'gardengauge/ALC.png'
		self.unit = 6
		self.peak_hold = 0.5
		self.size_gauge = 128
		self.size_text = 20
		# Local variables
		self.all_updates = dict()
		self.timed_event = None
		self.lastval = 0
		self.lastinc = 0
		self.pos = (10, 10)
		super(ALCmeter, self).__init__(**kwargs)
		self.value = rig.queryState('ALCmeter')
		rig.callback['ALCmeter'] = self.update
		self._turn()

	def target(self):
		# Eliminate values older than peak_hold
		now = time.time()
		cutoff = now - self.peak_hold
		for t in list(self.all_updates):
			if t < cutoff:
				del self.all_updates[t]
		# Find highest value
		sz = len(self.all_updates)
		if sz < 1:
			return (now, self.lastval)
		byval = dict(sorted(self.all_updates.items(), key = lambda x:x[1]))
		return (list(byval.keys())[sz - 1], list(byval.values())[sz - 1])

	def schedule(self):
		highval = self.target()
		if self.timed_event is not None:
			self.timed_event.cancel()
		if highval[1] != self.value:
			self.timed_event = Clock.schedule_once(lambda *t: self.tick(), 0.01)
		else:
			self.timed_event = Clock.schedule_once(lambda *t: self.tick(), (self.peak_hold - (time.time() - highval[0])))

	def tick(self):
		self.timed_event = None
		highval = self.target()
		if self.value != highval[1]:
			if highval[1] > self.value:
				inc = 3
				if self.lastinc > 0:
					inc = self.lastinc * 1.1
				newval = self.value + inc
				self.lastinc = inc
				if highval[1] < newval:
					newval = highval[1]
			else:
				inc = -0.02
				if self.lastinc < 0:
					inc = self.lastinc * 1.1
				newval = self.value + inc
				self.lastinc = inc
				if highval[1] > newval:
					newval = highval[1]
			self.value = newval
		else:
			self.lastinc = 0
		self.schedule()

	def update(self, value):
		if self._img_gauge != 'gardengauge/SWR.png':
			self.all_updates = {}
			self.lastval = value
		else:
			self._progress.value = value * 10 / 3
			now = time.time()
			self.lastval = value
			if now in self.all_updates:
				if value < self.all_updates[now]:
					return
			self.all_updates[now] = value
		self.schedule()

	def _turn(self, *args):
		'''
		Turn needle, 1 degree = 1 unit, 0 degree point start on 50 value.
		'''
		self._needle.center_x = self._gauge.center_x
		self._needle.center_y = self._gauge.center_y
		self._needle.rotation = (15 * self.unit) - (self.value * self.unit)
		if self._img_gauge != 'gardengauge/smeter.png':
			self._glab.text = ''
		else:
			if self.value < 16:
				self._glab.text = "S[b]{0:.0f}[/b]".format(self.value*9/15)
			else:
				self._glab.text = "+[b]{0:.0f}[/b]".format((self.value-15)*60/15)

class FreqDisplay(Label):
	freqValue = BoundedNumericProperty(0, min=0, max=99999999999, errorvalue=0)
	activeColour = ColorProperty(defaultvalue=[1.0, 1.0, 1.0, 1.0])
	inactiveColour = ColorProperty(defaultvalue=[0.45, 0.45, 0.45, 1.0])
	zeroColour = ColorProperty(defaultvalue=[0.2, 0.2, 0.2, 1.0])

	def __init__(self, **kwargs):
		self.markup = True
		self.bind(freqValue=self._updateFreq)
		super(FreqDisplay, self).__init__(**kwargs)
		self.freqValue = int(rig.queryState('vfoAFrequency'))
		rig.callback['vfoAFrequency'] = self.newFreq

	def newFreq(self, freq, *args):
		self.freqValue = int(freq)

	def _updateFreq(self, *args):
		new = '{:014,.3f}'.format(self.freqValue/1000)
		m = re.search('^[0,.]+', new)
		colour = '[color=' + kivy.utils.get_hex_from_color(self.activeColour) + ']'
		if ids is not None and ids.vfoBox.vfo != vfoa and ids.vfoBox.vfo != vfob:
			colour = '[color=' + kivy.utils.get_hex_from_color(self.inactiveColour) + ']'
		if m is not None:
			e = m.end()
			new = '[b][color=' + kivy.utils.get_hex_from_color(self.zeroColour) + ']' + new[0:e] + '[/color]' + colour + new[e:] + '[/color][/b]'
		else:
			new = '[b]' + colour + new + '[/color][/b]'
		self.text = new

	def on_touch_down(self, touch):
		if not 'button' in touch.profile:
			return False
		if not touch.button in ('scrollup', 'scrolldown', 'left'):
			return False
		#if ids.vfoBox.vfo != vfoa and ids.vfoBox.vfo != vfob:
		#	return
		if (touch.pos[0] > self.pos[0] + self.size[0]):
			return False
		if (touch.pos[0] < self.pos[0]):
			return False
		if (touch.pos[1] > self.pos[1] + self.size[1]):
			return False
		if (touch.pos[1] < self.pos[1]):
			return False
		cell = math.floor(14 - ((touch.pos[0] - self.pos[0]) / 42))
		if cell == 3 or cell == 7 or cell == 11:
			return False
		if cell > 2:
			cell = cell - 1
		if cell > 5:
			cell = cell - 1
		if cell > 8:
			cell = cell - 1
		up = (touch.pos[1] - self.pos[1]) >= (self.size[1] / 2)
		if touch.button == 'scrollup':
			up = False
		elif touch.button == 'scrolldown':
			up = True
		add = int(math.pow(10, cell))
		if up == False:
			add = 0 - add
		new = self.freqValue + add
		if new % add:
			new = math.floor(new / add) * add
		if ids.vfoBox.vfo == vfoa:
			rig.setState('vfoAFrequency', new)
		elif ids.vfoBox.vfo == vfob:
			rig.setState('vfoBFrequency', new)
		elif ids.vfoBox.vfo == mem:
			if up:
				rig.setState('up', None)
			else:
				rig.setState('down', None)
		elif ids.vfoBox.vfo == call:
			if up:
				rig.setState('bandUp', None)
			else:
				rig.setState('bandDown', None)
		return True

class MemoryDisplay(Label):
	memoryValue = BoundedNumericProperty(0, min=0, max=300, errorvalue=0)

	def __init__(self, **kwargs):
		self.markup = True
		self.bind(memoryValue=self._updateChannel)
		super(MemoryDisplay, self).__init__(**kwargs)
		self.memoryValue = int(rig.queryState('memoryChannel'))
		rig.callback['memoryChannel'] = self.newChannel
		rig.callback['MemoryData'] = self.updateChannel

	def newChannel(self, channel, *args):
		self.memoryValue = int(channel)
		if self.memoryValue == channel and channel == 300:
			self._updateChannel()

	def updateChannel(self, channel, *args):
		if channel == self.memoryValue:
			Clock.schedule_once(self._doUpdateChannel, -1)

	def _updateChannel(self, *args):
		# We can't query the rig in here because we're already
		# blocking the read method if we're called via a
		# callback
		Clock.schedule_once(self._doUpdateChannel, -1)

	def _doUpdateChannel(self, dt):
		memData = rig.queryMemory(self.memoryValue)
		if ids is not None:
			if ids.vfoBox.vfo == mem or ids.vfoBox.vfo == call:
				ids.mainFreq.freqValue = memData['Frequency']
		new = 'Memory: {:1d}-{:03d} {:8s} {:10s}'.format(memData['MemoryGroup'], memData['Channel'], memData['MemoryName'], 'Locked Out' if memData['LockedOut'] else '')
		if ids is not None:
			if ids.vfoBox.vfo == call:
				new = 'Calling Frequency'
		self.text = new

	def on_touch_down(self, touch):
		# TODO: Deal with clicks...
		return False

def setVFOCallback():
	if 'vfoAFrequency' in rig.callback:
		del rig.callback['vfoAFrequency']
	if 'vfoBFrequency' in rig.callback:
		del rig.callback['vfoBFrequency']
	if ids is not None:
		if ids.vfoBox.vfo == vfoa:
			ids.mainFreq.freqValue = int(rig.queryState('vfoAFrequency'))
			ids.mainFreq._updateFreq(ids.mainFreq)
			rig.callback['vfoAFrequency'] = ids.mainFreq.newFreq
		elif ids.vfoBox.vfo == vfob:
			ids.mainFreq.freqValue = int(rig.queryState('vfoBFrequency'))
			ids.mainFreq._updateFreq(ids.mainFreq)
			rig.callback['vfoBFrequency'] = ids.mainFreq.newFreq
		elif ids.vfoBox.vfo == mem:
			ids.mainMemory.memoryValue = int(rig.queryState('memoryChannel'))
			ids.mainMemory._updateChannel(ids.mainMemory)
		elif ids.vfoBox.vfo == call:
			ids.mainMemory.memoryValue = 300
			ids.mainMemory._updateChannel(ids.mainMemory)

def setMemoryVisibility():
	if ids is not None:
		if ids.vfoBox.vfo == mem or ids.vfoBox.vfo == call:
			ids.mainMemory.opacity = 1
			ids.mainMemory.disabled = False
		else:
			ids.mainMemory.opacity = 0
			ids.mainMemory.disabled = True

class VFOBoxButton(ToggleButton):
	allow_no_selection = False
	vfoID = NumericProperty(-1)

	def __init__(self, **kwargs):
		super(VFOBoxButton, self).__init__(**kwargs)
		self.group = 'VFOBoxButton'
		self.allow_no_selection = False

	def on_state(self, widget, value):
		if value == 'down':
			if self.vfoID != self.parent.vfo:
				rig.setState('RXtuningMode', kenwood.tuningMode(self.vfoID))

class VFOBox(GridLayout):
	vfo = NumericProperty(-1)

	def __init__(self, **kwargs):
		super(VFOBox, self).__init__(**kwargs)
		self.bind(vfo=self._updateVFO)
		self.vfo = int(rig.queryState('RXtuningMode'))
		rig.callback['RXtuningMode'] = self.newVFO

	def newVFO(self, vfo, *args):
		self.vfo = int(vfo)

	def _updateVFO(self, *args):
		Clock.schedule_once(lambda dt: setMemoryVisibility(), -1)
		Clock.schedule_once(lambda dt: setVFOCallback(), -1)
		for c in self.children:
			if c.vfoID == self.vfo:
				if c.state != 'down':
					c.dispatch('on_press')

class OPModeBoxButton(ToggleButton):
	modeID = NumericProperty(-1)

	def __init__(self, **kwargs):
		super(OPModeBoxButton, self).__init__(**kwargs)
		self.group = 'OPModeBoxButton'
		self.allow_no_selection = False

	def on_state(self, widget, value):
		if value == 'down':
			if self.modeID != self.parent.mode:
				rig.setState('mode', kenwood.mode(self.modeID))

class OPModeBox(GridLayout):
	mode = NumericProperty(0)

	def __init__(self, **kwargs):
		super(OPModeBox, self).__init__(**kwargs)
		self.bind(mode=self._updateMode)
		self.mode = int(rig.queryState('mode'))
		rig.callback['mode'] = self.newMode

	def newMode(self, mode, *args):
		self.mode = int(mode)

	def _updateMode(self, *args):
		# TODO: Update all the stuff that varies by mode here...
		# ie: Clock.schedule_once(lambda dt: setVFOCallback(), -1)
		for c in self.children:
			if c.modeID == self.mode:
				if c.state != 'down':
					c.dispatch('on_press')

'''
Handles bool rig properties
Adds rig_state string property with the name of the rig state to control
'''
class BoolToggle(ToggleButton):
	rig_state = StringProperty()
	poll_after = BooleanProperty(default_value=False)

	def __init__(self, **kwargs):
		super(BoolToggle, self).__init__(**kwargs)
		if (self.rig_state != ''):
			self.on_rig_state(self, self.rig_state)

	def on_rig_state(self, widget, value):
		self.refresh()
		rig.callback[self.rig_state] = self.toggle

	def refresh(self):
		st = rig.queryState(self.rig_state)
		if st == None:
			self.disabled = True
		else:
			self.disabled = False
			self.state = 'down' if st else 'normal'

	def toggle(self, on, *args):
		if on == None:
			self.disabled = True
		else:
			self.state = 'down' if on else 'normal'

	def on_press(self):
		rig.setState(self.rig_state, self.state == 'down')
		if self.poll_after:
			# We call this to force the update in case we exceeded
			# limits
			Clock.schedule_once(lambda dt: rig.forceState(self.rig_state), -1)

class StateSlider(Slider):
	rig_state = StringProperty()
	poll_after = BooleanProperty(default_value=False)

	def __init__(self, **kwargs):
		super(StateSlider, self).__init__(**kwargs)
		if (self.rig_state != ''):
			self.on_rig_state(self, self.rig_state)

	def refresh(self):
		Clock.schedule_once(lambda dt: self._refresh(), -1)

	def _refresh(self):
		st = rig.queryState(self.rig_state)
		self.newValue(st)

	def on_rig_state(self, widget, value):
		val = rig.queryState(self.rig_state)
		if val is None:
			self.disabled = True
		else:
			self.value = rig.queryState(self.rig_state)
		rig.callback[self.rig_state] = self.newValue

	def newValue(self, value, *args):
		if value is None:
			self.disabled = True
		else:
			self.disabled = False
			self.value = value

	def on_value(self, *args):
		rig.setState(self.rig_state, int(self.value))
		if self.poll_after:
			Clock.schedule_once(lambda dt: rig.forceState(self.rig_state), -1)

class StateLamp(Label):
	background_color = ColorProperty(defaultvalue=[0, 0, 0, 0])
	active_color = ColorProperty(defaultvalue=[1, 1, 0, 1.0])
	inactive_color = ColorProperty(defaultvalue=[0, 0, 0, 0])
	rig_state = StringProperty()
	meter_on = StringProperty()
	meter_off = StringProperty()
	update_meter = ObjectProperty()

	def __init__(self, **kwargs):
		super(StateLamp, self).__init__(**kwargs)
		self.col = Color(rgba=self.background_color)
		self.rect = Rectangle(pos = self.pos, size = self.size)
		self.canvas.before.add(self.col)
		self.canvas.before.add(self.rect)
		if self.rig_state != '':
			self.on_rig_state(self, self, self.rig_state)

	def on_active_color(self, widget, value):
		if self.rig_state != '':
			self.col.rgba = self.active_color if rig.queryState(self.rig_state) else self.inactive_color

	def on_inactive_color(self, widget, value):
		if self.rig_state != '':
			self.col.rgba = self.active_color if rig.queryState(self.rig_state) else self.inactive_color

	def on_rig_state(self, widget, value):
		st = rig.queryState(self.rig_state)
		self.col.rgba = self.active_color if rig.queryState(self.rig_state) else self.inactive_color
		rig.callback[self.rig_state] = self.newValue

	def on_pos(self, *args):
		self.rect.pos = self.pos

	def on_size(self, *args):
		self.rect.size = self.size

	def newValue(self, value, *args):
		self.background_color = self.active_color if value else self.inactive_color
		Clock.schedule_once(self._newValue, -1)

	def _newValue(self, dt):
		self.col.rgba = self.background_color
		st = rig.queryState(self.rig_state)
		self.col.rgba = self.active_color if st else self.inactive_color
		if st:
			if self.meter_on != '' and self.update_meter is not None:
				self.update_meter._img_gauge.source = self.meter_on
		else:
			if self.meter_off != '' and self.update_meter is not None:
				self.update_meter._img_gauge.source = self.meter_off
		rig.callback[self.rig_state] = self.newValue

class FilterDisplay(Widget):
	lr_offset = NumericProperty(default_value = 0)
	tb_offset = NumericProperty(default_value = 0)
	line_width = NumericProperty(default_value = 1)
	points = ListProperty()
	line_points = ListProperty()
	# TODO: This (and other radio-specific logic in here) doesn't beling
	#       in this file really.  It should be handled/exposed by the
	#       kenwood module.
	filter_widths = {
		kenwood.mode.CW: [50, 80, 100, 150, 200, 300, 400, 500, 600, 1000, 2000],
		kenwood.mode.CW_REVERSED: [50, 80, 100, 150, 200, 300, 400, 500, 600, 1000, 2000],
		kenwood.mode.FSK: [250, 500, 1000, 1500],
		kenwood.mode.FSK_REVERSED: [250, 500, 1000, 1500],
		kenwood.mode.FM: [0, 1],
		kenwood.mode.AM: [0, 1],
	}

	def __init__(self, **kwargs):
		super(FilterDisplay, self).__init__(**kwargs)
		self.lines = Line(points = self.points, width = self.line_width)
		self.canvas.add(Color(rgba=(1,1,1,1)))
		self.canvas.add(self.lines)
		self.points = rig.queryState('filterDisplayPattern')
		rig.callback['filterDisplayPattern'] = self.newValue

	def on_pos(self, *args):
		self.on_points(*args)

	def on_size(self, *args):
		self.on_points(*args)

	def on_line_width(self, widget, value):
		self.lines.width = self.line_width

	def on_points(self, widget, value):
		xstep = (self.size[0] - self.lr_offset * 2) / 32
		ystep = (self.size[1] - self.tb_offset * 2)
		xpos = self.lr_offset
		newline = (self.pos[0] + self.lr_offset, self.pos[1] + self.tb_offset,)
		for bit in self.points[:30]:
			xpos += xstep
			newline += (self.pos[0] + xpos, self.pos[1] + (ystep if bit else self.tb_offset),)
		newline += (self.pos[0] + xpos + xstep, self.pos[1] + self.tb_offset)
		self.line_points = newline
		Clock.schedule_once(self._on_points, -1)	

	def _on_points(self, dy):
		self.lines.points = self.line_points
		#self.canvas.ask_update()

	def newValue(self, value, *args):
		self.points = value

	def _get_max(self):
		# TODO: Packet Filter (Menu No. 50A) changes behaviour in ??? mode
		if ids.opModeBox.mode == int(kenwood.mode.AM):
			return 3
		elif ids.opModeBox.mode == int(kenwood.mode.FM):
			return 11
		elif ids.opModeBox.mode == int(kenwood.mode.LSB):
			return 11
		elif ids.opModeBox.mode == int(kenwood.mode.USB):
			return 11

	def on_touch_down(self, touch):
		if not 'button' in touch.profile:
			return False
		if (touch.pos[0] > self.pos[0] + self.size[0]):
			return False
		if (touch.pos[0] < self.pos[0]):
			return False
		if (touch.pos[1] > self.pos[1] + self.size[1]):
			return False
		if (touch.pos[1] < self.pos[1]):
			return False
		mode = rig.queryState('mode')
		if touch.button == 'left':
			if mode == kenwood.mode.AM or mode == kenwood.mode.FM:
				rig.setState('filterWidth', not rig.queryState('filterWidth'))
		if not touch.button in ('scrollup', 'scrolldown'):
			return False
		highpass = True if touch.pos[0] < self.pos[0] + self.width / 2 else False
		up = True if touch.button == 'scrolldown' else False
		# TODO: Packet Filter (Menu No. 50A) changes behaviour in ??? mode
		if mode == kenwood.mode.USB or mode == kenwood.mode.LSB or mode == kenwood.mode.FM or mode == kenwood.mode.AM:
			stateName = 'voiceHighPassCutoff' if highpass else 'voiceLowPassCutoff'
			newVal = rig.queryState(stateName) + (1 if up else -1)
			maxVal = self._get_max()
			if newVal < 0:
				newVal = 0
			if newVal > maxVal:
				newVal = maxVal
			rig.setState(stateName, newVal)
		elif mode in self.filter_widths:
			newVal = self.filter_widths[mode].index(rig.queryState('filterWidth'))
			newVal += (1 if up else -1)
			if newVal < 0:
				newVal = 0
			elif newVal >= len(self.filter_widths[mode]):
				newVal = len(self.filter_widths[mode]) - 1
			rig.setState('filterWidth', self.filter_widths[mode][newVal])
		return True

class HighPassLabel(Label):
	prefix = StringProperty()
	suffix = StringProperty()
	supportedModes = (kenwood.mode.AM, kenwood.mode.FM, kenwood.mode.LSB, kenwood.mode.USB,)

	def __init__(self, **kwargs):
		super(HighPassLabel, self).__init__(**kwargs)
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('voiceHighPassCutoff'))
		rig.callback['voiceHighPassCutoff'] = self.newValue

	def on_prefix(self, widget, value):
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('voiceHighPassCutoff'))

	def on_suffix(self, widget, value):
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('voiceHighPassCutoff'))

	def refresh(self):
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('voiceHighPassCutoff'))
		else:
			self.text = ''

	def newValue(self, value, *args):
		val = ''
		mode = int(rig.queryState('mode'))
		if mode == int(kenwood.mode.AM):
			if value == 0:
				val = '10'
			elif value == 1:
				val = '100'
			elif value == 2:
				val = '200'
			elif value == 3:
				val = '500'
			val = self.prefix + val + self.suffix
		elif mode == int(kenwood.mode.FM) or mode == int(kenwood.mode.LSB) or mode == int(kenwood.mode.USB):
			if value == 0:
				val = '10'
			elif value == 1:
				val = '50'
			elif value == 2:
				val = '100'
			elif value == 3:
				val = '200'
			elif value == 4:
				val = '300'
			elif value == 5:
				val = '400'
			elif value == 6:
				val = '500'
			elif value == 7:
				val = '600'
			elif value == 8:
				val = '700'
			elif value == 9:
				val = '800'
			elif value == 10:
				val = '900'
			elif value == 11:
				val = '1000'
			val = self.prefix + val + self.suffix
		self.text = val

class LowPassLabel(Label):
	prefix = StringProperty()
	suffix = StringProperty()
	supportedModes = (kenwood.mode.AM, kenwood.mode.FM, kenwood.mode.LSB, kenwood.mode.USB,)

	def __init__(self, **kwargs):
		super(LowPassLabel, self).__init__(**kwargs)
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('voiceLowPassCutoff'))
		rig.callback['voiceLowPassCutoff'] = self.newValue

	def on_prefix(self, widget, value):
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('voiceLowPassCutoff'))

	def on_suffix(self, widget, value):
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('voiceLowPassCutoff'))

	def refresh(self):
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('voiceLowPassCutoff'))
		else:
			self.text = ''

	def newValue(self, value, *args):
		val = ''
		mode = int(rig.queryState('mode'))
		if mode == int(kenwood.mode.AM):
			if value == 0:
				val = '2500'
			elif value == 1:
				val = '3000'
			elif value == 2:
				val = '4000'
			elif value == 3:
				val = '5000'
		elif mode == int(kenwood.mode.FM) or mode == int(kenwood.mode.LSB) or mode == int(kenwood.mode.USB):
			if value == 0:
				val = '1400'
			elif value == 1:
				val = '1600'
			elif value == 2:
				val = '1800'
			elif value == 3:
				val = '2000'
			elif value == 4:
				val = '2200'
			elif value == 5:
				val = '2400'
			elif value == 6:
				val = '2600'
			elif value == 7:
				val = '2800'
			elif value == 8:
				val = '3000'
			elif value == 9:
				val = '3400'
			elif value == 10:
				val = '4000'
			elif value == 11:
				val = '5000'
		self.text = self.prefix + val + self.suffix

class WideNarrowLabel(Label):
	prefix = StringProperty()
	suffix = StringProperty()
	supportedModes = (kenwood.mode.AM, kenwood.mode.FM,)

	def __init__(self, **kwargs):
		super(WideNarrowLabel, self).__init__(**kwargs)
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('filterWidth'))
		rig.callback['filterWidth'] = self.newValue

	def on_prefix(self, widget, value):
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('filterWidth'))

	def on_suffix(self, widget, value):
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('filterWidth'))

	def refresh(self):
		if rig.queryState('mode') in self.supportedModes:
			self.newValue(rig.queryState('filterWidth'))
		else:
			self.text = ''

	def newValue(self, value, *args):
		val = 'Narrow' if value == 0 else 'Wide'
		self.text = self.prefix + val + self.suffix

class NeatApp(App):
	def build(self):
		global ids
		ui = Neat()
		Window.size = ui.size
		if ids is not None:
			raise Exception("Only one instance of NeatApp allowed!")
		ids = ui.ids
		setVFOCallback()
		return ui

if __name__ == '__main__':
	NeatApp().run()
	rig.terminate()
