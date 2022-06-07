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

import getopt
import sys

opts, args = getopt.getopt(sys.argv[1:], "d", ["debug"])
verbose = False
for o, a in opts:
	if o in ('-d', '--debug'):
		verbose = True

import kenwood
import rigctld
import math
import re
import time
import threading
from kivy.app import App
from kivy.clock import Clock
from kivy.config import ConfigParser
from kivy.core.window import Window
from kivy.factory import Factory
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

rig = None
rigctldThread = None
rigctl = None
vfoa = int(kenwood.tuningMode.VFOA)
vfob = int(kenwood.tuningMode.VFOB)
mem = int(kenwood.tuningMode.MEMORY)
call = int(kenwood.tuningMode.CALL)

# See https://new.reddit.com/r/kivy/comments/v5joow/labeltext_can_no_longer_be_updated_after_f1/
# Monkey patch hack
Factory.unregister("SettingTitle")
class SettingTitle(Label):
    title = Factory.StringProperty()
    panel = Factory.ObjectProperty()
from kivy.uix import settings
settings.SettingTitle = SettingTitle

class Neat(FloatLayout):
	def control(self, **kwargs):
		for k in kwargs.keys():
			setattr(rig, k, kwargs[k])

class Meter(Gauge):
	rig_state = StringProperty()
	peak_hold = NumericProperty(0.5)
	low_cutoff = NumericProperty(16)
	low_format = StringProperty('{:.0f}')
	high_format = StringProperty('{:.0f}')
	accel_up_initial = NumericProperty(3)
	accel_up_mult = NumericProperty(1.1)
	accel_down_initial = NumericProperty(-0.02)
	accel_down_mult = NumericProperty(1.1)
	click_selects = NumericProperty(int(kenwood.meter.UNSELECTED))
	calculation = StringProperty()

	def __init__(self, **kwargs):
		# Local variables
		self.all_updates = dict()
		self.timed_event = None
		self.lastval = 0
		self.lastinc = 0
		self.pos = (10, 10)
		super(Meter, self).__init__(**kwargs)
		if self.rig_state != '':
			rig.add_callback('self.rig_state', self.stateUpdate)
			self.value = getattr(rig, self.rig_state)
		self._old_rig_state = self.rig_state
		self._turn()
		self.bind(low_format=self._turn)
		self.bind(high_format=self._turn)
		self.bind(rig_state=self._newRigState)

	def on_touch_down(self, touch):
		if self.click_selects == kenwood.meter.UNSELECTED:
			return False
		if not 'button' in touch.profile:
			return False
		if not touch.button in ('left'):
			return False
		if not self._gauge.collide_point(touch.pos[0], touch.pos[1]):
			return False
		if touch.pos[1] < (self._gauge.pos[1] + self._gauge.size[1] * 0.4):
			return False
		rig.meterType = kenwood.meter(self.click_selects)

	def _newRigState(self, *args):
		if self._old_rig_state != '':
			getattr(rig, self._old_rig_state).remove_callback(self.stateUpdate)
		rig.add_callback(self.rig_state, self.stateUpdate)
		self._old_rig_state = self.rig_state

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
				inc = self.accel_up_initial
				if self.lastinc > 0:
					inc = self.lastinc * self.accel_up_mult
				newval = self.value + inc
				self.lastinc = inc
				if highval[1] < newval:
					newval = highval[1]
			else:
				inc = self.accel_down_initial
				if self.lastinc < 0:
					inc = self.lastinc * self.accel_down_mult
				newval = self.value + inc
				self.lastinc = inc
				if highval[1] > newval:
					newval = highval[1]
			self.value = newval
		else:
			self.lastinc = 0
		self.schedule()

	def stateUpdate(self, value):
		if value is None:
			self.lastval = self.min_value
		else:
			self.lastval = value
		Clock.schedule_once(lambda dt: self._stateUpdate(), 0)

	def _stateUpdate(self):
		self._progress.value = self.lastval
		now = time.time()
		if now in self.all_updates:
			if value < self.all_updates[now]:
				return
		self.all_updates[now] = self.lastval
		self.schedule()

	def _turn(self, *args):
		'''
		Turn needle, 1 degree = 1 unit, 0 degree point start on 50 value.

		'''
		self._progress.value = self.lastval
		self._needle.center_x = self._gauge.center_x
		self._needle.center_y = self._gauge.center_y
		self._needle.rotation = 90 - ((self.value - self.min_value) * self.unit)
		if self.value < self.low_cutoff:
			if self.calculation == 'S-Level':
				self._glab.text = self.low_format.format(self.value*9/15)
			else:
				self._glab.text = self.low_format.format(self.value)
		else:
			if self.calculation == 'S-Level':
				self._glab.text = self.high_format.format((self.value-15)*60/15)
			else:
				self._glab.text = self.high_format.format(self.value)

