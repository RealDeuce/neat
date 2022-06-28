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

from getopt import getopt
from sys import argv

verbose = False
client_port = 3532
kv_file = 'neat-main.kv'

import rig
import rig.kenwood_hf as kenwood_hf
from neatc import NeatC
#import rigctld
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
from kivy.lang import Builder
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

rigobj = None
#rigctldThread_main = None
#rigctldThread_sub = None
rigctl_main = None
rigctl_sub = None
vfoa = int(kenwood_hf.tuningMode.VFOA)
vfob = int(kenwood_hf.tuningMode.VFOB)
mem = int(kenwood_hf.tuningMode.MEMORY)
call = int(kenwood_hf.tuningMode.CALL)

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
			setattr(rigobj, k, kwargs[k])

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
	click_selects = NumericProperty(int(kenwood_hf.meter.UNSELECTED))
	calculation = StringProperty()
	active_state = StringProperty()
	active_value = NumericProperty()
	active_opacity = NumericProperty()
	inactive_opacity = NumericProperty()

	def __init__(self, **kwargs):
		# Local variables
		self.all_updates = dict()
		self.timed_event = None
		self.lastval = 0
		self.lastinc = 0
		self.pos = (10, 10)
		super(Meter, self).__init__(**kwargs)
		if self.rig_state != '':
			rigobj.add_callback(self.rig_state, self.stateUpdate)
			self.value = getattr(rigobj, self.rig_state)
		self._old_rig_state = self.rig_state
		if self.active_state != '':
			rigobj.add_callback(self.active_state, self.activeStateUpdate)
			self.value = getattr(rigobj, self.active_state)
		self._old_active_state = self.rig_state
		self._turn()
		self.bind(low_format=self._turn)
		self.bind(high_format=self._turn)
		self.bind(rig_state=self._newRigState)
		self.bind(active_state=self._newActiveState)
		self.bind(active_value=self.activeStateUpdate)

	def on_touch_down(self, touch):
		if self.click_selects == kenwood_hf.meter.UNSELECTED:
			return False
		if not 'button' in touch.profile:
			return False
		if not touch.button in ('left'):
			return False
		if not self._gauge.collide_point(touch.pos[0], touch.pos[1]):
			return False
		if touch.pos[1] < (self._gauge.pos[1] + self._gauge.size[1] * 0.4):
			return False
		rigobj.meter_type = kenwood_hf.meter(self.click_selects)

	def _newActiveState(self, *args):
		if self._old_active_state != '':
			rigobj.remove_callback(self._old_active_state, self.activeStateUpdate)
		rigobj.add_callback(self.active_state, self.activeStateUpdate)
		self._old_active_state = self.active_state

	def _newRigState(self, *args):
		if self._old_rig_state != '':
			rigobj.remove_callback(self._old_rig_state, self.stateUpdate)
		rigobj.add_callback(self.rig_state, self.stateUpdate)
		self._old_rig_state = self.rig_state

	def activeStateUpdate(self, *args):
		self.timed_event = Clock.schedule_once(lambda *t: self._activeStateUpdate(), 0.01)

	def _activeStateUpdate(self):
		if self.active_value == getattr(rigobj, self.active_state):
			self.canvas.opacity = self.active_opacity
		else:
			self.canvas.opacity = self.inactive_opacity

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
	step_display = ObjectProperty()

	# TODO: Change frequency if appropriate when TXing
	def __init__(self, **kwargs):
		self.markup = True
		self.bind(freqValue=self._updateFreq)
		self.bind(vfo_box=self.newVFO)
		super(FreqDisplay, self).__init__(**kwargs)
		if rigobj.power_on:
			if rigobj.rx_frequency is not None:
				self.freqValue = int(rigobj.rx_frequency)
		self.cb_state = 'rx_frequency'
		rigobj.add_callback(self.cb_state, self.newFreq)
		self.bind(rig_state=self.newRigState)

	def newRigState(self, widget, value):
		rigobj.remove_callback(self.cb_state, self.newFreq)
		rigobj.add_callback(self.rig_state, self.newFreq)
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
			rigobj.remove_callback(self.cb_state, self.newFreq)
			if self.vfo_box is not None:
				if self.vfo_box.vfo == vfoa:
					if hasattr(rigobj, vfoa_frequency):
						self.freqValue = rigobj.vfoa_frequency
					else:
						self.freqValue = rigobj.vfo_frequency
					self._updateFreq(self)
					self.cb_state = 'VFOAsetFrequency'
					rigobj.add_callback(self.cb_state, self.newFreq)
				elif self.vfo_box.vfo == vfob:
					if hasattr(rigobj, vfoa_frequency):
						self.freqValue = rigobj.vfob_frequency
					else:
						self.freqValue = rigobj.vfo_frequency
					self._updateFreq(self)
					self.cb_state = 'VFOBsetFrequency'
					rigobj.add_callback(self.cb_state, self.newFreq)
				elif self.memory_display is not None:
					if self.vfo_box.vfo == mem:
						self.memory_display.memoryValue = rigobj.memory_channel
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
		# Detect sub-receiver and ensure step size
		if up == False:
			add = 0 - add
		new = self.freqValue + add
		if new % add:
			new = math.floor(new / add) * add
		if not hasattr(rigobj, 'vfoa_frequency'):
			# TODO: Should be in the rig API, not here...
			stepsize = (5000, 6250, 10000, 12500, 15000, 20000, 25000, 30000, 50000, 100000)[rigobj.multi_ch_frequency_steps]
			if abs(new - self.freqValue) < stepsize:
				if up:
					new = self.freqValue + stepsize
				else:
					new = self.freqValue - stepsize
		if self.vfo_box.vfo == vfoa:
			if hasattr(rigobj, 'vfoa_frequency'):
				rigobj.vfoa_frequency = new
			else:
				rigobj.vfo_frequency = new
		elif self.vfo_box.vfo == vfob:
			if hasattr(rigobj, 'vfoa_frequency'):
				rigobj.vfob_frequency = new
			else:
				rigobj.vfo_frequency = new
		elif self.vfo_box.vfo == mem and rigobj.rx_tuning_mode == kenwood_hf.tuningMode.MEMORY:
			if up:
				rigobj.up = True
			else:
				rigobj.down = True
		elif self.vfo_box.vfo == call and rigobj.rx_tuning_mode == kenwood_hf.tuningMode.CALL:
			if up:
				rigobj.band_up = True
			else:
				rigobj.band_down = True
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
		if rigobj.power_on:
			self.memoryValue = int(rigobj.memory_channel)
		rigobj.add_callback('memory_channel', self.newChannel)
		rigobj.add_callback('memory_groups', self.newGroups)
		rigobj.memories[self.memoryValue].add_modify_callback(self.updateChannel)
		self.bind(on_ref_press=self.toggle_group)
		rigobj.memories[300].add_modify_callback(self.updateChannel)
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
			rigobj.memories[self.memoryValue].remove_modify_callback(self.updateChannel)
			if self.memoryValue == channel and channel == 300:
				self._updateChannel()
		if channel is not None:
			self.memoryValue = int(channel)
			rigobj.memories[self.memoryValue].add_modify_callback(self.updateChannel)

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
		print('Toggling '+str(v))
		memGroups = rigobj.memory_groups
		memGroups[v] = not memGroups[v]
		rigobj.memory_groups = memGroups

	def _doUpdateChannel(self, dt):
		memData = rigobj.memories[self.memoryValue].value
		if memData is None:
			return
		if not 'MemoryGroup' in memData:
			return
		if not 'Channel' in memData:
			return
		if not 'MemoryName' in memData:
			return
		if not 'LockedOut' in memData:
			return
		if self.vfo_box is not None and self.freq_display is not None:
			if self.vfo_box.vfo == mem or self.vfo_box.vfo == call:
				if self.is_tx and ('TXfrequency' in memData):
					self.freq_display.freqValue = memData['TXfrequency']
				else:
					self.freq_display.freqValue = memData['Frequency']
		new = 'Memory: {:1d}-{:03d} {:8s} {:10s}'.format(memData['MemoryGroup'], memData['Channel'], memData['MemoryName'], 'Locked Out ' if memData['LockedOut'] else ' ')
		memGroups = rigobj.memory_groups
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

