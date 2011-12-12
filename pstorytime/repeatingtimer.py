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

import threading
import time

__all__ = [
  'RepeatingTimer',
  ]

class RepeatingTimer(object):
  """A timer that will repeat until stopped."""
  def __init__(self, interval, function, args=[], kwargs={}):
    """Create the repeating timer.
    
    Arguments:
      interval  How ofter to fire.
      function  The function to run.
      args      The arguments to the function.
      kwargs    The keyword arguments to send to the function.
    """
    self._interval = interval
    self._function = function
    self._args = args
    self._kwargs = kwargs

    self._state = "stopped"
    self._cond = threading.Condition()

    self._thread = threading.Thread(target=self._run,
                                    name="RepeatingTimerThread")
    self._thread.setDaemon(True)
    self._thread.start()

    self._begin = None

  def _run(self):
    """Wait for the next timer event to be reached and run function, rinse,
    repeat."""
    with self._cond:
      while self._state != "destroyed":
        # Hold the timer while stopped
        while self._state == "stopped":
          self._cond.wait()

        # Wait for next event, or stop/destroy of the timer
        self._begin = time.time()
        while self._state == "started":
          self._cond.wait(self._interval - (time.time()-self._begin))
          if time.time() - self._begin >= self._interval:
            break

        # Run function if a timer event has occurred
        if self._state == "started":
          self._cond.release()
          try:
            self._function(*self._args, **self._kwargs)
          finally:
            self._cond.acquire()

  def start(self):
    """Start firing timer events. If already running, reset timer."""
    with self._cond:
      # Start or restart current timer.
      self._begin = time.time()
      self._set("started")

  def stop(self):
    """Stop firing timer events."""
    self._set("stopped")

  def destroy(self):
    """Destroy this timer by killing its thread."""
    self._set("destroyed")

  def _set(self,state):
    """Set the state of the timer.
    
    Argements:
      state     The new state.
    """
    with self._cond:
      # Update state, if the timer is not destroyed.
      if self._state != "destroyed":
        self._state = state
        self._cond.notifyAll()

  def started(self):
    """Is the timer started?

    Returns:  True if the timer is started, otherwise False.
    """
    with self._cond:
      return self._state == "started"