class FreqDisplay(Label):
	freqValue = BoundedNumericProperty(0, min=0, max=99999999999, errorvalue=0)
	activeColour = ColorProperty(defaultvalue=[1.0, 1.0, 1.0, 1.0])
	inactiveColour = ColorProperty(defaultvalue=[0.45, 0.45, 0.45, 1.0])
	zeroColour = ColorProperty(defaultvalue=[0.2, 0.2, 0.2, 1.0])
	vfo_box = ObjectProperty()
	op_mode_box = ObjectProperty()
	memory_display = ObjectProperty()
	rig_state = StringProperty()

	# TODO: Change frequency if appropriate when TXing
	def __init__(self, **kwargs):
		self.markup = True
		self.bind(freqValue=self._updateFreq)
		self.bind(vfo_box=self.newVFO)
		super(FreqDisplay, self).__init__(**kwargs)
		if rig.powerOn:
			self.freqValue = int(rig.vfoAFrequency)
		self.cb_state = 'currentMainFrequency'
		rig.add_callback(self.cb_state, self.newFreq)
		self.bind(rig_state=self.newRigState)

	def newRigState(self, widget, value):
		rig.remove_callback(self.cb_state, self.newFreq)
		rig.add_callback(self.rig_state, self.newFreq)
		self._updateFreq()

	def newVFO(self, widget, value):
		Clock.schedule_once(lambda dt: self.setVFOCallback(), 0)

	def newMemory(self, widget, value):
		Clock.schedule_once(lambda dt: self._newMemory(), 0)

	def _newMemory(self):
		self.setVFOCallback()
		self._updateFreq()

	def setVFOCallback(self):
		if self.rig_state == '':
			rig.remove_callback(self.cb_state, self.newFreq)
			if self.vfo_box is not None:
				if self.vfo_box.vfo == vfoa:
					self.freqValue = rig.vfoAFrequency
					self._updateFreq(self)
					self.cb_state = 'vfoAFrequency'
					rig.add_callback(self.cb_state, self.newFreq)
				elif self.vfo_box.vfo == vfob:
					self.freqValue = rig.vfoBFrequency
					self._updateFreq(self)
					self.cb_state = 'vfoBFrequency'
					rig.add_callback(self.cb_state, self.newFreq)
				elif self.memory_display is not None:
					if self.vfo_box.vfo == mem:
						self.memory_display.memoryValue = rig.memoryChannel
						self.memory_display._updateChannel(self.memory_display)
					elif self.vfo_box.vfo == call:
						self.memory_display.memoryValue = 300
						self.memory_display._updateChannel(self.memory_display)

	def newFreq(self, freq, *args):
		if freq is not None:
			self.freqValue = int(freq)

	def _updateFreq(self, *args):
		new = '{:014,.3f}'.format(self.freqValue/1000)
		m = re.search('^[0,.]+', new)
		colour = '[color=' + kivy.utils.get_hex_from_color(self.activeColour) + ']'
		if self.vfo_box is not None and self.vfo_box.vfo != vfoa and self.vfo_box.vfo != vfob:
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
		if not self.collide_point(touch.pos[0], touch.pos[1]):
			return False
		#if self.vfo_box.vfo != vfoa and self.vfo_box.vfo != vfob:
		#	return
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
		if self.vfo_box.vfo == vfoa:
			rig.vfoAFrequency = new
		elif self.vfo_box.vfo == vfob:
			rig.vfoBFrequency = new
		elif self.vfo_box.vfo == mem and rig.RXtuningMode == kenwood.tuningMode.MEMORY:
			if up:
				rig.up = None
			else:
				rig.down = None
		elif self.vfo_box.vfo == call and rig.RXtuningMode == kenwood.tuningMode.CALL:
			if up:
				rig.bandUp = None
			else:
				rig.bandDown = None
		return True