class StepSizeDisplay(Label):
	afm_width = (5000, 6250, 10000, 12500, 15000, 20000, 25000, 30000, 50000, 100000)
	other_width = (1000, 2500, 5000, 10000)
	stepSize = BoundedNumericProperty(0, min=0, max=9, errorvalue=0)
	freq_display = ObjectProperty()
	is_tx = BooleanProperty(False)

	def __init__(self, **kwargs):
		self.markup = True
		self.bind(stepSize=self._updateSteps)
		super(StepSizeDisplay, self).__init__(**kwargs)
		if rigobj.power_on:
			self.stepSize = int(rigobj.multi_ch_frequency_steps)
		rigobj.add_callback('multi_ch_frequency_steps', self.newStepSize)
		self.bind(on_ref_press=self.set_step_size)
		self.bind(freq_display=self.newFreqDisplay)
		self.bind(is_tx=self.newIsTX)

	def newIsTX(self, widget, value):
		Clock.schedule_once(self._doUpdateStepSize, 0)

	def newFreqDisplay(self, widget, value):
		Clock.schedule_once(self._doUpdateStepSize, 0)

	def setVisibility(self):
		if self.freq_display is None or self.freq_display.vfo_box is None or self.freq_display.vfo_box.vfo == call or self.freq_display.vfo_box.vfo == mem:
			self.opacity = 0
			self.disabled = True
		else:
			self.opacity = 1
			self.disabled = False

	def newStepSize(self, stepSize, *args):
		if stepSize is not None:
			self.stepSize = int(stepSize)

	def _updateSteps(self, *args):
		# We can't query the rig in here because we're already
		# blocking the read method if we're called via a
		# callback
		Clock.schedule_once(self._doUpdateStepSize, 0)

	def set_step_size(self, widget, value):
		v = int(value)
		rigobj.multi_ch_frequency_steps = v

	def _doUpdateStepSize(self, dt):
		if self.freq_display == None or self.freq_display.op_mode_box == None:
			return
		stepSize = rigobj.multi_ch_frequency_steps
		if stepSize is None:
			return
		new = ''
		if self.freq_display.op_mode_box.mode in (rig.mode.AM, rig.mode.FM):
			t = self.afm_width
		else:
			t = self.other_width
		for i in range(len(t)):
			new += '[ref='+str(i)+']'
			if i == rigobj.multi_ch_frequency_steps:
				new += '[color=' + kivy.utils.get_hex_from_color(self.freq_display.activeColour)  + ']'
			else:
				new += '[color=' + kivy.utils.get_hex_from_color(self.freq_display.inactiveColour)  + ']'
			new += str(t[i])
			new += '[/color][/ref] '
		self.text = new

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

	def on_press(self):
		if self.vfoID != self.parent.vfo and self.parent.rig_state != '':
			self.state = 'normal'
			setattr(rigobj, self.parent.rig_state, kenwood_hf.tuningMode(self.vfoID))

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
			if getattr(rigobj, self.rig_state) is None:
				self.disable_children()
			else:
				self.vfo = int(getattr(rigobj, self.rig_state))
		if (self.rig_state != ''):
			self.on_rig_state(self, self.rig_state)
		self.bind(freq_display=self.newFreqDisplay)

	def newFreqDisplay(self, widget, value):
		self._updateVFO()

	def on_rig_state(self, widget, value):
		Clock.schedule_once(lambda dt: self.refresh(), 0)
		rigobj.add_callback(self.rig_state, self.newVFO)

	def refresh(self):
		st = getattr(rigobj, self.rig_state)
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
			if self.freq_display.step_display is not None:
				Clock.schedule_once(lambda dt: self.freq_display.step_display.setVisibility(), 0)
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
				self.state = 'normal'
				setattr(rigobj, self.parent.rig_state, rig.mode(self.modeID))

