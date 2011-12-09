# -*- coding: utf-8 -*-
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

from gobject import *

class Bus(GObject):
  __gsignals__ = {
      'eob' : (SIGNAL_RUN_LAST, TYPE_NONE, (TYPE_INT,)),
      'eos' : (SIGNAL_RUN_LAST, TYPE_NONE, (TYPE_INT,)),
      'error' : (SIGNAL_RUN_LAST, TYPE_NONE, (TYPE_STRING,)),
      'filename': (SIGNAL_RUN_LAST, TYPE_NONE, (TYPE_STRING,)),
      'playlog': (SIGNAL_RUN_LAST, TYPE_NONE, (TYPE_PYOBJECT,)),
      'playing': (SIGNAL_RUN_LAST, TYPE_NONE, (TYPE_BOOLEAN,))
    }

  def __init__(self):
    GObject.__init__(self)