class MemoryDisplay(Label):
	memoryValue = BoundedNumericProperty(0, min=0, max=300, errorvalue=0)
	freq_display = ObjectProperty()
	vfo_box = ObjectProperty()
	is_tx = BooleanProperty(False)

	def __init__(self, **kwargs):
		self.markup = True
		self.bind(memoryValue=self._updateChannel)
		super(MemoryDisplay, self).__init__(**kwargs)
		if rig.powerOn:
			self.memoryValue = int(rig.memoryChannel)
		rig.add_callback('memoryChannel', self.newChannel)
		rig.add_callback('memoryGroups', self.newGroups)
		rig.memories.memories[self.memoryValue].add_callback(self.updateChannel)
		self.bind(on_ref_press=self.toggle_group)
		rig.memories.memories[300].add_callback(self.updateChannel)
		self.bind(freq_display=self.newFreqDisplay)
		self.bind(vfo_box=self.newVFOBox)
		self.bind(is_tx=self.newIsTX)

	def newIsTX(self, widget, value):
		Clock.schedule_once(self._doUpdateChannel, 0)

	def newFreqDisplay(self, widget, value):
		Clock.schedule_once(self._doUpdateChannel, 0)

	def newVFOBox(self, widget, value):
		self.setVisibility()
		Clock.schedule_once(self._doUpdateChannel, 0)

	def setVisibility(self):
		if self.vfo_box is None or self.vfo_box.vfo == call or self.vfo_box.vfo == mem:
			self.opacity = 1
			self.disabled = False
		else:
			self.opacity = 0
			self.disabled = True

	def newChannel(self, channel, *args):
		if self.memoryValue is not None:
			rig.memories.memories[self.memoryValue].remove_callback(self.updateChannel)
			if self.memoryValue == channel and channel == 300:
				self._updateChannel()
		if channel is not None:
			self.memoryValue = int(channel)
			rig.memories.memories[self.memoryValue].add_callback(self.updateChannel)

	def newGroups(self, groups, *args):
		self._updateChannel()

	def updateChannel(self, channel, *args):
		if channel == self.memoryValue:
			Clock.schedule_once(self._doUpdateChannel, 0)

	def _updateChannel(self, *args):
		# We can't query the rig in here because we're already
		# blocking the read method if we're called via a
		# callback
		Clock.schedule_once(self._doUpdateChannel, 0)

	def toggle_group(self, widget, value):
		v = int(value)
		memGroups = rig.memoryGroups
		memGroups[v] = not memGroups[v]
		rig.memoryGroups = memGroups

	def _doUpdateChannel(self, dt):
		memData = rig.memories[self.memoryValue]
		if self.vfo_box is not None and self.freq_display is not None:
			if self.vfo_box.vfo == mem or self.vfo_box.vfo == call:
				if self.is_tx:
					self.freq_display.freqValue = memData['TXfrequency']
				else:
					self.freq_display.freqValue = memData['Frequency']
		new = 'Memory: {:1d}-{:03d} {:8s} {:10s}'.format(memData['MemoryGroup'], memData['Channel'], memData['MemoryName'], 'Locked Out ' if memData['LockedOut'] else ' ')
		memGroups = rig.memoryGroups
		if memGroups is not None:
			for i in range(len(memGroups)):
				if memGroups[i]:
					new += '[u]'
				new += '[ref='+str(i)+']' + str(i) + '[/ref]'
				if memGroups[i]:
					new += '[/u]'
			if self.vfo_box is not None:
				if self.vfo_box.vfo == call:
					new = 'Calling Frequency'
			self.text = new

	#def on_touch_down(self, touch):
	#	# TODO: Deal with clicks...
	#	return False