class OPModeBox(GridLayout):
	mode = NumericProperty(0)
	rig_state = StringProperty()

	def __init__(self, **kwargs):
		super(OPModeBox, self).__init__(**kwargs)
		self.new_mode = self.mode
		self.cb_installed = self.rig_state
		if self.rig_state != '':
			rigobj.add_callback(self.rig_state, self.newMode)
			rm = getattr(rigobj, self.rig_state)
			if rm is not None:
				self.mode = int(rm)
		self.bind(mode=self._updateMode)
		self.bind(rig_state=self.newRigState)

	def newRigState(self, widget, value):
		if self.cb_installed != '':
			rigobj.remove_callback(self.rig_state, self.newMode)
		rigobj.add_callback(self.rig_state, self.newMode)
		nm = getattr(rigobj, self.rig_state)
		if nm is None:
			self.mode = -1
		else:
			self.mode = int(getattr(rigobj, self.rig_state))

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
		self.remote_state = self.state

	def on_rig_state(self, widget, value):
		Clock.schedule_once(lambda dt: self.refresh(), 0)
		rigobj.add_callback(self.rig_state, self.toggle)

	def refresh(self):
		st = getattr(rigobj, self.rig_state)
		if st == None:
			self.disabled = True
		else:
			self.disabled = False
			self.remote_state = 'down' if st else 'normal'
			self.state = self.remote_state

	def toggle(self, on, *args):
		if on == None:
			self.disabled = True
		else:
			self.disabled = False
			self.remote_state = 'down' if on else 'normal'
			self.state = self.remote_state

	def on_state(self, widget, value):
		if self.state != self.remote_state:
			setattr(rigobj, self.rig_state, self.state == 'down')
			# We need the remote to tell us the state has changed,
			# we just requested a change.
			self.state = self.remote_state

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
		st = getattr(rigobj, self.rig_state)
		self.newValue(st)

	def on_rig_state(self, widget, value):
		val = getattr(rigobj, self.rig_state)
		if val is None:
			self.disabled = True
		else:
			self.value = val
		rigobj.add_callback(self.rig_state, self.newValue)

	def newValue(self, value, *args):
		if value is None:
			self.disabled = True
		else:
			self.disabled = False
			self._latest = value
			self.value = value

	def on_value(self, *args):
		if self._latest != self.value:
			setattr(rigobj, self.rig_state, int(self.value))

