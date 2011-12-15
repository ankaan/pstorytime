# -*- coding: utf-8 -*-
"""Audiobook playing API.

This module contains a frontend for gstreamer that makes it easy to play and
control audiobook playing. This differs from playing music in that the position
where you last stopped listening is very important.

The module also contains user interfaces that uses this API.
"""
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

__version__ = "0.1"
__author__ = "Anders Engstrom <ankan@ankan.eu>"
__all__ = [
  'AudioBook',
  ]

from pstorytime.audiobook import AudioBook