class VFOBoxButton(ToggleButton):
	allow_no_selection = False
	vfoID = NumericProperty(-1)
	force_disabled = BooleanProperty(False)

	def __init__(self, **kwargs):
		super(VFOBoxButton, self).__init__(**kwargs)
		self.group = str(self.parent)
		self.allow_no_selection = False
		self.bind(force_disabled=self.newForce_disabled)

	def newForce_disabled(self, widget, value):
		if value:
			self.disabled = True

	def on_parent(self, *args):
		self.group = str(self.parent)
		if self.parent.vfo == -1:
			self.disabled = True

	def on_state(self, widget, value):
		if value == 'down':
			if self.vfoID != self.parent.vfo and self.parent.rig_state != '':
				setattr(rig, self.parent.rig_state, kenwood.tuningMode(self.vfoID))

class VFOBox(GridLayout):
	rig_state = StringProperty()
	vfo = NumericProperty(-1)
	freq_display = ObjectProperty()

	def disable_children(self):
		for c in self.children:
			c.disabled = True

	def __init__(self, **kwargs):
		super(VFOBox, self).__init__(**kwargs)
		self.bind(vfo=self._updateVFO)
		if self.rig_state != '':
			if getattr(rig, self.rig_state) is None:
				self.disable_children()
			else:
				self.vfo = int(getattr(rig, self.rig_state))
		if (self.rig_state != ''):
			self.on_rig_state(self, self.rig_state)
		self.bind(freq_display=self.newFreqDisplay)

	def newFreqDisplay(self, widget, value):
		self._updateVFO()

	def on_rig_state(self, widget, value):
		Clock.schedule_once(lambda dt: self.refresh(), 0)
		rig.add_callback(self.rig_state, self.newVFO)

	def refresh(self):
		st = getattr(rig, self.rig_state)
		if st is None:
			self.vfo = -1
			self.disable_children()
		else:
			self.vfo = int(st)

	def newVFO(self, vfo, *args):
		if vfo is None:
			self.vfo = -1
			self.disable_children()
		else:
			self.vfo = int(vfo)
		self.freq_display._updateFreq()

	def _updateVFO(self, *args):
		if self.freq_display is not None:
			if self.freq_display.memory_display is not None:
				Clock.schedule_once(lambda dt: self.freq_display.memory_display.setVisibility(), 0)
			Clock.schedule_once(lambda dt: self.freq_display.setVFOCallback(), 0)
		for c in self.children:
			if self.vfo == -1:
				c.disabled = True
			else:
				if not c.force_disabled:
					c.disabled = False
				if c.vfoID == self.vfo:
					if c.state != 'down':
						c.dispatch('on_press')

class OPModeBoxButton(ToggleButton):
	modeID = NumericProperty(-1)

	def __init__(self, **kwargs):
		super(OPModeBoxButton, self).__init__(**kwargs)
		self.group = str(self.parent)
		self.allow_no_selection = False

	def on_parent(self, *args):
		self.group = str(self.parent)
		if self.parent.mode == 0:
			self.disabled = True

	def on_state(self, widget, value):
		if value == 'down':
			if self.modeID != self.parent.mode:
				rig.mode = kenwood.mode(self.modeID)