class RITSlider(StateSlider):
	def __init__(self, **kwargs):
		super(RITSlider, self).__init__(**kwargs)
		if self.rig_state != '':
			self._latest = getattr(rigobj, self.rig_state)
		if self._latest == None:
			self._latest = 0

	def on_rig_state(self, widget, value):
		val = getattr(rigobj, self.rig_state)
		if val is not None:
			self._latest = val
			self.value = self._latest
		rigobj.add_callback(self.rig_state, self.newValue)

	def refresh(self):
		pass

	def newValue(self, value, *args):
		if value is not None:
			self._latest = value
			self.value = self._latest

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
			self.col.rgba = self.active_color if getattr(rigobj, self.rig_state) else self.inactive_color

	def on_inactive_color(self, widget, value):
		if self.rig_state != '':
			self.col.rgba = self.active_color if getattr(rigobj, self.rig_state) else self.inactive_color

	def on_rig_state(self, widget, value):
		if hasattr(rig, self._old_rig_state):
			rigobj.remove_callback(self._old_rig_state, self.newValue)
		self._old_rig_state = self.rig_state
		st = getattr(rigobj, self.rig_state)
		self.col.rgba = self.active_color if st else self.inactive_color
		rigobj.add_callback(self.rig_state, self.newValue)

	def on_pos(self, *args):
		self.rect.pos = self.pos

	def on_size(self, *args):
		self.rect.size = self.size

	def newValue(self, value, *args):
		self.background_color = self.active_color if value else self.inactive_color
		Clock.schedule_once(self._newValue, 0)

	def _newValue(self, dt):
		self.col.rgba = self.background_color
		st = getattr(rigobj, self.rig_state)
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
		rig.mode.CW: [50, 80, 100, 150, 200, 300, 400, 500, 600, 1000, 2000],
		rig.mode.CW_REVERSED: [50, 80, 100, 150, 200, 300, 400, 500, 600, 1000, 2000],
		rig.mode.FSK: [250, 500, 1000, 1500],
		rig.mode.FSK_REVERSED: [250, 500, 1000, 1500],
		rig.mode.FM: [0, 1],
		rig.mode.AM: [0, 1],
	}
	filter_shifts = [400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000]

	def __init__(self, **kwargs):
		super(FilterDisplay, self).__init__(**kwargs)
		self.lines = Line(points = self.points, width = self.line_width)
		self.canvas.add(Color(rgba=(1,1,1,1)))
		self.canvas.add(self.lines)
		if rigobj.power_on:
			self.points = rigobj.filter_display_pattern
			rigobj.add_callback('filter_display_pattern', self.newValue)

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
			if self.op_mode_box.mode == int(rig.mode.AM):
				return 3
			elif self.op_mode_box.mode == int(rig.mode.FM):
				return 11
			elif self.op_mode_box.mode == int(rig.mode.LSB):
				return 11
			elif self.op_mode_box.mode == int(rig.mode.USB):
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
		mode = getattr(rigobj, self.op_mode_box.rig_state)
		if touch.button == 'left':
			if mode == rig.mode.AM or mode == rig.mode.FM:
				rigobj.filter_width = not rigobj.filter_width
		if not touch.button in ('scrollup', 'scrolldown'):
			return False
		highpass = True if touch.pos[0] < self.pos[0] + self.width / 2 else False
		up = True if touch.button == 'scrolldown' else False
		# TODO: Packet Filter (Menu No. 50A) changes behaviour in ??? mode
		if mode in (rig.mode.USB, rig.mode.LSB, rig.mode.FM, rig.mode.AM):
			stateName = 'voice_high_pass_cutoff' if highpass else 'voice_low_pass_cutoff'
			newVal = getattr(rigobj, stateName) + (1 if up else -1)
			maxVal = self._get_max()
			if newVal < 0:
				newVal = 0
			if newVal > maxVal:
				newVal = maxVal
			setattr(rigobj, stateName, newVal)
		elif mode == rig.mode.CW and not highpass:
			newVal = self.filter_shifts.index(rigobj.if_shift)
			newVal += (1 if up else -1)
			if newVal < 0:
				newVal = 0
			elif newVal >= len(self.filter_shifts):
				newVal = len(self.filter_shifts) - 1
			rigobj.if_shift = self.filter_shifts[newVal]
		elif mode in self.filter_widths:
			newVal = self.filter_widths[mode].index(rigobj.filter_width)
			newVal += (1 if up else -1)
			if newVal < 0:
				newVal = 0
			elif newVal >= len(self.filter_widths[mode]):
				newVal = len(self.filter_widths[mode]) - 1
			rigobj.filter_width = self.filter_widths[mode][newVal]
		return True

