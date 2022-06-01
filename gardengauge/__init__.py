#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

'''
Gauge
=====

The :class:`Gauge` widget is a widget for displaying gauge.

.. note::

Source svg file provided for customing.

'''

__all__ = ('Gauge',)

# This info is obsolete, but leaving here for reference
__title__ = 'garden.gauge'
__version__ = '0.2'
__author__ = 'julien@hautefeuille.eu'

import kivy
kivy.require('1.6.0')
from kivy.properties import BoundedNumericProperty, NumericProperty, StringProperty
from kivy.uix.widget import Widget
from kivy.uix.scatter import Scatter
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from os.path import join, dirname, abspath

class Gauge(Widget):
    '''
    Gauge class

    '''

    value = BoundedNumericProperty(0, min=0, max=100, errorvalue=0)
    path = dirname(abspath(__file__))
    file_gauge = StringProperty(join(path, "cadran.png"))
    file_needle = StringProperty(join(path, "needle.png"))
    size_gauge = BoundedNumericProperty(128, min=128, max=256, errorvalue=128)
    size_text = NumericProperty(10)
    min_value = NumericProperty(0)
    max_value = NumericProperty(100)

    def __init__(self, **kwargs):
        super(Gauge, self).__init__(**kwargs)
        self.unit = 1.8

        self._gauge = Scatter(
            size=(self.size_gauge, self.size_gauge),
            do_rotation=False,
            do_scale=False,
            do_translation=False
        )

        self._img_gauge = Image(
            source=self.file_gauge,
            size=(self.size_gauge, self.size_gauge)
        )

        self._needle = Scatter(
            size=(self.size_gauge, self.size_gauge),
            do_rotation=False,
            do_scale=False,
            do_translation=False
        )

        _img_needle = Image(
            source=self.file_needle,
            size=(self.size_gauge, self.size_gauge)
        )

        self._glab = Label(font_size=self.size_text, markup=True)
        self._progress = ProgressBar(max=100, height=20, value=self.value)

        self._gauge.add_widget(self._img_gauge)
        self._needle.add_widget(_img_needle)

        self.add_widget(self._gauge)
        self.add_widget(self._needle)
        self.add_widget(self._glab)
        self.add_widget(self._progress)
        self._updateMinMax(self)

        self.bind(pos=self._update)
        self.bind(size=self._update)
        self.bind(max_value=self._updateMinMax)
        self.bind(min_value=self._updateMinMax)
        self.bind(size_gauge=self._update)
        self.bind(value=self._turn)
        self.bind(file_gauge=self._newimage)
        self.bind(file_needle=self._newneedle)

    def _newimage(self, *args):
        self._img_gauge.source = self.file_gauge

    def _newneedle(self, *args):
        self._img_needle.source = self.file_needle

    def _updateMinMax(self, *args):
        self.unit = 180 / (self.max_value - self.min_value)
        self.unit = 180 / (self.max_value - self.min_value)
        self.property('value').set_min(self, self.min_value)
        self.property('value').set_max(self, self.max_value)
        self._progress.max = self.max_value - self.min_value

    def _update(self, *args):
        '''
        Update gauge and needle positions after sizing or positioning.

        '''
        self._gauge.size = (self.size_gauge, self.size_gauge)
        self._img_gauge.size = (self.size_gauge, self.size_gauge)
        self._needle.size = (self.size_gauge, self.size_gauge)
        self.unit = 180 / (self.max_value - self.min_value)
        self._gauge.pos = self.pos
        self._needle.pos = (self.x, self.y)
        self._needle.center = self._gauge.center
        self._glab.center_x = self._gauge.center_x
        self._glab.center_y = self._gauge.center_y + (self.size_gauge / 4)
        self._progress.x = self._gauge.x
        self._progress.y = self._gauge.y + (self.size_gauge / 4)
        self._progress.width = self.size_gauge

    def _turn(self, *args):
        '''
        Turn needle, 1 degree = 1 unit, 0 degree point start on 50 value.

        '''
        self._needle.center_x = self._gauge.center_x
        self._needle.center_y = self._gauge.center_y
        self._needle.rotation = 90 - ((self.value - self.min_value) * self.unit)
        self._glab.text = "[b]{0:.0f}[/b]".format(self.value)
        self._progress.value = self.value - self.min_value