class OPModeBox(GridLayout):
	mode = NumericProperty(0)
	rig_state = StringProperty()

	def __init__(self, **kwargs):
		super(OPModeBox, self).__init__(**kwargs)
		self.new_mode = self.mode
		self.cb_installed = self.rig_state
		if self.rig_state != '':
			rig.add_callback(self.rig_state, self.newMode)
			rm = getattr(rig, self.rig_state)
			if rm is not None:
				self.mode = int(rm)
		self.bind(mode=self._updateMode)
		self.bind(rig_state=self.newRigState)

	def newRigState(self, widget, value):
		if self.cb_installed != '':
			rig.remove_callback(self.rig_state, self.newMode)
		rig.add_callback(self.rig_state, self.newMode)
		nm = getattr(rig, self.rig_state)
		if nm is None:
			self.mode = -1
		else:
			self.mode = int(getattr(rig, self.rig_state))

	def disable_children(self):
		for c in self.children:
			c.disabled = True

	def newMode(self, mode, *args):
		if mode is None:
			self.new_mode = 0
			self.disable_children
		else:
			self.new_mode = mode
		Clock.schedule_once(lambda dt: self._newMode(), 0)

	def _newMode(self):
		self.mode = int(self.new_mode)

	def _updateMode(self, *args):
		# TODO: Update all the stuff that varies by mode here...
		# ie: Clock.schedule_once(lambda dt: setVFOCallback(), 0)
		for c in self.children:
			if self.mode == 0:
				c.disabled = True
			else:
				c.disabled = False
				if c.modeID == self.mode:
					if c.state != 'down':
						c.dispatch('on_press')

'''
Handles bool rig properties
Adds rig_state string property with the name of the rig state to control
'''
class BoolToggle(ToggleButton):
	rig_state = StringProperty()

	def __init__(self, **kwargs):
		super(BoolToggle, self).__init__(**kwargs)
		if (self.rig_state != ''):
			self.on_rig_state(self, self.rig_state)

	def on_rig_state(self, widget, value):
		Clock.schedule_once(lambda dt: self.refresh(), 0)
		rig.add_callback(self.rig_state, self.toggle)

	def refresh(self):
		st = getattr(rig, self.rig_state)
		if st == None:
			self.disabled = True
		else:
			self.disabled = False
			self.state = 'down' if st else 'normal'

	def toggle(self, on, *args):
		if on == None:
			self.disabled = True
		else:
			self.disabled = False
			self.state = 'down' if on else 'normal'

	def on_press(self):
		setattr(rig, self.rig_state, self.state == 'down')

class StateSlider(Slider):
	rig_state = StringProperty()

	def __init__(self, **kwargs):
		super(StateSlider, self).__init__(**kwargs)
		if (self.rig_state != ''):
			self.on_rig_state(self, self.rig_state)
		self._latest = None

	def refresh(self):
		Clock.schedule_once(lambda dt: self._refresh(), 0)

	def _refresh(self):
		st = getattr(rig, self.rig_state)
		self.newValue(st)

	def on_rig_state(self, widget, value):
		val = getattr(rig, self.rig_state)
		if val is None:
			self.disabled = True
		else:
			self.value = val
		rig.add_callback(self.rig_state, self.newValue)

	def newValue(self, value, *args):
		if value is None:
			self.disabled = True
		else:
			self.disabled = False
			self._latest = value
			self.value = value

	def on_value(self, *args):
		if self._latest != self.value:
			setattr(rig, self.rig_state, int(self.value))

