# -*- coding: utf-8 -*-
"""A timer that will repeat until stopped."""

#
# Copyright (C) 2011 Anders Engström <ankan@ankan.eu>
#
# This file is part of pstorytime.
#
# pstorytime is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pstorytime is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pstorytime.  If not, see <http://www.gnu.org/licenses/>.

import glib

__all__ = [
  'Timer',
  ]

class Timer(object):
  """A gobject timer with optional repeating feature."""
  def __init__(self, interval, function, args=[], kwargs={}, repeat=False):
    """Create the repeating timer.
    
    Arguments:
      interval  How ofter to fire, in milliseconds.
      function  The function to run.
      args      The arguments to the function.
      kwargs    The keyword arguments to send to the function.
      repeat    If the timer should repeat until stopped.
    """
    self._interval = interval
    self._function = function
    self._args = args
    self._kwargs = kwargs
    self._repeat = repeat

    self._id = None

  def _tick(self):
    """Wait for the next timer event to be reached and run function, rinse,
    repeat."""
    if self.started():
      if not self._repeat:
        self.stop()

      self._function(*self._args, **self._kwargs)

      return self.started()
    else:
      return False

  def start(self):
    """Start firing timer events. If already running, reset timer."""
    self.stop()
    self._id = glib.timeout_add(self._interval,self._tick)

  def stop(self):
    """Stop firing timer events."""
    if self._id != None:
      glib.source_remove(self._id)
      self._id = None

  def started(self):
    """Is the timer started?

    Returns:  True if the timer is started, otherwise False.
    """
    return self._id != None