class HighPassLabel(Label):
	prefix = StringProperty()
	suffix = StringProperty()
	supportedModes = (rig.mode.AM, rig.mode.FM, rig.mode.LSB, rig.mode.USB,)

	def __init__(self, **kwargs):
		super(HighPassLabel, self).__init__(**kwargs)
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.voice_high_pass_cutoff)
		rigobj.add_callback('voice_high_pass_cutoff', self.newValue)
		rigobj.add_callback('filter_width', self.newValue)

	def on_prefix(self, widget, value):
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.voice_high_pass_cutoff)
		else:
			self.newValue(FilterDisplay.filter_widths[rigobj.rx_mode][rigobj.filter_width])

	def on_suffix(self, widget, value):
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.voice_high_pass_cutoff)
		else:
			self.newValue(rigobj.filter_width)

	def refresh(self):
		Clock.schedule_once(lambda dt: self._refresh(), 0)

	def _refresh(self):
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.voice_high_pass_cutoff)
		else:
			self.newValue(rigobj.filter_width)

	def newValue(self, value, *args):
		val = ''
		mode = rigobj.rx_mode
		if mode == rig.mode.AM:
			if value == 0:
				val = '10'
			elif value == 1:
				val = '100'
			elif value == 2:
				val = '200'
			elif value == 3:
				val = '500'
			val = self.prefix + val + self.suffix
		elif mode == int(rig.mode.FM) or mode == int(rig.mode.LSB) or mode == int(rig.mode.USB):
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
	supportedModes = (rig.mode.AM, rig.mode.FM, rig.mode.LSB, rig.mode.USB, rig.mode.CW,)
	cwModes = (rig.mode.CW, rig.mode.CW_REVERSED,)

	def __init__(self, **kwargs):
		super(LowPassLabel, self).__init__(**kwargs)
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.voice_low_pass_cutoff)
		rigobj.add_callback('voice_low_pass_cutoff', self.newValue)
		rigobj.add_callback('if_shift', self.newValue)

	def on_prefix(self, widget, value):
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.voice_low_pass_cutoff)
		elif rigobj.rx_mode in self.cwModes:
			self.newValue(rigobj.if_shift)

	def on_suffix(self, widget, value):
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.voice_low_pass_cutoff)
		elif rigobj.rx_mode in self.cwModes:
			self.newValue(rigobj.if_shift)

	def refresh(self):
		Clock.schedule_once(lambda dt: self._refresh(), 0)

	def _refresh(self):
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.voice_low_pass_cutoff)
		elif rigobj.rx_mode in self.cwModes:
			self.newValue(rigobj.if_shift)
		else:
			self.text = ''

	def newValue(self, value, *args):
		val = ''
		if rigobj.rx_mode is None:
			mode = 0
		else:
			mode = int(rigobj.rx_mode)
		if mode == int(rig.mode.AM):
			if value == 0:
				val = '2500'
			elif value == 1:
				val = '3000'
			elif value == 2:
				val = '4000'
			elif value == 3:
				val = '5000'
			val = self.prefix + val + self.suffix
		elif mode == int(rig.mode.FM) or mode == int(rig.mode.LSB) or mode == int(rig.mode.USB):
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
		elif rigobj.rx_mode in self.cwModes:
			val = self.prefix + str(rigobj.if_shift) + self.suffix
		self.text = val