class StateLamp(Label):
	background_color = ColorProperty(defaultvalue=[0, 0, 0, 0])
	active_color = ColorProperty(defaultvalue=[1, 1, 0, 1.0])
	inactive_color = ColorProperty(defaultvalue=[0, 0, 0, 0])
	rig_state = StringProperty()
	meter_on = StringProperty()
	meter_off = StringProperty()
	meter_on_calculation = StringProperty()
	meter_off_calculation = StringProperty()
	meter_on_low = StringProperty()
	meter_off_low = StringProperty()
	meter_on_high = StringProperty()
	meter_off_high = StringProperty()

	update_meter = ObjectProperty()

	def __init__(self, **kwargs):
		super(StateLamp, self).__init__(**kwargs)
		self.col = Color(rgba=self.background_color)
		self.rect = Rectangle(pos = self.pos, size = self.size)
		self.canvas.before.add(self.col)
		self.canvas.before.add(self.rect)
		if self.rig_state != '':
			self.on_rig_state(self, self, self.rig_state)
		self._old_rig_state = self.rig_state

	def on_active_color(self, widget, value):
		if self.rig_state != '':
			self.col.rgba = self.active_color if getattr(rig, self.rig_state) else self.inactive_color

	def on_inactive_color(self, widget, value):
		if self.rig_state != '':
			self.col.rgba = self.active_color if getattr(rig, self.rig_state) else self.inactive_color

	def on_rig_state(self, widget, value):
		if hasattr(rig, self._old_rig_state):
			rig.remove_callback(self._old_rig_state, self.newValue)
		self._old_rig_state = self.rig_state
		st = getattr(rig, self.rig_state)
		self.col.rgba = self.active_color if st else self.inactive_color
		rig.add_callback(self.rig_state, self.newValue)

	def on_pos(self, *args):
		self.rect.pos = self.pos

	def on_size(self, *args):
		self.rect.size = self.size

	def newValue(self, value, *args):
		self.background_color = self.active_color if value else self.inactive_color
		Clock.schedule_once(self._newValue, 0)

	def _newValue(self, dt):
		self.col.rgba = self.background_color
		st = getattr(rig, self.rig_state)
		if st is None:
			return
		self.col.rgba = self.active_color if st else self.inactive_color
		if st:
			if self.meter_on != '' and self.update_meter is not None:
				self.update_meter.file_gauge = self.meter_on
				self.update_meter.low_format = self.meter_on_low
				self.update_meter.high_format = self.meter_on_high
				self.update_meter.calculation = self.meter_on_calculation
		else:
			if self.meter_off != '' and self.update_meter is not None:
				self.update_meter.file_gauge = self.meter_off
				self.update_meter.low_format = self.meter_off_low
				self.update_meter.high_format = self.meter_off_high
				self.update_meter.calculation = self.meter_off_calculation

class FilterDisplay(Widget):
	lr_offset = NumericProperty(default_value = 0)
	tb_offset = NumericProperty(default_value = 0)
	line_width = NumericProperty(default_value = 1)
	points = ListProperty()
	line_points = ListProperty()
	op_mode_box = ObjectProperty()

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
	filter_shifts = [400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000]

	def __init__(self, **kwargs):
		super(FilterDisplay, self).__init__(**kwargs)
		self.lines = Line(points = self.points, width = self.line_width)
		self.canvas.add(Color(rgba=(1,1,1,1)))
		self.canvas.add(self.lines)
		if rig.powerOn:
			self.points = rig.filterDisplayPattern
		rig.add_callback('filterDisplayPattern', self.newValue)

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
		Clock.schedule_once(self._on_points, 0)	

	def _on_points(self, dy):
		self.lines.points = self.line_points
		#self.canvas.ask_update()

	def newValue(self, value, *args):
		if value is not None:
			self.points = value

	def _get_max(self):
		# TODO: Packet Filter (Menu No. 50A) changes behaviour in ??? mode
		if self.op_mode_box is None:
			return 11
		else:
			if self.op_mode_box.mode == int(kenwood.mode.AM):
				return 3
			elif self.op_mode_box.mode == int(kenwood.mode.FM):
				return 11
			elif self.op_mode_box.mode == int(kenwood.mode.LSB):
				return 11
			elif self.op_mode_box.mode == int(kenwood.mode.USB):
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
		mode = rig.mode
		if touch.button == 'left':
			if mode == kenwood.mode.AM or mode == kenwood.mode.FM:
				rig.filterWidth = not rig.filterWidth
		if not touch.button in ('scrollup', 'scrolldown'):
			return False
		highpass = True if touch.pos[0] < self.pos[0] + self.width / 2 else False
		up = True if touch.button == 'scrolldown' else False
		# TODO: Packet Filter (Menu No. 50A) changes behaviour in ??? mode
		if mode in (kenwood.mode.USB, kenwood.mode.LSB, kenwood.mode.FM, kenwood.mode.AM):
			stateName = 'voiceHighPassCutoff' if highpass else 'voiceLowPassCutoff'
			newVal = getattr(rig, stateName) + (1 if up else -1)
			maxVal = self._get_max()
			if newVal < 0:
				newVal = 0
			if newVal > maxVal:
				newVal = maxVal
			setattr(rig, stateName, newVal)
		elif mode == kenwood.mode.CW and not highpass:
			newVal = self.filter_shifts.index(rig.IFshift)
			newVal += (1 if up else -1)
			if newVal < 0:
				newVal = 0
			elif newVal >= len(self.filter_shifts):
				newVal = len(self.filter_shifts) - 1
			rig.IFshift = self.filter_shifts[newVal]
		elif mode in self.filter_widths:
			newVal = self.filter_widths[mode].index(rig.filterWidth)
			newVal += (1 if up else -1)
			if newVal < 0:
				newVal = 0
			elif newVal >= len(self.filter_widths[mode]):
				newVal = len(self.filter_widths[mode]) - 1
			rig.filterWidth = self.filter_widths[mode][newVal]
		return True

class HighPassLabel(Label):
	prefix = StringProperty()
	suffix = StringProperty()
	supportedModes = (kenwood.mode.AM, kenwood.mode.FM, kenwood.mode.LSB, kenwood.mode.USB,)

	def __init__(self, **kwargs):
		super(HighPassLabel, self).__init__(**kwargs)
		if rig.mode in self.supportedModes:
			self.newValue(rig.voiceHighPassCutoff)
		rig.add_callback('voiceHighPassCutoff', self.newValue)
		rig.add_callback('filterWidth', self.newValue)

	def on_prefix(self, widget, value):
		if rig.mode in self.supportedModes:
			self.newValue(rig.voiceHighPassCutoff)
		else:
			self.newValue(FilterDisplay.filter_widths[rig.mode][rig.filterWidth])

	def on_suffix(self, widget, value):
		if rig.mode in self.supportedModes:
			self.newValue(rig.voiceHighPassCutoff)
		else:
			self.newValue(rig.filterWidth)

	def refresh(self):
		Clock.schedule_once(lambda dt: self._refresh(), 0)

	def _refresh(self):
		if rig.mode in self.supportedModes:
			self.newValue(rig.voiceHighPassCutoff)
		else:
			self.newValue(rig.filterWidth)

	def newValue(self, value, *args):
		val = ''
		mode = rig.mode
		if mode == kenwood.mode.AM:
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
		elif mode is not None:
			val = str(value)
			val = self.prefix + val + self.suffix

		self.text = val

class LowPassLabel(Label):
	prefix = StringProperty()
	suffix = StringProperty()
	supportedModes = (kenwood.mode.AM, kenwood.mode.FM, kenwood.mode.LSB, kenwood.mode.USB, kenwood.mode.CW,)
	cwModes = (kenwood.mode.CW, kenwood.mode.CW_REVERSED,)

	def __init__(self, **kwargs):
		super(LowPassLabel, self).__init__(**kwargs)
		if rig.mode in self.supportedModes:
			self.newValue(rig.voiceLowPassCutoff)
		rig.add_callback('voiceLowPassCutoff', self.newValue)
		rig.add_callback('IFshift', self.newValue)

	def on_prefix(self, widget, value):
		if rig.mode in self.supportedModes:
			self.newValue(rig.voiceLowPassCutoff)
		elif rig.mode in self.cwModes:
			self.newValue(rig.IFshift)

	def on_suffix(self, widget, value):
		if rig.mode in self.supportedModes:
			self.newValue(rig.voiceLowPassCutoff)
		elif rig.mode in self.cwModes:
			self.newValue(rig.IFshift)

	def refresh(self):
		Clock.schedule_once(lambda dt: self._refresh(), 0)

	def _refresh(self):
		if rig.mode in self.supportedModes:
			self.newValue(rig.voiceLowPassCutoff)
		elif rig.mode in self.cwModes:
			self.newValue(rig.IFshift)
		else:
			self.text = ''

	def newValue(self, value, *args):
		val = ''
		if rig.mode is None:
			mode = 0
		else:
			mode = int(rig.mode)
		if mode == int(kenwood.mode.AM):
			if value == 0:
				val = '2500'
			elif value == 1:
				val = '3000'
			elif value == 2:
				val = '4000'
			elif value == 3:
				val = '5000'
			val = self.prefix + val + self.suffix
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
			val = self.prefix + val + self.suffix
		elif rig.mode in self.cwModes:
			val = self.prefix + str(rig.IFshift) + self.suffix
		self.text = val