class WideNarrowLabel(Label):
	prefix = StringProperty()
	suffix = StringProperty()
	supportedModes = (rig.mode.AM, rig.mode.FM,)

	def __init__(self, **kwargs):
		super(WideNarrowLabel, self).__init__(**kwargs)
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.filter_width)
		rigobj.add_callback('filter_width', self.newValue)

	def on_prefix(self, widget, value):
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.filter_width)

	def on_suffix(self, widget, value):
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.filter_width)

	def refresh(self):
		Clock.schedule_once(lambda dt: self._refresh(), 0)

	def _refresh(self):
		if rigobj.rx_mode in self.supportedModes:
			self.newValue(rigobj.filter_width)
		else:
			self.text = ''

	def newValue(self, value, *args):
		if rigobj.rx_mode in self.supportedModes:
			val = 'Narrow' if value == 0 else 'Wide'
			self.text = self.prefix + val + self.suffix

class StateLabel(Label):
	prefix = StringProperty()
	suffix = StringProperty()
	rig_state = StringProperty()

	def __init__(self, **kwargs):
		super(StateLabel, self).__init__(**kwargs)
		self.text = self.prefix + self.text + self.suffix
		self.old_rig_state = self.rig_state
		self.last_text = self.text
		if self.rig_state != '':
			rigobj.add_callback(self.rig_state, self.setLabel)
		self.bind(rig_state=self.newRigState)
		self.bind(prefix=self._setLabel)
		self.bind(suffix=self._setLabel)

	def newRigState(self, widget, value):
		if self.old_rig_state != '':
			rigobj.remove_callback(self.old_rig_state, self.setLabel)
		self.old_rig_state = value
		rigobj.add_callback(self.old_rig_state, self.setLabel)

	def _setLabel(self, *args, **kwargs):
		self.setLabel(self.last_text)

	def setLabel(self, newLabel):
		self.last_text = str(newLabel)
		self.text = self.prefix + self.last_text + self.suffix

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
		global rigobj, rigctl_main, rigctl_sub, client_port, kv_file
		self.config = ConfigParser()
		self.build_config(self.config)
		self.config.read('neat.ini')
		rigobj = NeatC(port=client_port)
		self.rig = rigobj
		ui = Builder.load_file(kv_file)
		Window.size = ui.size
		return ui

	def on_config_change(self, config, section, key, value):
		global rigobj, rigctl_main, rigctl_sub
		if config is self.config:
			if ('Neat', 'verbose') == (section, key):
				rigobj._verbose = bool(int(value))
				rigctl_main.verbose = bool(int(value))
				rigctl_sub.verbose = bool(int(value))

if __name__ == '__main__':
	try:
		myargs = argv.index('--')
	except ValueError:
		myargs = 0
	opts, args = getopt(argv[myargs + 1:], "k:p:", ["kv=", "port="])
	for o, a in opts:
		if o in ('-k', '--kv'):
			kv_file = a
		elif o in ('-p', '--port'):
			client_port = int(a)

	NeatApp().run()
	rigobj.terminate()
	#if rigctldThread_main is not None:
	#	rigctldThread_main.join()
	#if rigctldThread_sub is not None:
	#	rigctldThread_sub.join()