class WideNarrowLabel(Label):
	prefix = StringProperty()
	suffix = StringProperty()
	supportedModes = (kenwood.mode.AM, kenwood.mode.FM,)

	def __init__(self, **kwargs):
		super(WideNarrowLabel, self).__init__(**kwargs)
		if rig.mode in self.supportedModes:
			self.newValue(rig.filterWidth)
		rig.add_callback('filterWidth', self.newValue)

	def on_prefix(self, widget, value):
		if rig.mode in self.supportedModes:
			self.newValue(rig.filterWidth)

	def on_suffix(self, widget, value):
		if rig.mode in self.supportedModes:
			self.newValue(rig.filterWidth)

	def refresh(self):
		Clock.schedule_once(lambda dt: self._refresh(), 0)

	def _refresh(self):
		if rig.mode in self.supportedModes:
			self.newValue(rig.filterWidth)
		else:
			self.text = ''

	def newValue(self, value, *args):
		if rig.mode in self.supportedModes:
			val = 'Narrow' if value == 0 else 'Wide'
			self.text = self.prefix + val + self.suffix

class NeatApp(App):
	def build_config(self, config):
		config.setdefaults('SerialPort', {
			'device': '/dev/ttyU0',
			'speed': 57600,
			'stopBits': 1,
		})
		config.setdefaults('Neat', {
			'verbose': 0,
			'rigctld': 1,
			'rigctld_address': 'localhost',
			'rigctld_port': 4532
		})
	def build_settings(self, settings):
		jsondata = """
			[
				{ "type": "title",
				  "title": "Program Options" },
				
				{ "type": "bool",
				  "title": "Verbose Output",
				  "section": "Neat",
				  "key": "verbose" },
				
				{ "type": "bool",
				  "title": "Run rigctld emulator",
				  "section": "Neat",
				  "key": "rigctld" },
				
				{ "type": "numeric",
				  "title": "rigctld listen address",
				  "section": "Neat",
				  "key": "rigctld_address" },
				
				{ "type": "numeric",
				  "title": "rigctld port",
				  "section": "Neat",
				  "key": "rigctld_port" },
				
				{ "type": "title",
				  "title": "Serial Port" },
				
				{ "type": "path",
				  "title": "Device Path",
				  "section": "SerialPort",
				  "key": "device" },
				
				{ "type": "options",
				  "title": "Speed",
				  "desc": "Serial port speed, must match menu 56",
				  "section": "SerialPort",
				  "key": "speed",
				  "options": ["4800", "9600", "19200", "38400", "57600"] },
				
				{ "type": "options",
				  "title": "Stop Bits",
				  "desc": "Serial port speed, must match menu 56",
				  "section": "SerialPort",
				  "key": "stopBits",
				  "options": ["1", "2"] }
			]
		"""
		settings.add_json_panel('Neat', self.config, data = jsondata)

	def build(self):
		global rig, rigctl
		self.config = ConfigParser()
		self.build_config(self.config)
		self.config.read('neat.ini')
		rig = kenwood.Kenwood(self.config.get('SerialPort', 'device'), self.config.getint('SerialPort', 'speed'), self.config.getint('SerialPort', 'stopBits'), verbose = self.config.getboolean('Neat', 'verbose'))
		self.rig = rig
		if self.config.getboolean('Neat', 'rigctld'):
			rigctl = rigctld.rigctld(rig, address = self.config.get('Neat', 'rigctld_address'), port = self.config.getint('Neat', 'rigctld_port'), verbose = self.config.getboolean('Neat', 'verbose'))
			rigctldThread = threading.Thread(target = rigctl.rigctldThread, name = 'rigctld')
			rigctldThread.start()
		ui = Neat()
		Window.size = ui.size
		return ui

	def on_config_change(self, config, section, key, value):
		if config is self.config:
			if ('Neat', 'verbose') == (section, key):
				rig._verbose = bool(int(value))
				rigctl.verbose = bool(int(value))

if __name__ == '__main__':
	NeatApp().run()
	rig.terminate()
	if rigctldThread is not None:
		rigctldThread.join()
